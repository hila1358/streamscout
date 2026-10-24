"""StreamScout - Shared helpers: config, token storage, and authenticated Twitch API calls."""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TOKENS_FILE = ROOT / ".twitch_tokens.json"
REDIRECT_URI = "http://localhost:3000"
SCOPES = ["moderator:read:followers", "channel:read:subscriptions", "bits:read"]


def load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        raise SystemExit("Missing .env - copy .env.example to .env and fill in your Twitch app's Client ID and Secret.")
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.strip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
    return os.environ["TWITCH_CLIENT_ID"], os.environ["TWITCH_CLIENT_SECRET"]


def post_form(url, params):
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=data, method="POST")) as resp:
        return json.load(resp)


def save_tokens(tokens):
    tokens["obtained_at"] = int(time.time())
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2))
    TOKENS_FILE.chmod(0o600)


def refresh_tokens():
    client_id, client_secret = load_env()
    tokens = json.loads(TOKENS_FILE.read_text())
    new = post_form("https://id.twitch.tv/oauth2/token", {
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": client_id,
        "client_secret": client_secret,
    })
    save_tokens(new)
    return new


def api_get(path, params=None, _retried=False):
    """GET a Helix endpoint, refreshing the access token once if it has expired."""
    client_id, _ = load_env()
    if not TOKENS_FILE.exists():
        raise SystemExit("Not connected yet - run: python3 twitch_auth.py")
    tokens = json.loads(TOKENS_FILE.read_text())
    url = "https://api.twitch.tv/helix/" + path
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + tokens["access_token"],
        "Client-Id": client_id,
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code == 401 and not _retried:
            refresh_tokens()
            return api_get(path, params, _retried=True)
        raise


def api_get_all(path, params, limit=2000):
    """Follow Helix cursor pagination until exhausted or `limit` items collected."""
    items, params = [], dict(params, first=100)
    while len(items) < limit:
        page = api_get(path, params)
        items.extend(page.get("data", []))
        cursor = page.get("pagination", {}).get("cursor")
        if not cursor or not page.get("data"):
            break
        params["after"] = cursor
    return items
