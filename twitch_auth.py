"""StreamScout - One-time login: opens Twitch in your browser and saves an access token locally."""
import secrets
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from twitch_common import REDIRECT_URI, SCOPES, api_get, load_env, post_form, save_tokens

client_id, client_secret = load_env()
state = secrets.token_urlsafe(16)
result = {}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if query.get("state", [None])[0] != state:
            self.send_response(400); self.end_headers()
            self.wfile.write(b"State mismatch - please try again.")
            return
        result["code"] = query.get("code", [None])[0]
        result["error"] = query.get("error_description", [None])[0]
        self.send_response(200); self.end_headers()
        self.wfile.write(b"<h2>StreamScout connected! You can close this tab and go back to the terminal.</h2>")

    def log_message(self, *args):
        pass


auth_url = "https://id.twitch.tv/oauth2/authorize?" + urllib.parse.urlencode({
    "response_type": "code",
    "client_id": client_id,
    "redirect_uri": REDIRECT_URI,
    "scope": " ".join(SCOPES),
    "state": state,
})
print("Opening Twitch login in your browser...\nIf it doesn't open, visit:\n" + auth_url)
webbrowser.open(auth_url)

server = HTTPServer(("localhost", 3000), Handler)
while "code" not in result:
    server.handle_request()

if not result["code"]:
    raise SystemExit("Login failed: " + str(result["error"]))

save_tokens(post_form("https://id.twitch.tv/oauth2/token", {
    "client_id": client_id,
    "client_secret": client_secret,
    "code": result["code"],
    "grant_type": "authorization_code",
    "redirect_uri": REDIRECT_URI,
}))
user = api_get("users")["data"][0]
print(f"Connected as {user['display_name']} (id {user['id']}). Token saved to .twitch_tokens.json")
