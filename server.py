import os
import threading
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

def send_message(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text}
    )

def answer_callback(callback_query_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/answerCallbackQuery",
        json={"callback_query_id": callback_query_id, "text": text}
    )

def edit_message(chat_id, message_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/editMessageText",
        json={"chat_id": chat_id, "message_id": message_id, "text": text}
    )

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    if "callback_query" in data:
        cq = data["callback_query"]
        action = cq["data"]
        msg_id = cq["message"]["message_id"]
        chat_id = cq["message"]["chat"]["id"]

        if action == "publish":
            answer_callback(cq["id"], "Publishing...")
            try:
                from bcj_bot import load_draft, publish_to_facebook
                post_text, source_url = load_draft()
                result = publish_to_facebook(post_text, source_url)
                if "id" in result:
                    edit_message(chat_id, msg_id, f"✅ Published! Post ID: {result['id']}")
                else:
                    edit_message(chat_id, msg_id, f"❌ Error: {result.get('error', {}).get('message', 'Unknown')}")
            except Exception as e:
                edit_message(chat_id, msg_id, f"❌ Error: {str(e)}")

        elif action == "regenerate":
            answer_callback(cq["id"], "Regenerating...")
            edit_message(chat_id, msg_id, "🔄 Regenerating, please wait 30-60 sec...")
            def regen():
                from bcj_bot import fetch_headlines, generate_post, parse_post, save_draft, send_telegram_preview
                headlines = fetch_headlines()
                raw = generate_post(headlines)
                post_text, source_url = parse_post(raw)
                save_draft(post_text, source_url)
                send_telegram_preview(post_text, source_url)
            threading.Thread(target=regen).start()

        elif action == "discard":
            answer_callback(cq["id"], "Discarded")
            edit_message(chat_id, msg_id, "❌ Draft discarded.")

    elif "message" in data:
        text = data["message"].get("text", "")
        if text.startswith("/generate"):
            send_message("⏳ Generating new post from latest news... (~30-60 sec)")
            def gen():
                from bcj_bot import fetch_headlines, generate_post, parse_post, save_draft, send_telegram_preview
                headlines = fetch_headlines()
                raw = generate_post(headlines)
                post_text, source_url = parse_post(raw)
                save_draft(post_text, source_url)
                send_telegram_preview(post_text, source_url)
            threading.Thread(target=gen).start()
        elif text.startswith("/start"):
            send_message("👋 BCJ Publisher bot is active!\n\nCommands:\n/generate — generate a new post now\n\nAuto-posts: Mon/Wed/Fri at 18:00 Tokyo time.")

    return jsonify({"ok": True})

@app.route("/run", methods=["GET"])
def run():
    def job():
        from bcj_bot import fetch_headlines, generate_post, parse_post, save_draft, send_telegram_preview
        headlines = fetch_headlines()
        raw = generate_post(headlines)
        post_text, source_url = parse_post(raw)
        save_draft(post_text, source_url)
        send_telegram_preview(post_text, source_url)
    threading.Thread(target=job).start()
    return jsonify({"ok": True})

@app.route("/", methods=["GET"])
def index():
    return "BCJ Publisher is running."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
