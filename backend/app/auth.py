from __future__ import annotations

import time

from fastapi import HTTPException, Request, Response, status

from .config import settings
from .db import (
    clear_auth_failure,
    create_session,
    delete_session,
    get_auth_failure,
    get_session,
    get_setting,
    prune_sessions,
    set_auth_failure,
    set_setting,
)
from .utils import generate_token, ip_allowed, password_hash, verify_password


LOCKOUT_THRESHOLD = 5
LOCKOUT_WINDOW_SECONDS = 15 * 60
LOCKOUT_DURATION_SECONDS = 10 * 60


class AuthService:
    def ensure_bootstrap_password(self) -> str | None:
        existing = get_setting("password_hash")
        if existing:
            return None
        if not settings.default_admin_password:
            return None
        set_setting("password_hash", password_hash(settings.default_admin_password))
        return settings.default_admin_password

    def current_whitelist(self) -> list[str]:
        raw = get_setting("ip_whitelist", settings.default_ip_whitelist)
        return [item.strip() for item in raw.split(",") if item.strip()]

    def assert_ip_allowed(self, request: Request) -> None:
        rules = self.current_whitelist()
        if not rules:
            return
        remote_ip = extract_client_ip(request)
        if not ip_allowed(remote_ip, rules):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="IP not allowed")

    def login(self, password: str, request: Request, response: Response) -> None:
        prune_sessions()
        remote_ip = extract_client_ip(request)
        failure = get_auth_failure(remote_ip)
        now = int(time.time())
        if failure and int(failure.get("locked_until", 0)) > now:
            retry_after = int(failure["locked_until"]) - now
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "message": f"登录失败次数过多，请 {retry_after} 秒后再试",
                    "retryAfter": retry_after,
                    "remainingAttempts": 0,
                },
            )

        password_digest = get_setting("password_hash")
        if not password_digest or not verify_password(password, password_digest):
            state = self.record_failed_login(remote_ip)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "message": f"密码错误，还可再错 {state['remaining_attempts']} 次",
                    "remainingAttempts": state["remaining_attempts"],
                    "retryAfter": max(state["locked_until"] - now, 0),
                },
            )

        token = generate_token()
        expires_at = int(time.time()) + settings.session_ttl_hours * 3600
        create_session(token, "admin", expires_at, remote_ip)
        clear_auth_failure(remote_ip)
        response.set_cookie(
            key=settings.session_cookie,
            value=token,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=settings.session_ttl_hours * 3600,
        )

    def logout(self, request: Request, response: Response) -> None:
        token = request.cookies.get(settings.session_cookie)
        if token:
            delete_session(token)
        response.delete_cookie(settings.session_cookie)

    def require_auth(self, request: Request) -> dict:
        prune_sessions()
        token = request.cookies.get(settings.session_cookie)
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
        session = get_session(token)
        if not session or int(session["expires_at"]) < int(time.time()):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
        return session

    def update_security_settings(self, password: str | None, whitelist: str | None) -> None:
        if password:
            set_setting("password_hash", password_hash(password))
        if whitelist is not None:
            set_setting("ip_whitelist", whitelist)

    def record_failed_login(self, ip_address: str) -> dict[str, int]:
        now = int(time.time())
        current = get_auth_failure(ip_address)
        if current and now - int(current.get("last_failed_at", 0)) <= LOCKOUT_WINDOW_SECONDS:
            failed_count = int(current.get("failed_count", 0)) + 1
        else:
            failed_count = 1
        locked_until = now + LOCKOUT_DURATION_SECONDS if failed_count >= LOCKOUT_THRESHOLD else 0
        set_auth_failure(ip_address, failed_count, now, locked_until)
        return {
            "failed_count": failed_count,
            "remaining_attempts": max(LOCKOUT_THRESHOLD - failed_count, 0),
            "locked_until": locked_until,
        }


def extract_client_ip(request: Request) -> str:
    cf_ip = request.headers.get("cf-connecting-ip", "").strip()
    if cf_ip:
        return cf_ip
    if settings.trust_forwarded_for:
        forwarded = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if forwarded:
            return forwarded
    return request.client.host if request.client else "127.0.0.1"


auth_service = AuthService()
