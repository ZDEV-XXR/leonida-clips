# Daily episode review run (scheduled Claude task, ~7:45 am Tucson)

The 6:07 am `daily episode` workflow has already built today's cut: `episode/<date>/plan.json`, `frames/NN.jpg`
(one per clip, label visible), `thumb_A/B/C.jpg`, `description.txt`, video in the `ep-<date>` GitHub release.
Your job: labels, title, thumbnail, then **the gauntlet rule** - nothing posts until a fresh agent says yes.

1. `git pull`. Today = Tucson date. If `episode/<date>/plan.json` is missing, or `approved.json` already exists, stop and say why in STATUS.md.
2. **Labels.** Look at every frame and clip title. Write `episode/labels/<date>.json` = `{clip_id: "label"}`:
   one line, max 6 words, says what happens ("Kai crashes the police chopper"), no story spoilers, no slurs.
   Add `"_drop": [ids]` for clips that are cutscenes, endings, exploits/glitch tutorials, dead air, or a bad crop.
   Then commit `episode/requests/<date>-rN.json` = `{"date": "<date>", "relabel": true}` and push; that rebuilds
   the same clips with the new labels. Poll `git pull` every 2 min (max 40 min) until `plan.json` `built_at` changes.
3. **Title + thumbnail.** Read `research/THUMBNAILS.md`, `research/outliers.csv` (format=long) and `RULES.md`.
   Write 5 titles in the winning patterns (short, curiosity, a name if a big streamer is in it, under 60 chars).
   Re-letter any thumbnail if the text is weak: `python episode/thumbs.py redo <date> B "TEXT" [arrow|circle|none] [x y]`
   (2-3 big words, x/y = where the action is, 0-1).
4. **Gauntlet.** Spawn a FRESH agent (Agent tool, general-purpose) that has not seen your notes. Give it only:
   the frame paths, the 3 thumbnail paths, the 5 titles, 4 outlier thumbnails from `research/thumbs/` with their titles,
   and the rules in `RULES.md`. Ask it to: pick the best title and thumbnail, then answer **yes or no** for the
   episode with every fault it found (bad crop, label typo/wrong, spoiler, gore in a thumbnail, misleading
   thumbnail, repeat clip, weak opener, text unreadable on a phone). It must not see your reasoning.
5. **No** -> fix what it named (relabel/drop + rebuild, or redo the thumbnail, or new titles) and run a NEW fresh
   agent. Max 3 rounds; still no -> do not post, log it in STATUS.md.
   **Yes** -> write `episode/<date>/approved.json`:
   `{"verdict": "yes", "title": "...", "thumbnail": "episode/<date>/thumb_X.jpg", "faults_fixed": [...], "rounds": N}`
6. Append every verdict (yes or no, with faults) as one line to `RULES.md` under `## Verdicts`. When the same fault
   shows up 3+ times, add a plain rule for it under `## Rules`.
7. Commit + push. The push of `approved.json` triggers the `upload episode` workflow, which posts to YouTube and
   writes the link to `STATUS.md`. After ~15 min `git pull` and confirm the link is there; if the workflow failed,
   say so in STATUS.md.

## Mondays, before step 1
The `outlier research` workflow ran at 7:23 am. Study `research/thumbs/*.jpg` against `research/outliers.csv` and
rewrite `research/THUMBNAILS.md`: what repeats (text length, colours, faces vs cars, arrows/circles, framing),
what the winning titles have in common, and a `## Words` list of 5-10 thumbnail phrases. Summarise
`research/CHANGES.md` (what changed this week) at the top of STATUS.md.
