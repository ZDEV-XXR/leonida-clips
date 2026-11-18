"""fetch.py - runs in GitHub Actions every 2 hours.
Pulls the fastest-rising GTA VI Twitch clips from approved streamers, renders the best new ones
into queue/<clip_id>.mp4 + .json, and prunes old files. Needs TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET."""
import datetime as dt, json, os, re, subprocess, sys, tempfile, time, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import render, learn

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
GAME = os.environ.get('GAME_NAME', 'Grand Theft Auto VI')
PER_RUN = int(os.environ.get('PER_RUN', '3'))        # clips rendered per run
QUEUE_MAX = int(os.environ.get('QUEUE_MAX', '12'))
MIN_VIEWS = int(os.environ.get('MIN_VIEWS', '25'))
LANGS = set(os.environ.get('CLIP_LANGS', 'en').split(','))   # page language(s); a Spanish page would set es
MIN_ACTION = float(os.environ.get('MIN_ACTION', '0.35'))   # clips scoring below this (calm, silent, dead air) are dropped
AUTO_MAX = int(os.environ.get('AUTO_MAX', '25'))      # cap on the streamer list when trend radar adds people
BAD_TITLE = re.compile(r'spoil|ending|final mission|last mission|credits|finale|beat the game|leak|strip|horny|lap ?dance|private dance|nsfw|naked|nude|thirst|rizz|hooker|prostitut|sexy|boob|twerk', re.I)


def load(p, default):
    return json.load(open(p)) if os.path.exists(p) else default


def save(p, obj):
    json.dump(obj, open(p, 'w'), indent=1)


class Twitch:
    def __init__(self):
        cid, sec = os.environ['TWITCH_CLIENT_ID'], os.environ['TWITCH_CLIENT_SECRET']
        body = urllib.parse.urlencode({'client_id': cid, 'client_secret': sec,
                                       'grant_type': 'client_credentials'}).encode()
        tok = json.load(urllib.request.urlopen('https://id.twitch.tv/oauth2/token', body, timeout=30))
        self.h = {'Client-Id': cid, 'Authorization': 'Bearer ' + tok['access_token']}

    def get(self, path, params):
        q = urllib.parse.urlencode(params, doseq=True)
        req = urllib.request.Request('https://api.twitch.tv/helix/%s?%s' % (path, q), headers=self.h)
        for i in range(3):
            try:
                return json.load(urllib.request.urlopen(req, timeout=30))['data']
            except urllib.error.HTTPError as e:
                if e.code == 429 and i < 2:
                    time.sleep(5)
                    continue
                raise


def score(c, now):
    age = (now - dt.datetime.fromisoformat(c['created_at'].replace('Z', '+00:00'))).total_seconds() / 3600
    return c['view_count'] / (age + 2) ** 1.2


def main():
    cfg = load('streamers.json', {'streamers': []})
    ok = [s for s in cfg['streamers'] if s.get('approved')]
    seen = load('state/seen.json', {'ids': [], 'moments': []})
    posted = load('state/posted.json', [])
    queued = [f[:-5] for f in os.listdir('queue') if f.endswith('.json')]
    prune(posted)
    if len(queued) >= QUEUE_MAX:
        print('queue full (%d)' % len(queued))
        return
    tw = Twitch()
    game = tw.get('games', {'name': GAME})
    if not game:
        sys.exit('game not found on Twitch: %s' % GAME)
    gid = game[0]['id']
    hist = learn.load()
    try:
        trend_radar(tw, gid, cfg, hist)
        learn.save_trend(hist['trend'])
        ok = [s for s in cfg['streamers'] if s.get('approved')]
    except Exception as e:
        print('trend radar failed:', e)
    users = {}
    for i in range(0, len(ok), 100):
        for u in tw.get('users', {'login': [s['login'] for s in ok[i:i + 100]]}):
            users[u['id']] = u
    now = dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(hours=36)).strftime('%Y-%m-%dT%H:%M:%SZ')
    clips = []
    for uid in users:
        for c in tw.get('clips', {'broadcaster_id': uid, 'started_at': since, 'first': 30}):
            if c['game_id'] != gid or c['id'] in seen['ids'] or c['id'] in queued or c.get('language', 'en')[:2] not in LANGS:
                continue
            if c['view_count'] < MIN_VIEWS or not (10 <= c['duration'] <= 60) or BAD_TITLE.search(c['title']):
                continue
            if c.get('vod_offset') is not None and c.get('video_id'):
                m = '%s:%d' % (c['video_id'], c['vod_offset'] // 45)
                if m in seen['moments']:
                    continue
                c['_moment'] = m
            clips.append(c)
    for c in clips:
        c['_rank'] = learn.rank({'login': users[c['broadcaster_id']]['login'], 'title': c['title'],
                                 'duration': c['duration']}, score(c, now), hist)
    clips.sort(key=lambda c: c['_rank'], reverse=True)
    # one moment per batch, max 2 per streamer per run so the feed stays varied
    picked, moments, per = [], set(), {}
    for c in clips:
        if c.get('_moment') in moments or per.get(c['broadcaster_id'], 0) >= 2:
            continue
        picked.append(c)
        moments.add(c.get('_moment'))
        per[c['broadcaster_id']] = per.get(c['broadcaster_id'], 0) + 1
        if len(picked) >= 3 * min(PER_RUN, QUEUE_MAX - len(queued)):    # extra candidates: some get dropped as too calm
            break
    want = min(PER_RUN, QUEUE_MAX - len(queued))
    print('%d candidate clips, trying %d to queue %d' % (len(clips), len(picked), want))
    made = 0
    for c in picked:
        if made >= want:
            break
        try:
            made += 1 if make(c, users[c['broadcaster_id']], cfg, now) else 0
        except Exception as e:
            print('failed %s: %s' % (c['id'], e))
        seen['ids'].append(c['id'])
        if c.get('_moment'):
            seen['moments'].append(c['_moment'])
    seen['ids'], seen['moments'] = seen['ids'][-3000:], seen['moments'][-3000:]
    save('state/seen.json', seen)
    save('streamers.json', cfg)


def make(c, user, cfg, now):
    tmp = tempfile.mkdtemp()
    raw = os.path.join(tmp, 'raw.mp4')
    subprocess.run(['yt-dlp', '-q', '-f', 'best[height<=1080]/best', '-o', raw, c['url']], check=True, timeout=300)
    st = next(s for s in cfg['streamers'] if s['login'].lower() == user['login'].lower())
    layout = st.get('layout', 'auto')
    dst = 'queue/%s.mp4' % c['id']
    genes = learn.choose()
    cam, transcript, used, kept, action = render.render(
        raw, dst, cam=st.get('cam'), layout=layout, credit='twitch.tv/' + user['login'],
        genes=dict(genes, _title=c['title'], _min_action=MIN_ACTION))
    if used == 'rejected':
        print('dropped %s (%s): action score %s %s' % (c['id'], user['login'], action[0], action[1]))
        return False
    if cam and not st.get('cam'):
        st['cam'] = cam
    meta = {'id': c['id'], 'streamer': user['display_name'], 'login': user['login'], 'title': c['title'],
            'views': c['view_count'], 'created_at': c['created_at'], 'duration': c['duration'],
            'clip_url': c['url'], 'layout': used, 'transcript': transcript,
            'score': round(c.get('_rank', score(c, now)), 1), 'campaign': st.get('campaign'),
            'genes': genes, 'kept': kept, 'action': action[0], 'action_parts': action[1],
            'queued_at': now.strftime('%Y-%m-%dT%H:%M:%SZ')}
    save('queue/%s.json' % c['id'], meta)
    print('queued', c['id'], user['login'], c['view_count'], 'views', used, 'action', action[0])
    return True


def trend_radar(tw, gid, cfg, hist):
    """What is blowing up right now, across ALL of GTA VI on Twitch (not just our list):
    hot topics in clip titles, streamers whose clips are exploding or who are live with big crowds,
    and hook wording from the top GTA 6 Shorts on YouTube. Adds breakout streamers to the list."""
    now = dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%SZ')
    clips = tw.get('clips', {'game_id': gid, 'started_at': since, 'first': 100})
    topic_w, streamer_w, logins, lang = {}, {}, {}, {}
    for c in clips:
        lang[c['broadcaster_id']] = (c.get('language') or 'en')[:2]
        if lang[c['broadcaster_id']] not in LANGS:
            continue
        v = score(c, now)
        for t in learn.topics_of(c['title']):
            topic_w[t] = topic_w.get(t, 0) + v
        streamer_w[c['broadcaster_id']] = streamer_w.get(c['broadcaster_id'], 0) + v
    live = tw.get('streams', {'game_id': gid, 'first': 30})
    for st in live:
        lang[st['user_id']] = (st.get('language') or 'en')[:2]
        if lang[st['user_id']] not in LANGS:
            continue
        streamer_w[st['user_id']] = streamer_w.get(st['user_id'], 0) + st['viewer_count'] / 50
        logins[st['user_id']] = st['user_login']
    ids = [i for i in streamer_w if i not in logins]
    for i in range(0, len(ids), 100):
        for u in tw.get('users', {'id': ids[i:i + 100]}):
            logins[u['id']] = u['login']
    norm = lambda d: {k: round(v / max(d.values()), 3) for k, v in d.items()} if d else {}
    sw = norm({logins.get(k, k).lower(): v for k, v in streamer_w.items()})
    tr = {'at': now.strftime('%Y-%m-%dT%H:%M:%SZ'), 'topics': norm(topic_w),
          'streamers': dict(sorted(sw.items(), key=lambda x: -x[1])[:30]),
          'titles': hist.get('trend', {}).get('titles', []), 'added': hist.get('trend', {}).get('added', [])}
    # breakout streamers join the list (unless blocked), up to AUTO_MAX in total
    have = {s['login'].lower() for s in cfg['streamers']}
    blocked = {b.lower() for b in cfg.get('blocked', [])}
    for login, w in sorted(sw.items(), key=lambda x: -x[1]):
        if len(cfg['streamers']) >= AUTO_MAX or w < 0.25:
            break
        if login not in have and login not in blocked:
            cfg['streamers'].append({'login': login, 'approved': True, 'cam': None, 'auto': tr['at']})
            tr['added'] = (tr['added'] + [login])[-50:]
            print('trend radar added streamer', login, w)
    # hook wording: top GTA 6 Shorts on YouTube right now (best effort)
    try:
        out = subprocess.run(['yt-dlp', '-J', '--flat-playlist', 'ytsearch40:gta 6 shorts'],
                             capture_output=True, text=True, timeout=120).stdout
        ents = [e for e in json.loads(out).get('entries', []) if e.get('title')]
        ents.sort(key=lambda e: -(e.get('view_count') or 0))
        tr['titles'] = [e['title'][:90] for e in ents[:15]]
        for e in ents[:15]:
            for t in learn.topics_of(e['title']):
                tr['topics'][t] = round(min(1.0, tr['topics'].get(t, 0) + 0.1), 3)
    except Exception as e:
        print('youtube trend check failed:', e)
    hist['trend'] = tr
    print('trend topics', sorted(tr['topics'].items(), key=lambda x: -x[1])[:5])


def prune(posted):
    """Drop queued clips older than 30h (stale at launch speed) and posted files older than 3 days."""
    # file mtimes are reset by every git checkout, so ages come from the timestamps in the json files
    now = dt.datetime.now(dt.timezone.utc)
    age = lambda s: (now - dt.datetime.fromisoformat(s.replace('Z', '+00:00'))).total_seconds() / 3600
    for f in os.listdir('queue'):
        if f.endswith('.json'):
            meta = load(os.path.join('queue', f), {})
            if age(meta.get('queued_at', '2000-01-01T00:00:00Z')) > 30:
                for ext in ('.json', '.mp4'):
                    q = os.path.join('queue', f[:-5] + ext)
                    if os.path.exists(q):
                        os.remove(q)
    for p in posted:
        f = os.path.join('out', p['id'] + '.mp4')
        if os.path.exists(f) and age(p.get('posted_at', '2000-01-01T00:00:00Z')) > 72:
            os.remove(f)


if __name__ == '__main__':
    main()
