import re
from datetime import datetime, timedelta

class CampaignPlanner:
    def __init__(self, topic, days, hour, minute):
        self.topic = topic
        self.days = days
        self.hour = hour
        self.minute = minute

    def generate_schedule(self):
        """
        Splits AI-generated multi-day content into individual posts for scheduling.
        """
        from ai_agent import AIPostAgent
        ai_agent = AIPostAgent()

        # Ask AI for a structured multi-day post plan
        prompt = (
            f"Create a {self.days}-day LinkedIn posting plan about '{self.topic}'. "
            f"Each day should start with 'Day X:' followed by 1–2 post ideas."
        )
        resp = ai_agent.handle_user_input(prompt, "linkedin")
        full_text = resp.get("text") or resp.get("preview", "")

        if not full_text:
            print("⚠️ No content generated from AI.")
            return []

        # --- Split the plan into days ---
        parts = re.split(r"(?=\bDay\s*\d+:)", full_text, flags=re.IGNORECASE)
        schedule = []
        today = datetime.now()

        for i, part in enumerate(parts):
            if not part.strip():
                continue

            day_num = i + 1
            run_time = (today + timedelta(days=day_num - 1)).replace(
                hour=self.hour, minute=self.minute, second=0, microsecond=0
            )

            schedule.append({
                "topic_variant": part.strip(),
                "datetime": run_time
            })

        print(f"🗓️ Generated {len(schedule)} scheduled posts for topic '{self.topic}'")
        return schedule
