# rec_engine.py  (NEW)
# requires - pyarrow, fastparquet
from typing import List, Tuple
import pandas as pd
from pathlib import Path
from gen_recs import Movie, TVShow, Model, fetch_plex_list   # uses your existing code
import numpy as np
import joblib

_CACHE = Path("plex_rec_cache")          # or any writable folder
_CACHE.mkdir(exist_ok=True)

def _paths(kind: str):
    """Return cache file paths for *kind* ('movie' | 'tv')."""
    return {
        "df":    _CACHE / f"{kind}_df.parquet",
        "X":     _CACHE / f"{kind}_X.npy",
        "knn":   _CACHE / f"{kind}_knn.joblib",
        "count": _CACHE / f"{kind}_count.txt",
    }


def _delete_cache(kind: str):
    for p in _paths(kind).values():
        try:
            p.unlink()
        except FileNotFoundError:
            pass

def _build(kind: str, *, force: bool = False) -> Tuple[pd.DataFrame, np.ndarray, joblib.Memory]:
    """Return `(df, X, knn)` for *kind* ('movie' | 'tv').

    If cache exists **and** library size hasn’t changed, loads from disk.
    Otherwise, rebuilds from scratch and overwrites the cache.
    """
    paths = _paths(kind)

    # fetch current library list once; we need its length anyway
    lib_df = fetch_plex_list(media_type=kind)
    cur_len = len(lib_df)

    # decide whether cache is valid
    cache_ok = (
        not force
        and all(p.exists() for k, p in paths.items() if k != "count")
        and paths["count"].exists()
        and int(paths["count"].read_text()) == cur_len
    )

    if cache_ok:
        df = pd.read_parquet(paths["df"])
        X = np.load(paths["X"])
        knn = joblib.load(paths["knn"])
        return df, X, knn

    # cache stale or missing ------------------------------------------------
    _delete_cache(kind)

    # enrich metadata (heavy part)
    enricher = Movie() if kind == "movie" else TVShow()
    meta_df = enricher.enrich_with_tmdb(lib_df)

    df = pd.concat([lib_df.reset_index(drop=True), meta_df.reset_index(drop=True)], axis=1)
    X = Model().build_features(df)
    knn = Model().train_index(X)

    # write cache
    df.to_parquet(paths["df"])
    np.save(paths["X"], X)
    joblib.dump(knn, paths["knn"])
    paths["count"].write_text(str(cur_len))
    return df, X, knn


def recommend_from_seeds(
    seeds: List[str],
    kind: str,
    per_seed: int = 5,
    top_n: int = 25,
    *,
    force: bool = False,
) -> pd.DataFrame:
    """Return a deduplicated recommendation list.

    • If *force* is True the cache is ignored and rebuilt.
    """
    df, X, knn = _build(kind, force=force)

    rec_frames = []
    for title in seeds:
        try:
            recs = Model().recommend(title, df, X, knn).head(per_seed)
            recs["seed"] = title
            rec_frames.append(recs)
        except ValueError:
            # Title not in library (maybe freshly added) – trigger rebuild once
            if not force:
                return recommend_from_seeds(seeds, kind, per_seed, top_n, force=True)
            continue

    if not rec_frames:
        return pd.DataFrame()

    out = (
        pd.concat(rec_frames)
        .drop_duplicates("title", keep="first")
        .sort_values("score", ascending=False)
        .head(top_n)
        .reset_index(drop=True)
    )
    return out

if __name__ == "__main__":
    print(recommend_from_seeds(["Inception", "Anchorman: The Legend of Ron Burgundy"], "movie"))