# -*- coding: utf-8 -*-
import os
import json
import random
import re
import feedparser
import backoff
import markdown as md
import google.generativeai as genai

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google.auth.transport.requests import Request

# ================= Secrets =================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")
BLOG_URL = os.getenv("BLOG_URL")  # optional, fallback only

missing = [
    name for name, val in {
        "GEMINI_API_KEY": GEMINI_API_KEY,
        "CLIENT_ID": CLIENT_ID,
        "CLIENT_SECRET": CLIENT_SECRET,
        "REFRESH_TOKEN": REFRESH_TOKEN,
    }.items() if not val
]

if missing:
    raise RuntimeError(f"❌ Missing secrets: {', '.join(missing)}")

# ================= Gemini =================

genai.configure(api_key=GEMINI_API_KEY)

FALLBACK_TOPICS = [
    "مستقبل الذكاء الاصطناعي في التعليم 2025",
    "أفضل طرق حماية الخصوصية على الإنترنت",
    "كيف تبدأ العمل الحر خطوة بخطوة",
    "تطبيقات لا غنى عنها لزيادة الإنتاجية",
    "شرح تقنية البلوك تشين للمبتدئين",
]

# ================= Blogger =================

def get_blogger_service():
    creds = Credentials(
        token=None,
        refresh_token=REFRESH_TOKEN,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=["https://www.googleapis.com/auth/blogger"],
    )

    # توليد access token فعلي
    creds.refresh(Request())

    return build("blogger", "v3", credentials=creds, cache_discovery=False)

def get_blog_id(service):
    blogs = service.blogs().listByUser(userId="self").execute()
    if blogs.get("items"):
        blog = blogs["items"][0]
        return blog["id"], blog["name"]

    if BLOG_URL:
        blog = service.blogs().getByUrl(url=BLOG_URL).execute()
        return blog["id"], blog["name"]

    return None, None

def get_recent_titles(service, blog_id):
    titles = []
    try:
        posts = service.posts().list(
            blogId=blog_id,
            fetchBodies=False,
            maxResults=15
        ).execute()
        for item in posts.get("items", []):
            titles.append(item.get("title", ""))
    except Exception as e:
        print(f"⚠ History warning: {e}")
    return titles

# ================= Logic =================

def clean(text):
    return re.sub(r"[^\w\s]", "", text).lower()

def is_duplicate(new_title, old_titles):
    nw = set(clean(new_title).split())
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

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def generate_article(topic):
    print(f"✍ Writing article: {topic}")

    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = f"""
    اكتب مقالًا تقنيًا عربيًا احترافيًا بعنوان: "{topic}"

    الشروط:
    - تنسيق Markdown
    - لغة عربية فصحى جذابة
    - لا تقل عن 500 كلمة
    - بدون مقدمات زائدة
    """

    res = model.generate_content(prompt)
    if not res.text:
        raise RuntimeError("Empty Gemini response")
    return res.text

def get_image():
    seed = random.randint(1, 9999)
    return (
        "https://image.pollinations.ai/prompt/"
        "futuristic%20technology%20ai%20background"
        f"?width=800&height=450&seed={seed}&nologo=true"
    )

# ================= Main =================

def main():
    print("🚀 Smart Iraq News Bot started")

    service = get_blogger_service()
    blog_id, blog_name = get_blog_id(service)

    if not blog_id:
        print("❌ No blog found")
        return

    print(f"✅ Connected to blog: {blog_name}")

    history = get_recent_titles(service, blog_id)
    topics = get_trends()

    topic = next(
        (t for t in topics if not is_duplicate(t, history)),
        random.choice(FALLBACK_TOPICS),
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
        <div style="text-align:center;margin-bottom:20px">
            <img src="{img}" style="max-width:100%;border-radius:12px">
        </div>
        <div dir="rtl" style="text-align:right;line-height:1.8">
            {html}
        </div>
        """,
        "labels": ["AI", "Technology"],
    }

    post = service.posts().insert(
        blogId=blog_id,
        body=body,
        isDraft=False
    ).execute()

    print(f"🎉 Published successfully: {post.get('url')}")

if __name__ == "__main__":
    main()
