from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from app.auth import auth_service
from app.db import get_auth_failure, init_db, set_setting
from app.utils import password_hash


def make_request(ip: str) -> Request:
    return Request({"type": "http", "headers": [], "client": (ip, 1000)})


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    from app import config

    db_path = tmp_path / "test.db"
    monkeypatch.setattr(config.settings, "db_path", db_path)
    init_db()
    set_setting("password_hash", password_hash("secret"))
    yield


def test_login_locks_after_repeated_failures(isolated_db):
    request = make_request("1.2.3.4")
    response = Response()

    for _ in range(4):
        with pytest.raises(HTTPException) as exc:
            auth_service.login("bad", request, response)
        assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        auth_service.login("bad", request, response)
    assert exc.value.status_code == 401

    with pytest.raises(HTTPException) as exc:
        auth_service.login("secret", request, response)
    assert exc.value.status_code == 429
    assert "秒后再试" in exc.value.detail["message"]


def test_successful_login_clears_failure_counter(isolated_db):
    request = make_request("9.9.9.9")
    response = Response()

    with pytest.raises(HTTPException):
        auth_service.login("bad", request, response)

    auth_service.login("secret", request, response)

    assert get_auth_failure("9.9.9.9") is None
