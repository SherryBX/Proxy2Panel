from __future__ import annotations

import hashlib
import hmac
import ipaddress
import os
import secrets
import time
from typing import Iterable


def stable_id(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def ip_allowed(ip: str, rules: Iterable[str]) -> bool:
    cleaned = [rule.strip() for rule in rules if rule and rule.strip()]
    if not cleaned:
        return True
    target = ipaddress.ip_address(ip)
    for rule in cleaned:
        try:
            if "/" in rule:
                if target in ipaddress.ip_network(rule, strict=False):
                    return True
            elif target == ipaddress.ip_address(rule):
                return True
        except ValueError:
            continue
    return False


def build_rate_series(rows: list[dict]) -> list[dict]:
    if len(rows) < 2:
        return []
    result: list[dict] = []
    for prev, current in zip(rows, rows[1:]):
        delta_t = max(current["ts"] - prev["ts"], 1)
        download_bps = round(max(current["rx_bytes"] - prev["rx_bytes"], 0) / delta_t, 2)
        upload_bps = round(max(current["tx_bytes"] - prev["tx_bytes"], 0) / delta_t, 2)
        result.append(
            {
                "ts": current["ts"],
                "download_bps": download_bps,
                "upload_bps": upload_bps,
                "node_id": current.get("node_id"),
                "service": current.get("service", "stack"),
            }
        )
    return result


def now_ts() -> int:
    return int(time.time())


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def password_hash(password: str, salt: bytes | None = None, rounds: int = 200_000) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        _, rounds_str, salt_hex, digest_hex = encoded.split("$", 3)
        check = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds_str)
        ).hex()
        return hmac.compare_digest(check, digest_hex)
    except Exception:
        return False
