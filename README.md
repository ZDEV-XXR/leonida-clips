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
`TWITCH_CLIENT_SECRET` (the client id is public and lives in the workflow) (Settings > Secrets and variables > Actions).

## Daily long-form episode (YouTube)
1. **Outlier research** (`.github/workflows/research.yml`, Mondays): `research/outliers.py scan` pulls the last 30 uploads of every
   approved channel in `research/channels.json`, keeps the ones that beat the channel's median views by 3x+ (`outliers.csv`),
   saves their thumbnails to `research/thumbs/` and writes `research/CHANGES.md`. `discover` finds candidate channels
   (`research/candidates.json`); only channels you approve are studied.
2. **Build** (`.github/workflows/episode.yml`, 6:07 am Tucson): `episode/build.py` takes the day's top GTA VI Twitch clips by
   views per hour (whole game + approved streamers, no spoilers/cutscenes/exploits, max 3 per streamer), opens on the best one,
   cuts to the winning compilation length, labels every clip + handle, writes chapters and credits, makes 3 thumbnails
   (`episode/thumbs.py`). Video goes to the `ep-<date>` release.
3. **Review** (scheduled Claude run, see `EPISODE_RUN.md`): labels, titles, thumbnail, then the gauntlet - a fresh agent says
   yes or no with faults. Verdicts go to `RULES.md`.
4. **Upload** (`.github/workflows/upload.yml`): runs when `approved.json` is pushed, posts to YouTube with the thumbnail,
   logs the link in `STATUS.md`.

Secrets for the upload: `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` (Google Cloud OAuth client with YouTube Data API v3,
refresh token from a one-time sign-in to the Leonida Replay channel).
