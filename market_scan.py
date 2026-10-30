"""StreamScout - Hourly snapshot of the Twitch market for the watchlist games plus the current top games.

Appends one line per run to data/market/<YYYY-MM-DD>.jsonl. Needs only the app's Client ID/Secret (no login).
Usage: python3 market_scan.py
"""
import json
import statistics
from collections import defaultdict
from datetime import datetime, timezone

from twitch_common import ROOT, api_get_all, app_get

WATCH_STREAM_LIMIT = 1000  # streams come sorted by viewers, so a cap only drops the smallest channels
TOP_STREAM_LIMIT = 300
SMALL = 50  # a "small" stream for opportunity stats: at most this many viewers

config = json.loads((ROOT / "watchlist.json").read_text())
lang = config.get("language", "en")
now = datetime.now(timezone.utc)


def resolve_watchlist(names):
    games = {}
    for i in range(0, len(names), 100):
        found = app_get("games", {"name": names[i:i + 100]})["data"]
        games.update({g["id"]: g["name"] for g in found})
    found_names = {n.lower() for n in games.values()}
    missing = [n for n in names if n.lower() not in found_names]
    return games, missing


def summarize(streams, limit, with_tags):
    viewers = sorted((s["viewer_count"] for s in streams), reverse=True)
    total = sum(viewers)
    small = [v for v in viewers if v <= SMALL]
    out = {
        "channels": len(viewers),
        "viewers": total,
        "truncated": len(viewers) >= limit,
        "viewers_per_channel": round(total / len(viewers), 1) if viewers else 0,
        "top1_share": round(viewers[0] / total, 3) if total else 0,
        "median": statistics.median(viewers) if viewers else 0,
        "small_channels": len(small),
        "small_avg_viewers": round(sum(small) / len(small), 2) if small else 0,
        # where a stream with N viewers would rank in the category directory
        "channels_with_at_least": {n: sum(v >= n for v in viewers) for n in (3, 5, 10, 25, 100)},
    }
    if with_tags:
        tag_views = defaultdict(list)
        for s in streams:
            if s["viewer_count"] <= SMALL:
                for t in s.get("tags") or []:
                    tag_views[t.lower()].append(s["viewer_count"])
        top = sorted(tag_views.items(), key=lambda kv: -len(kv[1]))[:20]
        out["small_stream_tags"] = {t: {"n": len(v), "avg_viewers": round(sum(v) / len(v), 2)} for t, v in top}
    return out


watch, missing = resolve_watchlist(config["games"])
steam_file = ROOT / "steam_games.json"
if steam_file.exists():  # games from the Steam wishlist/library, matched by steam_sync.py
    watch.update({g["twitch_id"]: g["twitch_name"] for g in json.loads(steam_file.read_text())["games"] if g["twitch_id"]})
top = {g["id"]: g["name"] for g in api_get_all("games/top", {}, limit=config.get("top_games_to_scan", 30), get=app_get)}

snapshot = {"at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "weekday": now.strftime("%a"), "hour_utc": now.hour,
            "language": lang, "watchlist": {}, "top": {}, "top_order": list(top.values())}
for gid, name in watch.items():
    streams = api_get_all("streams", {"game_id": gid, "language": lang}, limit=WATCH_STREAM_LIMIT, get=app_get)
    snapshot["watchlist"][name] = summarize(streams, WATCH_STREAM_LIMIT, with_tags=True)
for gid, name in top.items():
    if gid in watch:
        continue
    streams = api_get_all("streams", {"game_id": gid, "language": lang}, limit=TOP_STREAM_LIMIT, get=app_get)
    snapshot["top"][name] = summarize(streams, TOP_STREAM_LIMIT, with_tags=False)

out_dir = ROOT / "data" / "market"
out_dir.mkdir(parents=True, exist_ok=True)
path = out_dir / f"{now:%Y-%m-%d}.jsonl"
with path.open("a") as f:
    f.write(json.dumps(snapshot, separators=(",", ":"), ensure_ascii=False) + "\n")

live = sorted(snapshot["watchlist"].items(), key=lambda kv: -kv[1]["viewers"])
print(f"Snapshot {snapshot['at']} -> {path}")
for name, s in live:
    print(f"  {name:35} {s['channels']:4} live  {s['viewers']:6} viewers  small-stream avg {s['small_avg_viewers']}")
if missing:
    print("Not found on Twitch (check spelling in watchlist.json): " + ", ".join(missing))
