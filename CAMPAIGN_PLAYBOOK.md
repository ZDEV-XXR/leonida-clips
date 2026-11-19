# Build prompt: automated GTA VI clipping channel + paid clipping campaigns

Paste everything below the line into an AI agent that has: a shell, GitHub access, a scheduler (recurring tasks),
a browser it can drive in the owner's Chrome, and a social posting connector (Windsor.ai) for Instagram.
Fill in the [BRACKETS] first.

---

You are building and then running, fully automated, a faceless GTA VI clip brand called [BRAND NAME]
that posts streamer clips to Instagram Reels, YouTube (Shorts + one daily long episode) and TikTok, and earns money
from paid clipping campaigns (Content Rewards / Whop, Reach). The owner is [OWNER NAME]. Work in this order, test each
stage on real data before moving on, and stop to ask the owner only for things only a human can do: sign-ins,
passwords, ID verification, payout details, accepting terms, and spending money.

## 0. Accounts the owner creates (ask for these up front)
- One Google account for the brand ([BRAND EMAIL]); a YouTube channel created on THAT account (an account without a
  channel makes every upload fail with 401 "youtubeSignupRequired"); phone-verify it at youtube.com/verify or custom
  thumbnails fail with 403.
- Instagram professional account @[HANDLE], connected to Windsor.ai (posting) .
- TikTok @[HANDLE], logged in on the owner's Chrome.
- GitHub account; the agent creates a public repo [REPO] (public so video files have direct URLs for Instagram).
- Twitch developer app (client id + secret) for the Helix API.
- Whop / Content Rewards account (signed in on Chrome), socials connected under Whop → Settings → Connected
  Accounts, identity verified ("Verify as an individual"), payout method added (owner does all of this).
- Repurpose.io account (paid after a 10-video trial) for Instagram → TikTok, because no available API/connector
  can publish to TikTok publicly and browser file uploads are capped far below a Reel's size.

## 1. Clip engine (GitHub Actions, no AI keys needed)
- `streamers.json`: list of Twitch logins with `approved`, `cam` crop info, and optional `campaign` object.
- Fetch workflow: every 2 h AND on push of `state/fetch-request` (GitHub cron silently skips most runs on small
  repos, so the posting task must be able to trigger fetches itself). Pull GTA VI clips from approved streamers,
  English only, rank by views per hour, drop spoiler/ending/cutscene/exploit titles, render 1080x1920 vertical
  (facecam panel on top when a cam crop is known), 6 review frames + transcript per clip, write to `queue/`.
- Campaign clips sort to the front of the queue.
- Weekly: rank the top 10 English GTA VI streamers (60% 7-day clip views, 40% live viewers) and make them the only
  approved non-campaign streamers. Campaign streamers always stay approved.

## 2. Posting task (scheduled AI run, 6x a day)
For each run: refill the queue if < 3 candidates (push `state/fetch-request`, poll up to 15 min); read every
candidate's frames and transcript; SKIP anything below 7/10 action-or-funny, any blood/gore, spoilers, black or
frozen frames, slurs, and ANY sexual content including nude/topless NPCs in the background (titles like "wtf"
hide these; judge the frames). Write a max-6-word hook + caption with streamer credit and hashtags; campaign clips
must contain the campaign's required name and hashtag. Burn the hook, check the file, commit, post one Reel via
Windsor, record the media id. Posting nothing beats posting a weak clip.

## 3. YouTube
- Google Cloud project → enable YouTube Data API v3 → OAuth consent screen External, add homepage + privacy policy
  URLs (a PRIVACY.md in the repo works, authorized domain github.com) → **Publish app to production** (testing mode
  refresh tokens die after 7 days) → OAuth client "Web application" with redirect
  https://developers.google.com/oauthplayground → owner gets a refresh token in OAuth Playground with scopes
  youtube.upload + youtube → owner stores YT_CLIENT_ID / YT_CLIENT_SECRET / YT_REFRESH_TOKEN as repo secrets.
  (The agent must never type keys into forms; have the owner paste them.)
- Shorts: every posted Reel writes `shorts/<id>.json`; a push-triggered workflow uploads it. Quota is 10,000
  units/day and one upload costs 1,600, so cap Shorts at 5/day and keep one slot for the daily episode.
- Daily episode (16:9, 8-15 min): build at 06:00 local from the day's top clips (open on the best clip, second best
  last, one-line label + streamer handle on every clip, chapters, credits with links), NudeNet first-pass filter on
  8 frames per clip, over-collect 1.8x so drops still fill the length, 3 thumbnails (punch-in past overlays, 2-3
  huge yellow words, red arrow/circle on the motion). Store the mp4 as a GitHub release asset (too big for git).
- Daily review task (07:45): write labels, drop bad clips, rebuild, write 5 titles, then the **gauntlet rule**: a
  FRESH agent that never saw your notes gets only the frames, thumbnails, titles, a few outlier thumbnails and
  RULES.md, and answers yes/no with faults. Fix and re-check (max 3 rounds). Only "yes" writes `approved.json`,
  which triggers the upload workflow. Log every verdict in RULES.md. If the 06:00 build didn't run, trigger it.
- Weekly research: top 20 GTA creator channels by subscribers (yt-dlp metadata, no keys; exclude official/news
  channels and streamers' own channels), keep videos with 3x+ the channel median views (GTA titles only), save
  their thumbnails, study what repeats into THUMBNAILS.md, and set the episode length from winning compilations.

## 4. Campaigns (the money)
For every campaign the owner joins, add a `campaign` object to the streamer it covers:
`{id, name, mention, hashtag, rules, submit_at, min_total_views, ends}` (read the campaign's full rules page first;
typical rules: the streamer must be the main focus, caption must name them, a required hashtag, no logos, no
reposts, nothing negative about the creator, English audience, submit within 30 min of posting, pool campaigns
pay only after a minimum total of approved views).
- TikTok: Repurpose.io workflow Instagram Reels → TikTok with "Only publish videos containing" = every active
  campaign hashtag (non-campaign clips stay off TikTok).
- Submission task (runs ~20 min after each posting run, on the owner's computer through Chrome): for each new
  campaign post, get the Instagram permalink (Windsor `media_permalink`), the YouTube Short URL and the TikTok URL
  (from the TikTok profile, matched by caption), open the campaign's Content Rewards page, skip URLs already
  submitted, submit each once, log them in `campaigns/submissions.md`. If Whop needs a sign-in or account link,
  stop and tell the owner. Never touch payout or account settings.

## 5. Reporting
Every task ends with a 3-4 line report and a push notification: what posted, links, what was skipped and why,
anything the owner must do. Keep STATUS.md, RULES.md, LEARNING.md in the repo as the system's memory.

## Hard rules
Only the owner's own accounts. Credit every streamer. No sexual content, gore, slurs, spoilers, or misleading
thumbnails. Never bot or manipulate views. Never enter passwords, keys, ID or payment details. Ask before spending
money or accepting terms.
