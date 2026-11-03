#!/bin/bash
# Sobe o portal (API + frontend compilado) na porta 8096. Lê DATABASE_URL do ambiente ou de portal/.env.
# Login: com JWT_SECRET confere o cookie do console-gateway; sem ele, PORTAL_SEM_LOGIN=1 libera a API (só local).
set -euo pipefail
cd "$(dirname "$0")"
[[ -z "${DATABASE_URL:-}" && -f .env ]] && set -a && . ./.env && set +a
exec ../.venv/bin/python -m flask --app api/app.py run --host 0.0.0.0 --port "${PORTA:-8096}"
