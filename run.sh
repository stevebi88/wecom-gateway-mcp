#!/bin/bash
# 启动 wechat-gateway MCP Server（stdio）。由 MCP 客户端（如 WorkBuddy/Claude Code）拉起。
# 配置从同目录 .env 读取：WG_BASE_URL（网关 admin API 基址）、WG_API_TOKEN（网关 .env 的 MCP_API_TOKEN）
set -e
DIR="$(cd "$(dirname "$0")" && pwd)"

# 读取 .env（若存在）
if [ -f "$DIR/.env" ]; then
  set -a; . "$DIR/.env"; set +a
fi

export WG_BASE_URL="${WG_BASE_URL:-http://127.0.0.1:8000/api/v1/admin}"
export WG_API_TOKEN="${WG_API_TOKEN:-}"

exec "$DIR/.venv/bin/python" "$DIR/server.py" "$@"
