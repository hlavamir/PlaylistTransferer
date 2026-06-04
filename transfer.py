#!/usr/bin/env python3
"""Transfer a Spotify playlist into the macOS Music app."""

import os
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass

import spotipy
from dotenv import load_dotenv
from rapidfuzz import fuzz
from spotipy.oauth2 import SpotifyOAuth

# Config and token cache live in ~/.playlist-transferer so they survive
# across runs whether executed from the repo or as a bundled .app.
_CONFIG_DIR = os.path.expanduser("~/.playlist-transferer")
os.makedirs(_CONFIG_DIR, exist_ok=True)

load_dotenv(os.path.join(_CONFIG_DIR, ".env"))  # bundled app location
load_dotenv()                                    # repo .env fallback

MATCH_THRESHOLD = 80  # minimum score (0-100) to consider a track matched
SPOTIFY_FOLDER = "Spotify"

# ── ANSI colours ──────────────────────────────────────────────────────────────
_RESET  = "\033[0m"
_BOLD   = "\033[1m"
_DIM    = "\033[2m"
_CYAN   = "\033[36m"
_GREEN  = "\033[32m"
_YELLOW = "\033[33m"
_RED    = "\033[31m"

def _c(text: str, *codes: str) -> str:
    return "".join(codes) + str(text) + _RESET


@dataclass
class Track:
    title: str
    artist: str

    def search_key(self) -> str:
        return _normalize(f"{self.title} {self.artist}")

    def __str__(self) -> str:
        return f"{self.artist} — {self.title}"


# ── Spotify ───────────────────────────────────────────────────────────────────

def fetch_spotify_playlist(url: str) -> tuple[str, list[Track]]:
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit(
            "Error: SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET must be set "
            "in a .env file or environment variables."
        )

    redirect_uri = os.environ.get("SPOTIFY_REDIRECT_URI", "https://google.com")
    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope="playlist-read-private playlist-read-collaborative",
        open_browser=False,
        cache_path=os.path.join(_CONFIG_DIR, ".spotify-token"),
    )

    if not auth_manager.get_cached_token():
        auth_url = auth_manager.get_authorize_url()
        print(f"\nOpen this URL in your browser to authorise:\n\n  {auth_url}\n")
        print("After authorising, your browser will show an error — that's expected.")
        response = input("Paste the full redirect URL from the address bar here: ").strip()
        code = auth_manager.parse_response_code(response)
        auth_manager.get_access_token(code, check_cache=False)

    sp = spotipy.Spotify(auth_manager=auth_manager)

    playlist_id = _extract_playlist_id(url)
    playlist = sp.playlist(playlist_id)
    if playlist is None:
        sys.exit("Error: could not fetch playlist. Check the URL and your credentials.")

    name: str = playlist["name"]

    tracks: list[Track] = []
    first_page = sp.playlist_items(playlist_id)
    if first_page is None:
        sys.exit("Error: could not fetch playlist tracks.")
    page: dict = first_page
    while True:
        for item in page["items"]:
            t = item.get("item") or item.get("track")  # API returns "item" in newer responses
            if not t or not isinstance(t, dict):
                continue
            title: str = t["name"]
            artist: str = t["artists"][0]["name"] if t.get("artists") else ""
            tracks.append(Track(title=title, artist=artist))

        if not page.get("next"):
            break
        next_page = sp.next(page)
        if next_page is None:
            break
        page = next_page

    return name, tracks


def _extract_playlist_id(url: str) -> str:
    # handles both https://open.spotify.com/playlist/ID and spotify:playlist:ID
    match = re.search(r"playlist[/:]([A-Za-z0-9]+)", url)
    if not match:
        sys.exit(f"Error: could not parse playlist ID from: {url}")
    return match.group(1)


# ── macOS Music library ───────────────────────────────────────────────────────

def fetch_local_tracks() -> list[Track]:
    # Build a newline-delimited string inside AppleScript to avoid the
    # default comma-separated list output that collides with artist commas.
    script = """
    tell application "Music"
        set trackList to {}
        repeat with t in (every track of library playlist 1)
            set end of trackList to (name of t) & "|||" & (artist of t)
        end repeat
        set AppleScript's text item delimiters to linefeed
        set output to trackList as string
        set AppleScript's text item delimiters to ""
        return output
    end tell
    """
    result = _run_applescript(script)
    tracks: list[Track] = []
    for line in result.strip().splitlines():
        parts = line.split("|||", 1)
        if len(parts) == 2:
            tracks.append(Track(title=parts[0].strip(), artist=parts[1].strip()))
    return tracks


def create_playlist(name: str, folder: str = SPOTIFY_FOLDER) -> None:
    safe_name = name.replace('"', '\\"')
    safe_folder = folder.replace('"', '\\"')
    script = f"""
    tell application "Music"
        if not (exists (some folder playlist whose name is "{safe_folder}")) then
            make new folder playlist with properties {{name:"{safe_folder}"}}
        end if
        set theFolder to (first folder playlist whose name is "{safe_folder}")
        if not (exists (some user playlist whose name is "{safe_name}")) then
            set newPlaylist to make new user playlist with properties {{name:"{safe_name}"}}
            move newPlaylist to theFolder
        end if
    end tell
    """
    _run_applescript(script)


def playlist_exists(name: str) -> bool:
    safe_name = name.replace('"', '\\"')
    script = f"""
    tell application "Music"
        return exists (some user playlist whose name is "{safe_name}")
    end tell
    """
    return _run_applescript(script).strip() == "true"


def get_playlist_track_keys(playlist_name: str) -> set[tuple[str, str]]:
    safe_name = playlist_name.replace('"', '\\"')
    script = f"""
    tell application "Music"
        set trackList to {{}}
        repeat with t in (every track of user playlist "{safe_name}")
            set end of trackList to (name of t) & "|||" & (artist of t)
        end repeat
        set AppleScript's text item delimiters to linefeed
        set output to trackList as string
        set AppleScript's text item delimiters to ""
        return output
    end tell
    """
    result = _run_applescript(script)
    keys: set[tuple[str, str]] = set()
    for line in result.strip().splitlines():
        parts = line.split("|||", 1)
        if len(parts) == 2:
            keys.add((parts[0].strip(), parts[1].strip()))
    return keys


def clear_playlist(playlist_name: str) -> None:
    safe_name = playlist_name.replace('"', '\\"')
    script = f"""
    tell application "Music"
        delete every track of user playlist "{safe_name}"
    end tell
    """
    _run_applescript(script)


def add_track_to_playlist(playlist_name: str, title: str, artist: str) -> None:
    safe_playlist = playlist_name.replace('"', '\\"')
    safe_title = title.replace('"', '\\"')
    safe_artist = artist.replace('"', '\\"')
    script = f"""
    tell application "Music"
        set matchedTracks to (every track of library playlist 1 whose name is "{safe_title}" and artist is "{safe_artist}")
        if (count of matchedTracks) > 0 then
            duplicate item 1 of matchedTracks to (first user playlist whose name is "{safe_playlist}")
        end if
    end tell
    """
    _run_applescript(script)


def _run_applescript(script: str) -> str:
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"AppleScript warning: {result.stderr.strip()}", file=sys.stderr)
    return result.stdout


# ── Matching ──────────────────────────────────────────────────────────────────

_STRIP_QUALIFIERS = re.compile(
    r"\(?(original mix|original version|radio edit|extended mix|extended version|album version|instrumental|edit)\)?",
    re.IGNORECASE,
)
# Strip "feat. Artist Name" / "ft. Artist Name" — present in local titles, absent on Spotify
_STRIP_FEAT = re.compile(r"\b(feat\.?|ft\.?)\s+[^()\[\]-]+", re.IGNORECASE)


def _normalize(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(c for c in nfkd if not unicodedata.combining(c))
    cleaned = _STRIP_FEAT.sub("", ascii_text)
    cleaned = _STRIP_QUALIFIERS.sub("", cleaned)
    cleaned = re.sub(r"\s*[-–]\s*", " ", cleaned)  # "title - remix" → "title remix"
    cleaned = re.sub(r"[()]", " ", cleaned)         # strip parens, keep content
    return re.sub(r"\s{2,}", " ", cleaned).lower().strip()


def build_index(local_tracks: list[Track]) -> list[tuple[str, str, Track]]:
    # Precompute normalised title/artist for each local track once.
    return [(_normalize(t.title), _normalize(t.artist), t) for t in local_tracks]


def find_match(
    spotify_track: Track,
    index: list[tuple[str, str, Track]],
) -> tuple[Track | None, float, Track | None]:
    sp_title = _normalize(spotify_track.title)
    sp_artist = _normalize(spotify_track.artist)

    best_track: Track | None = None
    best_score = 0.0

    for loc_title, loc_artist, track in index:
        # partial_ratio checks if sp_artist appears as a substring of loc_artist —
        # correctly handles "Echonomist" matching "Echonomist, Alexandros Miaris".
        artist_score = fuzz.partial_ratio(sp_artist, loc_artist)
        if artist_score < 60:
            continue
        title_score = fuzz.token_set_ratio(sp_title, loc_title)
        # Require a minimum title contribution to prevent artist-only matches
        # (e.g. same artist, completely different short title) from passing.
        if title_score < 55:
            continue
        combined = title_score * 0.65 + artist_score * 0.35
        if combined > best_score:
            best_score = combined
            best_track = track

    if best_track and best_score >= MATCH_THRESHOLD:
        return best_track, best_score, None
    return None, best_score, best_track  # best_track is the closest miss


# ── Main ──────────────────────────────────────────────────────────────────────

def transfer_playlist(url: str) -> None:
    print(_c("Fetching Spotify playlist…", _CYAN))
    playlist_name, spotify_tracks = fetch_spotify_playlist(url)
    print(f"  {_c(playlist_name, _BOLD)} — {len(spotify_tracks)} tracks")

    print(_c("Scanning local Music library…", _CYAN))
    local_tracks = fetch_local_tracks()
    print(f"  {len(local_tracks)} local tracks found")

    index = build_index(local_tracks)

    matched: list[tuple[Track, Track, float]] = []           # (spotify, local, score)
    not_found: list[tuple[Track, float, Track | None]] = []  # (track, best_score, closest)

    print(_c("Matching tracks…", _CYAN))
    for sp_track in spotify_tracks:
        local, score, closest = find_match(sp_track, index)  # type: ignore[arg-type]
        if local:
            matched.append((sp_track, local, score))
        else:
            not_found.append((sp_track, score, closest))

    mode = "new"
    if playlist_exists(playlist_name):
        print(_c(f"\nPlaylist '{playlist_name}' already exists in Music.", _YELLOW))
        while True:
            choice = input(_c("  [a] Extend with new tracks  [b] Replace entirely: ", _BOLD)).strip().lower()
            if choice in ("a", "b"):
                mode = "extend" if choice == "a" else "replace"
                break
            print("  Please enter 'a' or 'b'.")

    print(_c(f"\nCreating playlist '{playlist_name}' in Music…", _CYAN))
    create_playlist(playlist_name)

    if mode == "replace":
        clear_playlist(playlist_name)
        tracks_to_add = matched
    elif mode == "extend":
        existing = get_playlist_track_keys(playlist_name)
        tracks_to_add = [(sp, loc, s) for sp, loc, s in matched if (loc.title, loc.artist) not in existing]
        skipped = len(matched) - len(tracks_to_add)
        if skipped:
            print(_c(f"  Skipping {skipped} track(s) already in the playlist.", _DIM))
    else:
        tracks_to_add = matched

    for sp_track, local_track, _ in tracks_to_add:
        add_track_to_playlist(playlist_name, local_track.title, local_track.artist)

    # ── Report ────────────────────────────────────────────────────────────────
    print(f"\n{'─'*60}")
    ratio = len(matched) / len(spotify_tracks) if spotify_tracks else 1
    summary_colour = _GREEN if ratio >= 0.8 else _YELLOW if ratio >= 0.5 else _RED
    added_label = f"{len(tracks_to_add)} added" if mode in ("extend", "replace") else f"{len(matched)} added"
    print(_c(f"Done.  {added_label} / {len(spotify_tracks)} tracks in playlist.", _BOLD, summary_colour))

    if not_found:
        print(_c(f"\n{len(not_found)} track(s) not found in local library:", _RED))
        for t, best_score, closest in sorted(not_found, key=lambda x: x[1], reverse=True):
            score_str = _c(f"[{best_score:4.1f}]", _DIM)
            print(f"  {_c('✗', _RED)}  {score_str}  {t}")
            if closest and best_score > 0:
                print(_c(f"         closest: {closest}", _DIM))

    low_confidence = [(sp, loc, s) for sp, loc, s in matched if s < 94]
    if low_confidence:
        print(_c(f"\n{len(low_confidence)} low-confidence match(es) — verify manually:", _YELLOW))
        for sp, loc, score in low_confidence:
            score_str = _c(f"[{score:4.1f}]", _DIM)
            print(f"  {_c('?', _YELLOW)}  {score_str}  {sp}  →  {_c(str(loc), _DIM)}")

    print(f"{'─'*60}")


def setup_wizard() -> None:
    """Run once when no credentials file exists."""
    env_path = os.path.join(_CONFIG_DIR, ".env")
    print(_c("\nNo credentials found. Let's set them up.", _YELLOW, _BOLD))
    print(
        "\nYou need a free Spotify Developer app to get a Client ID and Secret.\n"
        "\n  1. Go to https://developer.spotify.com/dashboard and log in"
        "\n  2. Click Create app — any name/description is fine"
        "\n  3. Set Redirect URI to:  https://google.com  and save"
        "\n  4. Open the app → Settings → copy Client ID and Client Secret\n"
    )
    client_id = input(_c("Client ID:     ", _BOLD)).strip()
    client_secret = input(_c("Client Secret: ", _BOLD)).strip()
    if not client_id or not client_secret:
        print(_c("Error: both values are required. Exiting.", _RED))
        sys.exit(1)
    with open(env_path, "w") as f:
        f.write(f"SPOTIFY_CLIENT_ID={client_id}\n")
        f.write(f"SPOTIFY_CLIENT_SECRET={client_secret}\n")
        f.write("SPOTIFY_REDIRECT_URI=https://google.com\n")
    load_dotenv(env_path, override=True)
    print(_c("\nCredentials saved. You're all set!\n", _GREEN))


def main() -> None:
    print(_c("Spotify → macOS Music Playlist Transferer", _BOLD, _CYAN))
    print("─" * 60)

    if not os.path.exists(os.path.join(_CONFIG_DIR, ".env")):
        setup_wizard()

    while True:
        url = input(_c("\nSpotify playlist URL (or 'q' to quit): ", _BOLD)).strip()
        if url.lower() in ("q", "quit", "exit", ""):
            print("Bye!")
            break
        try:
            transfer_playlist(url)
        except Exception as e:
            print(_c(f"\nError: {e}", _RED))

        again = input(_c("\nImport another playlist? [y/N] ", _BOLD)).strip().lower()
        if again != "y":
            print("Bye!")
            break


if __name__ == "__main__":
    main()
