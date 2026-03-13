**Plex Reccomendation Algorithm**

This project is still a work in progress, however it does mostly work. 
# IMPORTANT
It looks like I was misunderstood on how collections work, I can't find a way to hide recommendations for all users without entirely hiding the collection from the Home screen. I'm looking into adding it to the user's watchlist instead
### Installation
1. ```pip install requirements.txt```
2. Copy .env.template to .env
    1. Replace PLEX_BASE_URL with your Plex server
    2. Replace PLEX_TOKEN with your PLEX_X_TOKEN. 
        1. This can be found by going to your Plex library, finding any entry, clicking the 3 dots at the bottom of the movie/tv show card
        2. Scroll to the bottom of the list, and click "Get Info"
        3. Click "View XML"
        4. In the address bar, the last section of the url will contain a part saying "X-Plex-Token. Copy that, and paste it into .env
    3. Get a TMDB API key, and paste it in beside TMDB_TOKEN
        1. This can be done by first going to https://www.themoviedb.org/settings/api?language=en-CA
        2. Follow the instructions to create an API key, and paste that key beside TMDB_TOKEN in .env
    4. Copy your Tautulli information beside TAUTULLI_BASE_URL and TAUTULLI_TOKEN.
        1. Tautulli installation guides can be found on their Github repo: https://github.com/Tautulli/Tautulli?tab=readme-ov-file
    5. If you want to use Plex Watchlists to store your recommendations, set WATCHLIST=TRUE.
        1. Plex Home users work immediately.
        2. Regular shared users need to authorize once through the included auth server before their Watchlist can be updated.
        3. If those users are outside your LAN, set `PLEX_AUTH_BASE_URL` in your `.env` to the public root URL they can open in a browser, such as `https://plex-auth.example.com`.
3. Add the repo to Tautulli's docker image:
    1. In the volumes section, add ```- /path/to/repo/plex_reccomendation:/config/plex_reccomendation```
4. Have Tautulli use the script

### Linking shared users for Watchlist mode
There is no popup inside Plex for this. Instead, users visit a normal web page hosted by this project, Plex handles the login on its side, and then sends them back once the token has been granted.

1. Start the auth server with `./auth_server.sh --host 0.0.0.0 --port 3187`
2. If your users are remote, expose that port or reverse proxy it and set `PLEX_AUTH_BASE_URL` to the externally reachable URL before starting the server.
3. Send users to the public root URL, for example `https://plex.petergelgor.ca/recommendations/`
4. They can click through and sign in without entering a username. The returned Plex account is enough for the service to identify them automatically.
5. Optional: print pre-filled invite links with `./auth_server.sh --print-links` if you want a specific username hint in the URL
6. The user signs into Plex, approves access, and gets redirected back automatically
7. Their account token is stored in `plex_user_tokens.json`, and future recommendation runs can update their Watchlist without Plex Home

If a shared user has not linked their account yet, webhook runs will skip Watchlist updates for that user and log a warning instead of crashing the whole run.

### Docker / Compose setup
If you already run a reverse proxy and a shared Docker stack, the cleanest setup is to run this repo as its own container instead of only mounting it into Tautulli.

The container now serves both:
1. The shared-user Plex auth flow
2. A Tautulli HTTP webhook endpoint at `/tautulli`

Recommended stack shape:
1. Build this repo with the included `Dockerfile`
2. Run the container on your internal Docker network
3. Proxy a public path such as `/recommendations/` to the container so users can complete the one-time Plex auth flow
4. Point Tautulli at the container's `/tautulli` endpoint using a Webhook notification agent

Example container command:
1. `docker build -t plex-recommendation .`
2. `docker run --env-file .env -p 3187:3187 plex-recommendation`

Useful endpoints:
1. `/` or `/connect` for user linking
2. `/tautulli` for incoming Tautulli webhook posts
3. `/healthz` for health checks

### Using the service
#### On first run
To generate the collections in the first go, run ```python main.py```. This will generate collections for all your users based on what they recently watched, if you didn't set ```WATCHLIST=TRUE``` in your .env. Collections will be available for all users. To fix this, follow these steps:

1. In plex, go to your TV Shows/Movies library, and click "Collections".
2. At each Collection, hover over it and click the pencil icon.
3. Click "Labels", and add a label representing the user the collection was made for (I like to just use the user's name)
4. In the top right hand corner of Plex, click the "Wrench" icon (Settings)
5. On the left hand side, under your username, click "Manage Library Access"
6. For each user:
    1. Click their name
    2. Click "Restrictions"
    3. Click "Movies"
    4. Set "EXCLUDE LABELS" to be the labels you made for all other users so they only see their own collections
    5. Repeat steps 3/4 for TV as well

#### Integrating with Tautulli to automatically run
You can integrate this service directly into Tautulli such that it will automatically run whenever a user is finished watching something, so their reccomendations will automatically update.

There are now two ways to do that:
1. Legacy: Tautulli Script agent using `webhook.sh`
2. Recommended for Docker stacks: Tautulli Webhook agent posting to the container's `/tautulli` endpoint

Webhook mode:
1. In Tautulli, click the "Gear" icon in the top right corner
2. Click "Notification Agents"
3. Click "Add a new notification agent"
4. Choose "Webhook"
5. Set the webhook URL to your service, for example `http://plex-recommendation:3187/tautulli` inside Docker or your own proxied URL
6. Enable the `Playback Stop` and `Watched` triggers
7. Send a JSON body like `{"action":"{action}","media_type":"{media_type}","username":"{username}"}`
8. Save the agent

Script mode:
1. In Tautulli, click the "Gear" icon in the top right corner
2. Click "Notification Agents"
3. Click "Add a new notification agent"
4. Scroll to "Script" and click it
5. For "Script Folder", click "Browse", and browse to `/config/plex_reccomendation`
6. For "Script File", scroll to the bottom and select `webhook.sh`
7. For "Script Timeout", select `0`
8. Enable the `Playback Stop` and `Watched` triggers
9. In the "Arguments" section:
    1. For `Playback Stop`, paste `--action {action} --media_type {media_type} --username {username} --title {title}`
    2. For `Watched`, paste `--action {action} --media_type {media_type} --username {username} --title {title}`
10. Click "Save" at the bottom right corner

### Contributing to the project
Right now I haven't really thought about this, but if you want to contribute just make a branch off of main, and submit a PR when you're ready. I'll approve it when I get a chance.

### Future Goals
Right now I have two plans for this project:
1. Clean up the code (a lot). It's a mess, I know. I didn't really go into this with a plan, so I'm going to try and spend some time cleaning it up and making it more readable and maintainable. 
2. Full TMDB caching: I want to implement a feature where I can reccomend users movies/shows that aren't in their library, by indexing all of TMDB in my vector database.
