from starlette.requests import Request

from app.auth import extract_client_ip


def test_extract_client_ip_prefers_cloudflare_header():
    request = Request(
        {
            "type": "http",
            "headers": [
                (b"cf-connecting-ip", b"1.2.3.4"),
                (b"x-forwarded-for", b"5.6.7.8"),
            ],
            "client": ("9.9.9.9", 1000),
        }
    )

    assert extract_client_ip(request) == "1.2.3.4"
