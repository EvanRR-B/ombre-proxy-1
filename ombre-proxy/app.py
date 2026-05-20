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
    headers = {"Cookie": f"ombre_session={token}"}
    try:
        resp = requests.post(url, json={"query": query}, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json().get('result', '')
        else:
            print(f"记忆检索失败: {resp.status_code}")
            return ''
    except Exception as e:
        print(f"记忆检索异常: {e}")
        return ''

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    # 1. 解析请求
    data = request.get_json()
    messages = data.get('messages', [])
    if not messages:
        return jsonify({"error": "No messages"}), 400

    # 2. 提取用户最后一条消息
    user_msg = None
    for msg in reversed(messages):
        if msg['role'] == 'user':
            user_msg = msg['content']
            break
    if not user_msg:
        return jsonify({"error": "No user message"}), 400

    # 3. 获取身份令牌
    token = OMBRE_TOKEN
    if not token:
        return jsonify({"error": "No token provided"}), 500

    # 4. 检索记忆（注意：这里可能会失败，但不影响 DeepSeek 调用）
    memory = retrieve_memory(user_msg, token)
    print(f"检索到的记忆片段: {memory[:100]}...")

    # 5. 构建新的 messages（把记忆插入 system prompt）
    new_messages = []
    has_system = False
    for msg in messages:
        if msg['role'] == 'system':
            new_content = msg['content']
            if memory:
                new_content += f"\n\n【相关记忆】:\n{memory}"
            new_messages.append({"role": "system", "content": new_content})
            has_system = True
        else:
            new_messages.append(msg)
    if not has_system:
        system_content = "你是一个智能助手。"
        if memory:
            system_content += f"\n\n【相关记忆】:\n{memory}"
        new_messages.insert(0, {"role": "system", "content": system_content})

    # 【关键修改】在用户消息后面，强制加上一个“引导词”
    # 这样 DeepSeek 就一定会回复一段有内容的文字，而不会返回空白
    if len(new_messages) > 0 and new_messages[-1]['role'] == 'user':
        new_messages[-1]['content'] += "\n\n（请务必在回复的开头加上“你好，我是来自未来的智能助理：”这句话，然后再回答我的问题。）"

    # 6. 打印调试信息
    print(f"正在使用的 API Key 前缀: {DEEPSEEK_API_KEY[:10]}...")
    print(f"向 DeepSeek 发送 {len(new_messages)} 条消息，包含记忆")

    # 7. 调用 DeepSeek V4 Pro（使用官方 BASE URL 的正确地址）
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "deepseek-v4-pro",
        "messages": new_messages,
        "stream": False,
        "temperature": 1.0,
        "max_tokens": 4096
    }
    
    try:
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            json=payload,
            headers=headers,
            timeout=60
        )
        resp.raise_for_status()
        
        response_json = resp.json()
        if 'choices' in response_json and len(response_json['choices']) > 0:
            content = response_json['choices'][0].get('message', {}).get('content', '')
            print(f"DeepSeek 回复长度: {len(content)} 字符")
            print(f"DeepSeek 回复内容预览: {content[:50]}...")
        else:
            print("⚠️ 警告：DeepSeek 返回了没有 choices 的响应")
        
        return jsonify(response_json)
        
    except Exception as e:
        print(f"DeepSeek API 调用失败: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"错误响应内容: {e.response.text}")
        return jsonify({"error": f"DeepSeek API error: {str(e)}"}), 502

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
