"""render.py - turns a 16:9 stream clip into a 1080x1920 Short with word-by-word captions.

Layouts
  cam : facecam on top (1080x640), gameplay below (1080x1280)
  full: gameplay zoomed in the middle over a blurred copy of itself
Captions are burned from word timestamps (faster-whisper). The hook is added later by finish.py.
"""
import json, os, subprocess, sys, tempfile

W, H = 1080, 1920
TOP_H = 640                    # facecam panel height in the cam layout
FONT = 'DejaVu Sans'


def probe(path):
    out = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries',
                          'stream=width,height:format=duration', '-of', 'json', path],
                         capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    s = j['streams'][0]
    return s['width'], s['height'], float(j['format']['duration'])


def find_cam(path, dur):
    """Look for one face that stays put in a corner/edge region across most sampled frames.
    Returns [x, y, w, h] as fractions of the frame, or None."""
    import cv2
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    cap = cv2.VideoCapture(path)
    hits, n = [], 10
    for i in range(n):
        cap.set(cv2.CAP_PROP_POS_MSEC, (dur * (i + 0.5) / n) * 1000)
        ok, frame = cap.read()
        if not ok:
            continue
        fh, fw = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, 1.1, 6, minSize=(int(fw * 0.035), int(fw * 0.035)))
        for (x, y, w, h) in faces:
            cx = (x + w / 2) / fw
            if 0.3 < cx < 0.7 or w / fw > 0.25:   # facecams sit near the sides; skip mid-screen game faces
                continue
            hits.append(((x + w / 2) / fw, (y + h / 2) / fh, w / fw))
    cap.release()
    if len(hits) < n * 0.5:
        return None
    # largest cluster of hits that agree within 4% of the frame
    best = []
    for a in hits:
        grp = [b for b in hits if abs(a[0] - b[0]) < 0.04 and abs(a[1] - b[1]) < 0.06]
        if len(grp) > len(best):
            best = grp
    if len(best) < n * 0.5:
        return None
    cx = sorted(b[0] for b in best)[len(best) // 2]
    cy = sorted(b[1] for b in best)[len(best) // 2]
    fwid = sorted(b[2] for b in best)[len(best) // 2]
    # box around the face with the panel's 27:16 shape (in 16:9 frame fractions)
    bw = min(0.45, fwid * 3.4)
    bh = bw * (16 / 27) * (16 / 9)
    x = min(max(cx - bw / 2, 0), 1 - bw)
    y = min(max(cy - bh * 0.45, 0), 1 - bh)
    return [round(x, 4), round(y, 4), round(bw, 4), round(bh, 4)]


def transcribe(path):
    """Word timestamps. Returns [(start, end, word)]. Empty list if whisper is unavailable."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return []
    model = WhisperModel(os.environ.get('WHISPER_MODEL', 'base.en'), device='cpu', compute_type='int8')
    segs, _ = model.transcribe(path, word_timestamps=True, vad_filter=True)
    words = []
    for s in segs:
        for w in (s.words or []):
            t = w.word.strip()
            if t:
                words.append((w.start, w.end, t))
    return words


def ts(t):
    t = max(t, 0)
    return '%d:%02d:%05.2f' % (t // 3600, (t % 3600) // 60, t % 60)


def captions_ass(words, y, path):
    """2-3 word chunks, current chunk only, yellow highlight on the word being spoken."""
    head = ("[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 2\n\n"
            "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
            "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
            "Style: Cap,%s,84,&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,7,2,5,40,40,0,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n") % (W, H, FONT)
    lines, chunk = [], []
    for w in words:
        chunk.append(w)
        if len(chunk) == 3 or w[2][-1:] in '.?!,' or (len(chunk) == 2 and len(chunk[0][2] + w[2]) > 14):
            lines.append(chunk)
            chunk = []
    if chunk:
        lines.append(chunk)
    ev = []
    for i, ch in enumerate(lines):
        end_chunk = lines[i + 1][0][0] if i + 1 < len(lines) else ch[-1][1] + 0.4
        end_chunk = min(end_chunk, ch[-1][1] + 0.8)
        for j, (s, e, _) in enumerate(ch):
            e2 = ch[j + 1][0] if j + 1 < len(ch) else end_chunk
            txt = ' '.join(('{\\c&H00E5FF&}%s{\\c&HFFFFFF&}' if k == j else '%s') % clean(c[2]).upper()
                           for k, c in enumerate(ch))
            ev.append('Dialogue: 0,%s,%s,Cap,,0,0,0,,{\\pos(%d,%d)}%s' % (ts(s), ts(e2), W // 2, y, txt))
    open(path, 'w').write(head + '\n'.join(ev) + '\n')


def clean(t):
    return t.replace('{', '').replace('}', '').replace('\\', '')


def render(src, dst, cam=None, layout='auto', credit=''):
    """Returns the cam box used (or None) so the caller can save it for the streamer."""
    sw, sh, dur = probe(src)
    if layout == 'auto':
        cam = cam or find_cam(src, dur)
        layout = 'cam' if cam else 'full'
    words = transcribe(src)
    tmp = tempfile.mkdtemp()
    ass = os.path.join(tmp, 'cap.ass')
    cap_y = 1480 if layout == 'cam' else 1500
    captions_ass(words, cap_y, ass)
    base = '[0:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,setsar=1,split=2[a][b];'
    if layout == 'cam':
        x, y, bw, bh = cam
        cx, cy, cw, ch = int(x * 1920), int(y * 1080), int(bw * 1920), int(bh * 1080)
        gw = int(1080 * 1080 / 1280) // 2 * 2
        f = (base + '[a]crop=%d:%d:%d:%d,scale=%d:%d[top];' % (cw, ch, cx, cy, W, TOP_H) +
             '[b]crop=%d:1080:%d:0,scale=%d:%d[bot];' % (gw, (1920 - gw) // 2, W, H - TOP_H) +
             '[top][bot]vstack,drawbox=y=%d:w=iw:h=6:color=black@1:t=fill' % (TOP_H - 3))
    else:
        f = (base + '[a]crop=608:1080:656:0,scale=%d:%d,boxblur=24:2,eq=brightness=-0.12[bg];' % (W, H) +
             '[b]crop=1500:1080:210:0,scale=%d:%d[fg];' % (W, int(W * 1080 / 1500) // 2 * 2) +
             '[bg][fg]overlay=0:(H-h)/2')
    if credit:
        f += ",drawtext=font='%s':text='%s':fontsize=34:fontcolor=white@0.85:borderw=3:bordercolor=black@0.8:x=(w-tw)/2:y=h-120" % (
            FONT, credit.replace("'", '').replace(':', ''))
    f += ",subtitles='%s'[v]" % ass
    cmd = ['ffmpeg', '-y', '-v', 'error', '-i', src, '-filter_complex', f, '-map', '[v]', '-map', '0:a?',
           '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-r', '30',
           '-c:a', 'aac', '-b:a', '160k', '-movflags', '+faststart', dst]
    subprocess.run(cmd, check=True)
    return (cam if layout == 'cam' else None), ' '.join(w[2] for w in words), layout


if __name__ == '__main__':
    src, dst = sys.argv[1], sys.argv[2]
    print(render(src, dst, layout=os.environ.get('LAYOUT', 'auto'), credit=os.environ.get('CREDIT', '')))
