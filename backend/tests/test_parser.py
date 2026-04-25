from app.parser import parse_share_links

SAMPLE = '''
vless://271c0354-4b19-46c9-bd8a-92e27f0c3ca9@www.xiaoshuofen.com:443?flow=xtls-rprx-vision&type=ws&host=firm-superintendent-machines-dealer.trycloudflare.com&path=%2F271c0354-4b19-46c9-bd8a-92e27f0c3ca9-vw&security=tls&sni=firm-superintendent-machines-dealer.trycloudflare.com&fp=chrome#AWS-JP-main
vless://271c0354-4b19-46c9-bd8a-92e27f0c3ca9@cf.godns.cc:443?flow=xtls-rprx-vision&type=ws&host=firm-superintendent-machines-dealer.trycloudflare.com&path=%2F271c0354-4b19-46c9-bd8a-92e27f0c3ca9-vw&security=tls&sni=firm-superintendent-machines-dealer.trycloudflare.com&fp=chrome#AWS-JP-backup
invalid-line
'''


def test_parse_share_links_extracts_vless_nodes():
    nodes = parse_share_links(SAMPLE)

    assert len(nodes) == 2
    assert nodes[0]['scheme'] == 'vless'
    assert nodes[0]['address'] == 'www.xiaoshuofen.com'
    assert nodes[0]['port'] == 443
    assert nodes[0]['network'] == 'ws'
    assert nodes[0]['security'] == 'tls'
    assert nodes[0]['host'] == 'firm-superintendent-machines-dealer.trycloudflare.com'
    assert nodes[0]['path'] == '/271c0354-4b19-46c9-bd8a-92e27f0c3ca9-vw'
    assert nodes[0]['label'] == 'AWS-JP-main'


def test_parse_share_links_stable_ids_and_skips_invalid_lines():
    first = parse_share_links(SAMPLE)
    second = parse_share_links(SAMPLE)

    assert [node['id'] for node in first] == [node['id'] for node in second]
    assert all(node['raw_link'].startswith('vless://') for node in first)


def test_parse_share_links_shortens_overlong_default_labels():
    raw = """
vless://271c0354-4b19-46c9-bd8a-92e27f0c3ca9@yg7.ygkkk.dpdns.org:443?type=ws&host=firm-superintendent-machines-dealer.trycloudflare.com&path=%2Fabc&security=tls#AWS-JP-vless-ws-tls-argo-enc-vision-ip-172-31-46-191
vless://271c0354-4b19-46c9-bd8a-92e27f0c3ca9@52.195.225.132:35994?type=ws&path=%2Fabc&security=none#AWS-JP-vl-ws-enc-ip-172-31-46-191
"""
    nodes = parse_share_links(raw)

    assert nodes[0]["label"] == "Argo TLS"
    assert nodes[1]["label"] == "直连入口"
