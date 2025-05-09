# rec_engine.py  (NEW)
# requires - pyarrow, fastparquet
import pandas as pd
from pathlib import Path
from main import Movie, TVShow, Model, fetch_plex_list   # uses your existing code
import numpy as np
import joblib

_CACHE = Path("plex_rec_cache")          # or any writable folder
_CACHE.mkdir(exist_ok=True)

def _build(kind: str):
    """
    Build (or reload from cache) the dataframe, feature matrix and K‑NN index
    for `kind` = 'movie' | 'tv'
    """
    paths = {
        "df":   _CACHE / f"{kind}_df.parquet",
        "X":    _CACHE / f"{kind}_X.npy",
        "knn":  _CACHE / f"{kind}_knn.joblib",
    }
    if all(p.exists() for p in paths.values()):
        df  = pd.read_parquet(paths["df"])
        X   = np.load(paths["X"])
        knn = joblib.load(paths["knn"])
        return df, X, knn

    df_lib   = fetch_plex_list(media_type=kind)              # from main.py
    enricher = Movie() if kind == "movie" else TVShow()
    df_meta  = enricher.enrich_with_tmdb(df_lib)
    df       = pd.concat([df_lib.reset_index(drop=True),
                          df_meta.reset_index(drop=True)], axis=1)
    X        = Model().build_features(df)
    knn      = Model().train_index(X)

    df.to_parquet(paths["df"])
    np.save(paths["X"], X)
    joblib.dump(knn, paths["knn"])
    return df, X, knn


def recommend_from_seeds(seeds: list[str], kind: str, per_seed=5, top_n=25):
    """Return a merged, deduped DataFrame of recommendations."""
    df, X, knn = _build(kind)
    all_recs   = []
    for title in seeds:
        try:
            r = Model().recommend(title, df, X, knn).head(per_seed)
            r["seed"] = title
            all_recs.append(r)
        except ValueError:
            # seed title not in your library/index – ignore
            continue
    if not all_recs:
        return pd.DataFrame()

    out = (pd.concat(all_recs)
             .drop_duplicates("title", keep="first")
             .sort_values("score", ascending=False)
             .head(top_n)
             .reset_index(drop=True))
    return out

if __name__ == "__main__":
    print(recommend_from_seeds(["Inception", "Anchorman: The Legend of Ron Burgundy"], "movie"))