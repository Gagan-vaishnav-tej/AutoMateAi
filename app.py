from flask import Flask, render_template
from twitter_auth import twitter_bp
from linkedin_auth import linkedin_bp
from ai_post import ai_bp
import os

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_secret")

# Config
app.config["TWITTER_CLIENT_ID"] = os.environ.get("TWITTER_CLIENT_ID")
app.config["TWITTER_CLIENT_SECRET"] = os.environ.get("TWITTER_CLIENT_SECRET")
app.config["TWITTER_REDIRECT_URI"] = os.environ.get("TWITTER_REDIRECT_URI")

app.config["LINKEDIN_CLIENT_ID"] = os.environ.get("LINKEDIN_CLIENT_ID")
app.config["LINKEDIN_CLIENT_SECRET"] = os.environ.get("LINKEDIN_CLIENT_SECRET")
app.config["LINKEDIN_REDIRECT_URI"] = os.environ.get("LINKEDIN_REDIRECT_URI")

# Register Blueprints
app.register_blueprint(twitter_bp)
app.register_blueprint(linkedin_bp)
app.register_blueprint(ai_bp)
app.config["GROQ_API_KEY"] = os.environ.get("GROQ_API_KEY")

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
