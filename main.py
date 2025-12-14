# -*- coding: utf-8 -*-
import os
import time
import random
import re
import html
from datetime import datetime
import requests
import feedparser
import backoff
import markdown as md
import pytz
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ================= إعدادات =================
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
BLOG_URL = os.environ["BLOG_URL"]
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["REFRESH_TOKEN"]

# الموديل الذكي والمجاني
GEMINI_MODEL = "gemini-1.5-flash"

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
    """جلب آخر 30 عنوان منشور للتأكد من عدم التكرار"""
    titles = []
    try:
        posts = service.posts().list(
            blogId=blog_id, fetchBodies=False, maxResults=30, status=["live"]
        ).execute()
        for item in posts.get("items", []):
            titles.append(item.get("title", ""))
    except Exception as e:
        print(f"Warning: Could not fetch history: {e}")
    return titles

def check_duplication(new_topic, old_titles):
    """فحص ذكي للتشابه بين العناوين"""
    # تنظيف النص للمقارنة
    def clean(text):
        return re.sub(r'[^\w\s]', '', text).lower()
    
    nt = clean(new_topic)
    new_words = set(nt.split())
    
    for title in old_titles:
        ot = clean(title)
        # إذا تطابقت نصف الكلمات تقريباً نعتبره مكرراً
        common = new_words.intersection(set(ot.split()))
        if len(common) > 0 and len(common) / len(new_words) > 0.5:
            return True
    return False

def get_trends():
    """جلب ترندات من مصادر متعددة"""
    urls = [
        # ترندات جوجل (العراق)
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=IQ",
        # ترندات جوجل (السعودية - للمحتوى العربي)
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=SA",
        # أخبار تقنية عالمية
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=US&cat=t"
    ]
    trends = []
    for url in urls:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                trends.append({'title': entry.title, 'link': entry.link})
        except:
            continue
    random.shuffle(trends)
    return trends

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def generate_content_gemini(topic_title):
    print(f"Generating content for: {topic_title}")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""
    اكتب مقالاً احترافياً للمدونة حول الموضوع الرائج: "{topic_title}".
    
    التعليمات:
    1. العنوان: اجعله جذاباً جداً (Viral/Clickbait) لكن صادقاً، وضعه في أول سطر مسبوقاً بـ #.
    2. الأسلوب: سردي، ممتع، وسهل القراءة باللهجة العربية الفصحى الحديثة.
    3. البنية: مقدمة تشد الانتباه، تفاصيل الخبر، لماذا يهمنا هذا؟، وخاتمة.
    4. التنسيق: استخدم Markdown (عناوين فرعية H2).
    5. تجنب: المقدمات المملة مثل "في هذا المقال سوف نتحدث عن...". ادخل في الموضوع فوراً.
    6. الطول: حوالي 600-800 كلمة.
    """
    
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    response = requests.post(url, json=payload, timeout=60)
    response.raise_for_status()
    return response.json()["candidates"][0]["content"]["parts"][0]["text"]

def get_ai_image(query):
    # استخدام خدمة Pollinations لتوليد صورة مجانية وسريعة بدون مفاتيح
    # نأخذ أول كلمتين من العنوان للبحث
    keywords = " ".join(query.split()[:3])
    # نطلب صورة تقنية/واقعية
    return f"https://image.pollinations.ai/prompt/hyperrealistic photo of {keywords}, high quality, 4k?width=1200&height=630&nologo=true"

def main():
    service = get_blogger_service()
    blog_id = get_blog_id(service)
    
    if not blog_id:
        return

    # 1. فحص ماذا نشرنا سابقاً
    history = get_recent_titles(service, blog_id)
    
    # 2. البحث عن ترند جديد
    candidates = get_trends()
    selected_topic = None
    
    for cand in candidates:
        if not check_duplication(cand['title'], history):
            selected_topic = cand
            break
            
    if not selected_topic:
        print("No new unique trends found. Exiting.")
        return # لا ننشر شيئاً إذا كان كل شيء مكرراً

    # 3. توليد المقال
    raw_md = generate_content_gemini(selected_topic['title'])
    
    # استخراج العنوان
    lines = raw_md.split('\n')
    title = selected_topic['title']
    content_lines = []
    for line in lines:
        if line.strip().startswith("# "):
            title = line.replace("#", "").strip()
        else:
            content_lines.append(line)
            
    final_content_md = "\n".join(content_lines)
    final_html = md.markdown(final_content_md)
    
    # 4. الصورة
    img_url = get_ai_image(selected_topic['title'])
    
    post_body = f"""
    <div style="text-align: center; margin-bottom: 15px;">
        <img src="{img_url}" alt="{title}" style="max-width: 100%; border-radius: 8px;">
    </div>
    {final_html}
    <hr>
    <p style="text-align:center; font-size: small; color: #666;">المصدر: {selected_topic['link']}</p>
    """
    
    # 5. النشر
    body = {
        "kind": "blogger#post",
        "title": title,
        "content": post_body,
        "labels": ["ترند", "أخبار"]
    }
    
    post = service.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
    print(f"Published: {post.get('url')}")

if __name__ == "__main__":
    main()
