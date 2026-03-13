from __future__ import annotations

import argparse
import hashlib
import html
import json
import logging
import os
import secrets
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from dotenv import load_dotenv
from plexapi.myplex import MyPlexAccount, MyPlexPinLogin
from recommendation_webhook import process_tautulli_payload

load_dotenv(override=True)

from plex_user_tokens import build_connect_url, format_connected_accounts, list_accounts, normalize_identity, save_account, token_file

PLEX_TOKEN = os.getenv("PLEX_TOKEN")
APP_NAME = os.getenv("PLEX_AUTH_APP_NAME", "Plex Recommendation")
APP_VERSION = os.getenv("PLEX_AUTH_APP_VERSION", "1.0")
APP_PLATFORM = os.getenv("PLEX_AUTH_PLATFORM", "Web")
APP_PLATFORM_VERSION = os.getenv("PLEX_AUTH_PLATFORM_VERSION", "1.0")
APP_DEVICE = os.getenv("PLEX_AUTH_DEVICE", "Browser")
APP_DEVICE_NAME = os.getenv("PLEX_AUTH_DEVICE_NAME", "Plex Recommendation Auth")
PENDING_TTL_SECONDS = 900


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


@dataclass
class PendingLogin:
    login: MyPlexPinLogin
    expected_username: str | None
    created_at: float


PENDING_LOGINS: dict[str, PendingLogin] = {}
PENDING_LOCK = threading.Lock()


def _client_identifier() -> str:
    configured = os.getenv("PLEX_AUTH_CLIENT_ID")
    if configured:
        return configured

    digest = hashlib.sha256(str(token_file().resolve()).encode("utf-8")).hexdigest()
    return f"plex-rec-{digest[:24]}"


def _plex_headers() -> dict[str, str]:
    return {
        "X-Plex-Client-Identifier": _client_identifier(),
        "X-Plex-Device": APP_DEVICE,
        "X-Plex-Device-Name": APP_DEVICE_NAME,
        "X-Plex-Platform": APP_PLATFORM,
        "X-Plex-Platform-Version": APP_PLATFORM_VERSION,
        "X-Plex-Product": APP_NAME,
        "X-Plex-Version": APP_VERSION,
    }


def _normalize_query_param(values: list[str] | None) -> str | None:
    if not values:
        return None
    value = values[0].strip()
    return value or None


def _account_matches_hint(account: MyPlexAccount, hint: str | None) -> bool:
    normalized_hint = normalize_identity(hint)
    if not normalized_hint:
        return True

    candidates = {
        normalize_identity(getattr(account, "username", None)),
        normalize_identity(getattr(account, "title", None)),
        normalize_identity(getattr(account, "email", None)),
    }
    return normalized_hint in candidates


def _cleanup_pending_logins() -> None:
    now = time.time()
    with PENDING_LOCK:
        expired_states = [
            state
            for state, pending in PENDING_LOGINS.items()
            if (now - pending.created_at) > PENDING_TTL_SECONDS or pending.login.expired
        ]
        for state in expired_states:
            PENDING_LOGINS.pop(state, None)


def _get_pending_login(state: str) -> PendingLogin | None:
    with PENDING_LOCK:
        return PENDING_LOGINS.get(state)


def _set_pending_login(state: str, pending: PendingLogin) -> None:
    with PENDING_LOCK:
        PENDING_LOGINS[state] = pending


def _pop_pending_login(state: str) -> PendingLogin | None:
    with PENDING_LOCK:
        return PENDING_LOGINS.pop(state, None)


def _external_base_url(handler: BaseHTTPRequestHandler) -> str:
    configured = os.getenv("PLEX_AUTH_BASE_URL", "").rstrip("/")
    if configured:
        return configured

    forwarded_host = handler.headers.get("X-Forwarded-Host")
    host = forwarded_host or handler.headers.get("Host") or f"{handler.server.server_name}:{handler.server.server_port}"
    proto = handler.headers.get("X-Forwarded-Proto", "http")
    return f"{proto}://{host}".rstrip("/")


def _page(title: str, body: str, meta_refresh: str | None = None) -> bytes:
    refresh_html = ""
    if meta_refresh:
        refresh_html = f'<meta http-equiv="refresh" content="{html.escape(meta_refresh, quote=True)}">'

    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  {refresh_html}
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #111827;
      color: #f9fafb;
      margin: 0;
      padding: 32px 16px;
    }}
    main {{
      max-width: 760px;
      margin: 0 auto;
      background: #1f2937;
      border: 1px solid #374151;
      border-radius: 16px;
      padding: 24px;
      box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
    }}
    h1 {{
      margin-top: 0;
      font-size: 1.8rem;
    }}
    p, li {{
      line-height: 1.55;
    }}
    code {{
      background: #111827;
      border: 1px solid #374151;
      border-radius: 6px;
      padding: 2px 6px;
    }}
    a.button, button {{
      display: inline-block;
      background: #fbbf24;
      color: #111827;
      padding: 12px 18px;
      border-radius: 10px;
      text-decoration: none;
      font-weight: 600;
      border: 0;
      cursor: pointer;
    }}
    a.secondary {{
      color: #fbbf24;
    }}
    form {{
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      margin: 20px 0;
    }}
    input {{
      flex: 1 1 260px;
      min-width: 220px;
      padding: 12px 14px;
      border-radius: 10px;
      border: 1px solid #4b5563;
      background: #111827;
      color: #f9fafb;
    }}
    .panel {{
      background: #111827;
      border: 1px solid #374151;
      border-radius: 12px;
      padding: 16px;
      margin-top: 18px;
    }}
    .muted {{
      color: #d1d5db;
    }}
    ul {{
      padding-left: 20px;
    }}
  </style>
</head>
<body>
  <main>
    {body}
  </main>
</body>
</html>
"""
    return document.encode("utf-8")


class AuthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        _cleanup_pending_logins()
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)

        if parsed.path == "/":
            self._serve_index()
            return
        if parsed.path == "/connect":
            self._serve_connect(query)
            return
        if parsed.path == "/start":
            self._start_login(query)
            return
        if parsed.path == "/callback":
            self._complete_login(query)
            return
        if parsed.path == "/healthz":
            self._send_json(200, {"status": "ok"})
            return

        self._send_html(404, _page("Not Found", "<h1>Not found</h1><p>The requested page does not exist.</p>"))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path not in {"/tautulli", "/webhook/tautulli"}:
            self._send_json(404, {"status": "not_found"})
            return

        try:
            payload = self._read_json_or_form_payload()
            result = process_tautulli_payload(payload, log)
            self._send_json(200, result)
        except Exception as exc:  # pragma: no cover - integration path
            log.exception("HTTP webhook failed: %s", exc)
            self._send_json(500, {"status": "error", "reason": str(exc)})

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        log.info("[http] %s - %s", self.address_string(), format % args)

    def _serve_index(self) -> None:
        accounts = format_connected_accounts(list_accounts())
        account_html = "<p class=\"muted\">No shared-user Plex accounts have authenticated yet.</p>"
        if accounts:
            account_html = "<ul>" + "".join(f"<li>{html.escape(account)}</li>" for account in accounts) + "</ul>"

        connect_example = build_connect_url("plex_username")
        example_html = ""
        if connect_example:
            example_html = (
                "<div class=\"panel\">"
                "<p>Direct invite links work too. Replace the username and send this to a user:</p>"
                f"<p><code>{html.escape(connect_example)}</code></p>"
                "</div>"
            )

        body = f"""
<h1>{html.escape(APP_NAME)} account linking</h1>
<p>This page links a shared Plex account to your recommendation service. The user will authenticate on Plex's official sign-in page and then return here automatically.</p>
<form action="/connect" method="get">
  <input name="username" placeholder="Plex username or display name (optional)">
  <button type="submit">Connect a Plex account</button>
</form>
<div class="panel">
  <p><strong>Connected accounts</strong></p>
  {account_html}
</div>
{example_html}
"""
        self._send_html(200, _page("Plex account linking", body))

    def _serve_connect(self, query: dict[str, list[str]]) -> None:
        expected_username = _normalize_query_param(query.get("username"))
        hint_html = ""
        if expected_username:
            hint_html = f"<p><strong>Expected Plex account:</strong> <code>{html.escape(expected_username)}</code></p>"

        start_query = urlencode({"username": expected_username}) if expected_username else ""
        start_url = "/start"
        if start_query:
            start_url = f"{start_url}?{start_query}"

        body = f"""
<h1>Connect your Plex account</h1>
<p>You are about to sign in with Plex and authorize this recommendation service to update your personal Watchlist.</p>
{hint_html}
<p>No manual token copying is required. After you finish signing into Plex, you will be sent back here and the link will be stored automatically.</p>
<p><a class="button" href="{html.escape(start_url, quote=True)}">Continue to Plex</a></p>
<p><a class="secondary" href="/">Back</a></p>
"""
        self._send_html(200, _page("Connect Plex account", body))

    def _start_login(self, query: dict[str, list[str]]) -> None:
        expected_username = _normalize_query_param(query.get("username"))
        state = secrets.token_urlsafe(18)

        try:
            login = MyPlexPinLogin(headers=_plex_headers(), oauth=True)
            callback_url = f"{_external_base_url(self)}/callback?{urlencode({'state': state})}"
            auth_url = login.oauthUrl(forwardUrl=callback_url)
        except Exception as exc:  # pragma: no cover - requires live Plex auth service
            body = f"""
<h1>Unable to start Plex login</h1>
<p>The auth session could not be created.</p>
<div class="panel"><code>{html.escape(str(exc))}</code></div>
<p><a class="secondary" href="/">Back</a></p>
"""
            self._send_html(500, _page("Unable to start Plex login", body))
            return

        _set_pending_login(state, PendingLogin(
            login=login,
            expected_username=expected_username,
            created_at=time.time(),
        ))

        self.send_response(302)
        self.send_header("Location", auth_url)
        self.end_headers()

    def _complete_login(self, query: dict[str, list[str]]) -> None:
        state = _normalize_query_param(query.get("state"))
        if not state:
            self._send_html(400, _page("Missing state", "<h1>Missing login state</h1><p>This login link is incomplete.</p>"))
            return

        pending = _get_pending_login(state)
        if not pending:
            self._send_html(404, _page("Session expired", "<h1>Login session not found</h1><p>This link has expired. Start again from the connect page.</p>"))
            return

        success = False
        for _ in range(10):
            try:
                success = pending.login.checkLogin()
            except Exception:
                success = False
                pending.login.expired = True
                break
            if success:
                break
            time.sleep(1)

        if pending.login.expired:
            _pop_pending_login(state)
            self._send_html(410, _page("Session expired", "<h1>Login session expired</h1><p>Start again from the connect page.</p>"))
            return

        if not success or not pending.login.token:
            retry_query = urlencode({"state": state})
            body = f"""
<h1>Waiting for Plex</h1>
<p>Your browser is back, but Plex has not finished handing off the token yet.</p>
<p>This page will retry automatically.</p>
<p><a class="button" href="/callback?{html.escape(retry_query, quote=True)}">Retry now</a></p>
"""
            self._send_html(200, _page("Waiting for Plex", body, meta_refresh=f"2; url=/callback?{retry_query}"))
            return

        token = pending.login.token
        try:
            account = MyPlexAccount(token=token)
        except Exception as exc:  # pragma: no cover - requires live Plex auth service
            _pop_pending_login(state)
            body = f"""
<h1>Token retrieval failed</h1>
<p>Plex returned a token, but it could not be verified.</p>
<div class="panel"><code>{html.escape(str(exc))}</code></div>
<p><a class="secondary" href="/">Back</a></p>
"""
            self._send_html(500, _page("Token retrieval failed", body))
            return

        if pending.expected_username and not _account_matches_hint(account, pending.expected_username):
            _pop_pending_login(state)
            body = f"""
<h1>Wrong Plex account</h1>
<p>This link expected <code>{html.escape(pending.expected_username)}</code>, but Plex returned <code>{html.escape(account.username)}</code>.</p>
<p>Sign out of Plex in your browser and try again with the correct account.</p>
<p><a class="secondary" href="/">Back</a></p>
"""
            self._send_html(409, _page("Wrong Plex account", body))
            return

        save_account(account, token, expected_username=pending.expected_username)
        _pop_pending_login(state)

        display_name = account.title or account.username
        body = f"""
<h1>Account connected</h1>
<p><strong>{html.escape(display_name)}</strong> is now linked. Future recommendation runs can update this Plex account's Watchlist automatically.</p>
<div class="panel">
  <p><strong>Plex username</strong>: <code>{html.escape(account.username)}</code></p>
  <p><strong>Stored token file</strong>: <code>{html.escape(str(token_file()))}</code></p>
</div>
"""
        self._send_html(200, _page("Account connected", body))

    def _send_html(self, status_code: int, document: bytes) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(document)))
        self.end_headers()
        self.wfile.write(document)

    def _send_json(self, status_code: int, payload: dict) -> None:
        document = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(document)))
        self.end_headers()
        self.wfile.write(document)

    def _read_json_or_form_payload(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()

        if not raw:
            return {}

        if content_type == "application/json":
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}

        if content_type == "application/x-www-form-urlencoded":
            fields = {
                key: values[0] if len(values) == 1 else values
                for key, values in parse_qs(raw, keep_blank_values=True).items()
            }
            payload = fields.get("payload")
            if isinstance(payload, str):
                try:
                    parsed = json.loads(payload)
                    if isinstance(parsed, dict):
                        return parsed
                except json.JSONDecodeError:
                    pass
            return fields

        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {
                key: values[0] if len(values) == 1 else values
                for key, values in parse_qs(raw, keep_blank_values=True).items()
            }


def _default_base_url(port: int) -> str:
    configured = os.getenv("PLEX_AUTH_BASE_URL", "").rstrip("/")
    if configured:
        return configured
    return f"http://localhost:{port}"


def _print_links(port: int) -> int:
    if not PLEX_TOKEN:
        print("PLEX_TOKEN must be set to print shared-user auth links.")
        return 1

    account = MyPlexAccount(token=PLEX_TOKEN)
    base_url = _default_base_url(port)
    print(f"Auth base URL: {base_url}")
    if not os.getenv("PLEX_AUTH_BASE_URL"):
        print("PLEX_AUTH_BASE_URL is not set. The links below default to localhost; change that before sending them to remote users.")
    print("")

    for user in account.users():
        identity = user.username or user.title
        if not identity:
            continue
        url = f"{base_url}/connect?{urlencode({'username': identity})}"
        label = identity
        if user.title and user.title != identity:
            label = f"{identity} ({user.title})"
        print(f"{label}: {url}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Start the Plex shared-user auth server.")
    parser.add_argument("--host", default=os.getenv("PLEX_AUTH_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("PLEX_AUTH_PORT", "3187")))
    parser.add_argument("--print-links", action="store_true", help="Print user-specific auth URLs and exit.")
    args = parser.parse_args()

    if args.print_links:
        return _print_links(args.port)

    server = ThreadingHTTPServer((args.host, args.port), AuthHandler)
    base_url = _default_base_url(args.port)
    print(f"Starting Plex auth server on http://{args.host}:{args.port}")
    print(f"External auth URL base: {base_url}")
    print(f"Token store: {token_file()}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping auth server.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
