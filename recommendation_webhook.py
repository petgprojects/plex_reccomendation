from __future__ import annotations

from typing import Any

from plex_playlist import UserAuthenticationRequired, push_recs
from tautulli import get_recently_watched


VALID_EVENTS = {"watched", "playback_stop", "stop"}


def normalize_tautulli_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize Tautulli payload shapes from script args or webhook JSON."""
    event = payload.get("event") or payload.get("action")
    return {
        "event": event,
        "media_type": payload.get("media_type"),
        "title": payload.get("title"),
        "username": payload.get("username"),
    }


def process_tautulli_payload(payload: dict[str, Any], logger) -> dict[str, Any]:
    payload = normalize_tautulli_payload(payload)
    logger.info("Received payload: %s", payload)

    event = payload.get("event")
    if event not in VALID_EVENTS:
        logger.info("Ignoring event %s", event)
        return {"status": "ignored", "reason": f"unsupported event: {event}"}

    media_type = payload.get("media_type")
    username = payload.get("username")
    if not media_type or not username:
        logger.warning("Missing required payload fields: media_type=%s username=%s", media_type, username)
        return {"status": "invalid", "reason": "media_type and username are required"}

    kind = "tv" if media_type == "episode" else "movie"
    logger.info("Processing: user=%s kind=%s", username, kind)

    recent = get_recently_watched(username=username, media_type=media_type, limit=10)
    if recent.empty:
        logger.warning("No recent items found for user=%s", username)
        return {"status": "empty", "reason": f"no recent items for {username}"}

    titles = recent["title"].tolist()
    logger.info("Recently watched: %s", titles)
    try:
        push_recs(username, titles, kind)
    except UserAuthenticationRequired as exc:
        logger.warning("Skipping watchlist update for %s: %s", username, exc)
        return {"status": "auth_required", "reason": str(exc)}

    logger.info("Finished push_recs for %s (%d items)", username, len(recent))
    return {"status": "ok", "user": username, "kind": kind, "items": len(recent)}
