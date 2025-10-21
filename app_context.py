from flask import current_app

def get_scheduler():
    """Access the global scheduler safely via Flask's context."""
    return getattr(current_app, "scheduler", None)
