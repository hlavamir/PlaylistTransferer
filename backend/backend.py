#!/usr/bin/env python3
"""HTTP bridge: SwiftUI app ↔ transfer.py logic."""

import argparse
import json
import os
import shutil
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
import transfer

_CONFIG_DIR = transfer._CONFIG_DIR
_ENV_PATH = os.path.join(_CONFIG_DIR, ".env")

# Holds the most recently fetched playlist between /playlist/fetch and /playlist/import.
_fetched: dict = {}


def _load_credentials() -> dict:
    creds = {"client_id": "", "client_secret": ""}
    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH) as f:
            for line in f:
                key, _, val = line.partition("=")
                k = key.strip()
                if k == "SPOTIFY_CLIENT_ID":
                    creds["client_id"] = val.strip()
                elif k == "SPOTIFY_CLIENT_SECRET":
                    creds["client_secret"] = val.strip()
    return creds


def _save_credentials(client_id: str, client_secret: str) -> None:
    os.makedirs(_CONFIG_DIR, exist_ok=True)
    with open(_ENV_PATH, "w") as f:
        f.write(f"SPOTIFY_CLIENT_ID={client_id}\n")
        f.write(f"SPOTIFY_CLIENT_SECRET={client_secret}\n")
        f.write("SPOTIFY_REDIRECT_URI=https://google.com\n")
    load_dotenv(_ENV_PATH, override=True)


def _delete_all() -> None:
    if os.path.exists(_CONFIG_DIR):
        shutil.rmtree(_CONFIG_DIR)
    os.makedirs(_CONFIG_DIR, exist_ok=True)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress request log

    def _send(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _err(self, msg: str, status: int = 400) -> None:
        self._send({"error": msg}, status)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(n)) if n else {}

    # ── GET ───────────────────────────────────────────────────────────────────

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path

        if path == "/status":
            creds = _load_credentials()
            has_creds = bool(creds["client_id"] and creds["client_secret"])
            has_token = transfer.has_valid_token() if has_creds else False
            self._send({"has_token": has_token, "has_credentials": has_creds})

        elif path == "/credentials":
            self._send(_load_credentials())

        elif path == "/auth/url":
            client_id = qs.get("client_id", [""])[0]
            client_secret = qs.get("client_secret", [""])[0]
            if not client_id or not client_secret:
                return self._err("client_id and client_secret required")
            try:
                self._send({"url": transfer.get_auth_url(client_id, client_secret)})
            except Exception as e:
                self._err(str(e))

        elif path == "/playlist/exists":
            name = qs.get("name", [""])[0]
            try:
                self._send({"exists": transfer.playlist_exists(name)})
            except Exception as e:
                self._err(str(e))

        else:
            self._err("Not found", 404)

    # ── POST ──────────────────────────────────────────────────────────────────

    def do_POST(self):
        path = urlparse(self.path).path
        body = self._body()

        if path == "/credentials":
            cid = body.get("client_id", "").strip()
            sec = body.get("client_secret", "").strip()
            if not cid or not sec:
                return self._err("client_id and client_secret required")
            _save_credentials(cid, sec)
            self._send({})

        elif path == "/auth/exchange":
            cid = body.get("client_id", "").strip()
            sec = body.get("client_secret", "").strip()
            redir = body.get("redirect_response", "").strip()
            if not all([cid, sec, redir]):
                return self._err("client_id, client_secret, redirect_response required")
            try:
                transfer.exchange_token(cid, sec, redir)
                self._send({})
            except Exception as e:
                self._err(str(e))

        elif path == "/playlist/fetch":
            url = body.get("url", "").strip()
            if not url:
                return self._err("url required")
            try:
                name, tracks = transfer.fetch_spotify_playlist(url, interactive=False)
                _fetched["name"] = name
                _fetched["tracks"] = tracks
                self._send({"name": name, "track_count": len(tracks)})
            except Exception as e:
                self._err(str(e))

        elif path == "/playlist/import":
            if not _fetched:
                return self._err("Call /playlist/fetch first")
            mode = body.get("mode", "new")
            try:
                result = transfer.run_transfer_from_fetched(
                    _fetched["name"],
                    _fetched["tracks"],
                    mode,
                    log=lambda _: None,
                )
                self._send({
                    "playlist_name": result["playlist_name"],
                    "total": result["total"],
                    "matched": result["matched"],
                    "added": result["added"],
                    "not_found": [
                        [str(t), round(float(score), 1)]
                        for t, score, _ in result["not_found"]
                    ],
                    "low_confidence": [
                        [str(sp), str(loc), round(float(score), 1)]
                        for sp, loc, score in result["low_confidence"]
                    ],
                })
            except Exception as e:
                self._err(str(e))

        else:
            self._err("Not found", 404)

    # ── DELETE ────────────────────────────────────────────────────────────────

    def do_DELETE(self):
        if urlparse(self.path).path == "/credentials":
            _delete_all()
            self._send({})
        else:
            self._err("Not found", 404)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=17432)
    args = parser.parse_args()

    server = HTTPServer(("127.0.0.1", args.port), Handler)
    server.allow_reuse_address = True
    print(f"READY:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
