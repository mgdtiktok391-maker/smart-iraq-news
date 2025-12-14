# -*- coding: utf-8 -*-

import os
import random
import re
import requests
import feedparser
import backoff
import markdown as md

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# =================================================
# 🔐 Secrets
# =================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")
BLOG_URL = os.getenv("BLOG_URL")

missing = [
    k for k, v in {
        "GEMINI_API_KEY": GEMINI_API_KEY,
        "CLIENT_ID": CLIENT_ID,
        "CLIENT_SECRET": CLIENT_SECRET,
        "REFRESH_TOKEN": REFRESH_TOKEN,
    }.items() if not v
]

if missing:
    raise RuntimeError(f"❌ Missing secrets: {', '.join(missing)}")

# =================================================
# 📰 Blogger API
# =================================================

def get_blogger_service():
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/blogger"],
    )
    creds.refresh(Request())
    return build("blogger", "v3", credentials=creds, cache_discovery=False)

def get_blog_id(service):
    blogs = service.blogs().listByUser(userId="self").execute()
    if blogs.get("items"):
        b = blogs["items"][0]
        return b["id"], b["name"]
    if BLOG_URL:
        b = service.blogs().getByUrl(url=BLOG_URL).execute()
        return b["id"], b["name"]
    return None, None

# =================================================
# 🧠 Logic
# =================================================

FALLBACK_TOPICS = [
    "أفضل طرق حماية الخصوصية على الإنترنت",
    "مستقبل الذكاء الاصطناعي في التعليم",
    "كيف تبدأ العمل الحر خطوة بخطوة",
    "أهم أدوات الإنتاجية الرقمية",
    "شرح تقنية البلوك تشين للمبتدئين",
]

def clean(text):
    return re.sub(r"[^\w\s]", "", text).lower()

def is_duplicate(title, old_titles):
    nw = set(clean(title).split())
    for t in old_titles:
        ow = set(clean(t).split())
        if nw and len(nw & ow) / len(nw) > 0.5:
            return True
    return False

def get_trends():
    urls = [
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=SA",
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=EG",
    ]
    topics = []
    for url in urls:
        feed = feedparser.parse(url)
        for e in feed.entries[:2]:
            topics.append(e.title)
    topics.extend(FALLBACK_TOPICS)
    random.shuffle(topics)
    return topics

# =================================================
# 🤖 Gemini FREE (REST API)
# =================================================

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def generate_article(topic):
    print(f"✍ Writing article: {topic}")

    url = (
        "https://generativelanguage.googleapis.com/v1/models/"
        "gemini-1.5-flash:generateContent"
        f"?key={GEMINI_API_KEY}"
    )

    payload = {
        "contents": [{
            "parts": [{
                "text": f"""
اكتب مقالًا تقنيًا عربيًا احترافيًا بعنوان:
{topic}

الشروط:
- لغة عربية فصحى
- تنسيق Markdown
- لا يقل عن 500 كلمة
- بدون مقدمات زائدة
"""
            }]
        }]
    }

    r = requests.post(url, json=payload, timeout=60)
    r.raise_for_status()

    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]

def get_image():
    seed = random.randint(1, 9999)
    return (
        "https://image.pollinations.ai/prompt/"
        "futuristic%20technology%20ai%20background"
        f"?width=800&height=450&seed={seed}&nologo=true"
    )

# =================================================
# 🚀 Main
# =================================================

def main():
    print("🚀 Smart Iraq News Bot started")

    service = get_blogger_service()
    blog_id, blog_name = get_blog_id(service)
    if not blog_id:
        print("❌ No blog found")
        return

    print(f"✅ Connected to blog: {blog_name}")

    history = [
        p.get("title", "")
        for p in service.posts().list(
            blogId=blog_id, fetchBodies=False, maxResults=15
        ).execute().get("items", [])
    ]

    topic = next(
        (t for t in get_trends() if not is_duplicate(t, history)),
        random.choice(FALLBACK_TOPICS)
    )

    print(f"📝 Selected topic: {topic}")

    md_text = generate_article(topic)

    lines = md_text.strip().split("\n")
    title = topic
    if lines and lines[0].startswith("#"):
        title = lines[0].replace("#", "").strip()
        md_text = "\n".join(lines[1:])

    html = md.markdown(md_text)
    img = get_image()

    body = {
        "title": title,
        "content": f"""
<div style="text-align:center">
<img src="{img}" style="max-width:100%;border-radius:12px">
</div>
<div dir="rtl" style="text-align:right;line-height:1.8">
{html}
</div>
"""
    }

    post = service.posts().insert(
        blogId=blog_id,
        body=body,
        isDraft=False
    ).execute()

    print(f"🎉 Published: {post.get('url')}")

if __name__ == "__main__":
    main()
