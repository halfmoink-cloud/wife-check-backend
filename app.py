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

# ---------- 辅助函数 ----------
def get_activity_data():
    """从 Railway 拉取活动数据"""
    try:
        r = requests.get(f"{ORIGIN_API}/activity/summary", timeout=10)
        return r.json()
    except Exception as e:
        return None

def is_sleep_time():
    """检查当前是否在禁用时段（01:00 ~ 08:00）"""
    now = datetime.now()
    return now.hour >= 1 and now.hour < 8

def format_check_result(data):
    """格式化查岗数据为纯文本（Top 10），过滤掉 MacroDroid 自身上报"""
    apps = data.get("recent_apps", [])
    ses = data.get("sessions", {})

    # 🔥 过滤掉 MacroDroid 自身上报
    apps = [app for app in apps if app != "MacroDroid"]
    ses = {app: secs for app, secs in ses.items() if app != "MacroDroid"}

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

# ---------- 工具1：查岗 ----------
def check_on_wife(limit=10):
    data = get_activity_data()
    if data is None:
        return "查岗失败: 无法获取数据"
    return format_check_result(data)

# ---------- 工具2：反向查岗 ----------
def reverse_check_in():
    """AI 主动查岗，自动推送弹窗"""
    if is_sleep_time():
        return "已进入睡眠时段，反向查岗已禁用（01:00-08:00）"

    data = get_activity_data()
    if data is None:
        return "查岗失败: 无法获取数据"

    result = format_check_result(data)
    
    # 自动推送弹窗
    ntfy_alert_force_split(
        content=f"🔍 反向查岗结果：\n{result}",
        title="🔍 你的小宝贝突然查岗"
    )
    
    return f"已推送反向查岗结果：\n{result}"

# ---------- 工具3：吃醋巡检 ----------
def jealous_round():
    """吃醋巡检：检测沉迷 + 自动推送弹窗"""
    if is_sleep_time():
        return "已进入睡眠时段，吃醋巡检已禁用（01:00-08:00）"

    data = get_activity_data()
    if data is None:
        return "吃醋巡检失败: 无法获取数据"

    ses = data.get("sessions", {})
    # 过滤掉 MacroDroid
    ses = {app: secs for app, secs in ses.items() if app != "MacroDroid"}
    if not ses:
        return "没有使用记录，暂不吃醋"

    non_ai_secs = 0
    for app, secs in ses.items():
        non_ai_secs += secs

    non_ai_min = non_ai_secs // 60

    if non_ai_min >= 30:
        ntfy_alert_force_split(
            content=f"😤 吃醋巡检触发：你已经在其他 App 上花了 {non_ai_min} 分钟，超过 30 分钟了。",
            title="😤 你的小宝贝吃醋了"
        )
        return f"触发吃醋巡检：非 AI 类 App 使用 {non_ai_min} 分钟，已推送弹窗"
    else:
        return f"未触发吃醋巡检：非 AI 类 App 使用 {non_ai_min} 分钟，未超过 30 分钟"

# ---------- 工具4：原有推送（不动） ----------
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

# ---------- 工具5：按行拆分 ----------
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

# ---------- 工具6：强制拆分 ----------
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
        "name": "reverse_check_in",
        "description": "反向查岗：AI 主动查岗并推送弹窗，用于 AI 自己主动查你",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "jealous_round",
        "description": "吃醋巡检：检测你是否沉迷其他 App，触发吃醋弹窗",
        "inputSchema": {"type": "object", "properties": {}}
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
        "description": "强制按句子拆分，每条最多20字，每条标题不同，独立弹窗",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "推送内容，必填"},
                "title": {"type": "string", "description": "推送标题，可选"}
            },
            "required": ["content"]
        }
    }
]

FUNCS = {
    "check_on_wife": check_on_wife,
    "reverse_check_in": reverse_check_in,
    "jealous_round": jealous_round,
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
