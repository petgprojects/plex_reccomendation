from plexapi.server import PlexServer
from tmdbv3api import TMDb, Movie, Genre
from collections import Counter
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import requests, pandas as pd
from tqdm import trange
# from lightfm.data import Dataset

baseurl = 'http://peterubuntuserver.ddns.net:32400'
token = 'ydWQy8X6StWBJVPHiLf2'
plex = PlexServer(baseurl, token)

tmdb = TMDb()
tmdb.api_key = 'ea023fa0879737d0cfd9ae3ca7365a6e'
movie_api = Movie()

TAUTULLI_URL  = "http://192.168.2.73:8181"      # ⚠️  change if remote / SSL
TAUTULLI_KEY  = "c0766a7cd7a24f73b8d110a118fed994"      # ⚠️  copy from Tautulli settings
MAX_HISTORY   = None     # None = fetch every record; else int for quick tests
BATCH_SIZE    = 1000 

def get_tmdb_ids(plex):
    tmdb_ids = []
    movies = plex.library.section('Movies')
    for movie in movies.all():
        tmdb_id = None
        for guid in movie.guids:
            if 'themoviedb' in guid.id or "tmdb" in guid.id:
                # TMDb ID is the last part of the GUID
                tmdb_id = guid.id.split('//')[-1].split('?')[0]
                tmdb_ids.append(tmdb_id)
                break
    return tmdb_ids

def build_counters(ids):
    actor_counter = Counter()
    director_counter = Counter()

    # First pass: build name frequency
    for tmdb_id in ids:
        try:
            credits = movie_api.credits(tmdb_id)
            cast = list(credits.get('cast', []))
            crew = list(credits.get('crew', []))

            # Top 5 billed actors
            for actor in cast[:5]:
                actor_counter[actor['name']] += 1

            # Director(s)
            for crew_member in crew:
                if crew_member['job'] == 'Director':
                    director_counter[crew_member['name']] += 1
        except Exception as e:
            print(e)
    # Select most common people across all movies
    top_actors = [a for a, _ in actor_counter.most_common(500)]
    top_directors = [d for d, _ in director_counter.most_common(200)]

    return top_actors, top_directors

def vectorize_movie(metadata, genre_master_names, credits, top_actors, top_directors):
    vector = []

    # --- genres ---------------------------------------------------------
    movie_genres = {getattr(g, "name", None) or g.get("name")
                    for g in getattr(metadata, "genres", [])}
    genre_vector = [1 if name in movie_genres else 0
                    for name in genre_master_names]
    vector.extend(genre_vector)

    # --- numeric features ----------------------------------------------
    year = int(metadata.release_date[:4]) if metadata.release_date else 2000
    vector += [
        (year - 1900) / 125,                       # year
        (metadata.runtime or 90) / 300,            # runtime
        (metadata.vote_average or 5) / 10,         # rating
    ]

    # --- top‑5 actors ---------------------------------------------------
    actor_names = [a['name'] for a in list(credits.get('cast', []))[:5]]
    vector.extend(1 if n in actor_names else 0 for n in top_actors)
    

    # --- director(s) ----------------------------------------------------
    director_names = [m['name'] for m in credits.get('crew', [])
                      if m['job'] == 'Director']
    vector.extend(1 if n in director_names else 0 for n in top_directors)

    return np.array(vector)

def build_dataset(movie_api, movie_library,
                  top_actors, top_directors):
    """
    Return {title: np.array([vector])} for every movie.
    """
    # ---- 1️⃣  get the global genre list ---------------------------------
    genre_api = Genre()                         # wrapper around /genre/movie/list
    # returns objects that behave like  {'id': 28, 'name': 'Action'} …
    genre_master_names = [g['name'] for g in genre_api.movie_list()]

    vectors = {}

    for plex_movie in movie_library.all():
        # ---- 2️⃣  TMDb id out of Plex  ---------------------------------
        tmdb_id = next(
            (guid.id.split('//')[-1].split('?')[0]
             for guid in plex_movie.guids
             if 'themoviedb' in guid.id or 'tmdb' in guid.id),
            None
        )
        if not tmdb_id:
            continue

        # ---- 3️⃣  build vector -----------------------------------------
        try:
            metadata = movie_api.details(tmdb_id)
            credits  = movie_api.credits(tmdb_id)
            vec = vectorize_movie(
                metadata,
                genre_master_names,           # <- pass names, not objects
                credits,
                top_actors,
                top_directors,
            )
            vectors[plex_movie.title] = vec
        except Exception as e:
            print(f"Failed on {plex_movie.title}: {e}")

    return vectors

def recommend(title, vectors, top_n=5):
    target = vectors[title].reshape(1, -1)
    all_titles = list(vectors.keys())
    all_vecs = np.array([vectors[t] for t in all_titles])

    sims = cosine_similarity(target, all_vecs)[0]
    top_indices = sims.argsort()[::-1][1:top_n+1]  # skip self
    return [(all_titles[i], sims[i]) for i in top_indices]

def fetch_history_tautulli(url=TAUTULLI_URL, apikey=TAUTULLI_KEY,
                           media_type="movie", limit=MAX_HISTORY,
                           batch=BATCH_SIZE):
    """Return a DataFrame with at least user_id, rating_key, watched_status."""
    rows, start, keep_going = [], 0, True
    while keep_going:
        params = {
            "apikey": apikey,
            "cmd": "get_history",
            "media_type": media_type,
            "length": batch,
            "start": start,
            "order_column": "date",
            "order_dir": "asc",
        }
        r = requests.get(f"{url}/api/v2", params=params, timeout=20).json()
        if r["response"]["result"] != "success":
            raise RuntimeError(r["response"]["message"])
        data = r["response"]["data"]["data"]
        rows.extend(data)
        start += batch
        keep_going = data and (limit is None or start < limit)
    return pd.DataFrame(rows)[["user_id", "rating_key", "watched_status"]]

ids = get_tmdb_ids(plex)
top_actors, top_directors = build_counters(ids)
movie_library = plex.library.section('Movies')
vectors = build_dataset(movie_api, movie_library,
                        top_actors, top_directors)

seed_title = "Inception"          # any movie in your library
for title, score in recommend(seed_title, vectors, top_n=5):
    print(f"{title:<40}  similarity={score:.3f}")
