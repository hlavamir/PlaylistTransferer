# Spotify → macOS Music Playlist Transferer

Transfers Spotify playlists into the macOS Music app by fuzzy-matching tracks against your local library.

---

## Running the compiled app

The compiled app lives at `dist/PlaylistTransferer`. No Python or any other dependency required.

### First launch — credential setup

On first launch the app will guide you through a one-time setup:

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and log in
2. Click **Create app** — any name and description is fine
3. Set **Redirect URI** to `https://google.com` and save
4. Open the app → **Settings** → copy your **Client ID** and **Client Secret**
5. Paste them into the prompts when the app asks

Credentials are saved to `~/.playlist-transferer/.env` and reused on every subsequent launch.

### First launch — Spotify authorisation

After entering credentials the app will ask you to authorise with Spotify once:

1. Open the printed URL in your browser and click **Agree**
2. The browser redirects to Google — that's expected
3. Copy the full URL from the address bar (e.g. `https://www.google.com/?code=AQ...`)
4. Paste it back into the terminal

The token is cached at `~/.playlist-transferer/.spotify-token` and reused on future runs.

### Usage

Paste a Spotify playlist URL when prompted and the app will:

- Fetch all tracks from the playlist
- Scan your local Music library
- Fuzzy-match tracks by title and artist
- Create a playlist inside a **Spotify** folder in the Music app
- Report matched tracks, not-found tracks with their closest local match, and low-confidence matches to verify manually

After each import you'll be asked whether to import another playlist.

---

## Repository setup

### Prerequisites

- [pyenv](https://github.com/pyenv/pyenv) with Python 3.12.9 installed

### Install

```bash
pyenv local 3.12.9
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure credentials

See First launch chapter above.

### Run from source

```bash
source .venv/bin/activate
python transfer.py
```

### Rebuild the compiled app

```bash
source .venv/bin/activate
pyinstaller --onefile --name "PlaylistTransferer" --console transfer.py
```

Output lands in `dist/PlaylistTransferer`.

---

## License

MIT — see [LICENSE](LICENSE).

---

*This project is not affiliated with or endorsed by Spotify or Apple.*
