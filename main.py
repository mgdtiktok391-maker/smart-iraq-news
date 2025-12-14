# -*- coding: utf-8 -*-
import os
import time
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

# مواضيع احتياطية في حال فشل جلب الترند
FALLBACK_TOPICS = [
    "مستقبل الذكاء الاصطناعي في التعليم",
    "أهم ميزات تحديثات أندرويد الأخيرة",
    "كيف تحمي خصوصيتك على الإنترنت؟",
    "تطورات تقنية 5G وتأثيرها عالمياً",
    "أفضل تطبيقات تنظيم الوقت للطلاب",
    "مقارنة بين العملات الرقمية والتقليدية",
    "أسرار التصوير الاحترافي بالهاتف",
    "الفرق بين شاشات OLED و LCD",
    "كيف تبدأ مشروعك التجاري الإلكتروني",
    "تأثير الروبوتات على سوق العمل"
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
    """جلب العناوين السابقة (تم تصحيح الخطأ هنا)"""
    titles = []
    try:
        # التصحيح: استخدام LIVE بالحروف الكبيرة
        posts = service.posts().list(
            blogId=blog_id, fetchBodies=False, maxResults=20, status=["LIVE"]
        ).execute()
        for item in posts.get("items", []):
            titles.append(item.get("title", ""))
    except Exception as e:
        print(f"Warning: Could not fetch history: {e}")
    return titles

def check_duplication(new_topic, old_titles):
    def clean(text):
        return re.sub(r'[^\w\s]', '', text).lower()
    
    nt = clean(new_topic)
    new_words = set(nt.split())
    
    for title in old_titles:
        ot = clean(title)
        common = new_words.intersection(set(ot.split()))
        # إذا كان التشابه أكثر من 50% نعتبره مكرراً
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
    
    # دمج المواضيع الاحتياطية لضمان وجود محتوى دائماً
    for topic in FALLBACK_TOPICS:
        trends.append({'title': topic, 'link': 'https://news.google.com'})
        
    random.shuffle(trends)
    return trends

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def generate_content_gemini(topic_title):
    print(f"Generating content for: {topic_title}")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    أنت محرر تقني محترف. اكتب مقالاً حصرياً للمدونة عن: "{topic_title}".
    
    الشروط:
    1. العنوان: جذاب جداً (Viral) يبدأ بـ # في أول سطر.
    2. المحتوى: لا يقل عن 600 كلمة، مقسم لفقرات بعناوين فرعية.
    3. الأسلوب: شيق، عربي فصحى، ومفيد للقارئ.
    4. التنسيق: استخدم Markdown.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]

def get_ai_image(query):
    # استخدام صور رمزية عامة للتقنية لضمان العمل دائماً
    keywords = "technology news"
    return f"https://image.pollinations.ai/prompt/{keywords}?width=1200&height=630&nologo=true&seed={random.randint(1,1000)}"

def main():
    service = get_blogger_service()
    blog_id = get_blog_id(service)
    
    if not blog_id:
        print("Error: Blog ID not found.")
        return

    history = get_recent_titles(service, blog_id)
    candidates = get_trends()
    
    selected_topic = None
    for cand in candidates:
        if not check_duplication(cand['title'], history):
            selected_topic = cand
            break
            
    if not selected_topic:
        # إذا كان كل شيء مكرراً، خذ موضوعاً عشوائياً من الاحتياطي
        print("All trends duplicated. Using random fallback.")
        selected_topic = {'title': random.choice(FALLBACK_TOPICS), 'link': 'https://google.com'}

    print(f"Selected Topic: {selected_topic['title']}")

    try:
        raw_md = generate_content_gemini(selected_topic['title'])
    except Exception as e:
        print(f"Gemini Error: {e}")
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
    <p style="text-align:center; color: #888; font-size: small;">إعداد: فريق التحرير الذكي</p>
    """
    
    body = {
        "kind": "blogger#post",
        "title": title,
        "content": post_body,
        "labels": ["تكنولوجيا", "أخبار"]
    }
    
    try:
        # نشر مباشر (LIVE)
        post = service.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
        print(f"SUCCESS! Published to: {post.get('url')}")
    except Exception as e:
        print(f"Publishing Error: {e}")

if __name__ == "__main__":
    main()
