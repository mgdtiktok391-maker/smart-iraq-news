# -*- coding: utf-8 -*-
import os, random, requests
from datetime import datetime
from zoneinfo import ZoneInfo

import markdown as md
import bleach

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ================== الإعدادات ==================
TZ = ZoneInfo("Asia/Baghdad")

# أسرار مطلوبة (GitHub Secrets)
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
BLOG_URL = os.environ["BLOG_URL"]
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["REFRESH_TOKEN"]

# وضع النشر
PUBLISH_MODE = os.getenv("PUBLISH_MODE", "live").lower()

# ================== Gemini REST (الحل النهائي) ==================
GEMINI_URL = "https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent"

def ask_gemini(prompt: str) -> str:
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.85,
            "topP": 0.95,
            "maxOutputTokens": 4096
        }
    }

    r = requests.post(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        json=payload,
        timeout=120
    )

    if r.status_code != 200:
        raise RuntimeError(f"Gemini error {r.status_code}: {r.text}")

    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]

# ================== افتتاحيات متنوعة ==================
INTRO_STYLES = [
    "ابدأ المقال بسؤال فلسفي يربط التكنولوجيا بحياة الإنسان.",
    "ابدأ المقال بمشهد واقعي من الحياة اليومية.",
    "ابدأ المقال بحقيقة أو رقم صادم.",
    "ابدأ المقال بمقارنة بين الماضي والحاضر.",
    "ابدأ المقال بإشكالية فكرية تثير الفضول.",
    "ابدأ المقال بوصف سيناريو مستقبلي محتمل."
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
    "المدن الذكية: حلم أم واقع",
    "أخلاقيات الذكاء الاصطناعي",
    "التكنولوجيا والهوية الثقافية",
    "الاقتصاد المعرفي وأهميته",
    "التعليم الإلكتروني وتحدياته",
    "الذكاء الاصطناعي في السياسة",
    "مستقبل العمل عن بعد",
    "التحول الرقمي في الصحة",
    "الذكاء الاصطناعي التوليدي",
    "الأمن السيبراني العالمي",
    "الاقتصاد الرقمي الحديث",
    "الابتكار في الشرق الأوسط",
    "الذكاء الاصطناعي والبحث العلمي",
    "الثورة الصناعية الرابعة",
    "الذكاء الاصطناعي والمجتمع",
    "التكنولوجيا والتنمية المستدامة",
    "كيف تفكر الآلة",
    "الإنسان في عصر الخوارزميات",
    "التكنولوجيا وتوازن القوة",
    "مستقبل البرمجة",
    "التكنولوجيا والتعليم الجامعي",
    "التحول الرقمي الحكومي",
    "الذكاء الاصطناعي وصناعة المحتوى",
    "الإعلام الرقمي الحديث",
    "التكنولوجيا وصناعة القرار",
    "التفكير النقدي في العصر الرقمي",
    "الابتكار وريادة الأعمال",
    "الاقتصاد السلوكي والتكنولوجيا",
    "البيانات الضخمة وصناعة المستقبل",
    "الذكاء الاصطناعي والإبداع",
    "التكنولوجيا والعدالة الاجتماعية",
    "مستقبل المعرفة البشرية",
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

# ================== HTML ==================
def clean_html(md_text: str) -> str:
    raw = md.markdown(md_text)
    return bleach.clean(
        raw,
        tags=bleach.sanitizer.ALLOWED_TAGS.union(
            {"p","h1","h2","h3","ul","ol","li","strong","em","a","hr","br","img"}
        ),
        attributes={"a":["href","target","rel"],"img":["src","alt","loading","style"]},
        strip=True,
    )

def image_block(title: str) -> str:
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
def make_article_once(slot: int):
    topic = random.choice(FALLBACK_TOPICS)
    intro = random.choice(INTRO_STYLES)

    prompt = (
        f"{intro}\n\n"
        "اكتب مقالة عربية أصلية غير مكررة.\n"
        "- السطر الأول عنوان H1 يبدأ بـ #\n"
        "- الطول بين 1000 و1400 كلمة\n"
        "- أسلوب تحليلي عميق\n"
        "- لا تعيد افتتاحيات نمطية\n"
        "- أضف قسم \"المراجع\" في النهاية\n\n"
        f"الموضوع: {topic}"
    )

    article = ask_gemini(prompt).strip()
    lines = article.splitlines()

    title = topic
    if lines and lines[0].startswith("#"):
        title = lines[0].replace("#","").strip()
        article = "\n".join(lines[1:])

    html = image_block(title) + clean_html(article)

    service = blogger_service()
    blog_id = service.blogs().getByUrl(url=BLOG_URL).execute()["id"]

    post = service.posts().insert(
        blogId=blog_id,
        body={"title": title, "content": html},
        isDraft=(PUBLISH_MODE != "live")
    ).execute()

    print("✅ PUBLISHED:", post.get("url"))

# ================== تشغيل ==================
if __name__ == "__main__":
    slot = int(os.getenv("SLOT","0"))
    make_article_once(slot)
