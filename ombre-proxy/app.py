import os
import requests
import json
import time
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 从环境变量读取配置
OMBRE_BRAIN_URL = os.environ.get('OMBRE_BRAIN_URL', 'https://ombre-brain-p6yg.onrender.com')
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')
OMBRE_USERNAME = os.environ.get('OMBRE_USERNAME')
OMBRE_PASSWORD = os.environ.get('OMBRE_PASSWORD')

_token = None
_token_expire = 0

def get_ombre_token():
    global _token, _token_expire
    if _token and time.time() < _token_expire:
        return _token
    try:
        resp = requests.post(f"{OMBRE_BRAIN_URL}/api/auth/login", 
                           json={"username": OMBRE_USERNAME, "password": OMBRE_PASSWORD},
                           timeout=10)
        resp.raise_for_status()
        _token = resp.json().get('token')
        _token_expire = time.time() + 3600  # 1小时有效期
        return _token
    except:
        return None

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    data = request.get_json()
    messages = data.get('messages', [])
    if not messages:
        return jsonify({"error": "No messages"}), 400

    # 获取用户最后一条消息
    user_msg = next((msg['content'] for msg in reversed(messages) if msg['role'] == 'user'), None)
    if not user_msg:
        return jsonify({"error": "No user message"}), 400

    # 获取令牌
    token = get_ombre_token()
    if not token:
        return jsonify({"error": "Auth failed"}), 500

    # 检索记忆
    memory = ""
    try:
        resp = requests.post(f"{OMBRE_BRAIN_URL}/breath", 
                           json={"query": user_msg},
                           headers={"Authorization": f"Bearer {token}"},
                           timeout=10)
        if resp.status_code == 200:
            memory = resp.json().get('result', '')
    except:
        pass

    # 构建带记忆的 system prompt
    new_messages = []
    has_system = False
    for msg in messages:
        if msg['role'] == 'system':
            new_messages.append({"role": "system", "content": msg['content'] + (f"\n\n记忆参考:\n{memory}" if memory else "")})
            has_system = True
        else:
            new_messages.append(msg)
    if not has_system:
        new_messages.insert(0, {"role": "system", "content": f"你是智能助手。\n\n记忆参考:\n{memory}" if memory else "你是智能助手。"})

    # 调用 DeepSeek
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": new_messages,
        "stream": False,
        "temperature": 1.0,
        "max_tokens": 4096
    }
    try:
        resp = requests.post("https://api.deepseek.com/v1/chat/completions", json=payload, headers=headers, timeout=60)
        resp.raise_for_status()
        return jsonify(resp.json())
    except Exception as e:
        return jsonify({"error": str(e)}), 502

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)