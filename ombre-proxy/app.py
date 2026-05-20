import os
import requests
from flask import Flask, request, Response, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
DEEPSEEK_KEY = os.environ["DEEPSEEK_API_KEY"]

@app.route("/health")
def health():
    return {"status": "ok"}

@app.route("/v1/models", methods=["GET"])
def models():
    # 返回一个简单的模型列表，让 Chatbox 认为连接成功
    return jsonify({
        "object": "list",
        "data": [
            {"id": "deepseek-chat", "object": "model", "owned_by": "deepseek"}
        ]
    })

@app.route("/v1/chat/completions", methods=["POST"])
def chat():
    body = request.get_json()

    headers = {
        "Authorization": f"Bearer {DEEPSEEK_KEY}",
        "Content-Type": "application/json"
    }

    resp = requests.post(DEEPSEEK_URL, json=body, headers=headers, timeout=120)

    return Response(resp.content, status=resp.status_code, content_type="application/json")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
