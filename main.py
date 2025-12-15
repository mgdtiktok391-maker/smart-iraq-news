# -*- coding: utf-8 -*-
import os, re, random, json, html, hashlib, time
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import requests
import backoff
import feedparser
import markdown as md
import bleach

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# =================== إعدادات عامة ===================
TZ = ZoneInfo("Asia/Baghdad")

# ❗️مهم: لا Scheduler داخلي مع GitHub Actions
POST_TIMES_LOCAL = ["09:00", "17:00"]

# إعدادات أمان
SAFE_CALLS_PER_MIN = int(os.getenv("SAFE_CALLS_PER_MIN", "3"))
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "3"))
AI_BACKOFF_BASE = int(os.getenv("AI_BACKOFF_BASE", "4"))

# أسرار
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
BLOG_URL = os.environ["BLOG_URL"]
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["REFRESH_TOKEN"]

# وضع النشر
PUBLISH_MODE = os.getenv("PUBLISH_MODE", "live").lower()

# =================== مواضيع احتياطية (40) ===================
FALLBACK_TOPICS = [
    "مستقبل الذكاء الاصطناعي في العالم العربي",
    "كيف تغيّر الخوارزميات طريقة اتخاذ القرار",
    "أثر التكنولوجيا على التعليم الجامعي",
    "التحول الرقمي في المؤسسات الحكومية",
    "الأمن السيبراني في عصر العمل عن بُعد",
    "البيانات الضخمة ودورها في الاقتصاد الحديث",
    "أخلاقيات الذكاء الاصطناعي وتحدياتها",
    "مفهوم المدن الذكية وتطبيقاته الواقعية",
    "كيف تؤثر الأتمتة على سوق العمل",
    "الفرق بين الذكاء الاصطناعي الضيق والعام",
    "الحوسبة السحابية ومستقبل الشركات",
    "أهمية الثقافة الرقمية في القرن 21",
    "التحول الرقمي في القطاع الصحي",
    "كيف تعمل محركات البحث من الداخل",
    "الاقتصاد الرقمي ونماذج الأعمال الجديدة",
    "دور التكنولوجيا في مكافحة الفساد",
    "التعليم الإلكتروني: الفرص والتحديات",
    "الذكاء الاصطناعي وصناعة المحتوى",
    "كيف غيّرت التكنولوجيا مفهوم الخصوصية",
    "التكنولوجيا المالية وتأثيرها",
    "العمل الحر في العصر الرقمي",
    "الذكاء الاصطناعي في التحليل السياسي",
    "الابتكار التقني في الدول النامية",
    "تاريخ الإنترنت وتحولاته الكبرى",
    "كيف تؤثر المنصات الرقمية على الرأي العام",
    "التحول الرقمي وبناء رأس المال البشري",
    "التكنولوجيا والعدالة الاجتماعية",
    "الذكاء الاصطناعي وصنع السياسات العامة",
    "تحديات الأمن الرقمي في الشرق الأوسط",
    "مستقبل البرمجة بدون كود",
    "كيف غيّر الذكاء الاصطناعي البحث العلمي",
    "الاقتصاد المعرفي وأسس التنمية",
    "التكنولوجيا وتأثيرها على الهوية الثقافية",
    "التحول الرقمي في الإعلام",
    "الذكاء الاصطناعي في التنبؤ الاقتصادي",
    "أهمية التفكير النقدي في العصر الرقمي",
    "التكنولوجيا بين التقدم والمخاطر",
    "دور الابتكار في نهضة الأمم",
    "مستقبل الذكاء الاصطناعي التوليدي",
    "كيف تعيد الثورة الرقمية تشكيل العالم",
]

# =================== Blogger ===================
def get_blogger_service():
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/blogger"],
    )
    return build("blogger", "v3", credentials=creds, cache_discovery=False)

def get_blog_id(service):
    return service.blogs().getByUrl(url=BLOG_URL).execute()["id"]

# =================== Gemini REST ===================
GEMINI_API_ROOT = "https://generativelanguage.googleapis.com"
GEN_CONFIG = {"temperature": 0.7, "topP": 0.9, "maxOutputTokens": 4096}

def _rest_generate(ver, model, prompt):
    url = f"{GEMINI_API_ROOT}/{ver}/models/{model}:generateContent?key={GEMINI_API_KEY}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": GEN_CONFIG,
    }
    r = requests.post(url, json=body, timeout=120)
    if r.ok:
        data = r.json()
        if data.get("candidates"):
            return data["candidates"][0]["content"]["parts"][0]["text"]
    return None

@backoff.on_exception(backoff.expo, Exception, base=AI_BACKOFF_BASE, max_tries=AI_MAX_RETRIES)
def ask_gemini(prompt):
    attempts = [
        ("v1beta", "gemini-2.5-flash"),
        ("v1", "gemini-2.5-flash"),
        ("v1beta", "gemini-2.0-flash"),
        ("v1", "gemini-2.0-flash"),
        ("v1beta", "gemini-pro"),
        ("v1", "gemini-pro"),
    ]
    for ver, model in attempts:
        txt = _rest_generate(ver, model, prompt)
        if txt:
            return txt.strip()
    raise RuntimeError("Gemini REST failed on all models")

# =================== أدوات ===================
def markdown_to_clean_html(md_text):
    raw = md.markdown(md_text)
    clean = bleach.clean(
        raw,
        tags=bleach.sanitizer.ALLOWED_TAGS.union(
            {"p","h1","h2","h3","ul","ol","li","strong","em","a","hr","br"}
        ),
        attributes={"a":["href","title","target","rel"]},
        strip=True,
    )
    return clean.replace("<a ", '<a target="_blank" rel="noopener" ')

def build_prompt(topic):
    return f"""
- اكتب مقالة عربية واضحة.
- السطر الأول عنوان H1 يبدأ بـ #.
- الطول 1000–1400 كلمة.
- بدون حشو.
- أضف قسم "المراجع" بروابط حقيقية.
الموضوع: {topic}
"""

# =================== النشر ===================
def make_article_once(slot_idx):
    print(f"DEBUG: make_article_once(slot={slot_idx})")

    topic = random.choice(FALLBACK_TOPICS)
    article_md = ask_gemini(build_prompt(topic))

    lines = article_md.splitlines()
    title = topic
    if lines and lines[0].startswith("#"):
        title = lines[0].replace("#","").strip()
        article_md = "\n".join(lines[1:])

    html_content = markdown_to_clean_html(article_md)

    service = get_blogger_service()
    blog_id = get_blog_id(service)

    post = service.posts().insert(
        blogId=blog_id,
        body={
            "title": title,
            "content": html_content,
        },
        isDraft=(PUBLISH_MODE!="live")
    ).execute()

    print(f"PUBLISHED: {post.get('url','(no url)')}")

if __name__ == "__main__":
    # ❗️تشغيل مباشر فقط
    slot = int(os.getenv("SLOT","0"))
    make_article_once(slot)
