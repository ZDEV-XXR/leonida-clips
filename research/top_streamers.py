"""research/top_streamers.py - who is playing GTA VI the most right now (English Twitch), top N become the
only approved streamers for the Shorts and the daily episode. Runs weekly with the outlier research.
Score = 60% clip views over the last 7 days + 40% live viewers right now. Needs TWITCH_CLIENT_ID/SECRET."""
import datetime as dt, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, 'clipper')]
os.chdir(ROOT)
import fetch   # noqa: E402

N = int(os.environ.get('TOP_STREAMERS', '10'))


def pages(tw, path, params, n):
    import urllib.parse, urllib.request
    out, cur = [], None
    for _ in range(n):
        q = dict(params, **({'after': cur} if cur else {}))
        req = urllib.request.Request('https://api.twitch.tv/helix/%s?%s' % (path, urllib.parse.urlencode(q)), headers=tw.h)
        j = json.load(urllib.request.urlopen(req, timeout=30))
        out += j['data']
        cur = j.get('pagination', {}).get('cursor')
        if not cur:
            break
    return out


def main():
    tw = fetch.Twitch()
    gid = tw.get('games', {'name': fetch.GAME})[0]['id']
    now = dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(days=7)).strftime('%Y-%m-%dT%H:%M:%SZ')
    clip_v, live_v, name = {}, {}, {}
    for c in pages(tw, 'clips', {'game_id': gid, 'started_at': since, 'first': 100}, 8):
        if (c.get('language') or 'en')[:2] in fetch.LANGS:
            k = c['broadcaster_name'].lower()
            clip_v[k] = clip_v.get(k, 0) + c['view_count']
    for s in pages(tw, 'streams', {'game_id': gid, 'first': 100}, 2):
        if (s.get('language') or 'en')[:2] in fetch.LANGS:
            live_v[s['user_login'].lower()] = s['viewer_count']
            name[s['user_login'].lower()] = s['user_name']
    cfg = fetch.load('streamers.json', {'streamers': []})
    blocked = {b.lower() for b in cfg.get('blocked', [])}
    norm = lambda d: {k: v / max(d.values()) for k, v in d.items()} if d else {}
    cn, ln = norm(clip_v), norm(live_v)
    score = {k: 0.6 * cn.get(k, 0) + 0.4 * ln.get(k, 0) for k in set(cn) | set(ln) if k not in blocked}
    top = sorted(score, key=lambda k: -score[k])[:N]
    have = {s['login'].lower(): s for s in cfg['streamers']}
    for k in top:
        if k not in have:
            cfg['streamers'].append({'login': k, 'approved': True, 'cam': None})
    for s in cfg['streamers']:
        s['approved'] = s['login'].lower() in top
    cfg['top_n'] = N      # trend radar stops auto-adding people while a top-N list is in charge
    cfg['streamers'].sort(key=lambda s: (not s['approved'], -score.get(s['login'].lower(), 0)))
    fetch.save('streamers.json', cfg)
    rep = {'at': now.strftime('%Y-%m-%dT%H:%M:%SZ'), 'top': [
        {'login': k, 'score': round(score[k], 3), 'clip_views_7d': clip_v.get(k, 0), 'live_viewers_now': live_v.get(k, 0)} for k in top]}
    json.dump(rep, open('research/top_streamers.json', 'w'), indent=1)
    for r in rep['top']:
        print('%-18s score=%.3f clips7d=%-8d live=%d' % (r['login'], r['score'], r['clip_views_7d'], r['live_viewers_now']))


if __name__ == '__main__':
    main()
