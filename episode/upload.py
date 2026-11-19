"""episode/upload.py - uploads an approved episode to YouTube (Data API v3), sets the thumbnail, logs it.

Runs in GitHub Actions only after the review run wrote episode/<date>/approved.json (the gauntlet said yes):
  {"title": "...", "thumbnail": "episode/<date>/thumb_B.jpg", "verdict": "yes", "faults": []}
Secrets: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN (one-time sign-in, see README).
  python episode/upload.py --date YYYY-MM-DD --video out/episode.mp4
"""
import argparse, datetime as dt, json, os, sys, urllib.error, urllib.parse, urllib.request
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)


def load(p, d):
    return json.load(open(p)) if os.path.exists(p) else d


def token():
    body = urllib.parse.urlencode({'client_id': os.environ['YT_CLIENT_ID'], 'client_secret': os.environ['YT_CLIENT_SECRET'],
                                   'refresh_token': os.environ['YT_REFRESH_TOKEN'], 'grant_type': 'refresh_token'}).encode()
    return json.load(urllib.request.urlopen('https://oauth2.googleapis.com/token', body, timeout=30))['access_token']


def req(url, tok, data=None, headers=None, method=None):
    h = {'Authorization': 'Bearer ' + tok, **(headers or {})}
    return urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h, method=method), timeout=1800)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--date', required=True)
    ap.add_argument('--video', default='out/episode.mp4')
    a = ap.parse_args()
    d = 'episode/' + a.date
    plan, ok = load(d + '/plan.json', None), load(d + '/approved.json', None)
    if not plan or not ok or ok.get('verdict') != 'yes':
        sys.exit('not approved: ' + d)
    if ok.get('youtube_id'):
        sys.exit('already uploaded: ' + ok['youtube_id'])
    tok = token()
    try:
        ch = json.load(req('https://www.googleapis.com/youtube/v3/channels?part=snippet&mine=true', tok))
        print('channel:', [(c['id'], c['snippet']['title']) for c in ch.get('items', [])] or 'NONE - this Google account has no YouTube channel')
    except urllib.error.HTTPError as e:
        print('channel check failed:', e.code, e.read().decode()[:600])
    meta = {'snippet': {'title': ok['title'][:100], 'description': open(d + '/description.txt').read()[:4900],
                        'tags': ['gta 6', 'gta vi', 'gta 6 clips', 'gta 6 funny moments', 'gta 6 best moments'],
                        'categoryId': '20', 'defaultLanguage': 'en'},
            'status': {'privacyStatus': ok.get('privacy') or os.environ.get('YT_PRIVACY', 'public'), 'selfDeclaredMadeForKids': False}}
    size = os.path.getsize(a.video)
    try:
        r = req('https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status', tok,
            json.dumps(meta).encode(), {'Content-Type': 'application/json; charset=UTF-8',
                                        'X-Upload-Content-Type': 'video/mp4', 'X-Upload-Content-Length': str(size)})
    except urllib.error.HTTPError as e:
        sys.exit('upload refused: %s %s' % (e.code, e.read().decode()[:800]))
    loc = r.headers['Location']
    with open(a.video, 'rb') as f:
        vid = json.load(req(loc, tok, f.read(), {'Content-Type': 'video/mp4'}, 'PUT'))['id']
    print('uploaded', vid)
    thumb_note = 'set'
    try:
        req('https://www.googleapis.com/upload/youtube/v3/thumbnails/set?videoId=' + vid, tok,
            open(ok['thumbnail'], 'rb').read(), {'Content-Type': 'image/jpeg'})
    except Exception as e:      # custom thumbnails need a phone-verified channel
        thumb_note = 'FAILED (%s) - verify the channel phone number in YouTube Studio' % e
        print('thumbnail', thumb_note)
    ok.update(youtube_id=vid, uploaded_at=dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), thumbnail_status=thumb_note)
    json.dump(ok, open(d + '/approved.json', 'w'), indent=1)
    st = load('state/episodes.json', {'clip_ids': [], 'episodes': []})
    for e in st['episodes']:
        if e['date'] == a.date:
            e.update(status='posted', youtube_id=vid, title=ok['title'])
    json.dump(st, open('state/episodes.json', 'w'), indent=1)
    with open('STATUS.md', 'a') as f:
        f.write('- %s episode #%s "%s" https://youtu.be/%s (%d clips, %d:%02d, thumbnail %s)\n' % (
            a.date, plan['episode'], ok['title'], vid, len(plan['clips']), plan['length_s'] // 60, plan['length_s'] % 60,
            os.path.basename(ok['thumbnail']) if thumb_note == 'set' else thumb_note))


if __name__ == '__main__':
    main()
