import os
import requests
import numpy as np
import pandas as pd
from plexapi.server import PlexServer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.preprocessing import MultiLabelBinarizer, MinMaxScaler
from sklearn.neighbors import NearestNeighbors

# ————— CONFIG —————
PLEX_BASE_URL = "http://peterubuntuserver.ddns.net:32400"
PLEX_TOKEN    = "ydWQy8X6StWBJVPHiLf2"
TMDB_API_KEY  = "ea023fa0879737d0cfd9ae3ca7365a6e"

plex = PlexServer(PLEX_BASE_URL, PLEX_TOKEN)


def fetch_plex_list():
    rows = []
    for m in plex.library.section("Movies").all():
        tmdb_id = None
        for g in m.guids:
            if "tmdb" in g.id:
                tmdb_id = g.id.split("//")[-1].split("?")[0]
                break
        if tmdb_id:
            rows.append({"title": m.title, "tmdb_id": tmdb_id})
    return pd.DataFrame(rows)


def tmdb_get(path, **params):
    url = f"https://api.themoviedb.org/3{path}"
    params["api_key"] = TMDB_API_KEY
    return requests.get(url, params=params).json()


def enrich_with_tmdb(df):
    meta = []
    for _, row in df.iterrows():
        tid = row["tmdb_id"]
        info  = tmdb_get(f"/movie/{tid}", language="en-US")
        creds = tmdb_get(f"/movie/{tid}/credits")

        genres   = [g["name"] for g in info.get("genres", [])]
        overview = info.get("overview", "") or ""
        runtime  = info.get("runtime") or 0
        vote     = info.get("vote_average") or 0
        rd       = info.get("release_date") or ""

        cast5 = [c["name"] for c in creds.get("cast", [])[:5] if c.get("name")]
        dirs  = [c["name"] for c in creds.get("crew", []) if c.get("job") == "Director"]

        meta.append({
            "overview": overview,
            "genres": genres,
            "runtime": runtime,
            "vote": vote,
            "release_date": rd,
            "cast": cast5,
            "directors": dirs
        })
    return pd.DataFrame(meta)


def build_features(df):
    # MultiLabelBinarizer on pure Python lists
    G = MultiLabelBinarizer().fit_transform(df["genres"].tolist())
    C = MultiLabelBinarizer().fit_transform(df["cast"].tolist())
    D = MultiLabelBinarizer().fit_transform(df["directors"].tolist())

    # Numeric features via .values → ensure ndarray
    runtimes = df["runtime"].fillna(0).astype(float).values
    votes    = df["vote"].fillna(0).astype(float).values
    years    = (
        pd.to_datetime(df["release_date"], errors="coerce")
          .dt.year.fillna(2000).astype(int)
          .values
    )
    nums = np.vstack([runtimes, votes, years]).T

    # scale to [0,1]
    N = MinMaxScaler().fit_transform(nums)

    # TF-IDF on overview (force list) + SVD → dense float array
    overviews = df["overview"].fillna("").tolist()
    Xtxt = TfidfVectorizer(max_features=2000, stop_words="english")\
           .fit_transform(overviews)
    Ttxt = TruncatedSVD(n_components=100, random_state=42)\
           .fit_transform(Xtxt)

    # H-stack everything into one 2D float array
    X = np.hstack([G, C, D, N, Ttxt]).astype(float)
    return X


def train_index(X):
    # brute‐force cosine on a dense array
    return NearestNeighbors(
        n_neighbors=6,
        metric="cosine",
        algorithm="brute"
    ).fit(X)


def recommend(title, df, X, knn):
    if "title" not in df.columns:
        raise KeyError("DataFrame must have a 'title' column")
    mask = df["title"] == title
    if not mask.any():
        raise ValueError(f"'{title}' not in library")
    idx = df.index[mask][0]
    dist, nn = knn.kneighbors(X[idx].reshape(1, -1), n_neighbors=6)
    recs = df.iloc[nn[0]][["title"]].copy()
    recs["score"] = 1 - dist[0]
    return recs.iloc[1:].reset_index(drop=True)


if __name__ == "__main__":
    df_movies = fetch_plex_list()
    df_meta   = enrich_with_tmdb(df_movies)
    df = pd.concat([df_movies.reset_index(drop=True),
                    df_meta.reset_index(drop=True)], axis=1)

    X   = build_features(df)
    knn = train_index(X)

    seed = "Inception"
    print(f"\nRecommendations for {seed!r}:")
    print(recommend(seed, df, X, knn).to_string(index=False))
