import logging
import re
from tools import client  


class AIPostAgent:
    """
    Agentic layer on top of Groq API.
    Manages conversation memory and intelligent intent handling.
    """

    def __init__(self):
        self.memory = []  # stores conversation context

    def add_memory(self, role, content):
        self.memory.append({"role": role, "content": content})
        if len(self.memory) > 10:
            self.memory.pop(0)  # keep memory short

    def reflect(self, result):
        """
        Optional hook to store or log results after posting.
        """
        try:
            self.memory.append(result)
            self.last_action = result
            print("[Agent Reflect] Stored result in memory:", result)
        except Exception as e:
            print("[Agent Reflect Error]", e)

    def summarize_context(self):
        # Join recent user and AI messages for context
        return "\n".join([f"{m['role']}: {m['content']}" for m in self.memory[-6:]])

    def handle_user_input(self, user_input, platform):
        """
        Generate AI post + contextually relevant hashtags using Groq.
        """
        try:
            system_prompt = (
            "You are a professional LinkedIn content writer. "
            "All outputs must be formatted using Unicode bold characters for headings and emphasis, "
            "never Markdown (#, ##, **). "
            "For example, '# Day 1: Introduction to AI' → '𝐃𝐚𝐲 𝟏: 𝐈𝐧𝐭𝐫𝐨𝐝𝐮𝐜𝐭𝐢𝐨𝐧 𝐭𝐨 𝐀𝐈'. "
            "Use clean spacing and emojis sparingly (📈, 💡, 🚀). "
            "Write naturally and keep a professional, inspiring tone. "
            "Output should be ready to post directly on LinkedIn."
            )
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt },
                    {"role": "user", "content": f"Write a {platform} post about: {user_input}. Keep it natural and professional."}
                ],
                temperature=0.7
            )
            preview_text = completion.choices[0].message.content.strip()

            # Step 2 — Ask Groq to create *contextually relevant hashtags*
            hashtags = self.generate_hashtags(preview_text)
            if hashtags:
                preview_text = f"{preview_text}\n\n{' '.join(hashtags)}"

            self.last_preview = preview_text

            return {
                "ok": True,
                "message": "✨ Here's your preview:",
                "preview": preview_text,
            }

        except Exception as e:
            logging.exception("AI post generation failed")
            return {
                "ok": False,
                "error": str(e),
                "message": "⚠️ Failed to generate post.",
            }

    def generate_hashtags(self, text):
        """
        Ask the Groq model to produce 3–6 smart, platform-appropriate hashtags from the text.
        """
        try:
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": "You generate concise, relevant hashtags for social media posts."},
                    {"role": "user", "content": f"Generate 3 to 6 relevant hashtags (without explanations) for this text:\n{text}"}
                ],
                temperature=0.5
            )
            hashtags_text = completion.choices[0].message.content.strip()

            # Extract hashtags if the model returns in free form
            hashtags = re.findall(r"#\w+", hashtags_text)
            if not hashtags:
                hashtags = [f"#{w.capitalize()}" for w in re.findall(r'\b\w+\b', hashtags_text)[:5]]
            return hashtags

        except Exception as e:
            logging.warning(f"Hashtag generation failed: {e}")
            return []

        
    def decide_action(self, user_input, last_post):
        """
        Simple decision engine to determine what action to take.
        Returns: {"action": str, "details": str}
        """
        text = user_input.lower()

        if "post" in text:
            return {"action": "post", "details": "User wants to publish the post."}
        elif "save" in text:
            return {"action": "save", "details": "User wants to save draft."}
        elif "hashtag" in text or "tags" in text:
            return {"action": "hashtag", "details": "User wants hashtags for the post."}
        elif "summarize" in text:
            return {"action": "summarize", "details": "User wants a shorter summary."}
        else:
            return {"action": "generate", "details": "Default: generate or refine text."}

