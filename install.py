#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wechat-gateway MCP 安装器（跨平台）。

克隆/下载本项目后：
    python3 install.py
即可完成：①建虚拟环境 ②装依赖 ③把服务器注册进 ~/.workbuddy/mcp.json。
之后在 WorkBuddy「连接器管理」页找到 wechat-gateway，点 Trust 启用即可。
"""
import json
import os
import subprocess
import sys
import venv

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER_NAME = "wechat-gateway"
MCP_JSON = os.path.expanduser("~/.workbuddy/mcp.json")


def load_env() -> dict:
    env = {}
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


def main():
    env = load_env()
    if not env.get("WG_API_TOKEN"):
        sys.exit("❌ .env 缺少 WG_API_TOKEN，请先复制 .env.example 为 .env 并填入你自己的网关地址与服务令牌。")

    # 1) 虚拟环境
    venv_dir = os.path.join(HERE, ".venv")
    py = (os.path.join(venv_dir, "bin", "python")
          if os.name != "nt" else os.path.join(venv_dir, "Scripts", "python.exe"))
    if not os.path.isdir(venv_dir):
        print("① 创建虚拟环境 .venv ...")
        venv.create(venv_dir, with_pip=True)
    else:
        print("① 复用已有 .venv")

    # 2) 依赖
    print("② 安装依赖 (mcp, httpx) ...")
    subprocess.run([py, "-m", "pip", "install", "-r",
                    os.path.join(HERE, "requirements.txt"), "-q"], check=True)

    # 3) 注册进 mcp.json
    print("③ 注册到 WorkBuddy MCP 配置 ...")
    entry = {
        "command": py,
        "args": [os.path.join(HERE, "server.py")],
        "env": {
            "WG_BASE_URL": env.get("WG_BASE_URL", "https://your-wechat-gateway.example.com/api/v1/admin"),
            "WG_API_TOKEN": env["WG_API_TOKEN"],
        },
        "disabled": False,
    }
    data = {}
    if os.path.exists(MCP_JSON):
        try:
            with open(MCP_JSON, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
    data.setdefault("mcpServers", {})[SERVER_NAME] = entry
    os.makedirs(os.path.dirname(MCP_JSON), exist_ok=True)
    with open(MCP_JSON, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print("\n✅ 安装完成！")
    print("   服务器路径:", os.path.join(HERE, "server.py"))
    print("   已写入:", MCP_JSON)
    print("\n下一步：打开 WorkBuddy → 左侧「连接器」→ 找到 wechat-gateway → 点【Trust】启用。")
    print("启用后即可对 AI 说：「给 VIP 标签客户群发这条春分文案」。")


if __name__ == "__main__":
    main()
