"""StreamScout - Pull the last N days of channel data from Twitch into data/<date>.json.

Usage: python3 fetch_month.py [days]   (default 30)
"""
import json
import sys
from datetime import datetime, timedelta, timezone

from twitch_common import ROOT, api_get, api_get_all

days = int(sys.argv[1]) if len(sys.argv) > 1 else 30
now = datetime.now(timezone.utc)
since = now - timedelta(days=days)
iso = lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")

user = api_get("users")["data"][0]
uid = user["id"]
print(f"Fetching {days} days of data for {user['display_name']}...")

vods = [v for v in api_get_all("videos", {"user_id": uid, "type": "archive"}, limit=300)
        if v["created_at"] >= iso(since)]
clips = api_get_all("clips", {"broadcaster_id": uid, "started_at": iso(since), "ended_at": iso(now)}, limit=1000)

game_ids = sorted({c["game_id"] for c in clips if c.get("game_id")})
games = {}
for i in range(0, len(game_ids), 100):
    for g in api_get("games", {"id": game_ids[i:i + 100]})["data"]:
        games[g["id"]] = g["name"]

followers_page = api_get("channels/followers", {"broadcaster_id": uid, "first": 100})
followers = api_get_all("channels/followers", {"broadcaster_id": uid}, limit=5000)
new_followers = [f for f in followers if f["followed_at"] >= iso(since)]

try:
    subs = api_get("subscriptions", {"broadcaster_id": uid, "first": 1})
    sub_summary = {"total": subs.get("total"), "points": subs.get("points")}
except Exception as e:  # non-affiliates can't read subs
    sub_summary = {"error": str(e)}

channel = api_get("channels", {"broadcaster_id": uid})["data"][0]

out = {
    "fetched_at": iso(now),
    "period": {"from": iso(since), "to": iso(now), "days": days},
    "user": {"id": uid, "login": user["login"], "display_name": user["display_name"],
             "broadcaster_type": user["broadcaster_type"]},
    "channel": {"current_title": channel["title"], "current_game": channel["game_name"], "tags": channel.get("tags")},
    "followers": {"total": followers_page.get("total"), "new_in_period": len(new_followers),
                  "new_follow_dates": [f["followed_at"] for f in new_followers]},
    "subscriptions": sub_summary,
    "vods": [{k: v[k] for k in ("id", "title", "created_at", "published_at", "duration", "view_count", "url")}
             for v in vods],
    "clips": [{"title": c["title"], "created_at": c["created_at"], "view_count": c["view_count"],
               "game": games.get(c.get("game_id"), c.get("game_id")), "duration": c["duration"],
               "vod_offset": c.get("vod_offset"), "video_id": c.get("video_id"), "url": c["url"],
               "creator": c["creator_name"]} for c in clips],
}

path = ROOT / "data" / f"{now:%Y-%m-%d}.json"
path.write_text(json.dumps(out, indent=2))
print(f"Saved {len(out['vods'])} streams, {len(out['clips'])} clips, "
      f"{out['followers']['new_in_period']} new followers -> {path}")
