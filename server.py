import os
import requests
import threading
from flask import Flask, request, jsonify
from bcj_bot import fetch_headlines, generate_post, parse_post, publish_to_facebook, send_telegram_preview

app = Flask(__name__)

TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

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

def send_message(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text}
    )

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.json

    # Handle callback buttons
    if "callback_query" in data:
        cq = data["callback_query"]
        action = cq["data"]
        msg_id = cq["message"]["message_id"]
        chat_id = cq["message"]["chat"]["id"]

        if action == "publish":
            answer_callback(cq["id"], "Publishing...")
            try:
                with open("/tmp/bcj_draft.txt") as f:
                    parts = f.read().split("\n---SOURCE---\n")
                post_text = parts[0]
                source_url = parts[1].strip() if len(parts) > 1 else ""

                result = publish_to_facebook(post_text, source_url)
                if "id" in result:
                    edit_message(chat_id, msg_id, f"✅ Published! Post ID: {result['id']}")
                else:
                    edit_message(chat_id, msg_id, f"❌ Error: {result.get('error', {}).get('message', 'Unknown error')}")
            except Exception as e:
                edit_message(chat_id, msg_id, f"❌ Error: {str(e)}")

        elif action == "regenerate":
            answer_callback(cq["id"], "Regenerating...")
            edit_message(chat_id, msg_id, "🔄 Regenerating post, please wait...")

            def regen():
                headlines = fetch_headlines()
                raw = generate_post(headlines)
                post_text, source_url = parse_post(raw)
                with open("/tmp/bcj_draft.txt", "w") as f:
                    f.write(post_text + "\n---SOURCE---\n" + source_url)
                send_telegram_preview(post_text, source_url)

            threading.Thread(target=regen).start()

        elif action == "discard":
            answer_callback(cq["id"], "Discarded")
            edit_message(chat_id, msg_id, "❌ Draft discarded.")

    # Handle /generate command
    elif "message" in data:
        text = data["message"].get("text", "")
        if text.startswith("/generate"):
            send_message("⏳ Generating new post from latest news...")

            def gen():
                headlines = fetch_headlines()
                raw = generate_post(headlines)
                post_text, source_url = parse_post(raw)
                with open("/tmp/bcj_draft.txt", "w") as f:
                    f.write(post_text + "\n---SOURCE---\n" + source_url)
                send_telegram_preview(post_text, source_url)

            threading.Thread(target=gen).start()

        elif text.startswith("/start"):
            send_message("👋 BCJ Publisher bot is active!\n\nCommands:\n/generate — generate a new post now\n\nPosts are also auto-generated on schedule (Mon/Wed/Fri).")

    return jsonify({"ok": True})

@app.route("/run", methods=["GET"])
def run():
    """Endpoint called by Render cron job"""
    def job():
        headlines = fetch_headlines()
        raw = generate_post(headlines)
        post_text, source_url = parse_post(raw)
        with open("/tmp/bcj_draft.txt", "w") as f:
            f.write(post_text + "\n---SOURCE---\n" + source_url)
        send_telegram_preview(post_text, source_url)

    threading.Thread(target=job).start()
    return jsonify({"ok": True, "message": "Post generation started"})

@app.route("/", methods=["GET"])
def index():
    return "BCJ Publisher bot is running."

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
