import requests
from flask import Blueprint, session, redirect, request, url_for, current_app
from markupsafe import escape
from db import save_token

linkedin_bp = Blueprint("linkedin", __name__, url_prefix="/linkedin")

LINKEDIN_AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
LINKEDIN_TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
LINKEDIN_SCOPES = "openid profile email w_member_social"


@linkedin_bp.route("/login")
def login():
    params = {
        "response_type": "code",
        "client_id": current_app.config["LINKEDIN_CLIENT_ID"],
        "redirect_uri": current_app.config["LINKEDIN_REDIRECT_URI"],
        "scope": LINKEDIN_SCOPES
    }
    url = f"{LINKEDIN_AUTH_URL}?{requests.compat.urlencode(params)}"
    return redirect(url)


@linkedin_bp.route("/callback")
def callback():
    error = request.args.get("error")
    if error:
        return f"LinkedIn OAuth Error: {escape(error)}"

    code = request.args.get("code")
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": current_app.config["LINKEDIN_REDIRECT_URI"],
        "client_id": current_app.config["LINKEDIN_CLIENT_ID"],
        "client_secret": current_app.config["LINKEDIN_CLIENT_SECRET"]
    }

    response = requests.post(LINKEDIN_TOKEN_URL, data=data)
    token_json = response.json()
    access_token = token_json.get("access_token")
    session["linkedin_access_token"] = access_token
    save_token("linkedin", access_token)
    return redirect(url_for("index"))


@linkedin_bp.route("/logout")
def logout():
    session.pop("linkedin_access_token", None)
    return redirect(url_for("index"))
