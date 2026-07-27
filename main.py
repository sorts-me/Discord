import sys
import os
import json
import logging
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from sorts.database.connection import init_db, get_db
from sorts.services.seed_service import seed_database, seed_global_traits
from sorts.database import models as db_models
from sorts.bot.bot import run_bot

# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("main")


from sorts.web.compliance import TERMS_HTML, PRIVACY_HTML


from urllib.parse import urlparse, parse_qs
from sorts.web.api import handle_api_request


class _HealthHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        if path.startswith("/api/"):
            status_code, response_data = handle_api_request(path, "GET", params, {})
            self.send_response(status_code)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
        elif path == "/terms":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(TERMS_HTML.encode("utf-8"))
        elif path == "/privacy":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(PRIVACY_HTML.encode("utf-8"))
        else:
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"ok")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        content_length = int(self.headers.get("Content-Length", 0))
        body_bytes = self.rfile.read(content_length) if content_length > 0 else b"{}"
        try:
            body_data = json.loads(body_bytes.decode("utf-8"))
        except Exception:
            body_data = {}

        if path.startswith("/api/"):
            status_code, response_data = handle_api_request(path, "POST", params, body_data)
            self.send_response(status_code)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self._send_cors_headers()
            self.end_headers()
            self.wfile.write(json.dumps(response_data).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # Silence access logs


def start_health_server():
    """Starts a minimal HTTP server on PORT so Render & UptimeRobot health checks pass."""
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Health server running on port {port}")

def bootstrap():
    """Initializes database schema, seeds global traits, seeds university data, and imports clubs if missing."""
    logger.info("Initializing database schema...")
    init_db()

    from sorts.config.settings import DEFAULT_UNIVERSITY_SLUG

    with get_db() as db:
        # ── Always seed global traits first (safe for all universities) ──────
        seed_global_traits(db)

        # ── Seed default university if not already in database ────────────────
        # Data lives in Supabase after the first deploy; seed file only needed
        # on a completely fresh database (e.g. first migration to Supabase).
        default_univ = db.query(db_models.University).filter_by(slug=DEFAULT_UNIVERSITY_SLUG).first()
        if not default_univ:
            seed_path = f"sorts/assets/data/{DEFAULT_UNIVERSITY_SLUG}_seed.json"
            if os.path.exists(seed_path):
                logger.info(f"University '{DEFAULT_UNIVERSITY_SLUG}' not found in DB. Running auto-seeding from file...")
                try:
                    seed_database(db, seed_path)
                    logger.info("Auto-seeding completed.")
                    default_univ = db.query(db_models.University).filter_by(slug=DEFAULT_UNIVERSITY_SLUG).first()
                except Exception as e:
                    logger.error(f"Auto-seeding failed: {e}")
                    return
            else:
                logger.info(
                    f"Seed file for '{DEFAULT_UNIVERSITY_SLUG}' not present and university not found in DB. "
                    "If data is already in the persistent database this is fine. "
                    f"Otherwise restore sorts/assets/data/{DEFAULT_UNIVERSITY_SLUG}_seed.json and redeploy."
                )
                return
        else:
            logger.info(f"University '{DEFAULT_UNIVERSITY_SLUG}' present in database. Skipping seed.")

        # ── Auto-import clubs if none are published yet ──────────────────────
        club_count = db.query(db_models.Club).filter_by(
            university_id=default_univ.id
        ).count()

        if club_count == 0:
            logger.info("No clubs found. Running auto-import from source...")
            try:
                from sorts.services.import_service import ImportService
                svc = ImportService()
                sources = svc.get_university_sources(db, default_univ.id)
                if not sources:
                    logger.warning(f"No import sources configured for university '{DEFAULT_UNIVERSITY_SLUG}'.")
                    return
                live_source = next((s for s in sources if s.source_type == "website"), sources[-1])
                logger.info(f"Selected live source '{live_source.name}' (ID: {live_source.id})")
                job_id = svc.trigger_import(db, live_source.id)
                logger.info(f"Import job {job_id} complete. Publishing clubs...")
                svc.publish_job(db, job_id)
                published = db.query(db_models.Club).filter_by(
                    university_id=default_univ.id
                ).count()
                logger.info(f"Auto-import done. {published} clubs now live.")
            except Exception as e:
                logger.error(f"Auto-import failed: {e}")
        else:
            logger.info(f"{club_count} clubs already live. Skipping auto-import.")

        # ── Ensure Verified Club Registry and Events are synchronized ─────────
        try:
            from sorts.services.seed_service import sync_verified_clubs, sync_verified_events
            sync_verified_clubs(db)
            sync_verified_events(db)
        except Exception as e:
            logger.error(f"Failed to sync verified registry or events: {e}")

def main():
    start_health_server()  # Open port before anything else so Render health check passes
    bootstrap()
    
    # ── Start Reddit Bot Listener ─────────────────────────────────────────────
    try:
        from sorts.reddit.listener import get_reddit_listener
        reddit_listener = get_reddit_listener()
        if reddit_listener.is_configured():
            logger.info("Starting Sortling Reddit Bot Listener...")
            reddit_listener.start_polling()
    from sorts.config import settings
    if settings.DISCORD_TOKEN and os.getenv("ENABLE_DISCORD", "false").lower() == "true":
        logger.info("Starting Sortling Discord Bot...")
        run_bot()
    else:
        logger.info("Discord support is discontinued. Running HTTP API & Reddit Bot Listener for Mahindra University.")
        import time
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            logger.info("Shutting down Sortling server...")

if __name__ == "__main__":
    main()
