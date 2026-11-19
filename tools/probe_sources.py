"""One-off: can GitHub Actions reach Kick clips and YouTube heatmaps/downloads? Writes state/probe.json."""
import json, subprocess, urllib.request, time, os
out = {}
def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36', 'Accept': 'application/json'})
    try:
        r = urllib.request.urlopen(req, timeout=30); b = r.read().decode()[:3000]; return r.status, b
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:500]
    except Exception as e:
        return 0, str(e)[:300]
for slug in ['xqc', 'adinross']:
    out['kick_v2_' + slug] = get('https://kick.com/api/v2/channels/%s/clips?sort=view&time=day' % slug)
out['kick_v1_channel'] = get('https://kick.com/api/v1/channels/xqc')
def yt(args, t=240):
    p = subprocess.run(['yt-dlp', *args], capture_output=True, text=True, timeout=t)
    return p.returncode, p.stdout[-1500:], p.stderr[-800:]
code, so, se = yt(['-J', '--flat-playlist', '--playlist-end', '5', 'https://www.youtube.com/@KreekCraft/streams'])
out['yt_streams_list'] = [code, so[:600], se]
try:
    vids = [e['id'] for e in json.loads(subprocess.run(['yt-dlp', '-J', '--flat-playlist', '--playlist-end', '3', 'https://www.youtube.com/@KreekCraft/streams'], capture_output=True, text=True, timeout=240).stdout)['entries']]
except Exception as e:
    vids = []; out['yt_vids_err'] = str(e)
if vids:
    p = subprocess.run(['yt-dlp', '-J', 'https://www.youtube.com/watch?v=' + vids[0]], capture_output=True, text=True, timeout=240)
    try:
        j = json.loads(p.stdout); out['yt_meta'] = {'title': j.get('title'), 'dur': j.get('duration'), 'heatmap_points': len(j.get('heatmap') or []), 'views': j.get('view_count')}
    except Exception:
        out['yt_meta'] = ['fail', p.stderr[-600:]]
    out['yt_download'] = yt(['-f', 'best[height<=720]/best', '--download-sections', '*60-90', '-o', '/tmp/yt.mp4', 'https://www.youtube.com/watch?v=' + vids[0]], 300)
    out['yt_download_size'] = os.path.getsize('/tmp/yt.mp4') if os.path.exists('/tmp/yt.mp4') else 0
os.makedirs('state', exist_ok=True)
json.dump(out, open('state/probe.json', 'w'), indent=1)
print(json.dumps(out, indent=1)[:4000])
