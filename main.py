# -*- coding: utf-8 -*-
import os, re, time, random, json, html, hashlib
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import requests
import backoff
import feedparser
from apscheduler.schedulers.background import BackgroundScheduler

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import markdown as md
import bleach

from flask import Flask, request, jsonify

# =================== إعدادات عامة ===================
TZ = ZoneInfo("Asia/Baghdad")

# ⏰ أوقات النشر المعدلة
POST_TIMES_LOCAL = ["12:00", "20:00"]

SAFE_CALLS_PER_MIN = int(os.getenv("SAFE_CALLS_PER_MIN", "3"))
AI_MAX_RETRIES = int(os.getenv("AI_MAX_RETRIES", "3"))
AI_BACKOFF_BASE = int(os.getenv("AI_BACKOFF_BASE", "4"))

# أسرار
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
BLOG_URL = os.environ["BLOG_URL"]
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["REFRESH_TOKEN"]

# =================== صرامة الافتتاحيات ===================
INTRO_STYLES = [
    "ابدأ المقال بسؤال فلسفي عميق لا يُستخدم في مقالات تقنية تقليدية.",
    "ابدأ المقال بمشهد واقعي من حياة شخص عادي يتأثر مباشرة بالموضوع.",
    "ابدأ المقال بحقيقة صادمة أو رقم غير متوقع مرتبط بالموضوع.",
    "ابدأ المقال بمقارنة ذكية بين الماضي والحاضر دون ذكر التقنية مباشرة.",
    "ابدأ المقال بإشكالية فكرية تضع القارئ أمام مفترق طرق.",
    "ابدأ المقال بسيناريو مستقبلي واقعي وكأنه حدث بالفعل.",
    "ابدأ المقال بحكاية قصيرة جدًا (3–4 أسطر) ذات مغزى.",
    "ابدأ المقال بسؤال أخلاقي محرج يتعلق بالموضوع.",
    "ابدأ المقال بمفارقة عقلية تجعل القارئ يعيد التفكير.",
    "ابدأ المقال بنقد فكرة شائعة ثم تفكيكها."
]

INTRO_HISTORY_FILE = "intro_styles.jsonl"

def pick_strict_intro():
    used = [r.get("style") for r in load_jsonl(INTRO_HISTORY_FILE)][-10:]
    available = [s for s in INTRO_STYLES if s not in used]
    chosen = random.choice(available or INTRO_STYLES)
    append_jsonl(INTRO_HISTORY_FILE, {
        "style": chosen,
        "time": datetime.now(TZ).isoformat()
    })
    return chosen

# =================== 100 موضوع احتياطي ===================
FALLBACK_TOPICS = [
    "كيف تُعيد التكنولوجيا تشكيل مفهوم السلطة",
    "الذكاء الاصطناعي وحدود القرار البشري",
    "هل نحن نعيش وهم الاختيار في العصر الرقمي؟",
    "التكنولوجيا كأداة تحرر أم وسيلة ضبط",
    "الابتكار حين يصبح عبئًا اجتماعيًا",
    "اقتصاد الانتباه وتأثيره على الوعي",
    "من يملك البيانات يملك المستقبل",
    "الخوارزميات كفاعل سياسي غير مرئي",
    "هل الذكاء الاصطناعي محايد فعلًا؟",
    "التقدم التقني مقابل التآكل الإنساني",
    "العقل البشري في مواجهة الآلة",
    "التحكم الناعم: كيف تُدار المجتمعات رقميًا",
    "مستقبل الخصوصية في عالم شفاف",
    "هل التقنية تصنع الحقيقة؟",
    "نهاية العمل كما نعرفه",
    "الابتكار بدون أخلاق",
    "الدولة الرقمية وحدود السيادة",
    "التعليم في عصر اللايقين",
    "المعرفة بين الإتاحة والتضليل",
    "من يصمم الخوارزميات؟",
    "الذكاء الاصطناعي كمرآة للإنسان",
    "المجتمع المُراقَب طوعًا",
    "هل نحن أحرار داخل الأنظمة الذكية؟",
    "التكنولوجيا وإعادة تعريف النجاح",
    "الإنسان كمنتج بيانات",
    "كيف تغيرت السلطة بدون أن نشعر",
    "التقدم السريع وثمنه الخفي",
    "هل الابتكار دائمًا جيد؟",
    "المستقبل الذي لم نختره",
    "الآلة التي تفهم أكثر مما ينبغي",
    "الذكاء الاصطناعي وصناعة القناعات",
    "الاقتصاد الخوارزمي",
    "حين تسبق الأدوات القيم",
    "المعرفة السريعة مقابل الفهم العميق",
    "التكنولوجيا واللامساواة الجديدة",
    "الإنسان في مواجهة أنظمته",
    "هل نثق بما تبنيه الخوارزميات؟",
    "التحول الرقمي كتحول ثقافي",
    "التقدم بلا بوصلة",
    "من يحاسب الآلة؟",
    "العقل الجمعي في العصر الرقمي",
    "الذكاء الاصطناعي والهوية",
    "الابتكار حين يفقد معناه",
    "التكنولوجيا وإعادة تعريف الحقيقة",
    "هل ما زال الإنسان في المركز؟",
    "التحكم عبر الراحة",
    "الآلة كمُربي خفي",
    "المستقبل بين الكفاءة والمعنى",
    "هل نحتاج إلى إبطاء التقدم؟",
    "الذكاء الاصطناعي كقوة ناعمة",
    "الوعي في زمن السرعة",
    "من يصوغ السرديات الرقمية؟",
    "الإنسان داخل الصندوق الذكي",
    "التحكم بدون قمع",
    "هل التقنية تُفكر عنا؟",
    "المجتمع القابل للبرمجة",
    "الذكاء الاصطناعي وصناعة الطاعة",
    "التكنولوجيا كأيديولوجيا",
    "هل ما زالت الحقيقة مهمة؟",
    "الآلة التي تعلّمنا كيف نفكر",
    "نهاية الخصوصية الطوعية",
    "الإنسان كواجهة مستخدم",
    "الذكاء الاصطناعي وإعادة تشكيل الأخلاق",
    "من يضع قواعد المستقبل؟",
    "التكنولوجيا بين التمكين والتجريد",
    "الوعي في عصر الخوارزمية",
    "هل نعيش داخل تجربة ضخمة؟",
    "الآلة كوسيط للواقع",
    "التحكم عبر التصميم",
    "الذكاء الاصطناعي وسلطة التنبؤ",
    "التكنولوجيا كبيئة لا أداة",
    "هل ما زال التفكير حرًا؟",
    "الابتكار حين يصبح إلزاميًا",
    "الإنسان ككائن قابل للتحسين",
    "الذكاء الاصطناعي وإعادة تعريف الخطأ",
    "التقدم الذي لا ينتظرنا",
    "من يتحكم في الأسئلة؟",
    "الآلة التي تعرف أكثر مما نريد",
    "التكنولوجيا وتآكل الغموض",
    "الذكاء الاصطناعي ككاتب غير مرئي",
    "المستقبل المصمم سلفًا",
    "هل ما زال لدينا خيار؟",
    "الآلة كذاكرة جمعية",
    "التكنولوجيا وحدود المعنى",
    "الذكاء الاصطناعي وإعادة تشكيل الزمن",
    "الإنسان في عصر التوقع الدائم",
    "الابتكار كضرورة لا كخيار",
    "الآلة التي تفهم النوايا",
    "نهاية العشوائية",
    "الذكاء الاصطناعي وسلطة التفسير",
    "التكنولوجيا كواقع بديل",
    "هل ما زلنا نفكر بأنفسنا؟"
]

# =================== Gemini ===================
GEMINI_API_ROOT = "https://generativelanguage.googleapis.com"
GEN_CONFIG = {"temperature": 0.85, "topP": 0.9, "maxOutputTokens": 4096}

def _rest_generate(ver: str, model: str, prompt: str):
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

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def ask_gemini(prompt: str) -> str:
    return _rest_generate("v1", "gemini-1.5-flash", prompt)

# =================== المقال ===================
def build_prompt(topic):
    intro_rule = pick_strict_intro()
    return f"""
{intro_rule}

اكتب مقالة عربية تحليلية عميقة.
- لا تستخدم افتتاحية نمطية.
- لا تُكرر صياغات معروفة.
- الطول 1000–1400 كلمة.
- بنية واضحة.
- أضف قسم "المراجع" في النهاية.
- العنوان في السطر الأول بصيغة # H1.

الموضوع: {topic}
""".strip()

# =================== Blogger ===================
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

def make_article_once(slot):
    topic = random.choice(FALLBACK_TOPICS)
    article = ask_gemini(build_prompt(topic))
    if not article:
        print("❌ فشل توليد المقال")
        return

    lines = article.splitlines()
    title = topic
    if lines and lines[0].startswith("#"):
        title = lines[0].replace("#", "").strip()
        article = "\n".join(lines[1:])

    html_content = md.markdown(article)
    service = blogger_service()
    blog_id = service.blogs().getByUrl(url=BLOG_URL).execute()["id"]

    post = service.posts().insert(
        blogId=blog_id,
        body={"title": title, "content": html_content},
        isDraft=False
    ).execute()

    print("✅ نُشر:", post.get("url"))

# =================== الجدولة ===================
def schedule_jobs():
    sched = BackgroundScheduler(timezone=TZ)
    for i, t in enumerate(POST_TIMES_LOCAL):
        h, m = map(int, t.split(":"))
        sched.add_job(lambda i=i: make_article_once(i),
                      "cron", hour=h, minute=m)
    sched.start()
    print("⏰ الجدولة مفعلة:", POST_TIMES_LOCAL)

if __name__ == "__main__":
    schedule_jobs()
    while True:
        time.sleep(60)
