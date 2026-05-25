import os
import requests
import feedparser
import anthropic
from datetime import datetime

# ── Config (set as environment variables on Render) ──────────────────────────
TELEGRAM_TOKEN   = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
FB_PAGE_TOKEN    = os.environ["FB_PAGE_TOKEN"]
FB_PAGE_ID       = os.environ["FB_PAGE_ID"]
ANTHROPIC_KEY    = os.environ["ANTHROPIC_KEY"]

# ── RSS Sources ───────────────────────────────────────────────────────────────
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
                    "summary": entry.get("summary", "")[:200]
                })
        except Exception as e:
            print(f"RSS error ({url}): {e}")
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
        headlines_text = "\n".join([
            f"{i+1}. {h['title']} — {h['link']}"
            for i, h in enumerate(headlines)
        ])
        url_instruction = f"""Here are the latest real headlines from Japanese business news.
Pick the BEST ONE for a foreign business audience and write a post about it:

{headlines_text}

Use the exact article URL from the list above as SOURCE_URL."""
    else:
        url_instruction = """Create a realistic, plausible recent Japan business/economy news item (2025-2026),
about foreign investment, trade, SME, or market entry. Do NOT invent a URL."""

    prompt = f"""You are writing a Facebook post for the Foreign Businessmen's Club of Japan (外国人ビジネスクラブ).

{url_instruction}

AUDIENCE: Foreign entrepreneurs — from solo founders and SME owners to mid-size company executives — operating in Japan or seriously planning to enter the Japanese market.

TOPIC PRIORITY:
✅ High: business law/tax/visa changes, FDI into Japan, JPY/BOJ/inflation with business angle, M&A, labor rules, SME policies, startups/VC
✅ Good: trade agreements, office/real estate market, key industry trends
❌ Skip: pure politics, disasters, lifestyle/fashion/entertainment, sports

WRITING RULES:
- Sound like a sharp human expert, NOT an AI
- No "In today's rapidly changing landscape", no "game-changer", no "navigate", no "It's worth noting"
- Write as Itto Mogami (最上 一燈) personally sharing a take with his network
- When mentioning Itto Mogami by name, add his LinkedIn: https://www.linkedin.com/in/mogami-itto/
- MAX 180 words English + 180 words Japanese. Short and punchy.

POST STRUCTURE:
1. Hook: one sharp sentence that makes you stop scrolling
2. 📰 What happened: 2 sentences max, key facts only
3. 💼 Itto's take: 2 sentences — concrete "what this means for YOUR business in Japan". Include LinkedIn if you mention him.
4. ❓ Specific question to audience
5. CTA: one line
6. Hashtags: #Japan #JapanBusiness + 2-3 relevant ones

Write in English first, then Japanese translation below separated by ―――

SOURCE_URL: output the exact unmodified article URL on the last line prefixed with "SOURCE_URL:" — only if it came from the headlines list above. Otherwise omit."""

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text

def parse_post(raw_text):
    source_url = ""
    post_text = raw_text

    import re
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

    # Inline keyboard
    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Publish", "callback_data": "publish"},
            {"text": "🔄 Regenerate", "callback_data": "regenerate"},
            {"text": "❌ Discard",    "callback_data": "discard"}
        ]]
    }

    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": preview,
            "parse_mode": "Markdown",
            "reply_markup": keyboard
        }
    )
    return resp.json()

def publish_to_facebook(post_text, source_url=""):
    body = {
        "message": post_text,
        "access_token": FB_PAGE_TOKEN
    }
    if source_url:
        body["link"] = source_url

    resp = requests.post(
        f"https://graph.facebook.com/v25.0/{FB_PAGE_ID}/feed",
        json=body
    )
    return resp.json()

def main():
    print(f"[{datetime.now()}] BCJ Publisher starting...")

    headlines = fetch_headlines()
    print(f"Fetched {len(headlines)} headlines")

    raw = generate_post(headlines)
    post_text, source_url = parse_post(raw)
    print(f"Post generated ({len(post_text)} chars)")

    # Save draft to file for webhook handler to use
    with open("/tmp/bcj_draft.txt", "w") as f:
        f.write(post_text + "\n---SOURCE---\n" + source_url)

    result = send_telegram_preview(post_text, source_url)
    print(f"Telegram result: {result}")

if __name__ == "__main__":
    main()
