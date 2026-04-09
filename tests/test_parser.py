"""Тесты для модуля parser."""

import os
import sys
import tempfile

# Добавляем корень проекта в sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from parser import parse_mtproto_url, read_configs_from_file, read_mtproto_from_file


class TestParseMtproto:
    def test_valid_tme_url(self):
        url = "https://t.me/proxy?server=1.2.3.4&port=443&secret=abc123"
        result = parse_mtproto_url(url)
        assert result is not None
        assert result['server'] == '1.2.3.4'
        assert result['port'] == 443
        assert result['secret'] == 'abc123'

    def test_invalid_port(self):
        url = "https://t.me/proxy?server=1.2.3.4&port=99999&secret=abc"
        assert parse_mtproto_url(url) is None

    def test_port_zero(self):
        url = "https://t.me/proxy?server=1.2.3.4&port=0&secret=abc"
        assert parse_mtproto_url(url) is None

    def test_missing_secret(self):
        url = "https://t.me/proxy?server=1.2.3.4&port=443"
        assert parse_mtproto_url(url) is None

    def test_missing_server(self):
        url = "https://t.me/proxy?port=443&secret=abc"
        assert parse_mtproto_url(url) is None

    def test_not_mtproto_url(self):
        assert parse_mtproto_url("vless://uuid@host:443") is None
        assert parse_mtproto_url("") is None
        assert parse_mtproto_url("https://example.com") is None

    def test_tg_protocol_url(self):
        url = "tg://proxy?server=10.0.0.1&port=8080&secret=xyz"
        result = parse_mtproto_url(url)
        assert result is not None
        assert result['server'] == '10.0.0.1'
        assert result['port'] == 8080
        assert result['secret'] == 'xyz'


class TestReadConfigsFromFile:
    def test_nonexistent_file(self):
        assert read_configs_from_file("/nonexistent/path.txt") == []

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("")
            f.flush()
            path = f.name
        try:
            assert read_configs_from_file(path) == []
        finally:
            os.unlink(path)

    def test_comments_skipped(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("# comment\n")
            f.write("vless://abc@host:443?security=none#test\n")
            f.flush()
            path = f.name
        try:
            configs = read_configs_from_file(path)
            assert len(configs) == 1
            assert configs[0].startswith("vless://")
        finally:
            os.unlink(path)

    def test_profile_headers_skipped(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("#profile-title: Test\n")
            f.write("#profile-update-interval: 48\n")
            f.write("#support-url: https://example.com\n")
            f.write("\n")
            f.write("vless://abc@host:443?security=none#test\n")
            f.flush()
            path = f.name
        try:
            configs = read_configs_from_file(path)
            assert len(configs) == 1
        finally:
            os.unlink(path)

    def test_html_entities_decoded(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("vless://abc%26def@host:443?security=none#test\n")
            f.flush()
            path = f.name
        try:
            configs = read_configs_from_file(path)
            assert len(configs) == 1
        finally:
            os.unlink(path)

    def test_multiple_configs(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("vless://a@h1:443?security=none#t1\n")
            f.write("trojan://pass@h2:443#t2\n")
            f.write("vmess://dGVzdA==#t3\n")
            f.flush()
            path = f.name
        try:
            configs = read_configs_from_file(path)
            assert len(configs) == 3
        finally:
            os.unlink(path)

    def test_glued_configs_are_split(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("vless://a@h1:443?security=none#t1trojan://pass@h2:443#t2")
            f.flush()
            path = f.name
        try:
            configs = read_configs_from_file(path)
            assert len(configs) == 2
            assert configs[0].startswith("vless://")
            assert configs[1].startswith("trojan://")
        finally:
            os.unlink(path)


class TestReadMtprotoFromFile:
    def test_nonexistent_file(self):
        assert read_mtproto_from_file("/nonexistent/path.txt") == []

    def test_single_proxy(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("https://t.me/proxy?server=1.2.3.4&port=443&secret=abc\n")
            f.flush()
            path = f.name
        try:
            proxies = read_mtproto_from_file(path)
            assert len(proxies) == 1
            assert '1.2.3.4' in proxies[0]
        finally:
            os.unlink(path)

    def test_multiple_proxies(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("https://t.me/proxy?server=1.1.1.1&port=443&secret=a\n")
            f.write("https://t.me/proxy?server=2.2.2.2&port=8080&secret=b\n")
            f.flush()
            path = f.name
        try:
            proxies = read_mtproto_from_file(path)
            assert len(proxies) == 2
        finally:
            os.unlink(path)

    def test_proxy_without_secret_is_skipped(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("https://t.me/proxy?server=1.1.1.1&port=443\n")
            f.flush()
            path = f.name
        try:
            proxies = read_mtproto_from_file(path)
            assert proxies == []
        finally:
            os.unlink(path)

    def test_glued_mtproto_are_split(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(
                "https://t.me/proxy?server=1.1.1.1&port=443&secret=a"
                "https://t.me/proxy?server=2.2.2.2&port=8080&secret=b"
            )
            f.flush()
            path = f.name
        try:
            proxies = read_mtproto_from_file(path)
            assert len(proxies) == 2
            assert "1.1.1.1" in proxies[0]
            assert "2.2.2.2" in proxies[1]
        finally:
            os.unlink(path)

    def test_duplicate_mtproto_are_deduplicated(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            proxy = "https://t.me/proxy?server=1.1.1.1&port=443&secret=a"
            f.write(f"{proxy}\n{proxy}\n")
            f.flush()
            path = f.name
        try:
            proxies = read_mtproto_from_file(path)
            assert proxies == [proxy]
        finally:
            os.unlink(path)
