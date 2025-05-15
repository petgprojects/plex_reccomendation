**Plex Reccomendation Algorithm**

This project is still a work in progress, however it does mostly work. 

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
3. Add the repo to Tautulli's docker image:
    1. In the volumes section, add ```- /path/to/repo/plex_reccomendation:/config/plex_reccomendation```
4. Have Tautulli use the script

### Using the service
#### On first run
To generate the playlists/collections in the first go, run ```python main.py```. This will generate playlists and collections for all your users based on what they recently watched. The playlists will hide for all the other users, but collections will be available for all users. To fix this, follow these steps:

1. In plex, go to your TV Shows library, and click "Collections".
2. At each Collection, hover over it and click the pencil icon.
3. Click "Labels", and add a label representing the user the collection was made for (I like to just use the user's name)
4. In the top right hand corner of Plex, click the "Wrench" icon (Settings)
5. On the left hand side, under your username, click "Manage Library Access"
6. For each user:
    1. Click their name
    2. Click "Restrictions"
    3. Click "Movies"
    4. Set "ALLOW ONLY LABELS" to be the label you made for that user
    5. Repeat steps 3/4 for TV as well

#### Integrating with Tautulli to automatically run
You can integrate this service directly into Tautulli such that it will automatically run whenever a user is finished watching something, so their reccomendations will automatically update.

1. In Tautulli, click the "Gear" icon in the top right corner
2. Click "Notification Agents"
3. Click "Add a new notification agent"
4. Scroll to "Script" and click it
    1. For "Script Folder", click "Browse", and browse to /config/plex_reccomendation
    2. For "Script File", scroll to the bottom and select "webhook.sh"
    3. For Script Timeout, select 0.
5. Still in the "Script Settings" dialogue, click "Triggers"
    1. Select "Playback Stop", and "Watched".
6. Still in the "Script Settings" dialogue, click "Arguments"
    1. Open the "Playback Stop" sub-menu, and paste ```--action {action} --media_type {media_type} --username {username} --title {title}``` into "Script Arguments"
    2. Open the "Watched" sub-menu, and paste ```--action {action} --media_type {media_type} --username {username} --title {title}```
7. Click "Save" at the bottom right corner.

### Contributing to the project
Right now I haven't really thought about this, but if you want to contribute just make a branch off of main, and submit a PR when you're ready. I'll approve it when I get a chance.

### Future Goals
Right now I have two plans for this project:
1. Clean up the code (a lot). It's a mess, I know. I didn't really go into this with a plan, so I'm going to try and spend some time cleaning it up and making it more readable and maintainable. 
2. Full TMDB caching: I want to implement a feature where I can reccomend users movies/shows that aren't in their library, by indexing all of TMDB in my vector database.