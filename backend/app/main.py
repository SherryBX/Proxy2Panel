from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .auth import auth_service
from .config import settings
from fastapi.responses import PlainTextResponse

from .db import get_setting, init_db, insert_audit_log, set_setting
from .system_ops import ProxyManager
from .subscription import build_clash_profile, build_shadowrocket_profile, ensure_subscription_token


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.allow_origins == "*" else [settings.allow_origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    manager = ProxyManager()
    app.state.manager = manager

    @app.middleware("http")
    async def whitelist_middleware(request: Request, call_next):
        if request.url.path.startswith(settings.api_prefix) and request.url.path not in {
            f"{settings.api_prefix}/auth/login",
            f"{settings.api_prefix}/health",
        }:
            try:
                auth_service.assert_ip_allowed(request)
            except HTTPException as exc:
                return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
        return await call_next(request)

    @app.on_event("startup")
    async def startup() -> None:
        init_db()
        bootstrap = auth_service.ensure_bootstrap_password()
        if bootstrap:
            insert_audit_log("warning", "bootstrap_password", "系统首次启动已注入默认口令，请尽快修改", {})
        set_setting("subscription_token", ensure_subscription_token(get_setting("subscription_token", "")))
        app.state.sampler_task = asyncio.create_task(manager.sampler_loop())

    @app.on_event("shutdown")
    async def shutdown() -> None:
        task = getattr(app.state, "sampler_task", None)
        if task:
            task.cancel()

    def require_user(request: Request) -> dict[str, Any]:
        return auth_service.require_auth(request)

    @app.get(f"{settings.api_prefix}/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "demoMode": settings.demo_mode}

    @app.post(f"{settings.api_prefix}/auth/login")
    async def login(payload: dict[str, str], request: Request, response: Response):
        auth_service.login(payload.get("password", ""), request, response)
        insert_audit_log("info", "login", "管理员登录成功", {"ip": request.client.host if request.client else ""})
        return {"ok": True}

    @app.post(f"{settings.api_prefix}/auth/logout")
    async def logout(request: Request, response: Response, session: dict = Depends(require_user)):
        auth_service.logout(request, response)
        insert_audit_log("info", "logout", "管理员退出登录", {"username": session["username"]})
        return {"ok": True}

    @app.get(f"{settings.api_prefix}/auth/session")
    async def session(request: Request, session: dict = Depends(require_user)):
        return {"ok": True, "username": session["username"], "expiresAt": session["expires_at"]}

    @app.get(f"{settings.api_prefix}/overview")
    async def overview(session: dict = Depends(require_user)):
        return app.state.manager.get_overview()

    @app.get(f"{settings.api_prefix}/nodes")
    async def nodes(session: dict = Depends(require_user)):
        return {"items": app.state.manager.get_nodes()}

    @app.post(f"{settings.api_prefix}/nodes/{{node_id}}/activate")
    async def activate_node(node_id: str, session: dict = Depends(require_user)):
        app.state.manager.set_active_node(node_id)
        return {"ok": True, "activeNodeId": node_id}

    @app.post(f"{settings.api_prefix}/nodes/{{node_id}}/favorite")
    async def favorite_node(node_id: str, payload: dict[str, bool], session: dict = Depends(require_user)):
        app.state.manager.set_favorite(node_id, bool(payload.get("favorite", False)))
        return {"ok": True}

    @app.post(f"{settings.api_prefix}/nodes/{{node_id}}/rename")
    async def rename_node(node_id: str, payload: dict[str, str], session: dict = Depends(require_user)):
        app.state.manager.rename_node(node_id, payload.get("label", ""))
        return {"ok": True}

    @app.get(f"{settings.api_prefix}/traffic")
    async def traffic(
        range: str = "24h",
        node_id: str | None = None,
        service: str | None = None,
        session: dict = Depends(require_user),
    ):
        return app.state.manager.get_traffic(range_key=range, node_id=node_id, service=service)

    @app.get(f"{settings.api_prefix}/logs")
    async def logs(source: str = "combined", limit: int = 200, query: str = "", session: dict = Depends(require_user)):
        return app.state.manager.get_logs(source=source, limit=limit, query=query)

    @app.post(f"{settings.api_prefix}/actions/{{action}}")
    async def actions(action: str, payload: dict[str, str], session: dict = Depends(require_user)):
        target = payload.get("target", "stack")
        try:
            return app.state.manager.action(action, target)
        except Exception as exc:
            insert_audit_log("error", f"{action}_{target}", f"动作失败: {exc}")
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post(f"{settings.api_prefix}/diagnostics/latency-test")
    async def latency_test(payload: dict[str, str], session: dict = Depends(require_user)):
        return app.state.manager.diagnostics_latency_test(payload.get("node_id"))

    @app.get(f"{settings.api_prefix}/diagnostics/latency-map")
    async def latency_map(session: dict = Depends(require_user)):
        return app.state.manager.diagnostics_latency_map()

    @app.get(f"{settings.api_prefix}/diagnostics/site-latency")
    async def site_latency(session: dict = Depends(require_user)):
        return app.state.manager.diagnostics_site_latency()

    @app.post(f"{settings.api_prefix}/diagnostics/dns-check")
    async def dns_check(payload: dict[str, str], session: dict = Depends(require_user)):
        return app.state.manager.diagnostics_dns_check(payload.get("node_id"))

    @app.post(f"{settings.api_prefix}/diagnostics/config-validate")
    async def config_validate(session: dict = Depends(require_user)):
        return app.state.manager.diagnostics_config_validate()

    @app.get(f"{settings.api_prefix}/settings")
    async def get_settings(session: dict = Depends(require_user)):
        payload = app.state.manager.get_settings_payload()
        payload["clashSubscriptionUrl"] = f"/api/subscriptions/clash?token={get_setting('subscription_token', '')}"
        payload["shadowrocketSubscriptionUrl"] = f"/api/subscriptions/shadowrocket?token={get_setting('subscription_token', '')}"
        return payload

    @app.put(f"{settings.api_prefix}/settings")
    async def update_settings(payload: dict[str, str], session: dict = Depends(require_user)):
        auth_service.update_security_settings(payload.get("password") or None, payload.get("ipWhitelist"))
        insert_audit_log("warning", "update_settings", "更新安全设置", {"username": session["username"]})
        return {"ok": True}

    @app.get(f"{settings.api_prefix}/subscriptions/clash")
    async def clash_subscription(request: Request, token: str | None = None):
        valid_token = get_setting("subscription_token", "")
        if token != valid_token:
            auth_service.require_auth(request)
        profile = build_clash_profile(app.state.manager.get_nodes(), app.state.manager.get_active_node_id())
        return PlainTextResponse(profile, media_type="text/yaml; charset=utf-8")

    @app.get(f"{settings.api_prefix}/subscriptions/shadowrocket")
    async def shadowrocket_subscription(request: Request, token: str | None = None):
        valid_token = get_setting("subscription_token", "")
        if token != valid_token:
            auth_service.require_auth(request)
        profile = build_shadowrocket_profile(app.state.manager.get_shadowrocket_nodes())
        return PlainTextResponse(profile, media_type="text/plain; charset=utf-8")

    @app.websocket("/ws/overview")
    async def ws_overview(websocket: WebSocket):
        token = websocket.cookies.get(settings.session_cookie)
        if not token:
            await websocket.close(code=4401)
            return
        await websocket.accept()
        try:
            while True:
                await websocket.send_json(
                    {
                        "overview": app.state.manager.get_overview(),
                        "latestAudit": app.state.manager.get_logs(source="audit", limit=20),
                    }
                )
                await asyncio.sleep(5)
        except WebSocketDisconnect:
            return

    if settings.frontend_dist.exists():
        assets_dir = settings.frontend_dist / "assets"
        if assets_dir.exists():
            app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

        @app.get("/{full_path:path}")
        async def spa(full_path: str):
            if full_path.startswith("api") or full_path.startswith("ws"):
                return JSONResponse({"detail": "Not found"}, status_code=404)
            direct_file = settings.frontend_dist / full_path
            if full_path and direct_file.exists() and direct_file.is_file():
                return FileResponse(direct_file)
            index_file = settings.frontend_dist / "index.html"
            if index_file.exists():
                return FileResponse(index_file)
            return JSONResponse({"detail": "Frontend not built"}, status_code=404)

    return app


app = create_app()
