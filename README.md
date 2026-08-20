# 企业微信网关 · MCP Server

一个开源的 [MCP（Model Context Protocol）](https://modelcontextprotocol.io/) Server，让 AI Agent（如 WorkBuddy）通过自然语言指令驱动你自己部署的「企业微信客户管理网关」：

- 查客户 / 标签 / 内容库
- 预览并创建**企业群发**任务
- 预览并创建**朋友圈 SOP** 规则
- 查询任务状态、取消任务

> ⚠️ 本仓库只是 **MCP 客户端**。它不包含企业微信后端网关本身——你需要先自行部署一套「企微网关」后端（见下方「后端网关部署（概览）」），再用本仓库连上去。所有真实发送动作默认只做**预览**，需显式 `confirm=true` 才真正调用网关接口，避免误操作群发。

---

## 架构

```
┌──────────────┐   stdio + MCP    ┌──────────────────┐   HTTPS (Bearer)   ┌──────────────────────┐
│  AI Agent     │ ───────────────▶ │  wechat-gateway   │ ─────────────────▶ │  企业微信网关后端       │
│ (WorkBuddy)  │                  │  MCP Server       │                    │  (FastAPI 等，自部署)  │
└──────────────┘                  └──────────────────┘                    └──────────────────────┘
                                        ↑
                                   WG_BASE_URL / WG_API_TOKEN
                                   （你的 .env，不提交）
```

- **MCP Server（本仓库）**：读取 `WG_BASE_URL` / `WG_API_TOKEN`，把 Agent 的意图转成网关 API 调用。
- **网关后端（自部署）**：对接企业微信「客户联系」API，负责真实的客户同步、群发、朋友圈等，用 `MCP_API_TOKEN` 校验本 Server 的身份。

---

## 功能与工具清单

**只读 / 发现类**

| 工具 | 说明 |
|------|------|
| `list_accounts` | 列出网关已配置的企业微信账号（corpid 列表） |
| `list_members(corpid)` | 列出账号下的成员（userID），作群发/朋友圈 sender 候选 |
| `list_tags(corpid)` | 列出客户标签（tag_id + 名称） |
| `search_contacts(corpid, keyword, tag_id, userid, page, size)` | 搜索客户（external_userid + 名称 + 标签） |
| `list_contents(corpid, kind, tag, scene, kw, page, size)` | 浏览内容库（图文/视频/链接） |
| `get_content(cid)` | 获取单条内容详情 |
| `list_group_send_tasks(corpid, page, size, status)` | 列出历史群发任务 |
| `get_task_status(task_id, corpid)` | 查询群发任务执行状态与回执 |
| `list_moment_rules(corpid)` | 列出朋友圈 SOP 规则 |

**动作类（默认只预览、需 `confirm=true` 才真发）**

| 工具 | 说明 |
|------|------|
| `preview_group_send(...)` | 群发预览：校验参数 + 估算接收人数，不发送 |
| `create_group_send(confirm, ...)` | 创建企业群发；`confirm=false` 仅预览 |
| `create_moment_rule(confirm, ...)` | 创建朋友圈 SOP；`confirm=false` 仅预览 |
| `cancel_group_send(task_id, account)` | 停止待发送群发任务 |
| `cancel_moment_task(task_id)` | 停止未完成的朋友圈任务 |
| `get_moment_task_result(task_id)` | 查询朋友圈任务最终发布情况 |
| `resolve_content(cid, target)` | 把内容库条目解析成可直接发送的结构（自动取 media_id） |

---

## 前置条件

1. 已部署一套企业微信网关后端，并获得：
   - 后端 `admin` API 地址（形如 `https://gateway.your-domain.com/api/v1/admin`）
   - 后端分配的服务令牌 `MCP_API_TOKEN`
2. 本地 Python 3.10+
3. 一个支持 MCP 的 Agent 客户端（如 WorkBuddy）

---

## 快速开始

```bash
# 1) 克隆
git clone https://github.com/stevebi88/wechat-gateway-mcp.git
cd wechat-gateway-mcp

# 2) 配置环境变量（复制模板，填入你自己的网关地址与令牌）
cp .env.example .env
#   编辑 .env：
#     WG_BASE_URL=https://gateway.your-domain.com/api/v1/admin
#     WG_API_TOKEN=你网关后端分配的令牌

# 3) 安装并注册到 WorkBuddy（自动建 venv + 装依赖 + 写 mcp.json）
python3 install.py
```

完成后，在 WorkBuddy 左侧「连接器」找到 `wechat-gateway`，点 **Trust** 启用即可。启用后直接对 AI 说：

> 「给所有 VIP 标签客户群发这条春分活动文案」

Agent 会自行：找标签 → 估算人数 → 预览 →（你确认后）创建群发任务。

---

## 配置项

| 变量 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `WG_BASE_URL` | 是 | `https://your-wechat-gateway.example.com/api/v1/admin` | 网关 admin API 基址（结尾不含斜杠） |
| `WG_API_TOKEN` | 是 | 空 | 网关后端 `MCP_API_TOKEN`，用于 Bearer 鉴权 |

---

## 手动接入（不使用安装器）

在 WorkBuddy「连接器管理」手动添加一个 **stdio** 型 MCP：

```json
{
  "mcpServers": {
    "wechat-gateway": {
      "command": "/绝对路径/wechat-gateway-mcp/.venv/bin/python",
      "args": ["/绝对路径/wechat-gateway-mcp/server.py"],
      "env": {
        "WG_BASE_URL": "https://gateway.your-domain.com/api/v1/admin",
        "WG_API_TOKEN": "你网关后端分配的令牌"
      },
      "disabled": false
    }
  }
}
```

或直接用 `run.sh` 启动（它会读取同目录 `.env`）。

---

## 安全护栏

- 所有真实发送（`create_group_send` / `create_moment_rule`）默认 `confirm=false`，**只做预览、不发送**。
- 仅当 Agent 显式 `confirm=true` 才真实调用网关接口。
- 网关后端用 `MCP_API_TOKEN` 服务令牌鉴权；**本 Server 与令牌仅在你自有的网关与本地之间使用**。
- `.env` 含令牌，已被 `.gitignore` 忽略，请妥善保管、切勿提交或泄露。

---

## 后端网关部署（概览）

> 后端代码不在本仓库。以下为部署该 MCP 所连网关的**参考架构**，便于你自行搭建或核对环境。

建议栈（示例）：FastAPI（ASGI） + gunicorn + Nginx + Redis + SQLAlchemy，Python 3.12。

后端需提供的关键能力 / 配置：

- 企业微信「客户联系」相关凭据（corpid / secret / agentid 等），由后端自行保管，**不要放进本 MCP 仓库**。
- 暴露 `admin` API（本 Server 调用的各路径：`/accounts`、`/tags`、`/contacts`、`/contents`、`/group_send/*`、`/moment/*`、`/media/{id}/media_id` 等）。
- 后端 `.env` 需要有一个 `MCP_API_TOKEN`，其值与本 Server 的 `WG_API_TOKEN` 一致，用于校验调用方身份。
- 媒体素材建议转存对象存储（如 COS），避免 `resolve_content` 取 `media_id` 时因素材过期失败。

部署后拿到 `admin` 基址与 `MCP_API_TOKEN`，回填到本仓库 `.env` 即可。

---

## 已知数据问题

历史迁移素材若未转存对象存储，图片/视频类发送时 `resolve_content` 取 `media_id` 可能报「素材过期」。纯文本 / 链接发送不受影响；图片类发送需后端重新上传素材或转存对象存储。

---

## 许可证

[MIT](./LICENSE)
