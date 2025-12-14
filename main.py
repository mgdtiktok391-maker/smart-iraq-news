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

# ================= إعدادات =================
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
BLOG_URL = os.environ["BLOG_URL"]
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["REFRESH_TOKEN"]

GEMINI_MODEL = "gemini-1.5-flash"

# مواضيع احتياطية (تعمل دائماً إذا فشل الترند)
FALLBACK_TOPICS = [
    "مستقبل الذكاء الاصطناعي في حياتنا اليومية",
    "أهم نصائح الحماية من الاختراق الإلكتروني",
    "تطورات شبكات الجيل الخامس 5G",
    "أفضل تطبيقات الهاتف لزيادة الإنتاجية",
    "الفرق بين الواقع الافتراضي والواقع المعزز",
    "كيف تبدأ بتعلم البرمجة من الصفر",
    "أسرار التصوير الاحترافي بكاميرا الهاتف",
    "مقارنة بين أشهر العملات الرقمية",
    "كيفية الربح من الإنترنت للمبتدئين",
    "تكنولوجيا السيارات الكهربائية ومستقبلها"
]

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
    try:
        blog = service.blogs().getByUrl(url=BLOG_URL).execute()
        return blog["id"]
    except Exception as e:
        print(f"Error getting blog ID: {e}")
        return None

def get_recent_titles(service, blog_id):
    """جلب العناوين السابقة (بدون فلتر الحالة لتجنب المشاكل)"""
    titles = []
    try:
        # قمنا بإزالة status=["LIVE"] تماماً لتجنب أي خطأ
        posts = service.posts().list(
            blogId=blog_id, fetchBodies=False, maxResults=20
        ).execute()
        for item in posts.get("items", []):
            titles.append(item.get("title", ""))
    except Exception as e:
        print(f"Warning: Could not fetch history (Ignored): {e}")
    return titles

def check_duplication(new_topic, old_titles):
    def clean(text):
        return re.sub(r'[^\w\s]', '', text).lower()
    
    nt = clean(new_topic)
    new_words = set(nt.split())
    
    for title in old_titles:
        ot = clean(title)
        common = new_words.intersection(set(ot.split()))
        if len(new_words) > 0 and len(common) / len(new_words) > 0.5:
            return True
    return False

def get_trends():
    urls = [
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=IQ",
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=SA",
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US&cat=t"
    ]
    trends = []
    print("Fetching trends...")
    for url in urls:
        try:
            feed = feedparser.parse(url)
            if not feed.entries: continue
            for entry in feed.entries[:3]:
                trends.append({'title': entry.title, 'link': entry.link})
        except:
            continue
    
    # دمج الاحتياطي
    for topic in FALLBACK_TOPICS:
        trends.append({'title': topic, 'link': 'https://news.google.com'})
        
    random.shuffle(trends)
    return trends

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def generate_content_gemini(topic_title):
    print(f"Generating content for: {topic_title}")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    اكتب مقالاً تقنياً مشوقاً للمدونة عن: "{topic_title}".
    
    الشروط:
    1. عنوان جذاب (Viral) يبدأ بـ #.
    2. مقدمة قوية، صلب الموضوع، وخاتمة.
    3. لغة عربية فصحى سهلة.
    4. استخدم تنسيق Markdown.
    5. الطول: 600 كلمة تقريباً.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]

def get_ai_image(query):
    # صورة تقنية عشوائية لضمان العمل
    seed = random.randint(1, 9999)
    return f"https://image.pollinations.ai/prompt/futuristic technology concept art?width=1200&height=630&nologo=true&seed={seed}"

def main():
    print("Starting Bot...")
    service = get_blogger_service()
    blog_id = get_blog_id(service)
    
    if not blog_id:
        print("Error: Blog ID not found. Check BLOG_URL secret.")
        return

    history = get_recent_titles(service, blog_id)
    candidates = get_trends()
    
    selected_topic = None
    for cand in candidates:
        if not check_duplication(cand['title'], history):
            selected_topic = cand
            break
            
    if not selected_topic:
        # إذا فشل كل شيء، نستخدم موضوعاً عشوائياً مضموناً
        print("Using fallback topic...")
        selected_topic = {'title': random.choice(FALLBACK_TOPICS), 'link': 'https://google.com'}

    print(f"Selected Topic: {selected_topic['title']}")

    try:
        raw_md = generate_content_gemini(selected_topic['title'])
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return

    lines = raw_md.split('\n')
    title = selected_topic['title']
    content_lines = []
    
    for line in lines:
        if line.strip().startswith("# "):
            title = line.replace("#", "").strip()
        else:
            content_lines.append(line)
            
    final_html = md.markdown("\n".join(content_lines))
    img_url = get_ai_image(selected_topic['title'])
    
    post_body = f"""
    <div style="text-align: center; margin-bottom: 20px;">
        <img src="{img_url}" alt="{title}" style="max-width: 100%; border-radius: 10px;">
    </div>
    {final_html}
    <br><hr>
    <p style="text-align:center; color: #888; font-size: small;">إعداد: الذكاء الاصطناعي</p>
    """
    
    body = {
        "kind": "blogger#post",
        "title": title,
        "content": post_body,
        "labels": ["تكنولوجيا", "أخبار"]
    }
    
    try:
        post = service.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
        print(f"SUCCESS! Published to: {post.get('url')}")
    except Exception as e:
        print(f"Publishing Error: {e}")

if __name__ == "__main__":
    main()
