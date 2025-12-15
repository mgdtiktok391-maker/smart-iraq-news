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
# 🔐 Secrets (مطابقة للـ workflow)
# =================================================

HF_API_KEY = os.getenv("HF_API_KEY")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")
BLOG_URL = os.getenv("BLOG_URL")

required = {
    "HF_API_KEY": HF_API_KEY,
    "CLIENT_ID": CLIENT_ID,
    "CLIENT_SECRET": CLIENT_SECRET,
    "REFRESH_TOKEN": REFRESH_TOKEN,
}

missing = [k for k, v in required.items() if not v]
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

def get_recent_titles(service, blog_id):
    posts = service.posts().list(
        blogId=blog_id,
        fetchBodies=False,
        maxResults=15
    ).execute()
    return [p.get("title", "") for p in posts.get("items", [])]

# =================================================
# 🧠 Topics
# =================================================

FALLBACK_TOPICS = [
    "أفضل طرق حماية الخصوصية على الإنترنت",
    "كيف تحمي بياناتك الشخصية من الاختراق",
    "أهم أدوات الإنتاجية الرقمية في 2025",
    "مستقبل الذكاء الاصطناعي في التعليم",
    "كيف يؤثر الذكاء الاصطناعي على سوق العمل",
    "دليل المبتدئين إلى الأمن السيبراني",
    "أخطر الأخطاء الشائعة في استخدام الإنترنت",
    "كيف تختار كلمة مرور قوية وآمنة",
    "الفرق بين الذكاء الاصطناعي والتعلم الآلي",
    "أهم تطبيقات الذكاء الاصطناعي في الحياة اليومية",
    "كيف يعمل الإنترنت من الناحية التقنية",
    "مفهوم الحوسبة السحابية بطريقة مبسطة",
    "إيجابيات وسلبيات العمل عن بُعد",
    "كيف تبدأ العمل الحر خطوة بخطوة",
    "أفضل المهارات الرقمية المطلوبة في المستقبل",
    "شرح تقنية البلوك تشين للمبتدئين",
    "ما هو إنترنت الأشياء وكيف يعمل",
    "كيف تميّز بين الأخبار الصحيحة والمضللة",
    "مستقبل التجارة الإلكترونية عالميًا",
    "أهمية التفكير النقدي في العصر الرقمي",
]

def clean(text):
    return re.sub(r"[^\w\s]", "", text).lower()

def is_duplicate(title, history):
    nw = set(clean(title).split())
    for h in history:
        ow = set(clean(h).split())
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
# 🤖 Hugging Face (نموذج مستقر)
# =================================================

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def generate_article(topic):
    print(f"✍ Writing article: {topic}")

    url = "https://api-inference.huggingface.co/models/HuggingFaceH4/zephyr-7b-beta"
    headers = {
        "Authorization": f"Bearer {HF_API_KEY}",
        "Content-Type": "application/json",
    }

    prompt = f"""
اكتب مقالًا تقنيًا عربيًا احترافيًا بعنوان:
{topic}

الشروط:
- لغة عربية فصحى
- تنسيق Markdown
- لا يقل عن 500 كلمة
- بدون مقدمات زائدة
"""

    payload = {
        "inputs": prompt,
        "parameters": {
            "temperature": 0.7,
            "max_new_tokens": 1200,
            "return_full_text": False
        }
    }

    r = requests.post(url, headers=headers, json=payload, timeout=180)
    if r.status_code != 200:
        raise RuntimeError(f"HF error {r.status_code}: {r.text}")

    data = r.json()
    if isinstance(data, list):
        return data[0]["generated_text"]
    raise RuntimeError(f"Unexpected HF response: {data}")

def get_image():
    seed = random.randint(1, 9999)
    return (
        "https://image.pollinations.ai/prompt/"
        "futuristic%20technology%20background"
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

    history = get_recent_titles(service, blog_id)
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
<div style="text-align:center;margin-bottom:20px">
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
