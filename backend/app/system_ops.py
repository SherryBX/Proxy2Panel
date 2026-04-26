from __future__ import annotations

import asyncio
import concurrent.futures
import re
import socket
import ssl
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import settings
from .db import (
    fetch_audit_logs,
    fetch_traffic_samples,
    get_node_prefs,
    get_setting,
    insert_audit_log,
    insert_traffic_sample,
    set_setting,
    upsert_node_pref,
)
from .parser import parse_share_links
from .subscription import build_vless_link
from .utils import build_rate_series, now_ts, stable_id


class ProxyManager:
    SITE_TARGETS = [
        {"name": "OpenAI", "host": "openai.com"},
        {"name": "Claude", "host": "claude.ai"},
        {"name": "X", "host": "x.com"},
        {"name": "YouTube", "host": "youtube.com"},
        {"name": "GitHub", "host": "github.com"},
        {"name": "Google", "host": "google.com"},
        {"name": "Cloudflare", "host": "cloudflare.com"},
    ]

    def __init__(self) -> None:
        self.demo_mode = settings.demo_mode
        self.agsbx_dir = settings.agsbx_dir
        self.jh_file = self.agsbx_dir / "jh.txt"
        self.argo_log = self.agsbx_dir / "argo.log"
        self.xr_json = self.agsbx_dir / "xr.json"
        self.xray_bin = self.agsbx_dir / "xray"
        self._autostart_cache: tuple[int, dict[str, bool]] | None = None

    def get_overview(self) -> dict[str, Any]:
        nodes = self.get_nodes()
        active_node = next((node for node in nodes if node["id"] == self.get_active_node_id()), None)
        traffic = self.get_current_bandwidth()
        service_status = self.get_service_status()
        audit_errors = len([log for log in fetch_audit_logs(limit=100) if log["level"] == "error"])
        return {
            "appName": settings.app_name,
            "demoMode": self.demo_mode,
            "serviceStatus": service_status,
            "activeNode": active_node or (nodes[0] if nodes else None),
            "nodeCount": len(nodes),
            "favoriteCount": len([node for node in nodes if node.get("favorite")]),
            "traffic": traffic,
            "errorCount": audit_errors,
            "autostart": self.get_autostart_status(),
            "generatedAt": now_ts(),
        }

    def get_nodes(self) -> list[dict[str, Any]]:
        raw = self._demo_links() if self.demo_mode else self._safe_read(self.jh_file)
        nodes = parse_share_links(raw)
        prefs = get_node_prefs()
        active_id = self.get_active_node_id()
        for node in nodes:
            pref = prefs.get(node["id"], {})
            if pref.get("label_override"):
                node["label"] = pref["label_override"]
            node["favorite"] = pref.get("favorite", False)
            node["active"] = node["id"] == active_id
        if nodes and not active_id:
            self.set_active_node(nodes[0]["id"], audit=False)
            nodes[0]["active"] = True
        return nodes

    def get_shadowrocket_nodes(self) -> list[dict[str, Any]]:
        if self.demo_mode:
            node = {
                "id": stable_id("shadowrocket-demo"),
                "scheme": "vless",
                "address": "shadowrocket-demo.trycloudflare.com",
                "port": 443,
                "username": "271c0354-4b19-46c9-bd8a-92e27f0c3ca9",
                "network": "ws",
                "security": "tls",
                "encryption": "none",
                "host": "shadowrocket-demo.trycloudflare.com",
                "path": settings.shadowrocket_path,
                "sni": "shadowrocket-demo.trycloudflare.com",
                "flow": "",
                "fingerprint": "chrome",
                "label": "Shadowrocket TLS",
                "favorite": False,
                "active": False,
            }
            node["raw_link"] = build_vless_link(node)
            return [node]

        tunnel_url = self._extract_tunnel_url(settings.shadowrocket_service_name)
        if not tunnel_url:
            return []
        host = re.sub(r"^https://", "", tunnel_url.strip()).rstrip("/")
        uuid = self._safe_read(self.agsbx_dir / "uuid").strip()
        node = {
            "id": stable_id("shadowrocket:" + host),
            "scheme": "vless",
            "address": host,
            "port": 443,
            "username": uuid,
            "network": "ws",
            "security": "tls",
            "encryption": "none",
            "host": host,
            "path": settings.shadowrocket_path,
            "sni": host,
            "flow": "",
            "fingerprint": "chrome",
            "label": "Shadowrocket TLS",
            "favorite": False,
            "active": False,
        }
        node["raw_link"] = build_vless_link(node)
        return [node]

    def get_active_node_id(self) -> str:
        return get_setting("active_node_id", "")

    def set_active_node(self, node_id: str, audit: bool = True) -> None:
        set_setting("active_node_id", node_id)
        if audit:
            node = next((item for item in self.get_nodes() if item["id"] == node_id), None)
            insert_audit_log(
                "info",
                "switch_node",
                f"切换当前节点到 {node['label'] if node else node_id}",
                {"node_id": node_id},
            )

    def set_favorite(self, node_id: str, favorite: bool) -> None:
        upsert_node_pref(node_id, favorite=int(favorite))
        insert_audit_log(
            "info",
            "favorite_node",
            f"更新收藏状态: {node_id}",
            {"node_id": node_id, "favorite": favorite},
        )

    def rename_node(self, node_id: str, label: str) -> None:
        clean = label.strip()
        if not clean:
            raise ValueError("标签不能为空")
        upsert_node_pref(node_id, label_override=clean)
        insert_audit_log("info", "rename_node", f"节点已改名为 {clean}", {"node_id": node_id, "label": clean})

    def get_service_status(self) -> dict[str, Any]:
        if self.demo_mode:
            return {
                "xray": {"active": True, "status": "active", "uptime": "2h 13m"},
                "argo": {"active": True, "status": "active", "uptime": "2h 12m"},
                "stack": {"healthy": True},
            }
        xray_status = self._run(["/bin/systemctl", "is-active", "xr.service"], timeout=5).strip() or "unknown"
        xray_uptime = self._run(
            ["/bin/systemctl", "show", "xr.service", "-p", "ActiveEnterTimestamp", "--value"],
            timeout=5,
        ).strip()
        argo_active = bool(
            self._run(["/usr/bin/pgrep", "-f", "/root/agsbx/cloudflared tunnel"], timeout=5).strip()
        )
        return {
            "xray": {"active": xray_status == "active", "status": xray_status, "uptime": xray_uptime},
            "argo": {
                "active": argo_active,
                "status": "active" if argo_active else "inactive",
                "uptime": self._argo_started_at(),
            },
            "stack": {"healthy": xray_status == "active" and argo_active},
        }

    def get_autostart_status(self) -> dict[str, bool]:
        if self.demo_mode:
            return {"xray": True, "argo": True}
        if self._autostart_cache and (now_ts() - self._autostart_cache[0] < 60):
            return self._autostart_cache[1]
        xray_enabled = self._run(["/bin/systemctl", "is-enabled", "xr.service"], timeout=5).strip() == "enabled"
        crontab = self._run(["/usr/bin/crontab", "-l"], timeout=5)
        argo_enabled = "cloudflared tunnel --url http://localhost:" in crontab
        data = {"xray": xray_enabled, "argo": argo_enabled}
        self._autostart_cache = (now_ts(), data)
        return data

    def get_logs(self, source: str = "combined", limit: int = 200, query: str = "") -> dict[str, Any]:
        if source == "audit":
            return {"source": "audit", "entries": fetch_audit_logs(limit=limit, query=query)}
        if self.demo_mode:
            demo_entries = [
                {"ts": now_ts(), "line": "Xray active, Argo active"},
                {"ts": now_ts(), "line": "Current node: AWS-JP-main"},
            ]
            return {"source": source, "entries": demo_entries}
        entries: list[dict[str, Any]] = []
        if source in ("combined", "argo"):
            entries.extend(self._tail_file(self.argo_log, limit, query, tag="argo"))
        if source in ("combined", "xray"):
            xray_lines = self._run(
                ["/usr/bin/journalctl", "-u", "xr.service", "-n", str(limit), "--no-pager"], timeout=10
            )
            entries.extend(self._lines_to_entries(xray_lines, query, tag="xray"))
        entries.sort(key=lambda item: item["ts"], reverse=True)
        return {"source": source, "entries": entries[:limit]}

    def get_traffic(self, range_key: str = "24h", node_id: str | None = None, service: str | None = None) -> dict[str, Any]:
        if self.demo_mode:
            now = now_ts()
            series = []
            for i in range(24):
                series.append(
                    {
                        "ts": now - (23 - i) * 3600,
                        "download_bps": 3.2 + i * 0.18,
                        "upload_bps": 1.8 + i * 0.11,
                        "node_id": self.get_active_node_id() or "demo",
                        "service": "stack",
                    }
                )
            return {
                "range": range_key,
                "series": series,
                "services": ["stack"],
                "nodes": [node["id"] for node in self.get_nodes()],
            }
        seconds = {"1h": 3600, "6h": 21600, "24h": 86400, "7d": 604800}.get(range_key, 86400)
        rows = fetch_traffic_samples(now_ts() - seconds, node_id=node_id, service=service)
        series = build_rate_series(rows)
        services = sorted(set(row["service"] for row in rows)) or ["stack"]
        nodes = sorted(set(filter(None, (row.get("node_id") for row in rows))))
        return {"range": range_key, "series": series, "services": services, "nodes": nodes}

    def get_current_bandwidth(self) -> dict[str, float]:
        if self.demo_mode:
            return {"download_bps": 4.82, "upload_bps": 1.74}
        rows = fetch_traffic_samples(now_ts() - 600)
        series = build_rate_series(rows)
        if not series:
            return {"download_bps": 0.0, "upload_bps": 0.0}
        last = series[-1]
        return {"download_bps": last["download_bps"], "upload_bps": last["upload_bps"]}

    def sample_traffic(self) -> None:
        if self.demo_mode:
            return
        stats = self._read_interface_counters()
        if not stats:
            return
        insert_traffic_sample(
            now_ts(),
            stats["rx_bytes"],
            stats["tx_bytes"],
            self.get_active_node_id() or None,
            "stack",
        )

    async def sampler_loop(self) -> None:
        while True:
            try:
                self.sample_traffic()
            except Exception as exc:
                insert_audit_log("error", "sample_traffic", f"采样失败: {exc}")
            await asyncio.sleep(settings.sample_interval_seconds)

    def action(self, action: str, target: str) -> dict[str, Any]:
        if self.demo_mode:
            insert_audit_log("info", f"{action}_{target}", f"演示模式执行 {action} {target}")
            return {"ok": True, "message": f"演示模式已执行 {action} {target}"}
        commands = {
            ("start", "xray"): ["/bin/systemctl", "start", "xr.service"],
            ("stop", "xray"): ["/bin/systemctl", "stop", "xr.service"],
            ("restart", "xray"): ["/bin/systemctl", "restart", "xr.service"],
            ("reload", "xray"): ["/bin/systemctl", "restart", "xr.service"],
            ("refresh", "nodes"): ["/root/bin/agsbx", "list"],
            (
                "start",
                "argo",
            ): [
                "bash",
                "-lc",
                "nohup /root/agsbx/cloudflared tunnel --url http://localhost:$(cat /root/agsbx/argoport.log) --edge-ip-version auto --no-autoupdate --protocol http2 > /root/agsbx/argo.log 2>&1 &",
            ],
            ("stop", "argo"): ["/usr/bin/pkill", "-f", "/root/agsbx/cloudflared tunnel"],
            (
                "restart",
                "argo",
            ): [
                "bash",
                "-lc",
                "pkill -f '/root/agsbx/cloudflared tunnel' || true; nohup /root/agsbx/cloudflared tunnel --url http://localhost:$(cat /root/agsbx/argoport.log) --edge-ip-version auto --no-autoupdate --protocol http2 > /root/agsbx/argo.log 2>&1 &",
            ],
            (
                "restart",
                "stack",
            ): [
                "bash",
                "-lc",
                "/bin/systemctl restart xr.service && pkill -f '/root/agsbx/cloudflared tunnel' || true; nohup /root/agsbx/cloudflared tunnel --url http://localhost:$(cat /root/agsbx/argoport.log) --edge-ip-version auto --no-autoupdate --protocol http2 > /root/agsbx/argo.log 2>&1 &",
            ],
        }
        if (action, target) == ("enable_autostart", "xray"):
            self._run(["/bin/systemctl", "enable", "xr.service"], timeout=15, check=True)
            self._autostart_cache = None
            insert_audit_log("info", "enable_autostart_xray", "启用 Xray 开机自启")
            return {"ok": True, "message": "Xray 开机自启已启用"}
        if (action, target) == ("disable_autostart", "xray"):
            self._run(["/bin/systemctl", "disable", "xr.service"], timeout=15, check=True)
            self._autostart_cache = None
            insert_audit_log("info", "disable_autostart_xray", "关闭 Xray 开机自启")
            return {"ok": True, "message": "Xray 开机自启已关闭"}
        if (action, target) == ("enable_autostart", "argo"):
            self._ensure_argo_cron(True)
            self._autostart_cache = None
            insert_audit_log("info", "enable_autostart_argo", "启用 Argo 开机自启")
            return {"ok": True, "message": "Argo 开机自启已启用"}
        if (action, target) == ("disable_autostart", "argo"):
            self._ensure_argo_cron(False)
            self._autostart_cache = None
            insert_audit_log("info", "disable_autostart_argo", "关闭 Argo 开机自启")
            return {"ok": True, "message": "Argo 开机自启已关闭"}
        cmd = commands.get((action, target))
        if not cmd:
            raise ValueError(f"Unsupported action: {action} {target}")
        self._run(cmd, timeout=25, check=True)
        insert_audit_log("info", f"{action}_{target}", f"执行 {action} {target}")
        return {"ok": True, "message": f"已执行 {action} {target}"}

    def diagnostics_latency_test(self, node_id: str | None = None) -> dict[str, Any]:
        node = self._resolve_node(node_id)
        if not node:
            return {"ok": False, "message": "No node available"}
        host = node["address"]
        port = int(node["port"])
        samples = []
        for _ in range(3):
            start = time.perf_counter()
            try:
                with socket.create_connection((host, port), timeout=5):
                    samples.append(round((time.perf_counter() - start) * 1000, 1))
            except Exception as exc:
                return {"ok": False, "message": str(exc), "node": node}
        return {"ok": True, "node": node, "samples": samples, "median_ms": sorted(samples)[1]}

    def diagnostics_latency_map(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        for node in self.get_nodes():
            result = self.diagnostics_latency_test(node["id"])
            items.append(
                {
                    "node_id": node["id"],
                    "label": node["label"],
                    "ok": bool(result.get("ok")),
                    "median_ms": result.get("median_ms"),
                    "samples": result.get("samples", []),
                    "message": result.get("message", ""),
                }
            )
        return {"items": items}

    def diagnostics_site_latency(self) -> dict[str, Any]:
        with concurrent.futures.ThreadPoolExecutor(max_workers=min(6, len(self.SITE_TARGETS))) as executor:
            results = list(executor.map(self._probe_site_target, self.SITE_TARGETS))
        return {"items": results}

    def diagnostics_dns_check(self, node_id: str | None = None) -> dict[str, Any]:
        node = self._resolve_node(node_id)
        if not node:
            return {"ok": False, "message": "No node available"}
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(node["address"], None)})
        sni_addresses = []
        if node.get("sni"):
            sni_addresses = sorted({item[4][0] for item in socket.getaddrinfo(node["sni"], None)})
        return {"ok": True, "node": node, "address_records": addresses, "sni_records": sni_addresses}

    def diagnostics_config_validate(self) -> dict[str, Any]:
        if self.demo_mode:
            return {"ok": True, "message": "demo ok", "output": "demo mode validation"}
        proc = subprocess.run(
            [str(self.xray_bin), "run", "-test", "-c", str(self.xr_json)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = (proc.stdout + "\n" + proc.stderr).strip()
        return {"ok": proc.returncode == 0, "message": "valid" if proc.returncode == 0 else "invalid", "output": output}

    def get_settings_payload(self) -> dict[str, Any]:
        shadowrocket_nodes = self.get_shadowrocket_nodes()
        return {
            "ipWhitelist": get_setting("ip_whitelist", settings.default_ip_whitelist),
            "sampleIntervalSeconds": settings.sample_interval_seconds,
            "bindHost": settings.bind_host,
            "bindPort": settings.bind_port,
            "demoMode": self.demo_mode,
            "auditLogs": fetch_audit_logs(limit=100),
            "shadowrocketCompatible": bool(shadowrocket_nodes),
            "shadowrocketHint": "已生成 Shadowrocket 专用兼容节点" if shadowrocket_nodes else "Shadowrocket 专用兼容节点未就绪",
        }

    def _resolve_node(self, node_id: str | None) -> dict[str, Any] | None:
        nodes = self.get_nodes()
        if node_id:
            return next((node for node in nodes if node["id"] == node_id), None)
        active_id = self.get_active_node_id()
        return next((node for node in nodes if node["id"] == active_id), nodes[0] if nodes else None)

    def _safe_read(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            return ""

    def _tail_file(self, path: Path, limit: int, query: str, tag: str) -> list[dict[str, Any]]:
        content = self._safe_read(path)
        lines = content.splitlines()[-limit:]
        return self._lines_to_entries("\n".join(lines), query, tag=tag)

    def _lines_to_entries(self, content: str, query: str, tag: str) -> list[dict[str, Any]]:
        lines = [line for line in content.splitlines() if line.strip()]
        if query:
            lines = [line for line in lines if query.lower() in line.lower()]
        ts = now_ts()
        return [{"ts": ts - idx, "source": tag, "line": line} for idx, line in enumerate(reversed(lines))]

    def _run(self, command: list[str], timeout: int = 10, check: bool = False) -> str:
        proc = subprocess.run(command, capture_output=True, text=True, timeout=timeout)
        output = (proc.stdout + proc.stderr).strip()
        if check and proc.returncode != 0:
            insert_audit_log("error", "subprocess", "命令失败", {"command": command, "output": output})
            raise RuntimeError(output or f"Command failed: {command}")
        return output

    def _argo_started_at(self) -> str:
        try:
            stat = self.argo_log.stat()
            return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stat.st_mtime))
        except FileNotFoundError:
            return ""

    def _read_interface_counters(self) -> dict[str, int] | None:
        try:
            lines = Path("/proc/net/dev").read_text(encoding="utf-8").splitlines()[2:]
        except FileNotFoundError:
            return None
        counters = []
        for line in lines:
            name, values = line.split(":", 1)
            iface = name.strip()
            if iface == "lo" or iface.startswith("docker") or iface.startswith("veth"):
                continue
            parts = values.split()
            counters.append({"iface": iface, "rx_bytes": int(parts[0]), "tx_bytes": int(parts[8])})
        if not counters:
            return None
        if settings.interface_name:
            match = next((item for item in counters if item["iface"] == settings.interface_name), None)
            return match
        counters.sort(key=lambda item: item["rx_bytes"] + item["tx_bytes"], reverse=True)
        return counters[0]

    def _probe_site_target(self, target: dict[str, str]) -> dict[str, Any]:
        host = target["host"]
        start = time.perf_counter()
        try:
            infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            ip = infos[0][4][0]
            dns_ms = round((time.perf_counter() - start) * 1000, 1)

            tcp_start = time.perf_counter()
            raw = socket.create_connection((host, 443), timeout=4)
            tcp_ms = round((time.perf_counter() - tcp_start) * 1000, 1)

            tls_start = time.perf_counter()
            ctx = ssl.create_default_context()
            wrapped = ctx.wrap_socket(raw, server_hostname=host)
            tls_ms = round((time.perf_counter() - tls_start) * 1000, 1)
            wrapped.close()

            return {
                "name": target["name"],
                "host": host,
                "ip": ip,
                "dns_ms": dns_ms,
                "tcp_ms": tcp_ms,
                "tls_ms": tls_ms,
                "total_ms": round(dns_ms + tcp_ms + tls_ms, 1),
                "ok": True,
                "message": "",
            }
        except Exception as exc:
            return {
                "name": target["name"],
                "host": host,
                "ip": "",
                "dns_ms": None,
                "tcp_ms": None,
                "tls_ms": None,
                "total_ms": None,
                "ok": False,
                "message": str(exc),
            }

    def _ensure_argo_cron(self, enabled: bool) -> None:
        desired = '@reboot sleep 10 && /bin/sh -c "nohup $HOME/agsbx/cloudflared tunnel --url http://localhost:$(cat $HOME/agsbx/argoport.log) --edge-ip-version auto --no-autoupdate --protocol http2 > $HOME/agsbx/argo.log 2>&1 &"'
        current = self._run(["/usr/bin/crontab", "-l"], timeout=5)
        lines = [line for line in current.splitlines() if line.strip() and "cloudflared tunnel --url http://localhost:" not in line]
        if enabled:
            lines.append(desired)
        payload = "\n".join(lines) + ("\n" if lines else "")
        subprocess.run(["/usr/bin/crontab", "-"], input=payload, text=True, check=True)

    def _extract_tunnel_url(self, service_name: str) -> str:
        logs = self._run(
            ["/usr/bin/journalctl", "-u", service_name, "-n", "120", "--no-pager"],
            timeout=12,
            check=False,
        )
        matches = re.findall(r"https://([a-z0-9-]+(?:\.[a-z0-9-]+)+)", logs, flags=re.IGNORECASE)
        return f"https://{matches[-1]}" if matches else ""

    def _demo_links(self) -> str:
        return """vless://271c0354-4b19-46c9-bd8a-92e27f0c3ca9@www.xiaoshuofen.com:443?flow=xtls-rprx-vision&type=ws&host=firm-superintendent-machines-dealer.trycloudflare.com&path=%2F271c0354-4b19-46c9-bd8a-92e27f0c3ca9-vw&security=tls&sni=firm-superintendent-machines-dealer.trycloudflare.com&fp=chrome#AWS-JP-main
vless://271c0354-4b19-46c9-bd8a-92e27f0c3ca9@cf.godns.cc:443?flow=xtls-rprx-vision&type=ws&host=firm-superintendent-machines-dealer.trycloudflare.com&path=%2F271c0354-4b19-46c9-bd8a-92e27f0c3ca9-vw&security=tls&sni=firm-superintendent-machines-dealer.trycloudflare.com&fp=chrome#AWS-JP-backup
vless://271c0354-4b19-46c9-bd8a-92e27f0c3ca9@www.shopify.com:443?flow=xtls-rprx-vision&type=ws&host=firm-superintendent-machines-dealer.trycloudflare.com&path=%2F271c0354-4b19-46c9-bd8a-92e27f0c3ca9-vw&security=tls&sni=firm-superintendent-machines-dealer.trycloudflare.com&fp=chrome#AWS-JP-shopify"""
