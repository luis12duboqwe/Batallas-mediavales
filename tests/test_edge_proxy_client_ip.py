from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_caddy_overwrites_forwarded_client_ip_before_internal_proxy():
    caddyfile = (ROOT / "Caddyfile").read_text(encoding="utf-8")

    assert "reverse_proxy nginx:80" in caddyfile
    assert "header_up X-Forwarded-For {remote_host}" in caddyfile


def test_nginx_rate_limit_uses_sanitized_client_ip_not_caddy_container():
    nginx = (ROOT / "nginx.conf").read_text(encoding="utf-8")

    assert "map $http_x_forwarded_for $effective_client_ip" in nginx
    assert '"" $remote_addr;' in nginx
    assert "default $http_x_forwarded_for;" in nginx
    assert "limit_req_zone $effective_client_ip zone=api_limit:10m rate=10r/s;" in nginx
    assert "limit_req_zone $binary_remote_addr" not in nginx

    # Preserve the same effective address for the application instead of
    # re-appending Caddy's container IP to the sanitized forwarding header.
    assert nginx.count("proxy_set_header X-Real-IP $effective_client_ip;") == 3
    assert nginx.count("proxy_set_header X-Forwarded-For $effective_client_ip;") == 3
