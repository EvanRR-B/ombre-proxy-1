import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    # 1. 接收 Chatbox 发来的请求
    data = request.get_json()
    
    # 2. 为了保证能通，强制把模型名字改成最简单的 deepseek-chat
    if 'model' in data:
        data['model'] = 'deepseek-chat'
    
    # 3. 构造要发给 DeepSeek 的请求
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 4. 把 Chatbox 的请求完整转发给 DeepSeek
    try:
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            json=data,
            headers=headers,
            timeout=60
        )
        resp.raise_for_status()
        
        # 5. 把 DeepSeek 的回复直接返回给 Chatbox
        return jsonify(resp.json())
        
    except Exception as e:
        print(f"DeepSeek API 调用失败: {e}")
        return jsonify({"error": str(e)}), 502

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
