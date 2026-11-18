"""fetch.py - runs in GitHub Actions every 2 hours.
Pulls the fastest-rising GTA VI Twitch clips from approved streamers, renders the best new ones
into queue/<clip_id>.mp4 + .json, and prunes old files. Needs TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET."""
import datetime as dt, json, os, re, subprocess, sys, tempfile, time, urllib.parse, urllib.request
sys.path.insert(0, os.path.dirname(__file__))
import render

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
GAME = os.environ.get('GAME_NAME', 'Grand Theft Auto VI')
PER_RUN = int(os.environ.get('PER_RUN', '3'))        # clips rendered per run
QUEUE_MAX = int(os.environ.get('QUEUE_MAX', '12'))
MIN_VIEWS = int(os.environ.get('MIN_VIEWS', '25'))
BAD_TITLE = re.compile(r'spoil|ending|final mission|last mission|credits|finale|beat the game|leak', re.I)


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
    users = {}
    for i in range(0, len(ok), 100):
        for u in tw.get('users', {'login': [s['login'] for s in ok[i:i + 100]]}):
            users[u['id']] = u
    now = dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(hours=36)).strftime('%Y-%m-%dT%H:%M:%SZ')
    clips = []
    for uid in users:
        for c in tw.get('clips', {'broadcaster_id': uid, 'started_at': since, 'first': 30}):
            if c['game_id'] != gid or c['id'] in seen['ids'] or c['id'] in queued:
                continue
            if c['view_count'] < MIN_VIEWS or not (10 <= c['duration'] <= 60) or BAD_TITLE.search(c['title']):
                continue
            if c.get('vod_offset') is not None and c.get('video_id'):
                m = '%s:%d' % (c['video_id'], c['vod_offset'] // 45)
                if m in seen['moments']:
                    continue
                c['_moment'] = m
            clips.append(c)
    clips.sort(key=lambda c: score(c, now), reverse=True)
    # one moment per batch, max 2 per streamer per run so the feed stays varied
    picked, moments, per = [], set(), {}
    for c in clips:
        if c.get('_moment') in moments or per.get(c['broadcaster_id'], 0) >= 2:
            continue
        picked.append(c)
        moments.add(c.get('_moment'))
        per[c['broadcaster_id']] = per.get(c['broadcaster_id'], 0) + 1
        if len(picked) >= min(PER_RUN, QUEUE_MAX - len(queued)):
            break
    print('%d candidate clips, rendering %d' % (len(clips), len(picked)))
    for c in picked:
        try:
            make(c, users[c['broadcaster_id']], cfg, now)
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
    cam, transcript, used = render.render(raw, dst, cam=st.get('cam'), layout=layout,
                                          credit='twitch.tv/' + user['login'])
    if cam and not st.get('cam'):
        st['cam'] = cam
    meta = {'id': c['id'], 'streamer': user['display_name'], 'login': user['login'], 'title': c['title'],
            'views': c['view_count'], 'created_at': c['created_at'], 'duration': c['duration'],
            'clip_url': c['url'], 'layout': used, 'transcript': transcript,
            'score': round(score(c, now), 1), 'campaign': st.get('campaign'),
            'queued_at': now.strftime('%Y-%m-%dT%H:%M:%SZ')}
    save('queue/%s.json' % c['id'], meta)
    print('queued', c['id'], user['login'], c['view_count'], 'views', used)


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
