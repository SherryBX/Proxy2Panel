from __future__ import annotations

import base64
from typing import Any

import yaml

from .utils import generate_token


def ensure_subscription_token(existing: str) -> str:
    return existing or generate_token()


def build_clash_profile(nodes: list[dict[str, Any]], active_node_id: str | None = None) -> str:
    proxies = [node_to_clash_proxy(node) for node in nodes]
    proxy_names = [proxy["name"] for proxy in proxies]
    active_name = next((proxy["name"] for proxy, node in zip(proxies, nodes) if node["id"] == active_node_id), None)

    config: dict[str, Any] = {
        "mixed-port": 7890,
        "allow-lan": True,
        "mode": "rule",
        "log-level": "info",
        "ipv6": True,
        "proxies": proxies,
        "proxy-groups": [
            {
                "name": "Proxy Admin Auto",
                "type": "select",
                "proxies": ([active_name] if active_name else []) + [name for name in proxy_names if name != active_name],
            },
            {
                "name": "Fallback",
                "type": "fallback",
                "url": "https://www.gstatic.com/generate_204",
                "interval": 300,
                "proxies": proxy_names,
            },
        ],
        "rules": [
            "MATCH,Proxy Admin Auto",
        ],
    }
    return yaml.safe_dump(config, sort_keys=False, allow_unicode=True)


def build_shadowrocket_profile(nodes: list[dict[str, Any]]) -> str:
    payload = "\n".join(node["raw_link"] for node in nodes if node.get("raw_link"))
    return base64.b64encode(payload.encode("utf-8")).decode("ascii")


def node_to_clash_proxy(node: dict[str, Any]) -> dict[str, Any]:
    proxy: dict[str, Any] = {
        "name": node["label"],
        "type": node["scheme"],
        "server": node["address"],
        "port": int(node["port"]),
        "uuid": node["username"],
        "udp": True,
        "network": node.get("network", "tcp"),
        "tls": node.get("security") == "tls",
    }
    if node.get("flow"):
        proxy["flow"] = node["flow"]
    if node.get("fingerprint"):
        proxy["client-fingerprint"] = node["fingerprint"]
    if node.get("sni"):
        proxy["servername"] = node["sni"]
    if node.get("encryption") not in ("", "none"):
        proxy["encryption"] = node["encryption"]
    if node.get("scheme") == "vless" and node.get("security") == "none":
        proxy["tls"] = False
    if node.get("host") or node.get("path"):
        path = node.get("path") or "/"
        if not path.startswith("/"):
            path = "/" + path
        proxy["ws-opts"] = {
            "path": path,
            "headers": {"Host": node.get("host") or node.get("sni") or node["address"]},
        }
    return proxy
