"""episode/build.py - daily long-form episode, runs in GitHub Actions (needs TWITCH_CLIENT_ID/SECRET).

Picks the day's most-viewed GTA VI clips (views per hour), cuts them into one 16:9 compilation:
  - no intro: opens on the best clip of the day, second best goes last
  - total length follows the winning compilations in research/meta.json (target_len), else 10 min
  - every clip gets a one-line label (episode/labels/<date>.json if the review run wrote one, else the clip title)
    and the streamer's handle; every streamer is credited with a link in the description
Writes episode/<date>/ (plan.json, description.txt, review frames, 3 thumbnails) and out/episode.mp4
(the workflow uploads that to a GitHub release, it is too big for git).

  python episode/build.py [--date YYYY-MM-DD] [--relabel]   (--relabel reuses the plan's clips, new labels)
"""
import argparse, datetime as dt, json, os, re, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [HERE, ROOT, os.path.join(ROOT, 'clipper')]
os.chdir(ROOT)
import fetch, thumbs   # noqa: E402  (fetch gives the Twitch client and spoiler filter)

TZ = dt.timezone(dt.timedelta(hours=-7))      # Tucson
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
MIN_VIEWS = int(os.environ.get('EP_MIN_VIEWS', '150'))
PER_STREAMER = int(os.environ.get('EP_PER_STREAMER', '3'))
SKIP_WORDS = re.compile(r'strip|club|dance|thong|cutscene|cinematic|glitch|exploit|money glitch|dupe|infinite money|mod menu|cheat', re.I)


def load(p, d):
    return json.load(open(p)) if os.path.exists(p) else d


def save(p, o):
    json.dump(o, open(p, 'w'), indent=1)


def target_len():
    t = load('research/meta.json', {}).get('target_len') or 600
    return max(420, min(int(t), 900))


def clean_label(title):
    t = re.sub(r'https?://\S+|[@#]\S+|\b(xd|lol|lmao|kekw|omegalul|pog\w*)\b', '', title, flags=re.I)
    t = re.sub(r'\s+', ' ', t).strip(' -|:!.')
    return (t[:1].upper() + t[1:] if t[:1].islower() and not t[1:2].isupper() else t)[:48] or 'GTA 6'


def pick(date):
    cfg = fetch.load('streamers.json', {'streamers': []})
    ok = {s['login'].lower() for s in cfg['streamers'] if s.get('approved')}
    blocked = {b.lower() for b in cfg.get('blocked', [])}
    used = set(load('state/episodes.json', {}).get('clip_ids', []))
    tw = fetch.Twitch()
    gid = tw.get('games', {'name': fetch.GAME})[0]['id']
    now = dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(hours=26)).strftime('%Y-%m-%dT%H:%M:%SZ')
    clips = {}
    # the whole game's top clips today, plus deeper pulls for our approved streamers
    for c in tw.get('clips', {'game_id': gid, 'started_at': since, 'first': 100}):
        clips[c['id']] = c
    users = {}
    logins = sorted(ok)
    for i in range(0, len(logins), 100):
        for u in tw.get('users', {'login': logins[i:i + 100]}):
            users[u['id']] = u
    for uid in users:
        for c in tw.get('clips', {'broadcaster_id': uid, 'started_at': since, 'first': 20}):
            if c['game_id'] == gid:
                clips[c['id']] = c
    good = []
    for c in clips.values():
        login = c['broadcaster_name'].lower()
        if (c['id'] in used or login in blocked or (c.get('language') or 'en')[:2] not in fetch.LANGS
                or c['view_count'] < MIN_VIEWS or not (8 <= c['duration'] <= 60)
                or fetch.BAD_TITLE.search(c['title']) or SKIP_WORDS.search(c['title'])):
            continue
        c['_vph'] = fetch.score(c, now)
        good.append(c)
    good.sort(key=lambda c: -c['_vph'])
    picked, per, moments, total = [], {}, set(), 0
    for c in good:
        m = '%s:%d' % (c.get('video_id'), (c.get('vod_offset') or 0) // 45) if c.get('video_id') else None
        b = c['broadcaster_id']
        if (m and m in moments) or per.get(b, 0) >= PER_STREAMER:
            continue
        picked.append(c)
        per[b] = per.get(b, 0) + 1
        moments.add(m)
        total += c['duration']
        if total >= target_len():
            break
    if len(picked) < 6:
        sys.exit('only %d usable clips today, not enough for an episode' % len(picked))
    # best first, second best last, rest by views per hour
    order = [picked[0]] + picked[2:] + [picked[1]]
    return [{'id': c['id'], 'url': c['url'], 'title': c['title'], 'streamer': c['broadcaster_name'],
             'login': c['broadcaster_name'].lower(), 'views': c['view_count'], 'vph': round(c['_vph'], 1),
             'duration': c['duration'], 'created_at': c['created_at']} for c in order]


def segment(c, label, dst, tmp):
    raw = os.path.join(tmp, c['id'] + '.mp4')
    if not os.path.exists(raw):
        subprocess.run(['yt-dlp', '-q', '-f', 'best[height<=1080]/best', '-o', raw, c['url']], check=True, timeout=300)
    lf, hf = os.path.join(tmp, c['id'] + '.label'), os.path.join(tmp, c['id'] + '.handle')
    open(lf, 'w').write(label.upper())
    open(hf, 'w').write('twitch.tv/' + c['login'])
    vf = ("scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=30,format=yuv420p,"
          "drawtext=fontfile=%s:textfile=%s:fontsize=56:fontcolor=white:box=1:boxcolor=black@0.7:boxborderw=20:"
          "x=60:y=60:enable='lt(t,6)',"
          "drawtext=fontfile=%s:textfile=%s:fontsize=36:fontcolor=white@0.95:box=1:boxcolor=0x9146FF@0.85:boxborderw=12:"
          "x=60:y=h-110" % (FONT, lf, FONT, hf))
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-i', raw, '-vf', vf,
                    '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000', '-ac', '2',
                    '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '21', '-r', '30',
                    '-c:a', 'aac', '-b:a', '160k', dst], check=True, timeout=600)
    return raw


def dur(p):
    return float(subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', p],
                                capture_output=True, text=True).stdout.strip() or 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', default=dt.datetime.now(TZ).strftime('%Y-%m-%d'))
    ap.add_argument('--relabel', action='store_true')
    a = ap.parse_args()
    d = 'episode/' + a.date
    os.makedirs(d + '/frames', exist_ok=True)
    plan = load(d + '/plan.json', None)
    clips = plan['clips'] if (a.relabel and plan) else pick(a.date)
    labels = load('episode/labels/%s.json' % a.date, {})
    drop = set(labels.get('_drop', []))          # clips the review run threw out
    clips = [c for c in clips if c['id'] not in drop]
    if labels.get('_first'):                     # the review run can pick a stronger opener
        clips.sort(key=lambda c: c['id'] != labels['_first'])
    tmp = tempfile.mkdtemp()
    segs, t, chapters, raws = [], 0.0, [], {}
    for i, c in enumerate(clips):
        c['label'] = labels.get(c['id']) or (c.get('label') if a.relabel else None) or clean_label(c['title'])
        s = os.path.join(tmp, 'seg%03d.mp4' % i)
        try:
            raws[c['id']] = segment(c, c['label'], s, tmp)
        except Exception as e:
            print('dropped', c['id'], e)
            c['dropped'] = str(e)[:200]
            continue
        c['start'] = round(t, 1)
        chapters.append('%d:%02d %s - %s' % (int(t) // 60, int(t) % 60, c['label'], c['streamer']))
        subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', str(min(2.5, dur(s) / 2)), '-i', s, '-frames:v', '1',
                        '-vf', 'scale=640:-2', '%s/frames/%02d.jpg' % (d, i)])
        t += dur(s)
        segs.append(s)
    clips = [c for c in clips if not c.get('dropped')]
    lst = os.path.join(tmp, 'list.txt')
    open(lst, 'w').write(''.join("file '%s'\n" % s for s in segs))
    os.makedirs('out', exist_ok=True)
    subprocess.run(['ffmpeg', '-y', '-v', 'error', '-f', 'concat', '-safe', '0', '-i', lst, '-c', 'copy',
                    '-movflags', '+faststart', 'out/episode.mp4'], check=True)
    if chapters and not chapters[0].startswith('0:00'):
        chapters[0] = '0:00' + chapters[0][4:]
    credits = sorted({c['login'] for c in clips})
    desc = ('The best GTA 6 moments from the last 24 hours.\n\n' + '\n'.join(chapters) +
            '\n\nCredits - go follow them:\n' + '\n'.join('https://twitch.tv/' + l for l in credits) +
            '\n\nClips:\n' + '\n'.join(c['url'] for c in clips) +
            '\n\nAll clips belong to the streamers credited above. Want a clip removed? Comment and it comes down.\n'
            '#gta6 #gtavi #gta6clips')
    open(d + '/description.txt', 'w').write(desc)
    thumb_files = thumbs.make(clips, raws, d)
    ep_no = len(load('state/episodes.json', {}).get('episodes', [])) + (0 if a.relabel else 1)
    plan = {'date': a.date, 'episode': ep_no, 'length_s': round(t), 'target_s': target_len(), 'clips': clips,
            'thumbnails': thumb_files, 'default_title': 'GTA 6 Best Clips of the Day #%d' % ep_no,
            'release': 'ep-' + a.date, 'built_at': fetch.dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}
    save(d + '/plan.json', plan)
    st = load('state/episodes.json', {'clip_ids': [], 'episodes': []})
    if not a.relabel:
        st['clip_ids'] = (st['clip_ids'] + [c['id'] for c in clips])[-4000:]
        st['episodes'].append({'date': a.date, 'status': 'built', 'length_s': round(t), 'clips': len(clips)})
    save('state/episodes.json', st)
    print('episode %s: %d clips, %d:%02d' % (a.date, len(clips), int(t) // 60, int(t) % 60))


if __name__ == '__main__':
    main()
