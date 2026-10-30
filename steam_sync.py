"""StreamScout - Pull the Steam wishlist (and library, if public) and match each game to its Twitch category.

Writes steam_games.json, which market_scan.py adds to the hourly scan. Matching goes Steam app id -> IGDB -> Twitch,
so it doesn't depend on the two stores spelling names the same way.
Usage: python3 steam_sync.py
"""
import json
import re
import urllib.parse
import urllib.request

from twitch_common import ROOT, _app_token, app_get, load_env

config = json.loads((ROOT / "watchlist.json").read_text())
steam_id = config["steam_id"]


def get_json(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def wishlist():
    items = get_json(f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?steamid={steam_id}")
    return [i["appid"] for i in items["response"].get("items", [])]


def library():
    """Owned games with playtime; only works while the profile's 'Game details' privacy setting is Public."""
    url = f"https://steamcommunity.com/profiles/{steam_id}/games?tab=all&xml=1"
    with urllib.request.urlopen(url, timeout=30) as resp:
        xml = resp.read().decode("utf-8", "replace")
    if "<gamesList>" not in xml:
        return None
    hours = {}
    for block in re.findall(r"<game>(.*?)</game>", xml, re.S):
        appid = re.search(r"<appID>(\d+)</appID>", block)
        played = re.search(r"<hoursOnRecord>([\d,.]+)</hoursOnRecord>", block)
        if appid:
            hours[int(appid.group(1))] = float(played.group(1).replace(",", "")) if played else 0.0
    return hours


def store_info(appids):
    tag_names = {t["tagid"]: t["name"] for t in
                 get_json("https://api.steampowered.com/IStoreService/GetTagList/v1/?language=english")["response"]["tags"]}
    info = {}
    for i in range(0, len(appids), 100):
        query = {"ids": [{"appid": a} for a in appids[i:i + 100]],
                 "context": {"language": "english", "country_code": "US"},
                 "data_request": {"include_tag_count": 10, "include_release": True}}
        url = ("https://api.steampowered.com/IStoreBrowseService/GetItems/v1/?input_json="
               + urllib.parse.quote(json.dumps(query)))
        for it in get_json(url)["response"].get("store_items", []):
            if "name" in it:
                info[it["appid"]] = {"steam_name": it["name"],
                                     "steam_tags": [tag_names.get(t["tagid"]) for t in it.get("tags", [])],
                                     "coming_soon": bool(it.get("release", {}).get("is_coming_soon"))}
    return info


def igdb_ids(appids):
    client_id, _ = load_env()
    app_get("games/top", {"first": 1})  # makes sure the app token exists
    headers = {"Client-ID": client_id, "Authorization": "Bearer " + _app_token["access_token"]}
    found = {}
    for i in range(0, len(appids), 100):
        uids = ",".join(f'"{a}"' for a in appids[i:i + 100])
        body = f"fields game,uid; where external_game_source = 1 & uid = ({uids}); limit 500;"  # source 1 = Steam
        for row in get_json("https://api.igdb.com/v4/external_games", body.encode(), headers):
            found[int(row["uid"])] = row["game"]
    return found


def twitch_categories(igdb):
    by_igdb = {}
    ids = sorted(set(igdb.values()))
    for i in range(0, len(ids), 100):
        for g in app_get("games", {"igdb_id": ids[i:i + 100]})["data"]:
            by_igdb[int(g["igdb_id"])] = {"twitch_id": g["id"], "twitch_name": g["name"]}
    return by_igdb


wish = wishlist()
owned = library()
appids = sorted(set(wish) | set(owned or {}))
info = store_info(appids)
igdb = igdb_ids(appids)
twitch = twitch_categories(igdb)

games = []
for appid in appids:
    if appid not in info:
        continue
    games.append({"appid": appid, **info[appid], **twitch.get(igdb.get(appid), {"twitch_id": None, "twitch_name": None}),
                  "wishlist": appid in wish,
                  "hours_played": owned.get(appid) if owned else None})

(ROOT / "steam_games.json").write_text(json.dumps(
    {"steam_id": steam_id, "library_public": owned is not None, "games": games}, indent=1, ensure_ascii=False) + "\n")
matched = [g for g in games if g["twitch_id"]]
print(f"Steam: {len(wish)} wishlist games, " + (f"{len(owned)} owned" if owned is not None else "library is private")
      + f". Matched {len(matched)}/{len(games)} to Twitch categories -> steam_games.json")
unmatched = [g["steam_name"] for g in games if not g["twitch_id"]]
if unmatched:
    print("No Twitch category yet: " + ", ".join(unmatched))
