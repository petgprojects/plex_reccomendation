from plexapi.myplex import MyPlexAccount
from plexapi.server  import PlexServer, NotFound
from plexapi.video import Movie, Show
from rec_engine import recommend_from_seeds
from typing import List
from tautulli import get_recently_watched
from dotenv import load_dotenv
import os

load_dotenv(override=True)

BASE_URL = os.getenv("PLEX_BASE_URL")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")
PLAYLIST_TPL: str = "Fresh {kind} Recs for {name}"                     # for movies
COLLECTION_TPL: str = "Fresh {kind} Recs for {name}"                   # for shows
HOME_PROMOTE: bool = True                                   # put collection on Home row


def _pick_items(titles: list[str], plex_srv: PlexServer, kind: str):
    """Translate plain *titles* to Plex media objects.

    * **Movies**   → the first search hit whose `type == 'movie'`.
    * **TV shows** → the first hit whose `type == 'show'` (series level).

    Episodes are ignored so that a single playlist entry represents the whole
    show instead of a season/episode.
    """
    items = []
    for title in titles:
        hits = plex_srv.library.search(title=title)
        
        # If no hits, try splitting on colon and search first part
        if not hits and ":" in title:
            main_title = title.split(":")[0].strip()
            hits = plex_srv.library.search(title=main_title)
        
        # If still no hits, try a more flexible search
        if not hits:
            sections = plex_srv.library.sections()
            movieSection = None
            tvSection = None
            for section in sections:
                if section.type == "movie":
                    movieSection = section
                elif section.type == "show":
                    tvSection = section
            if kind == "movie":
                hits = movieSection.searchMovies(title=title)
            if kind == "tv":
                hits = tvSection.searchShows(title)
            hits = plex_srv.library.sections().search(filters={"title": title})
            
        if not hits:
            print(f"Could not find: {title}")
            continue

        if kind == "movie":
            # grab the first actual Movie object
            chosen = next((h for h in hits if isinstance(h, Movie) or h.type == "movie"), hits[0])
        else:  # kind == "tv"
            chosen = next((h for h in hits if isinstance(h, Show) or h.type == "show"), hits[0])
        items.append(chosen)
    return items

def _user_token(account: MyPlexAccount, machine_id: str, username: str) -> str:
    """Return a *server‑specific* token for **username**.

    • Works for the server owner them‑self, friends, and managed Plex‑Home users.
    • Accepts either the **username** shown in Plex or the *display name*
      (what Tautulli calls *username* in its payload).
    """
    # 0) Owner wants a playlist too?  Their token is the one we already have.
    if username.lower() in {account.username.lower(), getattr(account, "title", "").lower()}:
        return PLEX_TOKEN

    # 1) scan friends & home users – their "title" matches the display name
    for u in account.users():
        if username.lower() in {u.title.lower(), getattr(u, "username", "").lower()}:
            token = u.get_token(machine_id) or getattr(u, "authenticationToken", None)
            if token:
                return token

    raise RuntimeError(f"Cannot obtain token for user {username!r}. Available users: "
                       f"{[u.title for u in account.users()]}")

#for movies
def _movie_section(plex_srv: PlexServer):
    """Return the first library section of type 'movie'."""
    return next(s for s in plex_srv.library.sections() if s.type == "movie")

def _push_movie_collection(owner_srv: PlexServer, plex_u: PlexServer, titles: list[str], username: str, user_title: str):
    items = _pick_items(titles, plex_u, "movie")
    if not items:
        print("Movie titles not found in library – nothing added.")
        return
    
    movie_sec = _movie_section(owner_srv)  # collection must be created with owner perms
    name = COLLECTION_TPL.format(kind="Movie", name=user_title)

    try:
        coll = movie_sec.collection(name)
        coll.removeItems(coll.items())
        coll.addItems(items)
        print(f"Collection '{name}' updated ({len(items)} items).")
    except NotFound:
        coll = movie_sec.createCollection(name, items=items)
        print(f"Collection '{name}' created ({len(items)} items).")

    # Promote on Home for just this user (if desired and supported)
    if HOME_PROMOTE:
        try:
            hub = coll.visibility()
            hub.updateVisibility(home=True, recommended=True, shared=False)
        except Exception as exc:
            print(f"Home promotion skipped: {exc}")

#for tv
def _tv_section(plex_srv: PlexServer):
    """Return the first library section of type 'show'."""
    return next(s for s in plex_srv.library.sections() if s.type == "show")


def _push_tv_collection(owner_srv: PlexServer, plex_u: PlexServer, titles: list[str], username: str, user_title: str):
    items = _pick_items(titles, plex_u, "tv")
    if not items:
        print("Show titles not found in library – nothing added.")
        return
    
    tv_sec = _tv_section(owner_srv)  # collection must be created with owner perms
    name = COLLECTION_TPL.format(kind="TV", name=user_title)

    try:
        coll = tv_sec.collection(name)
        coll.removeItems(coll.items())
        coll.addItems(items)
        print(f"Collection '{name}' updated ({len(items)} items).")
    except NotFound:
        coll = tv_sec.createCollection(name, items=items)
        print(f"Collection '{name}' created ({len(items)} items).")

    # Promote on Home for just this user (if desired and supported)
    if HOME_PROMOTE:
        try:
            hub = coll.visibility()
            hub.updateVisibility(home=True, recommended=True, shared=False)
        except Exception as exc:
            # older Plex servers / tokens may not support per‑user promotion
            print(f"Home promotion skipped: {exc}")

def push_recs(username: str, seeds: List[str], kind: str):
    if kind not in {"movie", "tv"}:
        raise ValueError("kind must be 'movie' or 'tv'")

    # owner context to fetch machine ID & manage collections
    owner_srv = PlexServer(BASE_URL, PLEX_TOKEN)
    machine_id = owner_srv.machineIdentifier
    account = MyPlexAccount(token=PLEX_TOKEN)

    # connect as recipient user (for searches/playlists)
    user_token = _user_token(account, machine_id, username)
    plex_u = PlexServer(BASE_URL, user_token)
    user_title = get_name(username, account)

    # build recommendations
    recs = recommend_from_seeds(seeds, kind)
    if recs.empty:
        print("No recommendations produced – nothing to update.")
        return

    if kind == "movie":
        _push_movie_collection(owner_srv, plex_u, recs["title"].tolist(), username, user_title)
    else:
        _push_tv_collection(owner_srv, plex_u, recs["title"].tolist(), username, user_title)

def get_name(username: str, account: MyPlexAccount):
    if (account.username == username):
        return username
    for user in account.users():
        if (username == user.username):
            return user.title
    raise RuntimeError(f"Cannot obtain title for user {username!r}. Available users: "
                       f"{[u.username for u in account.users()]}")


if __name__ == "__main__":
    recent_movies = get_recently_watched(username="username", media_type="movie")["title"].tolist()
    recent_tv = get_recently_watched(username="username", media_type="episode")["title"].tolist()
    push_recs("username", recent_tv, "tv")