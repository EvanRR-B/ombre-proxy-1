import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 从环境变量读取 DeepSeek 密钥
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY')

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    # 1. 接收 Chatbox 发来的请求
    data = request.get_json()
    
    # 2. 强制模型名称为最基础的 deepseek-chat
    if 'model' in data:
        data['model'] = 'deepseek-chat'
    
    # 3. 准备转发给 DeepSeek
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # 4. 直接转发请求，并加入详细的错误日志
    try:
        # 使用 DeepSeek 官方的标准地址
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            json=data,
            headers=headers,
            timeout=60
        )
        # 打印状态码到 Render 日志，方便排查
        print(f"DeepSeek 返回状态码: {resp.status_code}")
        
        resp.raise_for_status()
        
        # 5. 把 DeepSeek 的回复直接返回给 Chatbox
        return jsonify(resp.json())
        
    except requests.exceptions.RequestException as e:
        print(f"DeepSeek 调用出错: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"错误响应内容: {e.response.text}")
        return jsonify({"error": f"DeepSeek API error: {str(e)}"}), 502

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
