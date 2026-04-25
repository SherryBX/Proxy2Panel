from app.parser import parse_share_links
import base64

from app.subscription import build_clash_profile, build_shadowrocket_profile
from app.utils import stable_id


RAW = """
vless://271c0354-4b19-46c9-bd8a-92e27f0c3ca9@yg7.ygkkk.dpdns.org:443?encryption=mlkem768.test&type=ws&host=firm-superintendent-machines-dealer.trycloudflare.com&path=%2F271c0354-4b19-46c9-bd8a-92e27f0c3ca9-vw&security=tls&sni=firm-superintendent-machines-dealer.trycloudflare.com&fp=chrome&flow=xtls-rprx-vision#AWS-JP-main
vless://271c0354-4b19-46c9-bd8a-92e27f0c3ca9@52.195.225.132:35994?type=ws&path=%2F271c0354-4b19-46c9-bd8a-92e27f0c3ca9-vw&security=none#AWS-JP-direct
"""


def test_build_clash_profile_keeps_vless_ws_tls_fields():
    nodes = parse_share_links(RAW)
    active_node_id = stable_id(RAW.splitlines()[1].strip())

    profile = build_clash_profile(nodes, active_node_id=active_node_id)

    assert "proxies:" in profile
    assert "proxy-groups:" in profile
    assert "type: vless" in profile
    assert "servername: firm-superintendent-machines-dealer.trycloudflare.com" in profile
    assert "client-fingerprint: chrome" in profile
    assert "ws-opts:" in profile
    assert "headers:" in profile
    assert "Host: firm-superintendent-machines-dealer.trycloudflare.com" in profile
    assert "encryption: mlkem768.test" in profile


def test_build_clash_profile_marks_current_node_in_select_group():
    nodes = parse_share_links(RAW)
    active_node_id = nodes[1]["id"]

    profile = build_clash_profile(nodes, active_node_id=active_node_id)

    assert "Proxy Admin Auto" in profile
    assert "AWS-JP-direct" in profile


def test_build_shadowrocket_profile_encodes_raw_links_as_base64_lines():
    nodes = parse_share_links(RAW)

    profile = build_shadowrocket_profile(nodes)
    decoded = base64.b64decode(profile).decode()

    assert "vless://" in decoded
    assert "AWS-JP-main" in decoded
    assert "AWS-JP-direct" in decoded
