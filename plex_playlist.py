from plexapi.myplex import MyPlexAccount
from plexapi.server  import PlexServer, NotFound
from plexapi.video import Movie, Show
from rec_engine import recommend_from_seeds
from typing import List
from tautulli import get_recently_watched

BASE_URL       = "http://peterubuntuserver.ddns.net:32400"
OWNER_TOKEN    = "ydWQy8X6StWBJVPHiLf2"        # any admin/owner token works
PLAYLIST_TPL: str = "Fresh {kind} Recs for {name}"                     # for movies
COLLECTION_TPL: str = "Fresh {kind} Recs for {name}"                   # for shows
HOME_PROMOTE: bool = True                                   # put collection on Home row

# account        = MyPlexAccount(token=OWNER_TOKEN)
# owner_srv   = PlexServer(BASE_URL, OWNER_TOKEN)   # we need its machine ID
# machine_id  = owner_srv.machineIdentifier


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
        if not hits:
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
        return OWNER_TOKEN

    # 1) scan friends & home users – their "title" matches the display name
    for u in account.users():
        if username.lower() in {u.title.lower(), getattr(u, "username", "").lower()}:
            token = u.get_token(machine_id) or getattr(u, "authenticationToken", None)
            if token:
                return token

    raise RuntimeError(f"Cannot obtain token for user {username!r}. Available users: "
                       f"{[u.title for u in account.users()]}")

#for movies
def _push_movie_playlist(plex_u: PlexServer, titles: list[str], user_title: str):
    items = _pick_items(titles, plex_u, "movie")
    if not items:
        print("Movie titles not found in library – nothing added.")
        return
    name = PLAYLIST_TPL.format(kind="Movie", name=user_title)
    try:
        pl = plex_u.playlist(name)
        pl.removeItems(pl.items())
        pl.addItems(items)
        print(f"Playlist '{name}' updated ({len(items)} items).")
    except NotFound:
        plex_u.createPlaylist(name, items=items)
        print(f"Playlist '{name}' created ({len(items)} items).")

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
    owner_srv = PlexServer(BASE_URL, OWNER_TOKEN)
    machine_id = owner_srv.machineIdentifier
    account = MyPlexAccount(token=OWNER_TOKEN)

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
        _push_movie_playlist(plex_u, recs["title"].tolist(), user_title)
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
    recent_movies = get_recently_watched(username="zafy4", media_type="movie")["title"].tolist()
    recent_tv = get_recently_watched(username="zafy4", media_type="episode")["title"].tolist()
    push_recs("zafy4", recent_tv, "tv")