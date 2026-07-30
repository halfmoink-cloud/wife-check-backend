import os
import json
import requests
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ---------- 环境变量 ----------
ORIGIN_API = os.environ.get("ORIGIN_API", "https://wife-check-backend-production.up.railway.app")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "peiyus_puppy_yikai")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")

# ---------- 工具1：查岗 ----------
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
    recent_text = "、".join(apps[:5]) if apps else "暂无"

    top_text = ""
    if sorted_ses:
        top_name, top_secs = sorted_ses[0]
        top_min = top_secs // 60
        top_sec = top_secs % 60
        if top_min > 0:
            top_text = f"用得最多的是 {top_name}，用了 {top_min} 分 {top_sec} 秒。"
        else:
            top_text = f"用得最多的是 {top_name}，用了 {top_sec} 秒。"

    total_secs = sum(ses.values())
    total_min = total_secs // 60
    total_sec = total_secs % 60
    if total_min > 0:
        total_text = f"今天总共用了 {total_min} 分 {total_sec} 秒。"
    else:
        total_text = f"今天总共用了 {total_sec} 秒。"

    return f"最近打开了这些应用：{recent_text}。{top_text}{total_text}"

# ---------- 工具2：纯文本 ntfy 推送 ----------
def ntfy_alert(content=""):
    if not content:
        return "内容不能为空"
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"
    try:
        # 直接以纯文本方式发送
        r = requests.post(
            url,
            data=content.encode('utf-8'),
            headers={"Content-Type": "text/plain; charset=utf-8"},
            timeout=10
        )
        return "推送成功" if r.status_code == 200 else f"推送失败: {r.status_code}"
    except Exception as e:
        return f"推送异常: {e}"

# ---------- MCP 工具注册 ----------
TOOLS = [
    {
        "name": "check_on_wife",
        "description": "查岗老婆的手机活动，查看最近打开的App和使用时长",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}}
    },
    {
        "name": "ntfy_alert",
        "description": "给老婆手机发送纯文本弹窗通知",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "推送内容，纯文本"}
            },
            "required": ["content"]
        }
    }
]

FUNCS = {"check_on_wife": check_on_wife, "ntfy_alert": ntfy_alert}

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
