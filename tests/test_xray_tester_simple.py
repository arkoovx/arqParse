"""Тесты для xray_tester_simple.py."""

import os
import sys
import json
from unittest import mock

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from xray_tester_simple import (
    _create_xray_config,
    _parse_vless_url,
    _parse_vmess_url,
    _parse_shadowsocks_url,
    _parse_trojan_url,
    _parse_hysteria2_to_outbound,
    _create_multi_config,
    _pre_validate_url,
    _get_next_port
)


def test_parse_vless_url():
    url = "vless://00000000-0000-0000-0000-000000000000@1.2.3.4:443?security=reality&sni=example.com&pbk=xxx#test"
    outbound = _parse_vless_url(url, tag="test_tag")
    assert outbound is not None
    assert outbound["tag"] == "test_tag"
    assert outbound["protocol"] == "vless"
    assert outbound["settings"]["vnext"][0]["address"] == "1.2.3.4"
    assert outbound["settings"]["vnext"][0]["port"] == 443
    assert outbound["settings"]["vnext"][0]["users"][0]["id"] == "00000000-0000-0000-0000-000000000000"
    assert outbound["streamSettings"]["security"] == "reality"
    assert outbound["streamSettings"]["realitySettings"]["serverName"] == "example.com"
    assert outbound["streamSettings"]["realitySettings"]["publicKey"] == "xxx"


def test_parse_vmess_url():
    # vmess://eyJhZGQiOiIxLjIuMy40IiwiYWlkIjoiMCIsImlkIjoiMDAwMDAwMDAtMDAwMC0wMDAwLTAwMDAtMDAwMDAwMDAwMDAwIiwibmV0IjoidGNwIiwicG9ydCI6IjQ0MyIsInBzIjoidGVzdCIsInNjeSI6ImF1dG8iLCJzbmkiOiIiLCJ0bHMiOiIiLCJ0eXBlIjoibm9uZSIsInYiOiIyIn0=
    # decoded: {"add":"1.2.3.4","aid":"0","id":"00000000-0000-0000-0000-000000000000","net":"tcp","port":"443","ps":"test","scy":"auto","sni":"","tls":"","type":"none","v":"2"}
    url = "vmess://eyJhZGQiOiIxLjIuMy40IiwiYWlkIjoiMCIsImlkIjoiMDAwMDAwMDAtMDAwMC0wMDAwLTAwMDAtMDAwMDAwMDAwMDAwIiwibmV0IjoidGNwIiwicG9ydCI6IjQ0MyIsInBzIjoidGVzdCIsInNjeSI6ImF1dG8iLCJzbmkiOiIiLCJ0bHMiOiIiLCJ0eXBlIjoibm9uZSIsInYiOiIyIn0="
    outbound = _parse_vmess_url(url, tag="vmess_tag")
    assert outbound is not None
    assert outbound["tag"] == "vmess_tag"
    assert outbound["protocol"] == "vmess"
    assert outbound["settings"]["vnext"][0]["address"] == "1.2.3.4"
    assert outbound["settings"]["vnext"][0]["port"] == 443
    assert outbound["settings"]["vnext"][0]["users"][0]["id"] == "00000000-0000-0000-0000-000000000000"
    assert outbound["streamSettings"]["network"] == "tcp"


def test_parse_shadowsocks_url():
    url = "ss://YWVzLTEyOC1nY206cGFzc3dvcmQ=@1.2.3.4:443#test"
    outbound = _parse_shadowsocks_url(url)
    assert outbound is not None
    assert outbound["protocol"] == "shadowsocks"
    assert outbound["settings"]["servers"][0]["address"] == "1.2.3.4"
    assert outbound["settings"]["servers"][0]["port"] == 443
    assert outbound["settings"]["servers"][0]["password"] == "password"
    assert outbound["settings"]["servers"][0]["method"] == "aes-128-gcm"


def test_parse_trojan_url():
    url = "trojan://password@example.com:443?type=ws&security=tls&path=%2Fws&host=cdn.example.com&sni=example.com"
    outbound = _parse_trojan_url(url)
    assert outbound is not None
    assert outbound["protocol"] == "trojan"
    assert outbound["streamSettings"]["network"] == "ws"
    assert outbound["streamSettings"]["wsSettings"]["path"] == "/ws"
    assert outbound["streamSettings"]["wsSettings"]["headers"]["Host"] == "cdn.example.com"


def test_parse_hysteria2_url():
    url = "hysteria2://password@1.2.3.4:443/?sni=example.com"
    outbound = _parse_hysteria2_to_outbound(url)
    assert outbound is not None
    assert outbound["protocol"] == "hysteria2"
    assert outbound["settings"]["servers"][0]["address"] == "1.2.3.4"
    assert outbound["settings"]["servers"][0]["port"] == 443
    assert outbound["settings"]["servers"][0]["password"] == "password"
    assert outbound["streamSettings"]["tlsSettings"]["serverName"] == "example.com"


def test_pre_validate_url():
    valid, msg = _pre_validate_url("")
    assert not valid
    valid, msg = _pre_validate_url("random_string")
    assert not valid
    valid, msg = _pre_validate_url("vless://@1.2.3.4:443")
    assert not valid  # empty UUID
    valid, msg = _pre_validate_url("vless://00000000-0000-0000-0000-000000000000@1.2.3.4:443")
    assert valid


@mock.patch("xray_tester_simple._get_next_port")
def test_create_multi_config(mock_get_next_port):
    mock_get_next_port.side_effect = [20000, 20001, 20002]
    urls = [
        "vless://00000000-0000-0000-0000-000000000000@1.2.3.4:443",
        "trojan://password@1.2.3.4:443",
        "invalid://url"
    ]
    config, port_map, skipped = _create_multi_config(urls)
    
    assert config is not None
    assert len(skipped) == 1
    assert skipped[0][0] == "invalid://url"
    
    # 2 urls parsed successfully
    assert len(port_map) == 2
    assert 20000 in port_map
    assert 20001 in port_map
    
    assert len(config["inbounds"]) == 2
    assert len(config["outbounds"]) == 4 # 2 proxies + direct + block
    
    inbounds = config["inbounds"]
    assert inbounds[0]["port"] == 20000
    assert inbounds[1]["port"] == 20001
    
    rules = config["routing"]["rules"]
    assert len(rules) == 2
    assert rules[0]["inboundTag"] == ["mixed20000"]
    assert rules[0]["outboundTag"] == "proxy20000"
