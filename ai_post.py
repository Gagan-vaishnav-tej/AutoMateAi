from flask import Blueprint, jsonify, render_template, session, request, redirect, url_for, current_app
import requests
import time
import os
from markupsafe import escape
from groq import Groq

ai_bp = Blueprint("ai", __name__, url_prefix="/ai")

GROQ_API_URL = os.environ.get("GROQ_API_URL")

# ==============================
# 🔹 Conversation Memory Helpers
# ==============================
def get_conversation():
    """Return the current conversation history."""
    return session.get("ai_conversation", [])


def add_message(role, content):
    """Append a message to the ongoing conversation."""
    convo = get_conversation()
    convo.append({"role": role, "content": content})
    session["ai_conversation"] = convo


def clear_conversation():
    """Reset chat memory for a new post."""
    session.pop("ai_conversation", None)
    session.pop("ai_generated_text", None)
    session.pop("ai_topic", None)
    session.pop("ai_platform", None)


# ==============================
# 🔹 Groq Utility Functions
# ==============================
def refine_prompt_with_llm(topic: str) -> str:
    """Expand a topic into a refined and structured LinkedIn post prompt."""
    GROQ_API_KEY = current_app.config.get("GROQ_API_KEY")
    if not GROQ_API_KEY:
        return "ERROR: GROQ_API_KEY is not set."

    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"""
You are an expert LinkedIn content strategist and writing assistant. Your job is to generate professional,
insightful, and engaging LinkedIn posts for industry professionals.

Generate a post on the topic below following these very strict rules:

1. Keep the total character count under 2600 characters.
2. Use a clear, professional, and conversational tone (no emojis, no hashtags unless requested).
3. Structure the post as follows:
   - **A bold headline** summarizing the topic (use markdown bold like **this**)
   - 1–2 short paragraphs providing background or insights
   - 2–3 concise bullet points or numbered takeaways if relevant
   - End with a short engaging question or statement that invites discussion
4. Avoid filler language and repetition. Prioritize clarity, accuracy, and flow.
5. Use real-world examples, credible references, or statistics when appropriate.
6. The writing should sound like a thought-leadership post from a professional, not a marketer.

Topic: "{topic}"

Now write a complete LinkedIn post draft following the above rules.
"""

    chat_completion = client.chat.completions.create(
        messages=[{"role": "user", "content": prompt}],
        model="llama-3.1-8b-instant",
        temperature=0.7,
        max_tokens=400,
    )

    return chat_completion.choices[0].message.content.strip()



def generate_ai_content(topic: str) -> str:
    """Generate the first version of the post."""
    GROQ_API_KEY = current_app.config.get("GROQ_API_KEY")
    if not GROQ_API_KEY:
        return "ERROR: GROQ_API_KEY is not set."

    refined = refine_prompt_with_llm(topic)
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
    data = {
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": refined}],
        "temperature": 0.7,
        "max_tokens": 600,
    }

    resp = requests.post(GROQ_API_URL, headers=headers, json=data, timeout=30)
    result = resp.json()
    generated = result["choices"][0]["message"]["content"].strip()
    return generated

def refine_existing_post(original_text: str, feedback: str) -> str:
    """Refine an existing LinkedIn post based on user feedback, keeping the topic and context intact."""
    GROQ_API_KEY = current_app.config.get("GROQ_API_KEY")
    if not GROQ_API_KEY:
        return "ERROR: GROQ_API_KEY is not set."

    client = Groq(api_key=GROQ_API_KEY)

    prompt = f"""
You are an expert LinkedIn writing assistant helping a user improve an existing post.

Your goals:
- Apply the user's feedback to refine the original post.
- Keep the same topic, intent, and factual content — do NOT change the subject.
- Maintain a professional, natural, and conversational tone suitable for LinkedIn.
- Keep the structure simple and scannable:
  - **Headline**
  - 1–2 concise paragraphs
  - Optional 2–3 bullet points if appropriate
  - A short closing statement or engaging question.
- Keep the total length under 2800 characters (LinkedIn limit).
- Never summarize or rewrite on a completely new topic.
- Only output the improved post, no explanations or commentary.

Original Post:
\"\"\"{original_text}\"\"\"

User Feedback:
\"\"\"{feedback}\"\"\"

Revise the post to align with the feedback while keeping the same topic and flow.
"""

    response = client.chat.completions.create(
        messages=[
            {"role": "system", "content": "You are a professional LinkedIn writing assistant."},
            {"role": "user", "content": prompt}
        ],
        model="llama-3.1-8b-instant",
        temperature=0.6,
        max_tokens=450,
    )

    revised_post = response.choices[0].message.content.strip()

    # Ensure LinkedIn safe length
    if len(revised_post) > 2800:
        revised_post = revised_post[:2790].rsplit(" ", 1)[0] + "..."

    return revised_post



# ==============================
# 🔹 Main Post Route (UI)
# ==============================
@ai_bp.route("/post", methods=["GET", "POST"])
def ai_post():
    if request.method == "GET":
        clear_conversation()
        return render_template("ai_post.html")

    action = request.form.get("action")
    platform = request.form.get("platform")
    topic = request.form.get("topic")

    if action == "Generate Preview":
        if not topic or not platform:
            return "Topic and platform are required.", 400

        generated_text = generate_ai_content(topic)
        session["ai_generated_text"] = generated_text
        session["ai_topic"] = topic
        session["ai_platform"] = platform
        add_message("assistant", generated_text)

        return jsonify({"preview": generated_text})

    elif action == "New Chat":
        clear_conversation()
        return jsonify({"status": "reset", "message": "🆕 New chat started."})

    elif action == "Post Now":
        return post_confirmed()

    return "Invalid action.", 400


# ==============================
# 🔹 Voice / Chat Interaction
# ==============================
@ai_bp.route("/api/voice_intent", methods=["POST"])
def voice_intent():
    data = request.get_json()
    user_input = data.get("input", "").strip()

    if not user_input:
        return jsonify({"error": "No input received"}), 400

    add_message("user", user_input)
    prev_text = session.get("ai_generated_text")

    # 🧠 First input → generate a new post
    if not prev_text:
        generated_text = generate_ai_content(user_input)
        session["ai_topic"] = user_input
        session["ai_generated_text"] = generated_text
        add_message("assistant", generated_text)

        return jsonify({
            "preview": generated_text,
            "message": "🧠 Generated initial post."
        })

    # 🔁 Feedback given → regenerate based on user feedback
    refined_text = refine_existing_post(prev_text, user_input)
    session["ai_generated_text"] = refined_text
    add_message("assistant", refined_text)

    return jsonify({
        "preview": refined_text,
        "message": "🔄 Regenerated content based on your feedback."
    })


# ==============================
# 🔹 Confirm + Publish Post
# ==============================
@ai_bp.route("/api/post_confirmed", methods=["POST"])
def post_confirmed():
    data = request.get_json(silent=True) or {}
    platform = data.get("platform") or session.get("ai_platform")
    generated_text = data.get("text") or session.get("ai_generated_text")
    generated_text = session.get("ai_generated_text")  # or from request body
    if len(generated_text) > 3000:
        generated_text = generated_text[:2997].rsplit(" ", 1)[0] + "..."
    generated_text = convert_markdown_bold_to_unicode(generated_text)

    if not platform or not generated_text:
        return jsonify({"error": "No content available to post."}), 400

    try:
        # --- LinkedIn ---
        if platform == "linkedin":
            access_token = session.get("linkedin_access_token")
            if not access_token:
                return jsonify({"error": "Not authenticated with LinkedIn"}), 401

            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
            user_info = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers)
            if user_info.status_code != 200:
                return jsonify({"error": "Failed to fetch LinkedIn user info"}), 400

            author = f"urn:li:person:{user_info.json()['sub']}"
            post_data = {
                "author": author,
                "lifecycleState": "PUBLISHED",
                "specificContent": {
                    "com.linkedin.ugc.ShareContent": {
                        "shareCommentary": {"text": generated_text},
                        "shareMediaCategory": "NONE",
                    }
                },
                "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
            }

            resp = requests.post("https://api.linkedin.com/v2/ugcPosts", headers=headers, json=post_data)
            if resp.status_code == 201:
                clear_conversation()
                return jsonify({"status": "success", "message": "✅ LinkedIn post shared successfully!"})
            else:
                return jsonify({"error": f"LinkedIn error: {resp.text}"}), 400

        # --- Twitter ---
        elif platform == "twitter":
            access_token = session.get("twitter_access_token")
            if not access_token:
                return jsonify({"error": "Not authenticated with Twitter"}), 401

            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
            chunks = [generated_text[i:i + 280] for i in range(0, len(generated_text), 280)]
            prev_id = None
            for chunk in chunks:
                time.sleep(1)
                payload = {"text": chunk}
                if prev_id:
                    payload["reply"] = {"in_reply_to_tweet_id": prev_id}
                resp = requests.post("https://api.twitter.com/2/tweets", headers=headers, json=payload)
                if resp.status_code == 201:
                    prev_id = resp.json()["data"]["id"]
                else:
                    return jsonify({"error": f"Twitter error: {resp.text}"}), 400

            clear_conversation()
            return jsonify({"status": "success", "message": f"✅ Posted {len(chunks)} tweets successfully!"})

        else:
            return jsonify({"error": f"Unsupported platform: {platform}"}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500

# helper functions (paste into ai_post.py or utils)
def to_unicode_bold(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch)
        if 0x41 <= code <= 0x5A:
            out.append(chr(0x1D400 + (code - 0x41)))
        elif 0x61 <= code <= 0x7A:
            out.append(chr(0x1D41A + (code - 0x61)))
        elif 0x30 <= code <= 0x39:
            out.append(chr(0x1D7CE + (code - 0x30)))
        else:
            out.append(ch)
    return "".join(out)

def bold_first_line(post_text: str) -> str:
    lines = post_text.splitlines()
    for i, line in enumerate(lines):
        if line.strip():
            lines[i] = to_unicode_bold(line.strip())
            break
    return "\n".join(lines)

import re

def convert_markdown_bold_to_unicode(text: str) -> str:
    """Replace all **bold** Markdown parts with Unicode bold."""
    def repl(match):
        inner = match.group(1).strip()
        return to_unicode_bold(inner)
    return re.sub(r"\*\*(.*?)\*\*", repl, text)






