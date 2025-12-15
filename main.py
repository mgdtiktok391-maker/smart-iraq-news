# -*- coding: utf-8 -*-
import os, random, re, html
from datetime import datetime
from zoneinfo import ZoneInfo
import requests
import markdown as md
import bleach

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ================== الإعدادات العامة ==================
TZ = ZoneInfo("Asia/Baghdad")

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
BLOG_URL = os.environ["BLOG_URL"]
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["REFRESH_TOKEN"]

PUBLISH_MODE = os.getenv("PUBLISH_MODE", "live").lower()

# ================== افتتاحيات صارمة غير مكررة ==================
INTRO_STYLES = [
    "هل يمكن للتكنولوجيا أن تعيد تعريف معنى التقدم الإنساني؟",
    "في عالم يتغير بوتيرة غير مسبوقة، تظهر أسئلة جوهرية حول علاقتنا بالتقنية.",
    "لم يعد التقدم التكنولوجي رفاهية، بل أصبح شرطًا للبقاء.",
    "بين الخوارزميات والإنسان، تتشكل ملامح عصر جديد.",
    "في كل حقبة تاريخية، كانت هناك أداة غيّرت مسار الحضارة.",
    "ما نعتبره اليوم تقدمًا تقنيًا، قد يكون غدًا ضرورة وجودية.",
    "لم يعد السؤال ماذا نملك من تقنية، بل كيف نستخدمها.",
    "حين تتقاطع المعرفة مع الآلة، تبدأ قصة مختلفة.",
]

# ================== 100 موضوع احتياطي ==================
FALLBACK_TOPICS = [
    "الابتكار كقوة محركة لنهضة الدول",
    "الذكاء الاصطناعي وإعادة تشكيل الاقتصاد العالمي",
    "كيف تغير الخوارزميات قرارات البشر",
    "التحول الرقمي في الدول النامية",
    "الأمن السيبراني كقضية سيادية",
    "مستقبل سوق العمل في عصر الأتمتة",
    "الذكاء الاصطناعي والتعليم",
    "التكنولوجيا والهوية الثقافية",
    "أخلاقيات الذكاء الاصطناعي",
    "المدن الذكية وتحديات الواقع",
    "الاقتصاد المعرفي",
    "البيانات الضخمة وصناعة القرار",
    "التكنولوجيا والتنمية المستدامة",
    "كيف تفكر الآلة",
    "الإنسان في عصر الخوارزميات",
    "التحول الرقمي الحكومي",
    "الذكاء الاصطناعي وصناعة المحتوى",
    "الإعلام الرقمي وتأثيره السياسي",
    "التكنولوجيا وتوازن القوى",
    "مستقبل البرمجة",
    "الثورة الصناعية الرابعة",
    "الذكاء الاصطناعي والبحث العلمي",
    "التكنولوجيا والعدالة الاجتماعية",
    "اقتصاد المنصات الرقمية",
    "الابتكار وريادة الأعمال",
    "الاقتصاد السلوكي والتقنية",
    "الذكاء الاصطناعي والإبداع",
    "التكنولوجيا وصناعة القرار",
    "مستقبل المعرفة البشرية",
    "الرقمنة وتأثيرها على المجتمعات",
    "التعليم في عصر الذكاء الاصطناعي",
    "تأثير التكنولوجيا على القيم",
    "التحول الرقمي في الصحة",
    "الذكاء الاصطناعي والسياسة",
    "الابتكار في الشرق الأوسط",
    "التكنولوجيا والأمن القومي",
    "كيف تصنع الدول تفوقها التقني",
    "الاقتصاد الرقمي الحديث",
    "دور المعرفة في بناء القوة",
    "الذكاء الاصطناعي ومستقبل الإنسان",
] * 3  # نكرر لضمان التنوع العشوائي

# ================== أدوات HTML ==================
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
<img src="{url}" alt="{html.escape(title)}" loading="lazy"
style="max-width:100%;border-radius:8px;display:block;margin:auto;">
</figure>
<hr>
"""

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

# ================== Gemini REST (مستقر) ==================
def ask_gemini(prompt):
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 4096
        }
    }
    r = requests.post(url, json=body, timeout=120)
    r.raise_for_status()
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]

# ================== النشر ==================
def make_article_once(slot):
    random.seed(datetime.now(TZ).strftime("%Y-%m-%d") + str(slot))

    topic = random.choice(FALLBACK_TOPICS)
    intro = random.choice(INTRO_STYLES)

    prompt = f"""
{intro}

اكتب مقالة عربية تحليلية عميقة غير مكررة.
- السطر الأول عنوان H1 يبدأ بـ #
- الطول بين 1000 و1400 كلمة
- أسلوب فكري تحليلي
- بدون حشو أو تكرار
- أضف قسم "المراجع" في النهاية مع 4 مصادر على الأقل

الموضوع: {topic}
"""

    article = ask_gemini(prompt).strip()
    lines = article.splitlines()

    title = topic
    if lines and lines[0].startswith("#"):
        title = lines[0].replace("#","").strip()
        article = "\n".join(lines[1:])

    html_content = image_block(title) + clean_html(article)

    service = blogger_service()
    blog_id = service.blogs().getByUrl(url=BLOG_URL).execute()["id"]

    post = service.posts().insert(
        blogId=blog_id,
        body={"title": title, "content": html_content},
        isDraft=(PUBLISH_MODE != "live")
    ).execute()

    print("✅ PUBLISHED:", post.get("url"))

# ================== التشغيل (مرة واحدة فقط) ==================
if __name__ == "__main__":
    hour = datetime.now(TZ).hour
    slot = 0 if hour < 16 else 1
    make_article_once(slot)
