import argparse
import json, os, sys, pathlib, logging
from datetime import datetime
from tautulli import get_recently_watched
from plex_playlist import push_recs

LOG_PATH = pathlib.Path(os.getenv("TAUTULLI_WEBHOOK_LOG", "/config/plex_reccomendation/logs/tautulli.log"))
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_PATH, encoding="utf‑8"),
        logging.StreamHandler(sys.stdout),                  # so `docker logs` shows it too
    ],
)
log = logging.getLogger(__name__)

def _get_payload() -> dict:
    """Return a dict describing the event, using whichever mechanism is available."""

    # 1. Preferred: full JSON passed via env var ("{payload}" in Arguments)
    raw = os.environ.get("TAUTULLI_PAYLOAD")
    if raw:
        log.debug("Using JSON payload from env var (len=%d)", len(raw))
        try:
            return json.loads(raw)
        except Exception as e:
            log.warning("Failed to parse TAUTULLI_PAYLOAD: %s", e)

    # 2. Fallback: parse individual CLI arguments inserted by Tautulli variables
    p = argparse.ArgumentParser(description="Tautulli custom webhook")
    p.add_argument("--action")
    p.add_argument("--media_type")
    p.add_argument("--username")
    p.add_argument("--title", required=False)
    # allow unknown so we ignore extra placeholders
    args, _unknown = p.parse_known_args()

    if not args.action:
        return {}

    return {
        "event": args.action,
        "media_type": args.media_type,
        "username": args.username,
        "title": args.title,
    }

def main():
    payload = _get_payload()
    log.info("Received payload: %s", json.dumps(payload)[:400])

    if payload.get("event") not in ("watched", "playback_stop"):
        log.info("Ignoring event %s", payload.get("event"))
        return

    kind = "tv" if payload["media_type"] == "episode" else "movie"
    user = payload["username"]
    log.info("Processing: user=%s kind=%s", user, kind)

    recent = get_recently_watched(username=user, media_type=payload["media_type"], limit=10)
    if recent.empty:
        log.warning("No recent items found for user=%s", user)
        return

    log.info("Recently watched: %s", recent["title"].tolist())
    push_recs(user, recent["title"].tolist(), kind)
    log.info("Finished push_recs for %s (%d items)", user, len(recent))

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log.exception("Webhook failed: %s", exc)
        raise

# try:
#     payload_raw = os.environ.get("TAUTULLI_PAYLOAD", "{}")
#     log.info("Received payload: %s", payload_raw[:400])     # truncate if huge
#     payload = json.loads(payload_raw)

#     if payload.get("event") not in ("watched", "playback_stop"):
#         log.info("Ignoring event %s", payload.get("event"))
#         sys.exit(0)

#     kind  = "tv" if payload["media_type"] == "episode" else "movie"
#     user  = payload["username"]
#     log.info("Event=%s user=%s kind=%s", payload["event"], user, kind)

#     recently_watched = get_recently_watched(
#         username=user,
#         media_type=payload["media_type"],
#     )
#     log.info("Recently watched titles: %s", recently_watched['title'].tolist())

#     push_recs(user, recently_watched["title"].tolist(), kind)
#     log.info("push_recs completed for user %s (%d titles)", user, len(recently_watched))

# except Exception as exc:
#     log.exception("Webhook failed: %s", exc)
#     raise

