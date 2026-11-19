"""episode/thumbs.py - three 1280x720 thumbnail options per episode, made from the day's own clips.

Style comes from research/THUMBNAILS.md (what repeats in the outliers): a punchy, saturated game frame,
short text in a few big words, a red arrow or circle on the action. Words are read from the
'## Words' list in THUMBNAILS.md when it has one. The review run's fresh agent picks the best one.
"""
import os, re, random
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

W, H = 1280, 720
FONTS = [os.path.expanduser('~/.cache/leonida/Anton-Regular.ttf'),
         '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf']
DEFAULT_WORDS = ['BEST CLIPS', 'NO WAY', 'INSANE', 'WATCH THIS', 'HE DID WHAT']


def words():
    p = 'research/THUMBNAILS.md'
    if os.path.exists(p):
        txt = open(p).read()
        m = re.search(r'## Words\n(.*?)(\n## |\Z)', txt, re.S)
        if m:
            ws = [l.strip('-* ').strip().upper() for l in m.group(1).splitlines() if l.strip().startswith(('-', '*'))]
            if ws:
                return ws
    return DEFAULT_WORDS


def font(size):
    for f in FONTS:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()


def best_frame(raw):
    """Sharpest, most colourful, not-dark frame, plus where the motion is (for the arrow)."""
    cap = cv2.VideoCapture(raw)
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 300
    best, prev, out = -1, None, (None, (0.5, 0.5))
    for i in range(16):
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(n * (0.08 + 0.84 * i / 15)))
        ok, f = cap.read()
        if not ok:
            continue
        small = cv2.resize(f, (480, 270))
        g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        sharp = cv2.Laplacian(g, cv2.CV_64F).var()
        sat, val = hsv[..., 1].mean() / 255, hsv[..., 2].mean() / 255
        s = np.log1p(sharp) * (0.4 + sat) * (1 if 0.25 < val < 0.85 else 0.4)
        spot = (0.5, 0.5)
        if prev is not None:
            diff = cv2.GaussianBlur(cv2.absdiff(g, prev), (31, 31), 0)
            # ignore the edges where facecams and overlays live
            diff[:, :70] = diff[:, -70:] = 0
            diff[:40] = diff[-40:] = 0
            y, x = np.unravel_index(diff.argmax(), diff.shape)
            spot = (x / 480, y / 270)
        if s > best:
            best, out = s, (f, spot)
        prev = g
    cap.release()
    return out


def text_block(img, text, anchor):
    d = ImageDraw.Draw(img)
    lines = text.split()
    lines = [' '.join(lines[:len(lines) // 2 + len(lines) % 2]), ' '.join(lines[len(lines) // 2 + len(lines) % 2:])] if len(lines) > 2 else [text]
    lines = [l for l in lines if l]
    size = 220
    while size > 60:
        f = font(size)
        if max(d.textlength(l, font=f) for l in lines) <= W * 0.62 and size * len(lines) * 1.0 <= H * 0.52:
            break
        size -= 6
    f = font(size)
    y = H - 40 - int(size * 1.02 * len(lines)) if anchor == 'bottom' else 36
    for l in lines:
        x = 48
        d.text((x + 8, y + 10), l, font=f, fill=(0, 0, 0))                       # drop shadow
        d.text((x, y), l, font=f, fill=(255, 226, 0), stroke_width=max(6, size // 18), stroke_fill=(0, 0, 0))
        y += int(size * 1.02)


def arrow(img, spot, circle=False):
    d = ImageDraw.Draw(img)
    x, y = int(spot[0] * W), int(spot[1] * H)
    x, y = min(max(x, 160), W - 160), min(max(y, 140), H - 160)
    red = (235, 20, 20)
    if circle:
        r = 95
        for k in range(3):
            d.ellipse([x - r - k * 3, y - r - k * 3, x + r + k * 3, y + r + k * 3], outline=red, width=10)
        return
    sx, sy = (x + 230, y - 150) if x < W - 300 else (x - 230, y - 150)
    sy = max(sy, 30)
    d.line([sx, sy, x, y], fill=(0, 0, 0), width=34)
    d.line([sx, sy, x, y], fill=red, width=24)
    v = np.array([x - sx, y - sy], float)
    v /= np.linalg.norm(v) or 1
    p = np.array([-v[1], v[0]])
    tip = np.array([x, y]) + v * 30
    pts = [tuple(tip), tuple(tip - v * 80 + p * 50), tuple(tip - v * 80 - p * 50)]
    d.polygon(pts, fill=red, outline=(0, 0, 0))


def finish(frame):
    im = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)).resize((W, H), Image.LANCZOS)
    im = ImageEnhance.Color(im).enhance(1.4)
    im = ImageEnhance.Contrast(im).enhance(1.15)
    im = im.filter(ImageFilter.UnsharpMask(2, 120, 3))
    # vignette so the text reads
    vg = Image.new('L', (W, H), 0)
    ImageDraw.Draw(vg).ellipse([-W * 0.25, -H * 0.35, W * 1.25, H * 1.35], fill=255)
    vg = vg.filter(ImageFilter.GaussianBlur(120))
    return Image.composite(im, ImageEnhance.Brightness(im).enhance(0.45), vg)


def make(clips, raws, outdir):
    ws = words()
    top = sorted([c for c in clips if c['id'] in raws], key=lambda c: -c['vph'])[:3]
    texts = [ws[0]] + random.sample(ws[1:], min(2, len(ws) - 1)) if len(ws) > 2 else (ws * 3)[:3]
    files = []
    for i, (c, txt) in enumerate(zip(top, texts)):
        frame, spot = best_frame(raws[c['id']])
        if frame is None:
            continue
        k = 'ABC'[i]
        base = '%s/base_%s.jpg' % (outdir, k)
        finish(frame).convert('RGB').save(base, quality=92)   # kept so the review run can re-letter it
        t = {'file': '%s/thumb_%s.jpg' % (outdir, k), 'base': base, 'spot': [round(float(spot[0]), 3), round(float(spot[1]), 3)],
             'mark': 'circle' if i == 2 else 'arrow', 'text': txt, 'from_clip': c['id']}
        draw(t)
        files.append(t)
    return files


def draw(t):
    im = Image.open(t['base']).convert('RGB')
    if t.get('mark') in ('arrow', 'circle'):
        arrow(im, t['spot'], circle=t['mark'] == 'circle')
    text_block(im, t['text'].upper(), 'bottom' if t['spot'][1] < 0.55 else 'top')
    im.save(t['file'], quality=90)


if __name__ == '__main__':
    # python episode/thumbs.py redo DATE A "NEW TEXT" [arrow|circle|none] [x y]
    import json, sys
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    _, cmd, date, key, text = sys.argv[:5]
    plan_p = 'episode/%s/plan.json' % date
    plan = json.load(open(plan_p))
    t = next(x for x in plan['thumbnails'] if x['file'].endswith('thumb_%s.jpg' % key))
    t['text'] = text
    if len(sys.argv) > 5:
        t['mark'] = sys.argv[5]
    if len(sys.argv) > 7:
        t['spot'] = [float(sys.argv[6]), float(sys.argv[7])]
    draw(t)
    json.dump(plan, open(plan_p, 'w'), indent=1)
    print(t['file'])
