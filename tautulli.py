import pandas as pd
import requests

TAUTULLI_BASE_URL = "http://192.168.2.73:8181"  # Tautulli's base URL
TAUTULLI_API_KEY   = "c0766a7cd7a24f73b8d110a118fed994"             # From Tautulli > Settings > General

def get_tautulli_data(endpoint, **params):
    """Helper to call Tautulli API with authentication"""
    params["apikey"] = TAUTULLI_API_KEY
    url = f"{TAUTULLI_BASE_URL}/api/v2?cmd={endpoint}"
    return requests.get(url, params=params).json()

def get_most_watched_movies_by_count(user_id=None, limit=10):
    # 1) resolve user_id if not given
    if user_id is None:
        users = get_tautulli_data("get_users")["response"]["data"]
        user_id = next(u["user_id"] for u in users if u["username"]=="peterg236")

    # 2) fetch up to N history rows for that user & media_type
    resp = get_tautulli_data(
        "get_history",
        user_id=user_id,
        media_type="movie",
        length=1000
    )["response"]["data"]

    # 3) build DataFrame
    df = pd.DataFrame([{
        "title":     e["title"],
        "played_at": pd.to_datetime(e["watched_at"]),
    } for e in resp])

    # 4) group & sort by play count
    top = (
        df.groupby("title")
          .size()
          .reset_index(name="plays")
          .sort_values("plays", ascending=False)
          .head(limit)
    )
    return top

if __name__ == "__main__":
    print(get_most_watched_movies_by_count(limit=5))