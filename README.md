**Plex Reccomendation Algorithm**

This project is still a work in progress, however it does mostly work. 

### Installation
1) pip install requirements.txt
2) Copy .env.template to .env
    2.1) Replace PLEX_BASE_URL with your Plex server
    2.2) Replace PLEX_TOKEN with your PLEX_X_TOKEN. 
        2.2.1) This can be found by going to your Plex library, finding any entry, clicking the 3 dots at the bottom of the movie/tv show card
        2.2.2) Scroll to the bottom of the list, and click "Get Info"
        2.2.3) Click "View XML"
        2.2.4) In the address bar, the last section of the url will contain a part saying "X-Plex-Token. Copy that, and paste it into .env
    2.3) Get a TMDB API key, and paste it in beside TMDB_TOKEN
        2.3.1) This can be done by first going to https://www.themoviedb.org/settings/api?language=en-CA
        2.3.2) Follow the instructions to create an API key, and paste that key beside TMDB_TOKEN in .env
    2.4) Copy your Tautulli information beside TAUTULLI_BASE_URL and TAUTULLI_TOKEN.
        2.4.1) Tautulli installation guides can be found on their Github repo: https://github.com/Tautulli/Tautulli?tab=readme-ov-file

### Using the service

