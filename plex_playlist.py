from plexapi.myplex import MyPlexAccount
from plexapi.server  import PlexServer
from plexapi.exceptions import BadRequest
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
                if not hits:
                    hits = movieSection.searchMovies(title__icontains=title)
            if kind == "tv":
                hits = tvSection.searchShows(title)

        if not hits:
            hits = plex_srv.library.search(
                title=title,
                libtype="movie" if kind == "movie" else "show"
            )
            
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
            token = getattr(u, "authenticationToken", None) or u.get_token(machine_id)
            if token:
                return token

    raise RuntimeError(f"Cannot obtain token for user {username!r}. Available users: "
                       f"{[u.title for u in account.users()]}")

def _get_account(owner_acc: MyPlexAccount, name: str) -> MyPlexAccount:
    """Return a plex.tv-authenticated account for *name* (owner or Home user)."""
    low = name.lower()
    if low in (owner_acc.username.lower(), owner_acc.email.lower()):
        return owner_acc                       # you

    # Managed Plex-Home profiles
    for u in owner_acc.users():
        if low in (u.title.lower(), u.username.lower()):
            return owner_acc.switchHomeUser(u)   # ⇢ account token

    raise RuntimeError(f"No Plex Home user named {name!r}")

def add_unique_to_watchlist(account, items):
    unique = [itm for itm in items if not account.onWatchlist(itm)]
    if not unique:
        return 0
    try:
        account.addToWatchlist(unique)
        return len(unique)
    except BadRequest as exc:
        print(f"Watch-list add failed: {exc}")
        return 0

def push_watchlist(username: str, seeds: list[str], kind: str):
    owner_srv = PlexServer(BASE_URL, PLEX_TOKEN)
    owner_acc = MyPlexAccount(token=PLEX_TOKEN)

    friend_acc = _get_account(owner_acc, username)

    items = _pick_items(seeds, owner_srv, kind)
    if not items:
        print("No matches in library, nothing to add")
        return
    
    added = add_unique_to_watchlist(friend_acc, items)
    print(f"Added {added} new titles to {username}'s watch-list")


def push_recs(username: str, seeds: List[str], kind: str):
    if kind not in {"movie", "tv"}:
        raise ValueError("kind must be 'movie' or 'tv'")

    # build recommendations
    recs = recommend_from_seeds(seeds, kind)
    if recs.empty:
        print("No recommendations produced – nothing to update.")
        return
    
    #push to watchlist
    push_watchlist(username, recs["title"].tolist(), kind)

def get_name(username: str, account: MyPlexAccount):
    if (account.username == username):
        return username
    for user in account.users():
        if (username == user.username):
            return user.title
    raise RuntimeError(f"Cannot obtain title for user {username!r}. Available users: "
                       f"{[u.username for u in account.users()]}")


if __name__ == "__main__":
    recent_movies = get_recently_watched(username="zafy4", media_type="movie")["title"].tolist()
    recent_tv = get_recently_watched(username="peterg236", media_type="episode")["title"].tolist()
    push_recs("zafy4", recent_movies, "movie")