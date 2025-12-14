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

# مواضيع احتياطية (تعمل دائماً)
FALLBACK_TOPICS = [
    "كيف يؤثر الذكاء الاصطناعي على مستقبل الوظائف؟",
    "أهم 5 نصائح لحماية هاتفك من الاختراق",
    "شرح مبسط لتقنية البلوك تشين والعملات الرقمية",
    "تطورات شبكات الجيل الخامس 5G ومميزاتها",
    "أفضل تطبيقات تنظيم الوقت وزيادة الإنتاجية",
    "كيف تبدأ تعلم البرمجة من الصفر مجاناً",
    "نصائح لالتقاط صور احترافية بكاميرا الهاتف",
    "مقارنة بين العمل في الشركات والعمل الحر Freelance",
    "أسرار التسويق الإلكتروني الناجح في 2025",
    "تكنولوجيا السيارات ذاتية القيادة: إلى أين وصلت؟"
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
    """جلب العناوين السابقة"""
    titles = []
    try:
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
    # محاولة جلب ترندات حقيقية
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
    
    # دمج المواضيع الاحتياطية
    for topic in FALLBACK_TOPICS:
        trends.append({'title': topic, 'link': 'https://news.google.com'})
        
    random.shuffle(trends)
    return trends

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def generate_content_gemini(topic_title):
    print(f"Generating content for: {topic_title}")
    
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
    
    # === المحاولة الأولى: استخدام Gemini 1.5 Flash (الأحدث) ===
    try:
        print("Trying Gemini 1.5 Flash (v1beta)...")
        # تأكدنا من الرابط الصحيح لنسخة البيتا
        url_flash = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
        response = requests.post(url_flash, json=payload, timeout=60)
        if response.status_code == 200:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
        else:
            print(f"Flash Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Flash model failed: {e}")

    # === المحاولة الثانية: استخدام Gemini Pro (المستقر) ===
    print("Trying Gemini Pro (v1) as backup...")
    # تأكدنا من الرابط الصحيح للنسخة المستقرة
    url_pro = f"https://generativelanguage.googleapis.com/v1/models/gemini-pro:generateContent?key={GEMINI_API_KEY}"
    response = requests.post(url_pro, json=payload, timeout=60)
    
    if response.status_code != 200:
        print(f"CRITICAL ERROR: {response.text}")
        response.raise_for_status()
        
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]

def get_ai_image(query):
    seed = random.randint(1, 9999)
    return f"https://image.pollinations.ai/prompt/futuristic technology news concept art?width=1200&height=630&nologo=true&seed={seed}"

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
