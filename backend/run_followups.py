import os

os.environ["DIGIDARA_SKIP_AUTO_APP"] = "1"

from app import create_app
from routes.ai_followups import run_scheduler

app = create_app()

with app.test_request_context("/api/ai-followups/run", method="POST", json={"limit": 50}):
    # Use the HTTP endpoint in production via a real admin token.
    # This script is a local cron helper and should be run only in trusted environments.
    print("Use POST /api/ai-followups/run from an authenticated admin session.")
