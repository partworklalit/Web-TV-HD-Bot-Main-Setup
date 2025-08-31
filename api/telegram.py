import os
import json
import requests
from http.server import BaseHTTPRequestHandler

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")  # Vercel environment variable
API_URL = f"https://api.telegram.org/bot{TOKEN}"

def send_message(chat_id, text):
    url = f"{API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    requests.post(url, json=payload)

class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        update = json.loads(body)

        # Agar user ka message aya hai
        if "message" in update and "text" in update["message"]:
            chat_id = update["message"]["chat"]["id"]
            text = update["message"]["text"]

            # Simple responder (baad me database add kar lena)
            if text.lower() == "hi":
                send_message(chat_id, "Hello! How are you?")
            else:
                send_message(chat_id, f"You said: {text}")

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")
        return
