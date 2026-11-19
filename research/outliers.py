"""research/outliers.py - weekly, in GitHub Actions. No API keys: uses yt-dlp metadata only.

  python research/outliers.py discover   find active English GTA YouTube channels -> research/candidates.json
  python research/outliers.py scan       pull recent uploads of every approved channel in channels.json,
                                         keep videos that beat their channel's usual views by far -> outliers.csv,
                                         download their thumbnails to research/thumbs/, write what changed to CHANGES.md
"""
import csv, datetime as dt, json, os, re, statistics, subprocess, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
R = 'research'
RATIO = float(os.environ.get('OUTLIER_RATIO', '3'))      # views must beat the channel median by this much
MIN_VIEWS = int(os.environ.get('OUTLIER_MIN_VIEWS', '20000'))
RECENT = int(os.environ.get('RECENT', '30'))              # uploads looked at per channel
QUERIES = ['gta 6 best moments', 'gta 6 funny moments compilation', 'gta 6 streamer clips', 'gta 6 secrets',
           'gta 6 easter eggs', 'gta 6 news', 'gta 6 gameplay', 'gta vi best clips', 'gta 6 daily clips',
           'gta 6 map', 'gta 6 tips and tricks', 'gta 6 cars', 'gta 6 funny', 'gta 6 vs gta 5', 'gta 6 everything we know',
           'gta 6 trailer breakdown', 'gta 6 first day', 'gta 6 heist', 'gta 6 police chase', 'gta 6 online',
           'gta 5 funny moments', 'gta online', 'gta 5 mods', 'gta rp', 'gta 6 reaction', 'gta 6 challenge',
           'gta 6 rampage', 'gta 6 story', 'gta 6 hidden details', 'gta 6 speedrun', 'gta 6 wanted level']
TOP = int(os.environ.get('TOP_CHANNELS', '20'))
NOT_CREATORS = re.compile(r'rockstar|\bign\b|gamespot|gamestar|gamingbolt|playstation|xbox|news|daily fix', re.I)


def load(p, d):
    return json.load(open(p)) if os.path.exists(p) else d


def save(p, o):
    json.dump(o, open(p, 'w'), indent=1)


def ytj(url, extra=()):
    try:
        out = subprocess.run(['yt-dlp', '-J', '--flat-playlist', '--no-warnings', *extra, url],
                             capture_output=True, text=True, timeout=300).stdout
        j = json.loads(out) if out.strip() else {}
        return j if isinstance(j, dict) else {}
    except Exception as e:
        print('yt-dlp failed for', url, str(e)[:120])
        return {}


def discover():
    cands = {}
    for q in QUERIES:
        for e in ytj('ytsearch50:' + q, ['--extractor-args', 'youtube:lang=en']).get('entries') or []:
            e = e or {}
            cid, name = e.get('channel_id'), e.get('channel') or e.get('uploader')
            if not cid or not name:
                continue
            c = cands.setdefault(cid, {'id': cid, 'name': name, 'url': 'https://www.youtube.com/channel/' + cid,
                                       'hits': 0, 'search_views': 0, 'sample': []})
            c['hits'] += 1
            c['search_views'] += e.get('view_count') or 0
            if len(c['sample']) < 3:
                c['sample'].append(e.get('title', '')[:80])
    have = {c['id'] for c in load(R + '/channels.json', {'channels': []})['channels']}
    out = []
    for c in sorted(cands.values(), key=lambda c: -c['search_views'])[:140]:
        if c['id'] in have or NOT_CREATORS.search(c['name']):
            continue
        j = ytj(c['url'] + '/videos', ['--playlist-end', '15'])
        ents = [e for e in (j.get('entries') or []) if e]
        subs = j.get('channel_follower_count')
        titles = ' '.join(e.get('title', '') for e in ents).lower()
        gta = sum(1 for e in ents if re.search(r'gta|grand theft|leonida|vice city', e.get('title', ''), re.I))
        ascii_share = sum(ch.isascii() for ch in titles) / max(len(titles), 1)
        if len(ents) < 5 or gta < len(ents) * 0.6 or ascii_share < 0.97:   # active, mostly GTA, English
            continue
        views = [e.get('view_count') or 0 for e in ents]
        c.update(subs=subs, gta_share=round(gta / len(ents), 2), median_views=int(statistics.median(views)),
                 latest=[e.get('title', '')[:80] for e in ents[:3]])
        out.append(c)
    out.sort(key=lambda c: -(c.get('subs') or c['median_views']))
    save(R + '/candidates.json', {'at': now(), 'candidates': out})
    if os.environ.get('AUTO_APPROVE_TOP'):        # David asked for the top 20 GTA creator channels by subscribers
        cfg = load(R + '/channels.json', {'channels': []})
        cfg['channels'] = [dict(id=c['id'], name=c['name'], url=c['url'], subs=c.get('subs'), approved=True) for c in out[:TOP]]
        save(R + '/channels.json', cfg)
        print('approved top %d channels' % len(cfg['channels']))
    print('%d candidate channels' % len(out))
    for c in out:
        print('%-32s subs=%-9s median=%-8s gta=%s' % (c['name'][:32], c.get('subs'), c['median_views'], c['gta_share']))


def now():
    return dt.datetime.now(dt.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def scan():
    chans = [c for c in load(R + '/channels.json', {'channels': []})['channels'] if c.get('approved')]
    if not chans:
        sys.exit('no approved channels in research/channels.json')
    old = {}
    if os.path.exists(R + '/outliers.csv'):
        old = {r['video_id']: r for r in csv.DictReader(open(R + '/outliers.csv'))}
    rows = []
    for c in chans:
        for tab in ('videos', 'shorts'):
            ents = [e for e in (ytj(c['url'] + '/' + tab, ['--playlist-end', str(RECENT)]).get('entries') or []) if e]
            ents = [e for e in ents if e.get('view_count') is not None]
            if len(ents) < 6:
                continue
            med = statistics.median(e['view_count'] for e in ents) or 1
            for e in ents:
                v = e['view_count']
                if v >= med * RATIO and v >= MIN_VIEWS and re.search(r'gta|grand theft|leonida|vice city', e.get('title', ''), re.I):
                    thumb = 'https://i.ytimg.com/vi/%s/hqdefault.jpg' % e['id']
                    rows.append({'video_id': e['id'], 'channel': c['name'], 'format': 'long' if tab == 'videos' else 'short',
                                 'title': e.get('title', ''), 'views': v, 'channel_median': int(med),
                                 'ratio': round(v / med, 1), 'duration_s': int(e.get('duration') or 0),
                                 'url': 'https://www.youtube.com/watch?v=' + e['id'], 'thumbnail': thumb,
                                 'found': old.get(e['id'], {}).get('found') or now()[:10]})
    rows.sort(key=lambda r: -r['ratio'])
    with open(R + '/outliers.csv', 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ['video_id'])
        w.writeheader()
        w.writerows(rows)
    os.makedirs(R + '/thumbs', exist_ok=True)
    keep = set()
    for r in rows:
        if r['format'] != 'long':
            continue
        p = '%s/thumbs/%s.jpg' % (R, r['video_id'])
        keep.add(os.path.basename(p))
        if not os.path.exists(p):
            try:
                urllib.request.urlretrieve(r['thumbnail'], p)
            except Exception as e:
                print('thumb failed', r['video_id'], e)
    for f in os.listdir(R + '/thumbs'):
        if f not in keep:
            os.remove(os.path.join(R, 'thumbs', f))
    # what changed since last week
    new = [r for r in rows if r['video_id'] not in old]
    gone = [r for k, r in old.items() if k not in {x['video_id'] for x in rows}]
    longs = [r for r in rows if r['format'] == 'long' and r['duration_s']]
    comp = [r for r in longs if re.search(r'best|funny|moments|clips|compilation|highlights|reacts', r['title'], re.I)]
    target = int(statistics.median(r['duration_s'] for r in (comp or longs))) if (comp or longs) else None
    lines = ['# Outliers - week of %s' % now()[:10], '',
             '%d outliers across %d channels (%d new, %d dropped off).' % (len(rows), len(chans), len(new), len(gone)),
             'Winning compilation length (median of outlier compilations): %s' % ('%d:%02d' % divmod(target, 60) if target else 'not enough data'), '']
    if new:
        lines += ['## New this week'] + ['- %sx %s - %s (%s views)' % (r['ratio'], r['channel'], r['title'], f"{r['views']:,}") for r in new[:25]] + ['']
    if gone:
        lines += ['## Dropped off'] + ['- %s - %s' % (r['channel'], r['title']) for r in gone[:15]] + ['']
    open(R + '/CHANGES.md', 'w').write('\n'.join(lines))
    meta = load(R + '/meta.json', {})
    meta.update(scanned=now(), target_len=target, outliers=len(rows))
    save(R + '/meta.json', meta)
    print('\n'.join(lines))


if __name__ == '__main__':
    {'discover': discover, 'scan': scan}[sys.argv[1]]()
