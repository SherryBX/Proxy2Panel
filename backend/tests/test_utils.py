from app.utils import ip_allowed, build_rate_series


def test_ip_allowed_supports_exact_and_cidr_rules():
    rules = ['192.168.1.10', '10.0.0.0/24']

    assert ip_allowed('192.168.1.10', rules) is True
    assert ip_allowed('10.0.0.55', rules) is True
    assert ip_allowed('10.0.1.55', rules) is False


def test_ip_allowed_defaults_to_allow_when_rule_list_empty():
    assert ip_allowed('8.8.8.8', []) is True


def test_build_rate_series_computes_upload_and_download_rates():
    rows = [
        {'ts': 1000, 'rx_bytes': 100, 'tx_bytes': 200},
        {'ts': 1060, 'rx_bytes': 700, 'tx_bytes': 500},
        {'ts': 1120, 'rx_bytes': 1300, 'tx_bytes': 1100},
    ]

    series = build_rate_series(rows)

    assert len(series) == 2
    assert series[0]['download_bps'] == 10.0
    assert series[0]['upload_bps'] == 5.0
    assert series[1]['download_bps'] == 10.0
    assert series[1]['upload_bps'] == 10.0


def test_site_target_catalog_includes_major_overseas_services():
    from app.system_ops import ProxyManager

    names = [item["name"] for item in ProxyManager.SITE_TARGETS]

    assert "OpenAI" in names
    assert "Claude" in names
    assert "X" in names
    assert "YouTube" in names
