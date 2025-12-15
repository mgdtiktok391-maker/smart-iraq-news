# -*- coding: utf-8 -*-
import os, random, requests
from datetime import datetime
from zoneinfo import ZoneInfo

import backoff
import markdown as md
import bleach

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ================== إعدادات ==================
TZ = ZoneInfo("Asia/Baghdad")

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
BLOG_URL = os.environ["BLOG_URL"]
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["REFRESH_TOKEN"]

PUBLISH_MODE = os.getenv("PUBLISH_MODE", "live").lower()

# ================== افتتاحيات متنوعة ==================
INTRO_STYLES = [
    "ابدأ المقال بسؤال فلسفي عميق يربط التكنولوجيا بحياة الإنسان اليومية.",
    "ابدأ المقال بحكاية قصيرة أو مشهد واقعي من الحياة المعاصرة.",
    "ابدأ المقال بإحصائية أو حقيقة رقمية صادمة متعلقة بالموضوع.",
    "ابدأ المقال بمقارنة تاريخية بين الماضي والحاضر.",
    "ابدأ المقال بطرح إشكالية فكرية تثير فضول القارئ.",
    "ابدأ المقال بوصف مشهد مستقبلي محتمل.",
]

# ================== مواضيع احتياطية (40) ==================
FALLBACK_TOPICS = [
    "دور الابتكار في نهضة الأمم",
    "مستقبل الذكاء الاصطناعي في التعليم",
    "كيف تغيّر التكنولوجيا سلوك المجتمعات",
    "الأمن الرقمي في العصر الحديث",
    "التحول الرقمي في الدول النامية",
    "أثر الخوارزميات على الرأي العام",
    "التكنولوجيا بين الحرية والرقابة",
    "الذكاء الاصطناعي وسوق العمل",
    "كيف تعيد البيانات الضخمة تشكيل الاقتصاد",
    "المدن الذكية: حلم أم واقع",
    "التفكير النقدي في زمن المعلومات",
    "أخلاقيات الذكاء الاصطناعي",
    "التكنولوجيا والهوية الثقافية",
    "الثورة الرقمية والإعلام",
    "الاقتصاد المعرفي وأهميته",
    "التعليم الإلكتروني وتحدياته",
    "التكنولوجيا وصناعة القرار",
    "الذكاء الاصطناعي في السياسة",
    "مستقبل العمل عن بعد",
    "الابتكار وريادة الأعمال",
    "التحول الرقمي في الصحة",
    "كيف تعمل محركات البحث",
    "الذكاء الاصطناعي التوليدي",
    "التكنولوجيا والعدالة الاجتماعية",
    "الأمن السيبراني العالمي",
    "تأثير التكنولوجيا على الخصوصية",
    "الاقتصاد الرقمي الحديث",
    "الابتكار في الشرق الأوسط",
    "الذكاء الاصطناعي والبحث العلمي",
    "مستقبل البرمجة",
    "التكنولوجيا والتعليم الجامعي",
    "التحول الرقمي الحكومي",
    "الذكاء الاصطناعي وصناعة المحتوى",
    "التكنولوجيا والتنمية المستدامة",
    "كيف تفكر الآلة",
    "الإنسان في عصر الخوارزميات",
    "التكنولوجيا وتوازن القوة",
    "الثورة الصناعية الرابعة",
    "الذكاء الاصطناعي والمجتمع",
    "التكنولوجيا بين الأمل والخطر",
]

# ================== Blogger ==================
def blogger_service():
    creds = Credentials(
        None,
        refresh_token=REFRESH_TOKEN,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=["https://www.googleapis.com/auth/blogger"],
    )
    return build("blogger", "v3", credentials=creds, cache_discovery=False)

# ================== Gemini REST ==================
API_ROOT = "https://generativelanguage.googleapis.com"

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def ask_gemini(prompt):
    url = f"{API_ROOT}/v1/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.85, "maxOutputTokens": 4096},
    }
    r = requests.post(url, json=body, timeout=120)
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]

# ================== أدوات ==================
def clean_html(md_text):
    raw = md.markdown(md_text)
    return bleach.clean(
        raw,
        tags=bleach.sanitizer.ALLOWED_TAGS.union(
            {"p","h1","h2","h3","ul","ol","li","strong","em","a","hr","br","img"}
        ),
        attributes={"a":["href","target","rel"],"img":["src","alt","loading","style"]},
        strip=True,
    )

def image_block(title):
    seed = abs(hash(title)) % 10000
    url = f"https://source.unsplash.com/1200x630/?technology,innovation&sig={seed}"
    return f"""
    <figure>
      <img src="{url}" alt="{title}" loading="lazy"
           style="max-width:100%;border-radius:8px;margin:auto;display:block;">
    </figure>
    <hr>
    """

# ================== النشر ==================
def make_article_once(slot):
    topic = random.choice(FALLBACK_TOPICS)
    intro_style = random.choice(INTRO_STYLES)

    prompt = f"""
{intro_style}

اكتب مقالة عربية متكاملة.
- السطر الأول عنوان H1 يبدأ بـ #
- الطول بين 1000 و1400 كلمة
- أسلوب تحليلي عميق غير مكرر
- لا تبدأ بمقدمة نمطية
- أضف قسم "المرا
