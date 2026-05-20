import os
import requests
import json
import threading
from flask import Flask, request, Response, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_KEY = os.environ["DEEPSEEK_API_KEY"]
OMBRE_URL = os.environ.get("OMBRE_BRAIN_URL", "https://ombre-brain-p6yg.onrender.com")
OMBRE_SESSION = os.environ.get("OMBRE_SESSION", "")
OMBRE_PASSWORD = os.environ.get("OMBRE_PASSWORD", "")

# ---------- Session 管理 ----------
_session_cookie = None

def get_session():
    """获取或刷新 ombre_session cookie"""
    global _session_cookie
    if _session_cookie:
        return _session_cookie

    # 优先用环境变量里直接给的 cookie
    if OMBRE_SESSION:
        _session_cookie = OMBRE_SESSION
        return _session_cookie

    # 如果有密码，自动登录获取 session
    if OMBRE_PASSWORD:
        try:
            login_resp = requests.post(
                f"{OMBRE_URL}/api/login",
                json={"password": OMBRE_PASSWORD},
                timeout=10
            )
            if login_resp.status_code == 200:
                cookies = login_resp.cookies.get_dict()
                if "ombre_session" in cookies:
                    _session_cookie = cookies["ombre_session"]
                    print("[认证] 自动登录成功")
                    return _session_cookie

            # 有些部署用表单登录
            login_resp2 = requests.post(
                f"{OMBRE_URL}/login",
                data={"password": OMBRE_PASSWORD},
                timeout=10,
                allow_redirects=False
            )
            if "ombre_session" in login_resp2.cookies:
                _session_cookie = login_resp2.cookies["ombre_session"]
                print("[认证] 表单登录成功")
                return _session_cookie
        except Exception as e:
            print(f"[认证] 自动登录失败: {e}")

    return None

def clear_session():
    global _session_cookie
    _session_cookie = None

# ---------- MCP 调用 ----------
def mcp_call(tool_name, arguments=None):
    """通过 MCP 协议调用 Ombre-Brain 工具"""
    if arguments is None:
        arguments = {}

    session = get_session()
    if not session:
        print("[MCP] 无可用 session，跳过")
        return None

    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
        "id": 1
    }

    headers = {
        "Content-Type": "application/json",
        "Cookie": f"ombre_session={session}"
    }

    try:
        resp = requests.post(
            f"{OMBRE_URL}/mcp",
            json=payload,
            headers=headers,
            timeout=15
        )

        if resp.status_code == 401 or resp.status_code == 403:
            print("[MCP] Session 过期，尝试重新登录")
            clear_session()
            return None

        if resp.status_code == 404:
            print(f"[MCP] 端点 /mcp 不存在 (404)，尝试根路径")
            # fallback 到根路径
            resp2 = requests.post(
                f"{OMBRE_URL}/",
                json=payload,
                headers=headers,
                timeout=15
            )
            if resp2.status_code == 200:
                data = resp2.json()
                if "result" in data:
                    return data["result"]
            return None

        if resp.status_code == 200:
            data = resp.json()
            if "result" in data:
                return data["result"]
            if "error" in data:
                print(f"[MCP] 工具错误: {data['error']}")
                return None

        print(f"[MCP] 非预期状态码: {resp.status_code}, body: {resp.text[:200]}")
        return None

    except Exception as e:
        print(f"[MCP] 调用异常: {e}")
        return None

# ---------- 记忆操作 ----------
def retrieve_memory(query):
    """检索相关记忆"""
    result = mcp_call("breath", {"query": query})
    if not result:
        return ""

    content = result.get("content", result)
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                if "text" in item:
                    texts.append(item["text"])
                elif "content" in item:
                    texts.append(str(item["content"]))
                else:
                    texts.append(str(item))
            else:
                texts.append(str(item))
        return "\n---\n".join(texts)
    return str(content)

def store_memory(content):
    mcp_call("hold", {"content": content})

# ---------- HTTP 端点 ----------
@app.route("/health")
def health():
    return {"status": "ok"}

@app.route("/v1/models", methods=["GET"])
def models():
    return jsonify({
        "object": "list",
        "data": [
            {"id": "deepseek-chat", "object": "model", "owned_by": "deepseek"},
            {"id": "deepseek-v4-pro", "object": "model", "owned_by": "deepseek"}
        ]
    })

@app.route("/v1/chat/completions", methods=["POST"])
def chat():
    body = request.get_json()
    messages = body.get("messages", [])

    user_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_msg = msg["content"]
            break

    # 检索记忆
    memory = ""
    if user_msg:
        try:
            memory = retrieve_memory(user_msg)
            if memory:
                print(f"[记忆] 检索到 {len(memory)} 字符")
        except Exception as e:
            print(f"[记忆] 检索失败: {e}")

    # 注入记忆
    if memory:
        has_system = False
        for msg in messages:
            if msg["role"] == "system":
                msg["content"] = (
                    f"{msg['content']}\n\n"
                    f"[以下是你过去的记忆。自然地参考它们，不要逐条复述。]\n"
                    f"{memory}"
                )
                has_system = True
                break
        if not has_system:
            messages.insert(0, {
                "role": "system",
                "content": (
                    f"[以下是你过去的记忆。自然地参考它们，不要逐条复述。]\n"
                    f"{memory}"
                )
            })

    body["messages"] = messages

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_KEY}",
        "Content-Type": "application/json"
    }

    resp = requests.post(DEEPSEEK_URL, json=body, headers=headers, timeout=120)

    # 异步存记忆
    def save():
        try:
            if user_msg:
                store_memory(f"用户说了：{user_msg[:500]}")
            resp_data = resp.json()
            if "choices" in resp_data and resp_data["choices"]:
                content = resp_data["choices"][0].get("message", {}).get("content", "")
                if content:
                    store_memory(f"裴扬回复：{content[:500]}")
        except Exception as e:
            print(f"[记忆] 保存失败: {e}")

    threading.Thread(target=save, daemon=True).start()

    return Response(resp.content, status=resp.status_code, content_type="application/json")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
