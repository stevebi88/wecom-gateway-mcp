"""企业微信网关 · MCP Server（stdio）。

让 AI Agent 通过自然语言指令驱动后台：查客户/标签/内容、预览并创建群发与朋友圈 SOP。
安全设计：所有真实发送动作（create_group_send / create_moment_rule）默认只做「预览」，
必须显式 confirm=true 才会真正调用网关接口；网关侧用 MCP_API_TOKEN 服务令牌鉴权。

运行（stdio，由 MCP 客户端拉起）：
    python server.py
环境变量：
    WG_BASE_URL   网关 admin API 基址，默认 https://your-wechat-gateway.example.com/api/v1/admin
    WG_API_TOKEN  服务令牌（对应网关 .env 的 MCP_API_TOKEN），必填
"""
import os
import json
from typing import Optional

import httpx
from mcp.server.fastmcp import FastMCP

BASE_URL = os.getenv("WG_BASE_URL", "https://your-wechat-gateway.example.com/api/v1/admin").rstrip("/")
API_TOKEN = os.getenv("WG_API_TOKEN", "")

mcp = FastMCP("wechat-gateway")


def _headers() -> dict:
    h = {"Content-Type": "application/json"}
    if API_TOKEN:
        h["Authorization"] = f"Bearer {API_TOKEN}"
    return h


async def _req(method: str, path: str, *, json=None, params=None) -> dict:
    """统一请求网关；非 2xx 返回 {"error":..., "status":...} 而非抛异常，便于 Agent 读取。"""
    url = f"{BASE_URL}{path}"
    async with httpx.AsyncClient(timeout=30) as client:
        try:
            r = await client.request(method, url, json=json, params=params, headers=_headers())
        except Exception as e:  # noqa: BLE001
            return {"error": f"request failed: {e}"}
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text}
    if r.status_code >= 400:
        return {"error": f"HTTP {r.status_code}", "status": r.status_code, "detail": data}
    return data


async def _default_sender(account: str) -> list:
    """未指定 sender 时，取该账号配置的第一个客户联系成员作为默认执行人。

    让 Agent 在「一句话群发」时即使省略 sender 也能跑通；返回空列表表示取不到。
    """
    data = await _req("GET", "/accounts")
    items = data if isinstance(data, list) else (data.get("items") or data.get("accounts") or [])
    for a in items:
        if a.get("corpid") == account:
            uids = a.get("userids") or []
            if uids:
                return [uids[0]]
    return []


# ===================== 只读 / 发现类工具 =====================


@mcp.tool()
async def list_accounts() -> dict:
    """列出网关中已配置的企业微信账号（corpid 列表）。其他工具大多需要 corpid 作为 account 参数。"""
    return await _req("GET", "/accounts")


@mcp.tool()
async def list_members(corpid: str) -> dict:
    """列出某账号下的企业微信成员（userID），用于群发/朋友圈的 sender 候选。"""
    return await _req("GET", f"/accounts/{corpid}/members")


@mcp.tool()
async def list_tags(corpid: str) -> dict:
    """列出客户标签（tag_id + 名称），用于按标签群发（scope=tag）时构造 tag_filter。"""
    return await _req("GET", "/tags", params={"account": corpid})


@mcp.tool()
async def search_contacts(corpid: str, keyword: str = "", tag_id: str = "", userid: str = "", page: int = 1, size: int = 20) -> dict:
    """搜索客户（external_userid + 名称 + 标签）。可按关键词或标签筛选，用于确定群发接收人。"""
    return await _req("GET", "/contacts", params={
        "account": corpid, "keyword": keyword, "tag_id": tag_id,
        "userid": userid, "page": page, "size": size,
    })


@mcp.tool()
async def list_contents(corpid: str, kind: str = "", tag: str = "", scene: str = "", kw: str = "", page: int = 1, size: int = 20) -> dict:
    """浏览内容库。可按类型（image_text/video/link）、标签、场景、关键词筛选。返回内容条目列表（含 id/title/text/kind/assets）。"""
    return await _req("GET", "/contents", params={
        "account": corpid, "kind": kind, "tag": tag, "scene": scene,
        "kw": kw, "page": page, "size": size,
    })


@mcp.tool()
async def get_content(cid: int) -> dict:
    """获取单条内容详情（含 assets 与 asset_meta 素材信息）。cid 来自 list_contents 返回的 id。"""
    return await _req("GET", f"/contents/{cid}")


@mcp.tool()
async def list_group_send_tasks(corpid: str, page: int = 1, size: int = 20, status: str = "") -> dict:
    """列出历史群发任务（可按状态 submitted/pending/running/failed/cancelled 筛选）。"""
    return await _req("GET", "/group_send/tasks", params={
        "account": corpid, "page": page, "size": size, "status": status,
    })


@mcp.tool()
async def get_task_status(task_id: int, corpid: str) -> dict:
    """查询某条群发任务的执行状态与回执（task_id 来自创建群发时的返回）。"""
    return await _req("GET", f"/group_send/tasks/{task_id}", params={"account": corpid})


@mcp.tool()
async def list_moment_rules(corpid: str) -> dict:
    """列出已有的朋友圈 SOP 规则（含启用状态、定时策略）。"""
    return await _req("GET", "/moment/rules", params={"account": corpid})


# ===================== 动作类工具（受两步确认约束） =====================


@mcp.tool()
async def preview_group_send(
    account: str,
    sender: list,
    scope: str,
    text: str = "",
    external_userid: Optional[list] = None,
    tag_filter: Optional[dict] = None,
    attachments: Optional[list] = None,
    send_at: Optional[int] = None,
    chat_type: str = "single",
) -> dict:
    """群发【预览】——只校验参数并估算将发送的接收人数，不真实发送。

    参数与 create_group_send 一致：scope 可选 selected(指定客户)/tag(按标签)/member(成员全部客户)；
    selected 需 external_userid 列表，tag 需 tag_filter={group_list:[{tag_list:[tag_id,...]}]}。
    返回 valid / recipient_estimate / 文案与附件预览，供确认前复核。
    """
    sender = sender or await _default_sender(account)
    payload = {
        "account": account, "mode": "enterprise", "chat_type": chat_type,
        "scope": scope, "sender": sender, "text": text,
        "external_userid": external_userid or [], "tag_filter": tag_filter or {},
        "attachments": attachments or [], "send_at": send_at or 0,
    }
    return await _req("POST", "/group_send/preview", json=payload)


@mcp.tool()
async def create_group_send(
    confirm: bool = False,
    account: str = "",
    sender: list = None,
    scope: str = "selected",
    text: str = "",
    external_userid: Optional[list] = None,
    tag_filter: Optional[dict] = None,
    attachments: Optional[list] = None,
    send_at: Optional[int] = None,
    chat_type: str = "single",
) -> dict:
    """创建企业群发任务。

    ⚠️ 安全：默认 confirm=false 时【只做预览、不发送】，返回将发送计划。
    仅当 confirm=true 才真实创建群发任务（多成员自动拆分，各自成员企微确认后发送）。

    参数：
      account   corpid
      sender    执行成员 userid 列表（1-50）
      scope     selected / tag / member
      text      文案（可与附件并存）
      external_userid  scope=selected 时的客户列表
      tag_filter scope=tag 时的 {group_list:[{tag_list:[tag_id,...]}]}
      attachments  见 resolve_content 产出的结构（image/video 需 media_id，link 用 url）
      send_at   定时发送的 unix 秒；不填或<=now 立即发送
    """
    sender = sender or await _default_sender(account)
    payload = {
        "account": account, "mode": "enterprise", "chat_type": chat_type,
        "scope": scope, "sender": sender or [], "text": text,
        "external_userid": external_userid or [], "tag_filter": tag_filter or {},
        "attachments": attachments or [], "send_at": send_at or 0,
    }
    if not confirm:
        plan = await _req("POST", "/group_send/preview", json=payload)
        plan["_note"] = "预览模式：未真实发送。确认无误后带 confirm=true 再次调用本工具即可创建群发任务。"
        return plan
    return await _req("POST", "/group_send", json=payload)


@mcp.tool()
async def create_moment_rule(
    confirm: bool = False,
    account: str = "",
    name: str = "",
    sender_userids: list = None,
    text_content: str = "",
    attach_json: Optional[list] = None,
    tag_ids: Optional[list] = None,
    schedule_type: str = "once",
    schedule_json: Optional[dict] = None,
    remind_minutes: int = 0,
    enabled: bool = True,
) -> dict:
    """创建朋友圈 SOP 规则（定时/立即由调度器执行，成员在企微确认后发布）。

    ⚠️ 安全：默认 confirm=false 时仅回显将创建的配置，不真正创建；confirm=true 才创建。
    参数：account/sender_userids/tag_ids/attach_json 见 resolve_content 产出；
    schedule_type 可选 once/daily/weekly/monthly，schedule_json 描述具体时间。
    """
    payload = {
        "account": account, "name": name, "sender_userids": sender_userids or [],
        "tag_ids": tag_ids or [], "text_content": text_content,
        "attach_json": attach_json or [], "schedule_type": schedule_type,
        "schedule_json": schedule_json or {}, "remind_minutes": remind_minutes,
        "enabled": enabled,
    }
    if not confirm:
        payload["_note"] = "预览模式：未真实创建。确认无误后带 confirm=true 再次调用本工具即可创建朋友圈 SOP 规则。"
        return payload
    return await _req("POST", "/moment/rules", json=payload)


@mcp.tool()
async def cancel_group_send(task_id: int, account: str) -> dict:
    """停止一条待发送的群发任务（task_id 来自 create_group_send 返回）。"""
    return await _req("POST", "/group_send/cancel", json={"account": account, "task_id": task_id})


@mcp.tool()
async def cancel_moment_task(task_id: int) -> dict:
    """停止发表一条朋友圈任务（task_id 来自 create_moment_rule 生成的任务，或 list_moment_tasks）。

    ⚠️ 企微限制：无法撤回已发表到客户朋友圈的信息，仅对尚未发表完成的成员停止。
    """
    return await _req("POST", f"/moment/tasks/{task_id}/cancel")


@mcp.tool()
async def get_moment_task_result(task_id: int) -> dict:
    """查询一条朋友圈任务的最终发布情况（task_id 同上）。

    返回 task_list（各成员 publish_status：0=未发表 1=已发表）与已发表/未发表计数。
    """
    return await _req("GET", f"/moment/tasks/{task_id}/result")


@mcp.tool()
async def resolve_content(cid: int, target: str = "group_send") -> dict:
    """把内容库中的一条内容解析成可直接用于发送的结构，省去 Agent 自己拼媒体。

    target="group_send"：返回 {account, text, attachments} —— 图片/视频已自动调 /media/{id}/media_id
        拿到企微 media_id，可直接作为 create_group_send 的 attachments 参数。
    target="moment"：返回 {account, text_content, attach_json} —— 按 MomentRuleIn.attach_json 结构
        组织（含 asset_id），可直接作为 create_moment_rule 的 attach_json 参数。
    """
    c = await _req("GET", f"/contents/{cid}")
    if "error" in c:
        return c
    account = c.get("account", "")
    assets = c.get("assets") or []
    asset_meta = c.get("asset_meta") or {}
    text = c.get("text", "")

    def _atype(a: dict) -> str:
        t = a.get("type")
        if not t:
            mid = a.get("asset_id")
            t = (asset_meta.get(str(mid), {}) or {}).get("media_type") or "image"
        return t

    if target == "moment":
        attach = []
        for a in assets:
            aid = a.get("asset_id")
            attach.append({
                "type": _atype(a),
                "asset_id": aid,
                "title": a.get("title") or c.get("title", ""),
                "url": a.get("url", ""),
                "cover_asset_id": None,
            })
        return {"account": account, "text_content": text, "attach_json": attach, "target": "moment"}

    # group_send：图片/视频需 media_id
    atts = []
    for a in assets:
        aid = a.get("asset_id")
        try:
            aid = int(aid)
        except (TypeError, ValueError):
            atts.append({"_skip": "asset 无有效 asset_id", "raw": a})
            continue
        t = _atype(a)
        if t == "link":
            atts.append({"msgtype": "link", "link": {
                "title": a.get("title") or c.get("title", ""),
                "desc": "", "picurl": "", "url": a.get("url", ""),
            }})
            continue
        mid = await _req("POST", f"/media/{aid}/media_id", params={"account": account})
        m = mid.get("media_id") if isinstance(mid, dict) else None
        if not m:
            atts.append({"_error": f"asset {aid} 获取 media_id 失败（可能素材已过期且未存 COS）", "raw": mid})
            continue
        if t == "video":
            atts.append({"msgtype": "video", "video": {"media_id": m}})
        else:
            atts.append({"msgtype": "image", "image": {"media_id": m}})
    ok = [x for x in atts if "image" in x or "video" in x or "link" in x]
    return {
        "account": account, "text": text, "attachments": atts, "target": "group_send",
        "_resolved_count": len(ok),
        "_note": f"已成功解析 {len(ok)}/{len(assets)} 个素材为可发送附件；失败项见 _error（多为迁移素材过期未存 COS，需后台重新上传）。",
    }


if __name__ == "__main__":
    mcp.run()
