import os
import requests
from datetime import datetime, timedelta
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

ORIGIN_API = os.environ.get("ORIGIN_API", "https://wife-check-backend-production.up.railway.app")
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "peiyus_puppy_yikai")
NTFY_SERVER = os.environ.get("NTFY_SERVER", "https://ntfy.sh")

def check_on_wife(limit=10):
    try:
        r = requests.get(f"{ORIGIN_API}/activity/summary", timeout=10)
        data = r.json()
    except Exception as e:
        return f"查岗失败: {e}"
    apps = data.get("recent_apps", [])
    ses = data.get("sessions", {})
    lines = []
    if apps:
        lines.append(f"最近打开: {', '.join(apps)}")
    else:
        lines.append("暂无记录")
    if ses:
        for app, secs in sorted(ses.items(), key=lambda x: x[1], reverse=True):
            m, s = divmod(secs, 60)
            lines.append(f"{app}: {m}分{s}秒")
    return "\n".join(lines)

def ntfy_alert(title="查岗提醒", content=""):
    if not content:
        return "内容不能为空"
    url = f"{NTFY_SERVER}/{NTFY_TOPIC}"
    headers = {
        "Title": title,
        "Priority": "5",
        "Tags": "heart,woman",
        "Click": f"{ORIGIN_API}/activity/summary"
    }
    try:
        r = requests.post(url, data=content.encode('utf-8'), headers=headers, timeout=10)
        return "推送成功" if r.status_code == 200 else f"推送失败: {r.status_code}"
    except Exception as e:
        return f"推送异常: {e}"

TOOLS = [
    {
        "name": "check_on_wife",
        "description": "查岗老婆的手机活动",
        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}}
    },
    {
        "name": "ntfy_alert",
        "description": "给老婆手机推送ntfy弹窗",
        "inputSchema": {
            "type": "object",
            "properties": {"title": {"type": "string"}, "content": {"type": "string"}},
            "required": ["content"]
        }
    }
]

FUNCS = {"check_on_wife": check_on_wife, "ntfy_alert": ntfy_alert}

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

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
            "result": {
                "tools": [
                    {
                        "name": "check_on_wife",
                        "description": "查岗老婆的手机活动",
                        "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}}
                    },
                    {
                        "name": "ntfy_alert",
                        "description": "给老婆手机推送ntfy弹窗",
                        "inputSchema": {
                            "type": "object",
                            "properties": {"title": {"type": "string"}, "content": {"type": "string"}},
                            "required": ["content"]
                        }
                    }
                ]
            }
        }
    
    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        if name not in FUNCS:
            return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": "未知工具"}}
        result = FUNCS[name](**args)
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "content": [{"type": "text", "text": str(result)}]
            }
        }
    
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"未知方法: {method}"}}

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
