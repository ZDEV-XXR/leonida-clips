"""episode/upload_short.py - posts every Instagram Reel to the Leonida Replay YouTube channel as a Short.

`finish.py posted` writes shorts/<id>.json after each Instagram post; the push runs .github/workflows/shorts.yml,
which calls this. YouTube's default API quota is 10,000 units a day and an upload costs 1,600, so at most
MAX_PER_DAY Shorts go up per Pacific day; one upload slot is always left for the daily episode.
"""
import datetime as dt, glob, json, os, sys, urllib.error
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(os.path.dirname(HERE))
from upload import token, req   # noqa: E402

MAX_PER_DAY = int(os.environ.get('SHORTS_PER_DAY', '5'))
PT = dt.timezone(dt.timedelta(hours=-8))      # quota resets at midnight Pacific


def main():
    today = dt.datetime.now(PT).date().isoformat()
    items = [(p, json.load(open(p))) for p in sorted(glob.glob('shorts/*.json'))]
    done_today = sum(1 for _, s in items if (s.get('uploaded_at_pt') or '').startswith(today))
    todo = [(p, s) for p, s in items if not s.get('youtube_id') and not s.get('skipped')
            and s.get('created', '') >= (dt.date.today() - dt.timedelta(days=1)).isoformat()]
    if not todo:
        print('nothing to upload')
        return
    tok = token()
    for p, s in todo:
        if done_today >= MAX_PER_DAY:
            s['skipped'] = 'daily YouTube quota (%d Shorts/day, 1 slot kept for the episode)' % MAX_PER_DAY
            json.dump(s, open(p, 'w'), indent=1)
            print('quota: skipped', s['id'])
            continue
        if not os.path.exists(s['file']):
            s['skipped'] = 'file missing'
            json.dump(s, open(p, 'w'), indent=1)
            continue
        meta = {'snippet': {'title': s['title'][:100], 'description': s['description'][:4900],
                            'tags': ['gta 6', 'gta vi', 'gta 6 clips', 'shorts', s.get('streamer') or ''],
                            'categoryId': '20'},
                'status': {'privacyStatus': 'public', 'selfDeclaredMadeForKids': False}}
        try:
            r = req('https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status', tok,
                    json.dumps(meta).encode(), {'Content-Type': 'application/json; charset=UTF-8',
                                                'X-Upload-Content-Type': 'video/mp4',
                                                'X-Upload-Content-Length': str(os.path.getsize(s['file']))})
            vid = json.load(req(r.headers['Location'], tok, open(s['file'], 'rb').read(), {'Content-Type': 'video/mp4'}, 'PUT'))['id']
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:500]
            print('upload refused', s['id'], e.code, body)
            if 'quotaExceeded' in body:
                s['skipped'] = 'YouTube quota exceeded'
                json.dump(s, open(p, 'w'), indent=1)
            continue
        s.update(youtube_id=vid, uploaded_at_pt=dt.datetime.now(PT).strftime('%Y-%m-%dT%H:%M'))
        json.dump(s, open(p, 'w'), indent=1)
        done_today += 1
        print('short uploaded', s['id'], 'https://youtube.com/shorts/' + vid)


if __name__ == '__main__':
    main()
