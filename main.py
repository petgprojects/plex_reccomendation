import argparse
from tautulli import get_recently_watched
from plex_playlist import push_recs
import os
from dotenv import load_dotenv
from plexapi.myplex import MyPlexAccount

load_dotenv()

PLEX_TOKEN = os.getenv("PLEX_TOKEN")

def recently_watched(username, kind):
    return get_recently_watched(username=username, media_type=kind)["title"].tolist()

def rec_all():
    account = MyPlexAccount(token=PLEX_TOKEN)
    for user in account.users():
        print(user)
        username = user.username
        recent_movie = recently_watched(username, "movie")
        recent_tv = recently_watched(username, "episode")
        
        if (recent_movie):
            push_recs(username=username, seeds=recent_movie, kind="movie")
        if (recent_tv):
            push_recs(username=username, seeds=recent_tv, kind="tv")

    recent_movie = recently_watched(account.username, "movie")
    recent_tv = recently_watched(account.username, "episode")
    if (recent_movie):
        push_recs(username=account.username, seeds=recent_movie, kind="movie")
    if (recent_tv):
        push_recs(username=account.username, seeds=recent_tv, kind="tv")
if __name__ == "__main__":
    rec_all()
