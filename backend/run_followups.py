"""Production-safe AI follow-up cron entry point.

Run from the backend directory with: python run_followups.py --limit 50
The database idempotency key and row claim protect overlapping invocations.
"""
import argparse
import json
import os

os.environ["DIGIDARA_SKIP_AUTO_APP"] = "1"

from app import create_app
from extensions import db
from routes.ai_followups import process_due_followups


def main():
    parser = argparse.ArgumentParser(description="Process due DigiDARA AI follow-ups")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        try:
            result = process_due_followups(limit=min(max(args.limit, 1), 500))
            print(json.dumps(result, sort_keys=True))
        except Exception:
            db.session.rollback()
            app.logger.exception("AI follow-up cron failed")
            raise
        finally:
            db.session.remove()


if __name__ == "__main__":
    main()
