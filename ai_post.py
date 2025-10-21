from datetime import datetime, timedelta
import logging
import re
from flask import Blueprint, request, jsonify, current_app
from ai_agent import AIPostAgent
from memory import Memory
import tools
from flask import current_app
from db import save_campaign, save_scheduled_post, get_token, mark_post_done

ai_bp = Blueprint("ai", __name__, url_prefix="/ai")
agent = AIPostAgent()

# Shared in-memory memory & agent instance (simple for now)
memory = Memory(maxlen=100)

@ai_bp.route("/api/voice_intent", methods=["POST"])
def voice_intent():
    data = request.get_json()
    user_input = data.get("input")
    platform = data.get("platform", "linkedin")

    if not user_input:
        return jsonify({"ok": False, "error": "No input provided"}), 400

    result = agent.handle_user_input(user_input, platform)
    return jsonify(result)


@ai_bp.route("/api/post_confirmed", methods=["POST"])
def post_confirmed():
    """
    Body: { platform, text }
    """
    try:
        data = request.get_json() or {}
        platform = data.get("platform")
        text = data.get("text")
        if not platform or not text:
            return jsonify({"ok": False, "message": "platform and text are required"}), 400

        # choose tool
        if platform == "linkedin":
            access_token = get_token("linkedin")
            res = tools.post_to_linkedin(text,access_token)
        elif platform in ("twitter", "x"):
            access_token = get_token("twitter")
            res = tools.post_to_twitter(text,access_token)
        else:
            return jsonify({"ok": False, "message": "Unknown platform"}), 400

        agent.reflect(res)
        return jsonify(res)
    except Exception as e:
        current_app.logger.exception("post_confirmed error")
        return jsonify({"ok": False, "message": "Internal error", "error": str(e)}), 500

@ai_bp.route("/post", methods=["POST"])
def post_action():
    """
    Support the 'New Chat' button that your frontend calls via /ai/post
    Expects form body like { action: "New Chat" }
    """
    try:
        action = request.form.get("action")
        if action and action.lower().strip() == "new chat":
            # clear memory for simplicity
            memory.history.clear()
            memory.last_preview = None
            return jsonify({"ok": True, "message": "🆕 New chat started."})
        return jsonify({"ok": False, "message": "Unknown action"}), 400
    except Exception as e:
        current_app.logger.exception("post_action error")
        return jsonify({"ok": False, "message": "Internal error", "error": str(e)}), 500



def split_plan_into_days(plan_text: str):
    """
    Splits a multi-day AI-generated plan into individual daily posts.
    Expects text like 'Day 1: ...', 'Day 2: ...'
    Returns: [{"title": "Day 1: ...", "content": "..."}]
    """
    # plan_text = re.sub(r"(?:\*{0,2}|#*\s*)?(?:𝐃𝐚𝐲|Day|DAY)\s*[\d𝟎-𝟗]+\s*[:\-–]\s*", "", plan_text, flags=re.IGNORECASE)

    pattern = r"(?=(?:\bDay|𝐃𝐚𝐲)\s*\d+\s*[:：])"
    parts = re.split(pattern, plan_text, flags=re.IGNORECASE)
    daily_posts = []

    for part in parts:
        clean = part.strip()
        if not clean:
            continue

        # Extract title (e.g., "Day 1: Something")
        lines = clean.splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()

        daily_posts.append({
            "title": title,
            "content": body or title  # fallback if body is empty
        })

    return daily_posts


@ai_bp.route("/campaign/start", methods=["POST"])
def start_campaign():
    try:
        data = request.get_json()
        topic = data.get("topic")
        days = int(data.get("days", 7))
        hour = int(data.get("hour", 9))
        minute = int(data.get("minute", 0))

        if not topic:
            return jsonify({"ok": False, "error": "Topic is required"}), 400

        # STEP 1: Ask AI for a multi-day content plan
        ai_agent = AIPostAgent()
        # plan_prompt = f"Create a {days}-day LinkedIn post campaign plan about '{topic}', with each day labeled 'Day 1:', 'Day 2:' etc., and a brief title/summary for each."
        
        if int(days) == 1:
            plan_prompt = (
                f"Create ONE standalone LinkedIn post about '{topic}'. "
                f"Write it as a single post (not a campaign). "
                f"Include a short, bold Unicode-style heading and a concise, professional paragraph."
            )
        else:
            plan_prompt = (
                f"Create a {days}-day LinkedIn post campaign plan about '{topic}'. "
                f"Each day should be clearly labeled as 'Day 1:', 'Day 2:', etc. "
                f"Give each day a bold Unicode-style title (e.g., 𝐃𝐚𝐲 𝟏: 𝐈𝐧𝐭𝐫𝐨𝐝𝐮𝐜𝐭𝐢𝐨𝐧 𝐭𝐨 ...). "
                f"Include 1–2 engaging sentences describing the focus for that day."
            )
        
        resp = ai_agent.handle_user_input(plan_prompt, "linkedin")
        generated_plan = resp.get("text") or resp.get("preview", "")

        if not generated_plan:
            return jsonify({"ok": False, "error": "AI plan generation failed"}), 500

        daily_posts = split_plan_into_days(generated_plan)
        campaign_id = save_campaign(topic, days, hour, minute)

        start_time = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        scheduler = current_app.scheduler

        for i, post in enumerate(daily_posts):
            run_time = start_time + timedelta(days=i)
            job_id = f"campaign_{campaign_id}_{i+1}"

            # Store only subtopic title — full post will be generated later
            scheduler.add_job(
                func=execute_scheduled_post,
                trigger="date",
                run_date=run_time,
                args=[post["title"], f"{campaign_id}_{i+1}"],
                id=job_id,
            )
            save_scheduled_post(campaign_id, post["title"], run_time.isoformat())

        return jsonify({
            "ok": True,
            "message": f"📅 Campaign scheduled with {len(daily_posts)} posts."
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500



def execute_scheduled_post(topic_variant, post_id=None):
    """
    This runs automatically each day at the scheduled time.
    Generates AI content and posts to LinkedIn, then marks the post done.
    """

    from tools import post_to_linkedin
    from datetime import datetime
    from app import get_app_context  # ✅ import the helper

    logging.info(f"🚀 Executing scheduled post: {topic_variant[:80]}... (Post ID: {post_id})")

    try:
        # ✅ Manually create and push an app context
        ctx = get_app_context()

        access_token = get_token("linkedin")
        if not access_token:
            logging.warning("⚠️ LinkedIn not authenticated. Skipping scheduled post.")
            return

        # Generate post text
        ai_agent = AIPostAgent()
        generated_post = ai_agent.handle_user_input(topic_variant, "linkedin")

        text = generated_post.get("text") or generated_post.get("preview", "")
        if not text.strip():
            logging.warning(f"⚠️ No text generated for {topic_variant}")
            return

        # Post to LinkedIn
        res = post_to_linkedin(text, access_token)
        logging.info(f"[{datetime.now()}] 📤 LinkedIn response: {res}")

        if isinstance(res, dict) and res.get("ok"):
            logging.info(f"✅ Auto-post successful for topic: {topic_variant}")
            if post_id:
                mark_post_done(post_id)
                logging.info(f"🗂️ Post {post_id} marked as done in DB.")
        else:
            logging.warning(f"⚠️ Post may have failed. Response: {res}")

    except Exception as e:
        logging.exception(f"💥 Error while executing scheduled post for topic '{topic_variant}': {e}")
    finally:
        if 'ctx' in locals():
            ctx.pop()  # ✅ pop the context cleanly

def split_posts_into_list(plan_text: str):
    """
    Splits a single-day multi-post AI-generated plan into individual posts.
    Expects text like 'Post 1: ...', 'Post 2: ...'
    Returns: [{"title": "Post 1: ...", "content": "..."}]
    """
    import re

    # Match Post 1:, 𝐏𝐨𝐬𝐭 𝟐:, etc.
    pattern = r"(?=(?:\bPost|𝐏𝐨𝐬𝐭)\s*\d+\s*[:：])"
    parts = re.split(pattern, plan_text, flags=re.IGNORECASE)
    posts = []

    for part in parts:
        clean = part.strip()
        if not clean:
            continue

        # Separate first line as title
        lines = clean.splitlines()
        title = lines[0].strip()
        body = "\n".join(lines[1:]).strip()

        posts.append({
            "title": title,
            "content": body or title
        })

    return posts


@ai_bp.route("/campaign/start_single_day", methods=["POST"])
def start_single_day_campaign():
    """
    Start a single-day LinkedIn campaign.
    The user specifies number of posts and their timestamps (hour/minute for each post).
    Example input:
    {
        "topic": "AI in Marketing",
        "posts": 3,
        "schedule": [
            {"hour": 9, "minute": 0},
            {"hour": 13, "minute": 30},
            {"hour": 17, "minute": 0}
        ]
    }
    """
    try:
        data = request.get_json() or {}
        topic = data.get("topic")
        num_posts = int(data.get("posts", 1))
        schedule_list = data.get("schedule", [])

        if not topic:
            return jsonify({"ok": False, "message": "Topic is required"}), 400

        if not schedule_list or len(schedule_list) != num_posts:
            return jsonify({
                "ok": False,
                "message": "Schedule list must match the number of posts (each with hour & minute)."
            }), 400

        # === STEP 1: Generate multiple post ideas for the same day ===
        # === STEP 1: Generate post subtopics for the day ===
        ai_agent = AIPostAgent()
        plan_prompt = (
            f"Create {num_posts} LinkedIn post ideas for a single-day campaign on '{topic}'. "
            "Each idea should be short and labeled as 'Post 1:', 'Post 2:', etc. "
            "Use bold Unicode-style titles for each (e.g., 𝐏𝐨𝐬𝐭 𝟏: 𝐀𝐈 𝐢𝐧 𝐌𝐚𝐫𝐤𝐞𝐭𝐢𝐧𝐠 𝐓𝐨𝐝𝐚𝐲). "
            "Do NOT write the full post content — just concise subtopic titles."
        )
        resp = ai_agent.handle_user_input(plan_prompt, "linkedin")
        generated_plan = resp.get("text") or resp.get("preview", "")

        if not generated_plan:
            return jsonify({"ok": False, "error": "AI plan generation failed"}), 500

        # Parse post subtopics
        daily_posts = split_posts_into_list(generated_plan)

        # === STEP 2: Save metadata ===
        campaign_id = save_campaign(topic, num_posts, None, None)

        # === STEP 3: Schedule post generation & posting ===
        now = datetime.now()
        scheduler = current_app.scheduler

        for i, post in enumerate(daily_posts):
            hour = schedule_list[i]["hour"]
            minute = schedule_list[i]["minute"]

            run_time = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if run_time < now:
                run_time += timedelta(days=1)

            job_id = f"single_day_{campaign_id}_{i+1}"

            print(f"🕒 Scheduling {job_id} for {run_time}")

            scheduler.add_job(
                func=execute_scheduled_post,
                trigger="date",
                run_date=run_time,
                args=[post["title"], f"{campaign_id}_{i+1}"],
                id=job_id,
                replace_existing=True,
            )

            current_app.logger.info(f"🕒 Scheduled single-day post {i+1}/{num_posts} at {run_time}")

        return jsonify({
            "ok": True,
            "message": f"📅 Single-day campaign scheduled with {num_posts} posts.",
            "posts": num_posts,
            "mode": "single-day",
            "schedule": schedule_list
        })


    except Exception as e:
        current_app.logger.exception("start_single_day_campaign error")
        return jsonify({
            "ok": False,
            "message": "Internal error",
            "error": str(e)
        }), 500


