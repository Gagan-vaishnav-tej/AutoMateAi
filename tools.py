import os
from venv import logger
from groq import Groq
import logging
import json
import time

import requests

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("❌ GROQ_API_KEY not found. Make sure it's set in your .env file.")

client = Groq(api_key=GROQ_API_KEY)

def generate_post(prompt, platform="linkedin", context=None):
    """
    Generate a social media post using Groq API.
    Includes optional 'context' for conversational memory.
    """
    try:
        # Build conversation context for the AI
        messages = []
        if context:
            messages.append({"role": "system", "content": f"Context so far: {context}"})

        messages.append({
            "role": "user",
            "content": f"Write a professional {platform} post about: {prompt}. "
                       f"Make it engaging, clear, and platform-appropriate."
        })

        # Call Groq API
        start_time = time.time()
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            temperature=0.7,
            max_tokens=400,
        )
        duration = time.time() - start_time

        text = response.choices[0].message.content.strip()

        logging.info(f"✅ Generated post in {duration:.2f}s")
        return {
            "ok": True,
            "text": text,
            "time_taken": duration,
            "model": "llama-3.1-70b-versatile"
        }

    except Exception as e:
        logging.error(f"Groq error: {str(e)}")
        return {
            "ok": False,
            "error": str(e),
            "text": "Sorry, I couldn’t generate your post right now."
        }

def improve_post(existing_preview, feedback, platform):
    if not existing_preview:
        return {"ok": False, "message": "No existing preview to improve."}
    # If you have an LLM, use it. Fallback to simple concatenation for testing.
    improved = f"{existing_preview}\n\n(Edited based on feedback: {feedback})"
    return {"ok": True, "message": "🔄 Updated content:", "preview": improved}

def post_to_linkedin(text, access_token, image_url=None, hashtags=None):
    """
    Post text (optionally with image and hashtags) to LinkedIn using OAuth access token.
    """
    if not access_token:
        return {"ok": False, "error": "LinkedIn not authenticated"}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "X-Restli-Protocol-Version": "2.0.0"
    }

    # --- Step 1: Get profile ID ---
    profile_res = requests.get("https://api.linkedin.com/v2/userinfo", headers=headers)
    if profile_res.status_code != 200:
        return {
            "ok": False,
            "error": f"LinkedIn profile fetch failed: {profile_res.status_code}",
            "details": profile_res.text
        }

    user = profile_res.json()
    author_urn = f"urn:li:person:{user['sub']}"

    # --- Step 2: Build message ---
    if hashtags:
        hashtag_text = " ".join(f"#{tag.strip()}" for tag in hashtags)
        text = f"{text}\n\n{hashtag_text}"

    content = {
        "author": author_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {
            "com.linkedin.ugc.ShareContent": {
                "shareCommentary": {"text": text},
                "shareMediaCategory": "NONE"
            }
        },
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"}
    }

    # --- Step 3: Handle optional image ---
    if image_url:
        upload_req = requests.post(
            "https://api.linkedin.com/v2/assets?action=registerUpload",
            headers=headers,
            json={
                "registerUploadRequest": {
                    "owner": author_urn,
                    "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                    "serviceRelationships": [
                        {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
                    ]
                }
            }
        )

        if upload_req.status_code == 200:
            upload_info = upload_req.json()
            upload_url = upload_info["value"]["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"]["uploadUrl"]
            asset = upload_info["value"]["asset"]

            # Upload the image bytes
            img = requests.get(image_url)
            requests.put(upload_url, data=img.content, headers={"Authorization": f"Bearer {access_token}"})

            # Attach the image to post
            content["specificContent"]["com.linkedin.ugc.ShareContent"]["shareMediaCategory"] = "IMAGE"
            content["specificContent"]["com.linkedin.ugc.ShareContent"]["media"] = [
                {
                    "status": "READY",
                    "description": {"text": "AI-generated image"},
                    "media": asset,
                    "title": {"text": "Generated Content"}
                }
            ]
        else:
            return {"ok": False, "error": "Image upload failed", "details": upload_req.text}

    # --- Step 4: Post to LinkedIn ---
    post_res = requests.post("https://api.linkedin.com/v2/ugcPosts", headers=headers, json=content)
    if post_res.status_code == 201:
        return {"ok": True, "message": "✅ Post shared successfully on LinkedIn!"}
    else:
        return {"ok": False, "error": f"LinkedIn post failed: {post_res.status_code}", "details": post_res.text}




def post_to_twitter(post_text,access_token):
    """
    Posts a compressed, Groq-optimized tweet to Twitter (X).
    - Takes the full LinkedIn-style post
    - Compresses to <=280 chars using Groq intelligently
    - Posts with verified user token
    """
    try:
        if not access_token:
            return {"ok": False, "message": "⚠️ No Twitter login found. Please login first."}, 400

        headers = {"Authorization": f"Bearer {access_token}"}

        # Step 1 — Verify Twitter token
        verify_resp = requests.get("https://api.twitter.com/2/users/me", headers=headers)
        if verify_resp.status_code != 200:
            return {
                "ok": False,
                "message": "⚠️ Invalid Twitter access token. Please re-login.",
                "error": verify_resp.text
            }, 400

        user_data = verify_resp.json().get("data", {})
        username = user_data.get("username", "Unknown")

        # Step 2 — Compress text using Groq (LLM smart shortening)
        compression_prompt = (
            "You are a professional Twitter content editor. "
            "Rewrite the following text to fit within 280 characters, "
            "while keeping its essence, tone, hashtags, and Unicode bold formatting (𝐛𝐨𝐥𝐝). "
            "Do not add explanations, just output the final tweet text.\n\n"
            f"Text:\n{post_text}"
        )

        groq_resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You shorten posts for Twitter preserving meaning and engagement."},
                {"role": "user", "content": compression_prompt},
            ],
            temperature=0.6
        )

        compressed_text = groq_resp.choices[0].message.content.strip()
        if len(compressed_text) > 280:
            compressed_text = compressed_text[:277] + "…"  # hard truncate fallback

        # Step 3 — Post to Twitter
        post_url = "https://api.twitter.com/2/tweets"
        payload = {"text": compressed_text}
        headers["Content-Type"] = "application/json"

        resp = requests.post(post_url, headers=headers, json=payload)
        if resp.status_code == 201:
            tweet_data = resp.json().get("data", {})
            return {
                "ok": True,
                "message": f"✅ Tweet posted successfully as @{username}",
                "tweet": tweet_data,
                "compressed_text": compressed_text
            }
        elif resp.status_code == 429:
            logging.warning("⚠️ Rate limit hit, waiting before retrying...")
            time.sleep(60)
            return post_to_twitter(post_text)
        else:
            return {
                "ok": False,
                "message": f"❌ Error posting to Twitter",
                "status": resp.status_code,
                "error": resp.text
            }, 400

    except Exception as e:
        logging.exception("Twitter posting failed")
        return {"ok": False, "message": "⚠️ Internal error while posting to Twitter.", "error": str(e)}, 500

