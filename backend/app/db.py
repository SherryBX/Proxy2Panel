from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Iterator

from .config import settings


SCHEMA = [
    """CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS node_prefs (
        node_id TEXT PRIMARY KEY,
        favorite INTEGER NOT NULL DEFAULT 0,
        label_override TEXT,
        updated_at INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS traffic_samples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER NOT NULL,
        rx_bytes INTEGER NOT NULL,
        tx_bytes INTEGER NOT NULL,
        node_id TEXT,
        service TEXT NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS audit_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts INTEGER NOT NULL,
        level TEXT NOT NULL,
        action TEXT NOT NULL,
        message TEXT NOT NULL,
        metadata_json TEXT NOT NULL DEFAULT '{}'
    )""",
    """CREATE TABLE IF NOT EXISTS sessions (
        session_id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        expires_at INTEGER NOT NULL,
        created_at INTEGER NOT NULL,
        ip_address TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS auth_failures (
        ip_address TEXT PRIMARY KEY,
        failed_count INTEGER NOT NULL DEFAULT 0,
        last_failed_at INTEGER NOT NULL DEFAULT 0,
        locked_until INTEGER NOT NULL DEFAULT 0
    )""",
]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = _connect()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    now = int(time.time())
    with get_conn() as conn:
        for stmt in SCHEMA:
            conn.execute(stmt)
        defaults = {
            "active_node_id": "",
            "ip_whitelist": settings.default_ip_whitelist,
            "password_hash": "",
            "subscription_token": "",
            "created_at": str(now),
        }
        for key, value in defaults.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings(key, value, updated_at) VALUES (?, ?, ?)",
                (key, value, now),
            )


def get_setting(key: str, default: str = "") -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    now = int(time.time())
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO settings(key, value, updated_at) VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at""",
            (key, value, now),
        )


def upsert_node_pref(node_id: str, favorite: int | None = None, label_override: str | None = None) -> None:
    now = int(time.time())
    with get_conn() as conn:
        current = conn.execute("SELECT * FROM node_prefs WHERE node_id = ?", (node_id,)).fetchone()
        current_favorite = int(current["favorite"]) if current else 0
        current_label = current["label_override"] if current else None
        conn.execute(
            """INSERT INTO node_prefs(node_id, favorite, label_override, updated_at) VALUES (?, ?, ?, ?)
               ON CONFLICT(node_id) DO UPDATE SET favorite = excluded.favorite, label_override = excluded.label_override, updated_at = excluded.updated_at""",
            (
                node_id,
                current_favorite if favorite is None else int(favorite),
                current_label if label_override is None else label_override,
                now,
            ),
        )


def get_node_prefs() -> dict[str, dict[str, Any]]:
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM node_prefs").fetchall()
    return {
        row["node_id"]: {
            "favorite": bool(row["favorite"]),
            "label_override": row["label_override"],
        }
        for row in rows
    }


def insert_traffic_sample(ts: int, rx_bytes: int, tx_bytes: int, node_id: str | None, service: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO traffic_samples(ts, rx_bytes, tx_bytes, node_id, service) VALUES (?, ?, ?, ?, ?)",
            (ts, rx_bytes, tx_bytes, node_id, service),
        )


def fetch_traffic_samples(since_ts: int, node_id: str | None = None, service: str | None = None) -> list[dict[str, Any]]:
    query = "SELECT ts, rx_bytes, tx_bytes, node_id, service FROM traffic_samples WHERE ts >= ?"
    params: list[Any] = [since_ts]
    if node_id:
        query += " AND node_id = ?"
        params.append(node_id)
    if service and service != "all":
        query += " AND service = ?"
        params.append(service)
    query += " ORDER BY ts ASC"
    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def insert_audit_log(level: str, action: str, message: str, metadata: dict[str, Any] | None = None) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO audit_logs(ts, level, action, message, metadata_json) VALUES (?, ?, ?, ?, ?)",
            (int(time.time()), level, action, message, json.dumps(metadata or {}, ensure_ascii=False)),
        )


def fetch_audit_logs(limit: int = 200, query: str = "") -> list[dict[str, Any]]:
    sql = "SELECT * FROM audit_logs"
    params: list[Any] = []
    if query:
        sql += " WHERE message LIKE ? OR action LIKE ? OR metadata_json LIKE ?"
        like = f"%{query}%"
        params.extend([like, like, like])
    sql += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with get_conn() as conn:
        rows = conn.execute(sql, params).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
        result.append(item)
    return result


def create_session(session_id: str, username: str, expires_at: int, ip_address: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO sessions(session_id, username, expires_at, created_at, ip_address) VALUES (?, ?, ?, ?, ?)",
            (session_id, username, expires_at, int(time.time()), ip_address),
        )


def get_session(session_id: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
    return dict(row) if row else None


def delete_session(session_id: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))


def prune_sessions() -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM sessions WHERE expires_at < ?", (int(time.time()),))


def get_auth_failure(ip_address: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM auth_failures WHERE ip_address = ?", (ip_address,)).fetchone()
    return dict(row) if row else None


def set_auth_failure(ip_address: str, failed_count: int, last_failed_at: int, locked_until: int) -> None:
    with get_conn() as conn:
        conn.execute(
            """INSERT INTO auth_failures(ip_address, failed_count, last_failed_at, locked_until) VALUES (?, ?, ?, ?)
               ON CONFLICT(ip_address) DO UPDATE SET
                 failed_count = excluded.failed_count,
                 last_failed_at = excluded.last_failed_at,
                 locked_until = excluded.locked_until""",
            (ip_address, failed_count, last_failed_at, locked_until),
        )


def clear_auth_failure(ip_address: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM auth_failures WHERE ip_address = ?", (ip_address,))
