import pandas as pd
import requests
from datetime import datetime

# Tautulli configuration
TAUTULLI_BASE_URL = "http://192.168.2.73:8181"
TAUTULLI_API_KEY   = "c0766a7cd7a24f73b8d110a118fed994"


def get_tautulli_data(cmd, **params):
    """Helper to call the Tautulli API and return the JSON payload."""
    params["apikey"] = TAUTULLI_API_KEY
    url = f"{TAUTULLI_BASE_URL}/api/v2?cmd={cmd}"
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


def get_recently_watched(user_id=None, username="peterg236", limit=10, media_type="movie"):
    """
    media_type: one of 'movie' or 'episode' (for show)
    Returns a DataFrame of the user's most recently watched movies (title, watched_at).
    """
    # 1) Resolve user_id if not provided
    if user_id is None:
        resp = get_tautulli_data("get_users")
        users = resp.get("response", {}).get("data", resp)
        if isinstance(users, dict):
            users = [users]
        user = next((u for u in users if u.get("username") == username), users[0])
        user_id = user.get("user_id")

    # 2) Fetch history sorted by date descending
    resp = get_tautulli_data(
        "get_history",
        user_id=user_id,
        media_type=media_type,
        # length=limit,
        order_column="date",
        order_dir="desc"
    )
    data = resp.get("response", {}).get("data", resp)

    # Unwrap v2 history payload: data may be dict with 'data' list, or list directly
    if isinstance(data, dict) and "data" in data:
        history = data["data"]
    elif isinstance(data, list):
        history = data
    else:
        history = []

    # 3) Build list of recent watches
    records = []
    for entry in history:
        ts = entry.get("date") or entry.get("timestamp") or entry.get("watched_at")
        try:
            watched_at = datetime.fromtimestamp(int(ts))
        except Exception:
            watched_at = None
        if (media_type == "movie"):
            title = entry.get("title") or entry.get("full_title")
        else:
            title = entry.get("grandparent_title")
        records.append({
            "title": title,
            "watched_at": watched_at
        })

    # 4) Return DataFrame of the most recent N
    df = pd.DataFrame(records)
    recent_shows = (
        df.groupby("title", as_index=False)["watched_at"]
        .max()
        .sort_values("watched_at", ascending=False)
        .head(limit)
    )
    return recent_shows


if __name__ == "__main__":
    recent5 = get_recently_watched(username="zafy4", limit=10, media_type="movie")
    print("Most Recently Watched Movies:\n", recent5)