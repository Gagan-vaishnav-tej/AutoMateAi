import os
import atexit
import logging
from dotenv import load_dotenv
load_dotenv()
from flask import Flask, jsonify, render_template
from flask_apscheduler import APScheduler

from db import init_db, clear_all_data
from twitter_auth import twitter_bp
from linkedin_auth import linkedin_bp
from ai_post import ai_bp

# --- Load environment ---


# --- Create Flask app ---
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev_secret")

# --- Scheduler setup ---
scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

# ✅ Always clear previous jobs at startup
scheduler.remove_all_jobs()
print("🧹 Cleared all scheduled jobs on startup.")

# ✅ Always clear DB posts & campaigns on startup
clear_all_data()
print("🗑️ Cleared all campaigns & scheduled_posts from DB.")

# --- Initialize fresh DB ---
init_db()

# --- Config ---
app.config.update({
    "TWITTER_CLIENT_ID": os.environ.get("TWITTER_CLIENT_ID"),
    "TWITTER_CLIENT_SECRET": os.environ.get("TWITTER_CLIENT_SECRET"),
    "TWITTER_REDIRECT_URI": os.environ.get("TWITTER_REDIRECT_URI"),
    "LINKEDIN_CLIENT_ID": os.environ.get("LINKEDIN_CLIENT_ID"),
    "LINKEDIN_CLIENT_SECRET": os.environ.get("LINKEDIN_CLIENT_SECRET"),
    "LINKEDIN_REDIRECT_URI": os.environ.get("LINKEDIN_REDIRECT_URI"),
    "GROQ_API_KEY": os.environ.get("GROQ_API_KEY"),
})

# --- Blueprints ---
app.register_blueprint(twitter_bp)
app.register_blueprint(linkedin_bp)
app.register_blueprint(ai_bp)

# --- Logging ---
logging.basicConfig(level=logging.INFO)
logging.getLogger("apscheduler").setLevel(logging.INFO)

# --- Graceful shutdown ---
atexit.register(lambda: scheduler.shutdown(wait=False))

# --- Helpers ---
def get_app_context():
    """Provides app context for scheduled jobs."""
    ctx = app.app_context()
    ctx.push()
    return ctx

app.scheduler = scheduler

# --- Routes ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/generatepost")
def ai_post_ui():
    return render_template("ai_post.html")

@app.route("/createcampaign")
def campaign_ui():
    return render_template("campaign.html")

@app.route("/singleday")
def singleday_ui():
    return render_template("singleday.html")

@app.route("/jobs")
def list_jobs():
    """List all active scheduled jobs"""
    jobs = [
        {"id": job.id, "next_run_time": str(job.next_run_time), "args": job.args}
        for job in app.scheduler.get_jobs()
    ]
    return jsonify(jobs)

@app.route("/jobs/cancel/<job_id>", methods=["DELETE"])
def cancel_job(job_id):
    """Cancel a scheduled campaign job"""
    try:
        app.scheduler.remove_job(job_id)
        return jsonify({"ok": True, "message": f"🗑️ Job {job_id} cancelled."})
    except Exception as e:
        return jsonify({"ok": False, "message": f"Failed to cancel: {str(e)}"}), 400


# --- Run ---
if __name__ == "__main__":
    app.run(debug=True)
