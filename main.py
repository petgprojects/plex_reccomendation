from plexapi.server import PlexServer
from tmdbv3api import TMDb, Movie
from collections import Counter

baseurl = 'http://peterubuntuserver.ddns.net:32400'
token = 'ydWQy8X6StWBJVPHiLf2'
plex = PlexServer(baseurl, token)

tmdb = TMDb()
tmdb.api_key = 'ea023fa0879737d0cfd9ae3ca7365a6e'
movie_api = Movie()

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

ids = get_tmdb_ids(plex)
tmdb_id = ids[0]
data = movie_api.details(tmdb_id)
print(data)

actor_counter = Counter()
director_counter = Counter()

# First pass: build name frequency
for tmdb_id in ids:
    try:
        credits = movie_api.credits(tmdb_id)
        cast = credits.get('cast', [])
        crew = credits.get('crew', [])

        # Top 5 billed actors
        for actor in cast[:5]:
            actor_counter[actor['name']] += 1

        # Director(s)
        for crew_member in crew:
            if crew_member['job'] == 'Director':
                director_counter[crew_member['name']] += 1
    except:
        continue

# Select most common people across all movies
top_actors = [a for a, _ in actor_counter.most_common(100)]
top_directors = [d for d, _ in director_counter.most_common(50)]

print(top_actors)