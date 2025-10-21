# memory.py
from collections import deque

class Memory:
    def __init__(self, maxlen=50):
        self.history = deque(maxlen=maxlen)
        self.last_preview = None

    def add_observation(self, obs):
        self.history.append({"type": "obs", **obs})

    def add_reflection(self, result):
        self.history.append({"type": "result", "value": result})

    def remember_preview(self, preview):
        self.last_preview = preview
        self.history.append({"type": "preview", "preview": preview})

    def get_last_preview(self):
        return self.last_preview

    def get_context_summary(self, limit=5):
        # return last few items as compact strings for prompt context
        items = list(self.history)[-limit:]
        summary = []
        for it in items:
            if it.get("type") == "obs":
                summary.append(f"Input({it.get('platform')}): {it.get('input')}")
            elif it.get("type") == "preview":
                summary.append(f"Preview: {it.get('preview')}")
            elif it.get("type") == "result":
                summary.append(f"Result: {it.get('value')}")
        return "\n".join(summary)
