from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]


@dataclass(slots=True)
class Settings:
    app_name: str = os.getenv("PROXY_ADMIN_APP_NAME", "Proxy Admin")
    api_prefix: str = "/api"
    secret_key: str = os.getenv("PROXY_ADMIN_SECRET_KEY", "change-me-in-production")
    session_cookie: str = "proxy_admin_session"
    session_ttl_hours: int = int(os.getenv("PROXY_ADMIN_SESSION_TTL_HOURS", "24"))
    sample_interval_seconds: int = int(os.getenv("PROXY_ADMIN_SAMPLE_INTERVAL_SECONDS", "30"))
    bind_host: str = os.getenv("PROXY_ADMIN_HOST", "127.0.0.1")
    bind_port: int = int(os.getenv("PROXY_ADMIN_PORT", "8781"))
    db_path: Path = Path(os.getenv("PROXY_ADMIN_DB", str(BASE_DIR / "data" / "proxy_admin.db")))
    agsbx_dir: Path = Path(os.getenv("PROXY_ADMIN_AGSBX_DIR", "/root/agsbx"))
    frontend_dist: Path = Path(os.getenv("PROXY_ADMIN_FRONTEND_DIST", str(BASE_DIR / "static")))
    allow_origins: str = os.getenv("PROXY_ADMIN_ALLOW_ORIGINS", "*")
    default_admin_password: str = os.getenv("PROXY_ADMIN_DEFAULT_PASSWORD", "")
    default_ip_whitelist: str = os.getenv("PROXY_ADMIN_IP_WHITELIST", "")
    interface_name: str = os.getenv("PROXY_ADMIN_INTERFACE", "")
    trust_forwarded_for: bool = os.getenv("PROXY_ADMIN_TRUST_FORWARDED_FOR", "1") == "1"
    demo_mode: bool = os.getenv("PROXY_ADMIN_DEMO", "0") == "1"
    shadowrocket_port: int = int(os.getenv("PROXY_ADMIN_SHADOWROCKET_PORT", "35995"))
    shadowrocket_path: str = os.getenv("PROXY_ADMIN_SHADOWROCKET_PATH", "/shadowrocket-ws")
    shadowrocket_service_name: str = os.getenv(
        "PROXY_ADMIN_SHADOWROCKET_TUNNEL_SERVICE", "proxy-admin-shadowrocket-tunnel.service"
    )
    shadowrocket_public_host: str = os.getenv("PROXY_ADMIN_SHADOWROCKET_PUBLIC_HOST", "")
    admin_public_host: str = os.getenv("PROXY_ADMIN_ADMIN_PUBLIC_HOST", "")

    def __post_init__(self) -> None:
        if os.name == "nt" and os.getenv("PROXY_ADMIN_DEMO") is None:
            self.demo_mode = True
        if not self.demo_mode and not self.agsbx_dir.exists():
            self.demo_mode = True
        self.db_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
