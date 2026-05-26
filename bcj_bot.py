import os
import re
import requests
import feedparser
import anthropic
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
FB_PAGE_TOKEN    = os.environ["FB_PAGE_TOKEN"]
FB_PAGE_ID       = os.environ["FB_PAGE_ID"]
ANTHROPIC_KEY    = os.environ["ANTHROPIC_KEY"]

RSS_FEEDS = [
    "https://news.yahoo.co.jp/rss/categories/business.xml",
    "https://www.nhk.or.jp/rss/news/cat5.xml",
    "https://news.google.com/rss/search?q=日本+経済+ビジネス+外国人&hl=ja&gl=JP&ceid=JP:ja",
]

KNOWN_DOMAINS = [
    "yahoo.co.jp", "nhk.or.jp", "nikkei.com", "japantimes.co.jp",
    "kyodonews.net", "toyokeizai.net", "reuters.com", "bloomberg.com",
    "asahi.com", "mainichi.jp", "yomiuri.co.jp", "jiji.com", "google.com"
]

def fetch_headlines():
    items = []
    for url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                items.append({
                    "title": entry.get("title", ""),
                    "link":  entry.get("link", ""),
                })
        except Exception as e:
            print(f"RSS error: {e}")
    return items[:10]

def is_known_domain(url):
    try:
        domain = url.replace("https://","").replace("http://","").split("/")[0]
        return any(d in domain for d in KNOWN_DOMAINS)
    except:
        return False

def generate_post(headlines):
    client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
    if headlines:
        headlines_text = "\n".join([f"{i+1}. {h['title']} — {h['link']}" for i, h in enumerate(headlines)])
        url_instruction = f"Here are the latest real headlines from Japanese business news. Pick the BEST ONE for a foreign business audience:\n\n{headlines_text}\n\nUse the exact article URL from the list above as SOURCE_URL."
    else:
        url_instruction = "Create a realistic Japan business/economy news item (2025-2026). Do NOT invent a URL."

    prompt = f"""You are writing a Facebook post for the Foreign Businessmen's Club of Japan (外国人ビジネスクラブ).

{url_instruction}

AUDIENCE: Foreign entrepreneurs — from solo founders and SME owners to mid-size executives — operating in Japan or planning to enter.

TOPIC PRIORITY:
✅ High: business law/tax/visa changes, FDI into Japan, JPY/BOJ/inflation, M&A, labor rules, SME policies, startups/VC
❌ Skip: pure politics, disasters, lifestyle, sports

WRITING RULES:
- Sound like a sharp human expert, NOT an AI
- No "In today's rapidly changing landscape", no "game-changer", no "navigate"
- Write as Itto Mogami (最上 一燈) personally sharing a take
- When mentioning Itto Mogami by name: add https://www.linkedin.com/in/mogami-itto/
- MAX 180 words English + 180 words Japanese

STRUCTURE:
1. Hook: one sharp sentence
2. 📰 What happened: 2 sentences max
3. 💼 Itto's take: 2 sentences with LinkedIn if name mentioned
4. ❓ Specific question
5. CTA: one line
6. Hashtags: #Japan #JapanBusiness + 2-3 relevant

Write English first, then Japanese below separated by ―――

SOURCE_URL: output exact unmodified URL on last line prefixed "SOURCE_URL:" — only if from headlines list. Otherwise omit."""

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

def parse_post(raw_text):
    source_url = ""
    post_text = raw_text
    match = re.search(r"SOURCE_URL:\s*(https?://\S+)", raw_text)
    if match:
        url = match.group(1)
        if is_known_domain(url):
            source_url = url
        post_text = re.sub(r"SOURCE_URL:.*$", "", raw_text, flags=re.MULTILINE).strip()
    return post_text, source_url

def send_telegram_preview(post_text, source_url):
    preview = f"📋 *BCJ Publisher — New Draft*\n\n{post_text}"
    if source_url:
        preview += f"\n\n🔗 {source_url}"
    preview += "\n\n━━━━━━━━━━━━━━━\nApprove to publish on Facebook?"

    keyboard = {"inline_keyboard": [[
        {"text": "✅ Publish", "callback_data": "publish"},
        {"text": "🔄 Regenerate", "callback_data": "regenerate"},
        {"text": "❌ Discard", "callback_data": "discard"}
    ]]}

    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": preview, "parse_mode": "Markdown", "reply_markup": keyboard}
    )
    print(f"Telegram response: {resp.status_code} {resp.text[:200]}")
    return resp.json()

def publish_to_facebook(post_text, source_url=""):
    body = {"message": post_text, "access_token": FB_PAGE_TOKEN}
    if source_url:
        body["link"] = source_url
    resp = requests.post(f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}/feed", json=body)
    return resp.json()

def save_draft(post_text, source_url):
    with open("/tmp/bcj_draft.txt", "w") as f:
        f.write(post_text + "\n---SOURCE---\n" + source_url)

def load_draft():
    try:
        with open("/tmp/bcj_draft.txt") as f:
            parts = f.read().split("\n---SOURCE---\n")
        return parts[0], parts[1].strip() if len(parts) > 1 else ""
    except:
        return "", ""

def main():
    print(f"[{datetime.now()}] BCJ Publisher starting...")
    headlines = fetch_headlines()
    print(f"Fetched {len(headlines)} headlines")
    raw = generate_post(headlines)
    post_text, source_url = parse_post(raw)
    print(f"Post generated ({len(post_text)} chars)")
    save_draft(post_text, source_url)
    send_telegram_preview(post_text, source_url)
    print("Done!")

if __name__ == "__main__":
    main()
