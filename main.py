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

# ================= إعدادات البيئة =================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BLOGGER_TOKEN_STR = os.getenv("BLOGGER_TOKEN")

if not GEMINI_API_KEY:
    raise RuntimeError("❌ Missing GEMINI_API_KEY in GitHub Secrets")

if not BLOGGER_TOKEN_STR:
    raise RuntimeError("❌ Missing BLOGGER_TOKEN in GitHub Secrets")

# إعداد Gemini
genai.configure(api_key=GEMINI_API_KEY)

FALLBACK_TOPICS = [
    "مستقبل الذكاء الاصطناعي في التعليم 2025",
    "أفضل طرق حماية الخصوصية على الإنترنت",
    "كيف تبدأ العمل الحر Freelancing خطوة بخطوة",
    "تطبيقات لا غنى عنها لزيادة الإنتاجية",
    "شرح تقنية البلوك تشين للمبتدئين"
]

# ================= Blogger =================

def get_blogger_service():
    token_info = json.loads(BLOGGER_TOKEN_STR)
    creds = Credentials.from_authorized_user_info(
        token_info,
        scopes=["https://www.googleapis.com/auth/blogger"]
    )
    return build("blogger", "v3", credentials=creds, cache_discovery=False)

def get_blog_id(service):
    blogs = service.blogs().listByUser(userId="self").execute()
    if not blogs.get("items"):
        return None, None
    blog = blogs["items"][0]
    return blog["id"], blog["name"]

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

def clean_text(text):
    return re.sub(r"[^\w\s]", "", text).lower()

def check_duplication(new_topic, old_titles):
    new_words = set(clean_text(new_topic).split())
    for title in old_titles:
        common = new_words.intersection(set(clean_text(title).split()))
        if new_words and len(common) / len(new_words) > 0.5:
            return True
    return False

def get_trends():
    urls = [
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=SA",
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=EG",
    ]
    trends = []
    for url in urls:
        feed = feedparser.parse(url)
        for entry in feed.entries[:2]:
            trends.append(entry.title)
    trends.extend(FALLBACK_TOPICS)
    random.shuffle(trends)
    return trends

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def generate_content(topic):
    print(f"✍ Generating article: {topic}")
    model = genai.GenerativeModel("gemini-1.5-flash")

    prompt = f"""
    اكتب مقالاً تقنياً احترافياً بعنوان: "{topic}"

    الشروط:
    - تنسيق Markdown
    - لغة عربية فصحى جذابة
    - لا تقل عن 500 كلمة
    - بدون مقدمات زائدة
    """

    response = model.generate_content(prompt)
    if not response.text:
        raise RuntimeError("Empty Gemini response")
    return response.text

def get_ai_image():
    seed = random.randint(1, 9999)
    return f"https://image.pollinations.ai/prompt/futuristic%20technology%20ai%20background?width=800&height=450&seed={seed}&nologo=true"

# ================= Main =================

def main():
    print("🚀 Auto Blogger Bot Started")

    service = get_blogger_service()
    blog_id, blog_name = get_blog_id(service)

    if not blog_id:
        print("❌ No blog found")
        return

    print(f"✅ Connected to: {blog_name}")

    history = get_recent_titles(service, blog_id)
    topics = get_trends()

    topic = next((t for t in topics if not check_duplication(t, history)), random.choice(FALLBACK_TOPICS))
    print(f"📝 Topic selected: {topic}")

    raw_md = generate_content(topic)

    lines = raw_md.strip().split("\n")
    title = topic
    if lines[0].startswith("#"):
        title = lines[0].replace("#", "").strip()
        content_md = "\n".join(lines[1:])
    else:
        content_md = raw_md

    html = md.markdown(content_md)
    img = get_ai_image()

    body = {
        "title": title,
        "content": f"""
        <div style="text-align:center">
            <img src="{img}" style="max-width:100%;border-radius:12px">
        </div>
        <div dir="rtl" style="text-align:right;line-height:1.8">
            {html}
        </div>
        """,
        "labels": ["AI", "Technology"]
    }

    post = service.posts().insert(
        blogId=blog_id,
        body=body,
        isDraft=False
    ).execute()

    print(f"🎉 Published: {post.get('url')}")

if __name__ == "__main__":
    main()
