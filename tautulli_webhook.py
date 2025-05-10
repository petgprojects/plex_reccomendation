import json, os, sys, pathlib
from datetime import datetime
from tautulli import get_recently_watched
from plex_playlist import push_recs

payload = json.loads(os.environ.get("TAUTULLI_PAYLOAD", "{}"))
if payload.get("event") not in ("watched", "playback_stop"):
    sys.exit(0)     

kind  = "tv" if payload["media_type"] == "episode" else "movie"
user  = payload["username"]

recently_watched = get_recently_watched(username=user, media_type=payload["media_type"])
push_recs(user, recently_watched, kind)

