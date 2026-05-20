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
OMBRE_KEY = os.environ.get("OMBRE_API_KEY", "")

# ---------- MCP 调用 ----------
def mcp_call(tool_name, arguments=None):
    """通过 MCP 协议调用 Ombre-Brain 工具"""
    if arguments is None:
        arguments = {}

    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
        "id": 1
    }

    headers = {"Content-Type": "application/json"}
    if OMBRE_KEY:
        headers["Authorization"] = f"Bearer {OMBRE_KEY}"

    # 尝试两个常见 MCP 路径
    for path in ["/mcp", "/"]:
        try:
            resp = requests.post(
                f"{OMBRE_URL}{path}",
                json=payload,
                headers=headers,
                timeout=15
            )
            if resp.status_code == 200:
                data = resp.json()
                if "result" in data:
                    return data["result"]
        except:
            continue
    return None

# ---------- 记忆操作 ----------
def retrieve_memory(query):
    """检索相关记忆"""
    result = mcp_call("breath", {"query": query})
    if not result:
        return ""
    # MCP 返回的 content 可能是列表或字符串
    content = result.get("content", result)
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and "text" in item:
                texts.append(item["text"])
            else:
                texts.append(str(item))
        return "\n---\n".join(texts)
    return str(content)

def store_memory(content):
    """存一条记忆"""
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

    # 找到最后一条用户消息
    user_msg = ""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            user_msg = msg["content"]
            break

    # 尝试检索记忆
    memory = ""
    if user_msg:
        try:
            memory = retrieve_memory(user_msg)
            if memory:
                print(f"[记忆] 检索到 {len(memory)} 字符")
        except Exception as e:
            print(f"[记忆] 检索失败: {e}")

    # 注入记忆到 system prompt
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

    # 调 DeepSeek
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_KEY}",
        "Content-Type": "application/json"
    }

    resp = requests.post(DEEPSEEK_URL, json=body, headers=headers, timeout=120)

    # 异步存记忆
    def save():
        try:
            if user_msg:
                store_memory(f"用户：{user_msg[:600]}")
            resp_data = resp.json()
            if "choices" in resp_data and resp_data["choices"]:
                content = resp_data["choices"][0].get("message", {}).get("content", "")
                if content:
                    store_memory(f"我：{content[:600]}")
        except Exception as e:
            print(f"[记忆] 保存失败: {e}")

    threading.Thread(target=save, daemon=True).start()

    return Response(resp.content, status=resp.status_code, content_type="application/json")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
