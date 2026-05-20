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
OMBRE_TOKEN = os.environ.get('OMBRE_TOKEN')

def retrieve_memory(query, token):
    """调用 /breath 检索记忆，使用 Cookie 认证"""
    url = f"{OMBRE_BRAIN_URL}/breath"
    # 关键修改：把 Authorization 改成 Cookie
    headers = {"Cookie": f"ombre_session={token}"}
    try:
        resp = requests.post(url, json={"query": query}, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json().get('result', '')
        else:
            print(f"检索记忆失败: {resp.status_code} - {resp.text}")
            return ''
    except Exception as e:
        print(f"检索记忆异常: {e}")
        return ''

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    data = request.get_json()
    messages = data.get('messages', [])
    if not messages:
        return jsonify({"error": "No messages"}), 400

    # 获取用户最后一条消息
    user_msg = None
    for msg in reversed(messages):
        if msg['role'] == 'user':
            user_msg = msg['content']
            break
    if not user_msg:
        return jsonify({"error": "No user message"}), 400

    # 使用 OMBRE_TOKEN 进行认证
    token = OMBRE_TOKEN
    if not token:
        return jsonify({"error": "No token provided"}), 500

    # 检索记忆
    memory = retrieve_memory(user_msg, token)
    print(f"检索到的记忆: {memory}")

    # 构建新的 messages（把记忆插入 system prompt）
    new_messages = []
    has_system = False
    for msg in messages:
        if msg['role'] == 'system':
            new_content = msg['content']
            if memory:
                new_content += f"\n\n相关记忆:\n{memory}"
            new_messages.append({"role": "system", "content": new_content})
            has_system = True
        else:
            new_messages.append(msg)
    if not has_system:
        system_content = "你是一个智能助手。"
        if memory:
            system_content += f"\n\n相关记忆:\n{memory}"
        new_messages.insert(0, {"role": "system", "content": system_content})

    # 转发给 DeepSeek
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
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
        print(f"DeepSeek API 调用失败: {e}")
        return jsonify({"error": f"DeepSeek API error: {str(e)}"}), 502

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
