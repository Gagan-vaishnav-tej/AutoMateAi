import secrets, hashlib, base64, requests
from flask import Blueprint, session, redirect, request, url_for, current_app
from markupsafe import escape
import os

twitter_bp = Blueprint("twitter", __name__, url_prefix="/twitter")

TWITTER_AUTH_URL = "https://twitter.com/i/oauth2/authorize"
TWITTER_TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
TWITTER_SCOPES = "tweet.read tweet.write users.read offline.access"
TWITTER_CLIENT_ID = os.environ.get("TWITTER_CLIENT_ID")
TWITTER_CLIENT_SECRET = os.environ.get("TWITTER_CLIENT_SECRET")
TWITTER_REDIRECT_URI = os.environ.get("TWITTER_REDIRECT_URI", "http://127.0.0.1:5000/twitter/callback")

def generate_code_verifier():
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b'=').decode('utf-8')

def generate_code_challenge(verifier):
    digest = hashlib.sha256(verifier.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b'=').decode('utf-8')


@twitter_bp.route("/login")
def login():
        state = secrets.token_urlsafe(16)
        session["twitter_oauth_state"] = state

        code_verifier = generate_code_verifier()
        session["twitter_code_verifier"] = code_verifier

        code_challenge = generate_code_challenge(code_verifier)

        params = {
            "response_type": "code",
            "client_id": TWITTER_CLIENT_ID,
            "redirect_uri": TWITTER_REDIRECT_URI,
            "scope": TWITTER_SCOPES,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256"
        }
        url = f"{TWITTER_AUTH_URL}?{requests.compat.urlencode(params)}"
        print("Redirecting to Twitter authorize URL with state:", state)
        return redirect(url)


@twitter_bp.route("/callback")
def callback():
    expected = session.get("twitter_oauth_state")
    received = request.args.get("state")
    if received != expected:
        session.pop("twitter_oauth_state", None)
        session.pop("twitter_code_verifier", None)
        return redirect(url_for("twitter.login"))

    code = request.args.get("code")
    if not code:
        return "No code returned from Twitter", 400

    code_verifier = session.get("twitter_code_verifier")
    if not code_verifier:
        return "Missing code_verifier in session", 400

    # --- Add Basic Auth header ---
    auth_header = base64.b64encode(f"{TWITTER_CLIENT_ID}:{TWITTER_CLIENT_SECRET}".encode()).decode()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {auth_header}"
    }

    data = {
        "code": code,
        "grant_type": "authorization_code",
        "client_id": TWITTER_CLIENT_ID,
        "redirect_uri": TWITTER_REDIRECT_URI,
        "code_verifier": code_verifier
    }

    token_response = requests.post(TWITTER_TOKEN_URL, data=data, headers=headers)
    if token_response.status_code != 200:
        return f"Error fetching Twitter token: {escape(token_response.text)}", 400

    tokens = token_response.json()
    access_token = tokens.get("access_token")
    if not access_token:
        return f"Missing access_token in response: {escape(str(tokens))}", 400

    session["twitter_access_token"] = access_token
    session.pop("twitter_oauth_state", None)
    session.pop("twitter_code_verifier", None)

    return redirect(url_for("index"))

@twitter_bp.route("/logout")
def logout():
    session.pop("twitter_access_token", None)
    return redirect(url_for("index"))
