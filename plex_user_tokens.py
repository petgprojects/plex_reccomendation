from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode


DEFAULT_TOKEN_FILE = Path(__file__).resolve().with_name("plex_user_tokens.json")


def token_file() -> Path:
    return Path(os.getenv("PLEX_USER_TOKEN_FILE", str(DEFAULT_TOKEN_FILE)))


def normalize_identity(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    return value.casefold()


def _empty_store() -> dict:
    return {"accounts": []}


def _load_store() -> dict:
    store_path = token_file()
    if not store_path.exists():
        return _empty_store()

    try:
        data = json.loads(store_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return _empty_store()

    if not isinstance(data, dict):
        return _empty_store()

    accounts = data.get("accounts")
    if not isinstance(accounts, list):
        data["accounts"] = []

    return data


def _write_store(data: dict) -> None:
    store_path = token_file()
    store_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(
        dir=store_path.parent,
        prefix=f"{store_path.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")

        os.replace(temp_path, store_path)
        try:
            os.chmod(store_path, 0o600)
        except OSError:
            pass
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _record_identities(record: dict) -> set[str]:
    identities: set[str] = set()

    for field in ("username", "title", "email"):
        normalized = normalize_identity(record.get(field))
        if normalized:
            identities.add(normalized)

    for alias in record.get("aliases", []):
        normalized = normalize_identity(alias)
        if normalized:
            identities.add(normalized)

    return identities


def _record_sort_key(record: dict) -> tuple[str, str]:
    return (
        (record.get("username") or "").casefold(),
        (record.get("title") or "").casefold(),
    )


def list_accounts() -> list[dict]:
    store = _load_store()
    accounts = [record for record in store["accounts"] if isinstance(record, dict)]
    return sorted(accounts, key=_record_sort_key)


def find_account_record(identity: str | None) -> dict | None:
    normalized = normalize_identity(identity)
    if not normalized:
        return None

    for record in list_accounts():
        if normalized in _record_identities(record):
            return record

    return None


def save_account(account, token: str, expected_username: str | None = None) -> dict:
    store = _load_store()
    now = datetime.now(timezone.utc).isoformat()
    uuid = getattr(account, "uuid", None)
    account_id = getattr(account, "id", None)
    username = getattr(account, "username", None)
    title = getattr(account, "title", None)
    email = getattr(account, "email", None)

    existing: dict | None = None
    for record in store["accounts"]:
        if not isinstance(record, dict):
            continue
        if uuid and record.get("uuid") == uuid:
            existing = record
            break
        if account_id and record.get("id") == account_id:
            existing = record
            break

    aliases: set[str] = set()
    if existing:
        aliases.update(alias for alias in existing.get("aliases", []) if isinstance(alias, str))
    if expected_username:
        aliases.add(expected_username)

    actual_identities = {
        normalize_identity(username),
        normalize_identity(title),
        normalize_identity(email),
    }
    clean_aliases = sorted(
        alias
        for alias in aliases
        if normalize_identity(alias) and normalize_identity(alias) not in actual_identities
    )

    record = {
        "aliases": clean_aliases,
        "connected_at": existing.get("connected_at", now) if existing else now,
        "email": email,
        "id": account_id,
        "title": title,
        "token": token,
        "updated_at": now,
        "username": username,
        "uuid": uuid,
    }

    if existing:
        store["accounts"] = [
            record if item is existing else item
            for item in store["accounts"]
        ]
    else:
        store["accounts"].append(record)

    store["accounts"] = sorted(
        [item for item in store["accounts"] if isinstance(item, dict)],
        key=_record_sort_key,
    )
    _write_store(store)
    return record


def build_connect_url(username: str | None = None) -> str | None:
    auth_base_url = os.getenv("PLEX_AUTH_BASE_URL", "").rstrip("/")
    if not auth_base_url:
        return None

    url = f"{auth_base_url}/connect"
    if username:
        url = f"{url}?{urlencode({'username': username})}"
    return url


def format_connected_accounts(accounts: Iterable[dict]) -> list[str]:
    lines: list[str] = []
    for record in accounts:
        username = record.get("username") or "(unknown username)"
        title = record.get("title") or ""
        if title and title != username:
            lines.append(f"{username} ({title})")
        else:
            lines.append(username)
    return lines
