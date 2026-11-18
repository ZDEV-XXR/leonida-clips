# Leonida Clips

Automated GTA VI clip channel. Twitch viewers make the clips; this repo picks the fastest-rising ones from approved streamers, turns them into vertical Shorts, and a scheduled Claude run reviews and posts them.

## How it runs
1. **GitHub Actions** (`.github/workflows/fetch.yml`, every 2 hours) runs `clipper/fetch.py`:
   - gets GTA VI clips from the last 36 hours for every `approved` streamer in `streamers.json`
   - skips clips already seen, repeat moments (same stream within 45 s), spoiler-ish titles, clips under 10 s, and anything under 25 views
   - ranks by views per hour, renders the top 3 with `clipper/render.py` into `queue/` (max 12 queued)
   - render: facecam on top + gameplay below when a facecam is found (saved per streamer), otherwise zoomed gameplay over a blurred background; word-by-word captions from Whisper; streamer credit at the bottom
2. **Scheduled Claude run** (3 times a day) runs `finish.py next`, looks at the review frames and transcript, skips anything with gore in the first 7 seconds, story spoilers, slurs or a bad crop, writes a hook and caption, runs `finish.py make`, pushes, posts the Reel through Windsor and runs `finish.py posted`.

## Files
- `streamers.json` - who gets clipped. `cam` is the saved facecam box; set `"layout": "full"` to turn the split off for someone.
- `queue/` - rendered clips waiting for review. `out/` - posted files (kept 3 days so the links keep working).
- `state/seen.json`, `state/posted.json`, `state/skipped.json` - memory.

## Secrets
`TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET` (Settings > Secrets and variables > Actions).
