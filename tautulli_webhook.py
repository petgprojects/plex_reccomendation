import json, os, sys, pathlib, logging
from datetime import datetime
from tautulli import get_recently_watched
from plex_playlist import push_recs

LOG_PATH = pathlib.Path(os.getenv("TAUTULLI_WEBHOOK_LOG", "/plex_reccomendation/logs/webhook.log"))
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

try:
    payload_raw = os.environ.get("TAUTULLI_PAYLOAD", "{}")
    log.info("Received payload: %s", payload_raw[:400])     # truncate if huge
    payload = json.loads(payload_raw)

    if payload.get("event") not in ("watched", "playback_stop"):
        log.info("Ignoring event %s", payload.get("event"))
        sys.exit(0)

    kind  = "tv" if payload["media_type"] == "episode" else "movie"
    user  = payload["username"]
    log.info("Event=%s user=%s kind=%s", payload["event"], user, kind)

    recently_watched = get_recently_watched(
        username=user,
        media_type=payload["media_type"],
    )
    log.info("Recently watched titles: %s", recently_watched['title'].tolist())

    push_recs(user, recently_watched["title"].tolist(), kind)
    log.info("push_recs completed for user %s (%d titles)", user, len(recently_watched))

except Exception as exc:
    log.exception("Webhook failed: %s", exc)
    raise

