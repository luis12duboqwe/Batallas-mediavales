#!/usr/bin/env bash
set -euo pipefail

# Renew certificates and reload nginx
cd "$(dirname "$0")"

docker compose run --rm certbot renew --webroot -w /var/www/certbot

docker compose exec nginx nginx -s reload
