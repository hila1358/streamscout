---
name: stream-tonight
description: Recommend which game to stream tonight (and when to go live, with a title and tags) from StreamScout's Twitch market data. Use when the user asks "what should I stream tonight", "what to stream today", or similar.
---

# What should I stream tonight?

The user is a small English-language Twitch streamer who loves story-rich games they can talk about with chat (Return of the Obra Dinn now; previously Doki Doki Literature Club, Fran Bow, Little Misfortune). Explain things simply - they are not technical.

1. Get the freshest data: `git pull -q` in the repo root (the hourly GitHub job commits new snapshots).
2. Run `python3 report.py --tonight`. It ranks the watchlist games for the next 8 hours (Israel time) from past snapshots and shows who is live right now.
3. Answer in this shape, short:
   - **Stream:** one game, with the one-line reason in numbers (e.g. "only 2 streamers, small streams average 22 viewers").
   - **Go live at:** the best start hour from the report, in Israel time.
   - **Backup pick:** a second game and why.
   - **Title idea:** one catchy title for that game that invites chat to talk.
   - **Tags:** up to 10, preferring tags that performed well in `python3 report.py --days 7`'s tag table, plus game-relevant ones.
4. Be honest about thin data: if the report says there is little or no history for these hours, say the pick rests mostly on the live numbers and will get sharper as data builds up.
