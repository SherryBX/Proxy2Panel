from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

from .utils import stable_id


SUPPORTED_SCHEMES = {"vless", "vmess", "trojan"}


def parse_share_links(raw_text: str) -> list[dict]:
    nodes: list[dict] = []
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or "://" not in line:
            continue
        parsed = urlparse(line)
        if parsed.scheme.lower() not in SUPPORTED_SCHEMES:
            continue
        query = parse_qs(parsed.query)
        address = parsed.hostname or ""
        fragment = unquote(parsed.fragment or address)
        node = {
            "id": stable_id(line),
            "scheme": parsed.scheme.lower(),
            "address": address,
            "port": parsed.port or 0,
            "username": parsed.username or "",
            "network": _one(query, "type", "tcp"),
            "security": _one(query, "security", "none"),
            "encryption": _one(query, "encryption", "none"),
            "host": _one(query, "host", ""),
            "path": unquote(_one(query, "path", "/")),
            "sni": _one(query, "sni", ""),
            "flow": _one(query, "flow", ""),
            "fingerprint": _one(query, "fp", ""),
            "label": derive_short_label(fragment, address, parsed.port or 0, _one(query, "security", "none")),
            "favorite": False,
            "raw_link": line,
        }
        nodes.append(node)
    return nodes


def _one(query: dict[str, list[str]], key: str, default: str) -> str:
    values = query.get(key)
    return values[0] if values else default


def derive_short_label(fragment: str, address: str, port: int, security: str) -> str:
    raw = (fragment or address).strip()
    lower = raw.lower()
    if raw and len(raw) <= 28:
        return raw
    if "tls-argo" in lower or (address.startswith("yg7.") and security == "tls"):
        return "Argo TLS"
    if "ws-argo" in lower or (address.startswith("yg10.") and port == 80):
        return "Argo 80"
    if address.replace(".", "").isdigit() or port >= 30000:
        return "直连入口"
    if address:
        first = address.split(".")[0]
        if first:
            return first[:20]
    return raw[:20] if raw else "未命名节点"
