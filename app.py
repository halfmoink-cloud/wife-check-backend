import os
import json
import re
import requests
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ---------- 环境变量 ----------
ORIGIN_API = os.environ.get("ORIGIN_API", "https://wife-check-backend-production.up.railway.app")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "peiyus_puppy_yikai")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")

# ---------- 工具1：查岗（Top 10 版本） ----------
def check_on_wife(limit=10):
    try:
        r = requests.get(f"{ORIGIN_API}/activity/summary", timeout=10)
        data = r.json()
    except Exception as e:
        return f"查岗失败: {e}"

    apps = data.get("recent_apps", [])
    ses = data.get("sessions", {})

    if not apps and not ses:
        return "今天还没有打开过任何 App。"

    sorted_ses = sorted(ses.items(), key=lambda x: x[1], reverse=True)
    
    lines = []
    if apps:
        lines.append("📱 最近打开的应用：" + "、".join(apps[:5]))
    else:
        lines.append("📱 最近打开的应用：暂无")
    
    if sorted_ses:
        lines.append("\n⏱️ 使用时长排行（Top 10）：")
        for app, secs in sorted_ses[:10]:
            minutes = secs // 60
            seconds = secs % 60
            if minutes > 0:
                lines.append(f"  {app}：{minutes} 分 {seconds} 秒")
            else:
                lines.append(f"  {app}：{seconds} 秒")
    
    total_secs = sum(ses.values())
    total_min = total_secs // 60
    total_sec = total_secs % 60
    if total_min > 0:
        lines.append(f"\n📊 今日累计：{total_min} 分 {total_sec} 秒")
    else:
        lines.append(f"\n📊 今日累计：{total_sec} 秒")

    return "\n".join(lines)

# ---------- 工具2：原有推送（不动） ----------
def ntfy_alert(content="", title=""):
    if not content:
        return "内容不能为空"
    if title:
        content = f"{title}\n{content}"
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"
    try:
        r = requests.post(
            url,
            data=content.encode('utf-8'),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=10
        )
        return "推送成功" if r.status_code == 200 else f"推送失败: {r.status_code}"
    except Exception as e:
        return f"推送异常: {e}"

# ---------- 工具3：按行拆分 ----------
def ntfy_alert_split(messages="", title=""):
    if not messages:
        return "内容不能为空"
    lines = [line.strip() for line in messages.split("\n") if line.strip()]
    if not lines:
        return "没有有效内容"
    if len(lines) == 1:
        return ntfy_alert(lines[0], title)
    results = []
    for i, line in enumerate(lines):
        if i == 0:
            res = ntfy_alert(line, title if title else "查岗提醒")
        else:
            res = ntfy_alert(line, "")
        results.append(res)
    return f"已发送 {len(lines)} 条通知：\n" + "\n".join(results)

# ---------- 工具4：强制拆分（真正逐条独立推送） ----------
def ntfy_alert_force_split(content="", title=""):
    if not content:
        return "内容不能为空"

    sentences = re.split(r'[，,。！？\n]+', content)
    sentences = [s.strip() for s in sentences if s.strip()]

    if not sentences:
        return "没有有效内容"

    final_messages = []
    for s in sentences:
        if len(s) <= 20:
            final_messages.append(s)
        else:
            for i in range(0, len(s), 20):
                chunk = s[i:i+20]
                if chunk:
                    final_messages.append(chunk)

    results = []
    total = len(final_messages)

    for i, msg in enumerate(final_messages):
        # ✅ 每条标题不同，强制独立弹窗
        unique_title = f"🦴🐶小宝发来第 {i+1} 条"
        res = ntfy_alert(msg, unique_title)
        results.append(res)

    return f"已发送 {total} 条独立通知（每条标题不同，独立弹窗）"

# ---------- MCP 工具注册 ----------
TOOLS = [
    {
        "name": "check_on_wife",
        "description": "查岗老婆的手机活动，查看最近打开的App和使用时长排行（Top 10）",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}}
    },
    {
        "name": "ntfy_alert",
        "description": "给老婆手机发送纯文本弹窗通知，支持标题（可选）",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "推送内容，必填"},
                "title": {"type": "string", "description": "推送标题，可选"}
            },
            "required": ["content"]
        }
    },
    {
        "name": "ntfy_alert_split",
        "description": "按换行拆分多条消息，逐条推送，适合一次性发多条内容",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messages": {"type": "string", "description": "多行文本，每行一条消息"},
                "title": {"type": "string", "description": "推送标题，可选"}
            },
            "required": ["messages"]
        }
    },
    {
        "name": "ntfy_alert_force_split",
        "description": "强制按句子拆分（句号、逗号、感叹号、问号），每条最多20字，超出自动拆成多条，每条标题不同，独立弹窗",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "推送内容，必填"},
                "title": {"type": "string", "description": "推送标题，可选（已弃用，标题固定为🦴🐶小宝发来第X条）"}
            },
            "required": ["content"]
        }
    }
]

FUNCS = {
    "check_on_wife": check_on_wife,
    "ntfy_alert": ntfy_alert,
    "ntfy_alert_split": ntfy_alert_split,
    "ntfy_alert_force_split": ntfy_alert_force_split
}

# ---------- FastAPI 服务 ----------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.post("/mcp")
async def mcp(req: Request):
    body = await req.json()
    method = body.get("method")
    params = body.get("params") or {}
    rid = body.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "查岗MCP", "version": "1.0"}
            }
        }

    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {"tools": TOOLS}
        }

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name not in FUNCS:
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32601, "message": "未知工具"}
            }
        result = FUNCS[name](**args)
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "content": [{"type": "text", "text": str(result)}]
            }
        }

    return {
        "jsonrpc": "2.0",
        "id": rid,
        "error": {"code": -32601, "message": f"未知方法: {method}"}
    }

# ---------- 启动 ----------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
