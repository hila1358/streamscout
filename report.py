"""StreamScout - Turn the hourly market snapshots into a readable Markdown report.

Usage:
  python3 report.py              weekly report (last 7 days)
  python3 report.py --days 30    monthly report
  python3 report.py --tonight    which watchlist game to stream in the next few hours
"""
import argparse
import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from twitch_common import ROOT

parser = argparse.ArgumentParser()
parser.add_argument("--days", type=int, default=7)
parser.add_argument("--tonight", action="store_true")
parser.add_argument("--window", type=int, default=8, help="hours ahead to consider with --tonight")
args = parser.parse_args()

config = json.loads((ROOT / "watchlist.json").read_text())
tz = ZoneInfo(config.get("timezone", "UTC"))
now = datetime.now(timezone.utc)
since = now - timedelta(days=28 if args.tonight else args.days)  # tonight uses all recent history for its averages


def load_snapshots():
    snaps = []
    for path in sorted((ROOT / "data" / "market").glob("*.jsonl")):
        for line in path.read_text().splitlines():
            s = json.loads(line)
            at = datetime.strptime(s["at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            if at >= since:
                s["local"] = at.astimezone(tz)
                snaps.append(s)
    return snaps


def game_stats(snaps):
    """Per watchlist game: how often it is live, competition, and what small streams get."""
    acc = defaultdict(lambda: defaultdict(float))
    for s in snaps:
        for name, g in s["watchlist"].items():
            a = acc[name]
            a["hours"] += 1
            a["live_hours"] += g["channels"] > 0
            a["channels"] += g["channels"]
            a["viewers"] += g["viewers"]
            a["small_channels"] += g["small_channels"]
            a["small_viewers"] += g["small_channels"] * g["small_avg_viewers"]
            a["above_at_5"] += g["channels_with_at_least"]["5"]
    rows = []
    for name, a in acc.items():
        h = a["hours"]
        rows.append({
            "game": name,
            "live_pct": round(100 * a["live_hours"] / h),
            "avg_streamers": round(a["channels"] / h, 1),
            "avg_viewers": round(a["viewers"] / h),
            "small_avg": round(a["small_viewers"] / a["small_channels"], 1) if a["small_channels"] else 0,
            "rank_at_5": round(a["above_at_5"] / h + 1, 1),
        })
    return sorted(rows, key=lambda r: (-r["small_avg"], -r["avg_viewers"]))


def slot_stats(snaps, games=None):
    """Small-stream viewers per small channel, grouped by local (weekday, hour)."""
    acc = defaultdict(lambda: [0.0, 0, 0, 0])  # small viewers, small channels, all viewers, all channels
    for s in snaps:
        key = (s["local"].strftime("%a"), s["local"].hour)
        for name, g in s["watchlist"].items():
            if games and name not in games:
                continue
            a = acc[key]
            a[0] += g["small_channels"] * g["small_avg_viewers"]
            a[1] += g["small_channels"]
            a[2] += g["viewers"]
            a[3] += g["channels"]
    return {k: {"small_avg": round(v[0] / v[1], 1) if v[1] else 0, "viewers": v[2], "streamers": v[3]}
            for k, v in acc.items()}


def tag_stats(snaps, min_n=5):
    acc = defaultdict(lambda: [0, 0.0])
    for s in snaps:
        for g in s["watchlist"].values():
            for tag, t in g.get("small_stream_tags", {}).items():
                acc[tag][0] += t["n"]
                acc[tag][1] += t["n"] * t["avg_viewers"]
    rows = [{"tag": t, "uses": n, "avg_viewers": round(v / n, 1)} for t, (n, v) in acc.items() if n >= min_n]
    return sorted(rows, key=lambda r: -r["avg_viewers"])


def table(rows, cols):
    out = ["| " + " | ".join(c for c, _ in cols) + " |", "|" + "---|" * len(cols)]
    out += ["| " + " | ".join(str(r[k]) for _, k in cols) + " |" for r in rows]
    return "\n".join(out)


snaps = load_snapshots()
if not snaps:
    raise SystemExit("No market snapshots in this period yet - market_scan.py needs to run first.")
first, last = snaps[0]["local"], snaps[-1]["local"]
GAME_COLS = [("Game", "game"), ("Avg viewers per small stream", "small_avg"), ("Avg streamers", "avg_streamers"),
             ("Avg total viewers", "avg_viewers"), ("% of hours live", "live_pct"), ("Your rank at 5 viewers", "rank_at_5")]

if args.tonight:
    local_now = now.astimezone(tz)
    hours = [(local_now + timedelta(hours=i)).hour for i in range(args.window)]
    window = [s for s in snaps if s["local"].hour in hours]
    same_day = [s for s in window if s["local"].strftime("%a") == local_now.strftime("%a")]
    print(f"# What to stream tonight - {local_now:%a %d %b, %H:%M} ({tz.key})\n")
    print(f"Based on {len(window)} hourly snapshots covering {hours[0]:02d}:00-{hours[-1]:02d}:59 "
          f"({len(same_day)} of them on a {local_now:%A}), from {first:%d %b} to {last:%d %b}.\n")
    print("## Games ranked for this time window\n")
    rows = [r for r in game_stats(window) if r["live_pct"] > 0 or r["game"] in config.get("current", [])]
    print(table(rows, GAME_COLS) if rows else "No history for these hours yet - only the live numbers below are available.")
    latest = snaps[-1]
    print(f"\n## Right now (snapshot {latest['local']:%H:%M})\n")
    for name, g in sorted(latest["watchlist"].items(), key=lambda kv: -kv[1]["viewers"]):
        if g["channels"]:
            print(f"- {name}: {g['channels']} streaming, {g['viewers']} watching")
    print("\n## Best start hour in the window (all watchlist games)\n")
    slots = slot_stats(window)
    by_hour = defaultdict(list)
    for (_, h), v in slots.items():
        by_hour[h].append(v["small_avg"])
    for h in hours:
        if by_hour[h]:
            print(f"- {h:02d}:00 - small streams averaged {sum(by_hour[h]) / len(by_hour[h]):.1f} viewers")
    raise SystemExit

print(f"# StreamScout report - {first:%d %b} to {last:%d %b %Y}\n")
print(f"{len(snaps)} hourly snapshots of English Twitch streams (expected ~{24 * args.days}). "
      f"Times are {tz.key}.\n")
print("**How to read this:** \"Avg viewers per small stream\" is what channels with 50 or fewer viewers got on average - "
      "the best guide to what you could get. \"Your rank at 5 viewers\" is where a 5-viewer stream would sit in that "
      "game's directory (1 = top of the page).\n")
print("## Watchlist games\n")
rows = game_stats(snaps)
print(table([r for r in rows if r["live_pct"]], GAME_COLS))
idle = [r["game"] for r in rows if not r["live_pct"]]
if idle:
    print("\nNobody streamed these in English during this period (empty directory - first-mover chance if the game "
          "has an audience): " + ", ".join(idle) + ".")

print("\n## Best times to go live (all watchlist games together)\n")
slots = slot_stats(snaps)
best = sorted(slots.items(), key=lambda kv: (-kv[1]["small_avg"], kv[1]["streamers"]))[:10]
print(table([{"slot": f"{d} {h:02d}:00", **v} for (d, h), v in best],
            [("Day & hour", "slot"), ("Avg viewers per small stream", "small_avg"),
             ("Watchlist viewers", "viewers"), ("Watchlist streamers", "streamers")]))

print("\n## Tags on small streams\n")
tags = tag_stats(snaps)
if tags:
    print("Tags used at least 5 times on small streams in watchlist games, best-performing first:\n")
    print(table(tags[:15], [("Tag", "tag"), ("Times seen", "uses"), ("Avg viewers", "avg_viewers")]))
else:
    print("Not enough tag data yet.")

print("\n## Movers in Twitch's top 30\n")
half = len(snaps) // 2
early = {n for s in snaps[:max(half, 1)] for n in s["top_order"]}
late = {n for s in snaps[half:] for n in s["top_order"]}
new = sorted(late - early)
print("Entered the top 30 in the second half of the period: " + (", ".join(new) if new else "none") + ".")
