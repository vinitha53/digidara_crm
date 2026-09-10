import logging
import signal
import time

from app import create_app
from extensions import db
from services.campaign_service import process_due_campaigns


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s campaign-worker %(message)s")
logger = logging.getLogger("campaign-worker")
running = True


def stop_worker(*_args):
    global running
    running = False


def main():
    signal.signal(signal.SIGINT, stop_worker)
    signal.signal(signal.SIGTERM, stop_worker)
    app = create_app()
    interval = app.config["CAMPAIGN_WORKER_INTERVAL_SECONDS"]
    lock_connection = None
    lock_cursor = None
    with app.app_context():
        if db.engine.dialect.name in {"mysql", "mariadb"}:
            lock_connection = db.engine.raw_connection()
            lock_cursor = lock_connection.cursor()
            lock_cursor.execute("SELECT GET_LOCK('digidara_campaign_worker', 0)")
            if lock_cursor.fetchone()[0] != 1:
                logger.error("another campaign worker owns the database lock; exiting")
                lock_cursor.close()
                lock_connection.close()
                return
    logger.info("started; send_enabled=%s interval=%ss", app.config["CAMPAIGN_SEND_ENABLED"], interval)
    while running:
        with app.app_context():
            try:
                result = process_due_campaigns()
                if result.get("processed"):
                    logger.info("processed=%s campaigns=%s", result["processed"], result.get("campaigns", 0))
            except Exception:
                db.session.rollback()
                logger.exception("campaign processing failed")
            finally:
                db.session.remove()
        time.sleep(interval)
    if lock_cursor and lock_connection:
        lock_cursor.execute("SELECT RELEASE_LOCK('digidara_campaign_worker')")
        lock_cursor.close()
        lock_connection.close()
    logger.info("stopped")


if __name__ == "__main__":
    main()
