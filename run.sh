#!/bin/bash
# wechat-gateway MCP Server 启动器（stdio）。由 WorkBuddy 拉起。
# 读取同目录 .env 注入 WG_BASE_URL / WG_API_TOKEN。
set -e
DIR="$(cd "$(dirname "$0") && pwd)"
set -a
[ -f "$DIR/.env" ] && . "$DIR/.env"
set +a
exec "$DIR/.venv/bin/python" "$DIR/server.py" "$@"
