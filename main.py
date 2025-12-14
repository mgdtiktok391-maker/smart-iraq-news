# -*- coding: utf-8 -*-
import os
import random
import re
import feedparser
import backoff
import markdown as md
import google.generativeai as genai  # <--- المكتبة الرسمية
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ================= إعدادات =================
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
BLOG_URL = os.environ["BLOG_URL"]
CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["REFRESH_TOKEN"]

# إعداد مكتبة Gemini
genai.configure(api_key=GEMINI_API_KEY)

# مواضيع احتياطية
FALLBACK_TOPICS = [
    "كيف يؤثر الذكاء الاصطناعي على مستقبل الوظائف؟",
    "أهم 5 نصائح لحماية هاتفك من الاختراق",
    "شرح مبسط لتقنية البلوك تشين والعملات الرقمية",
    "أفضل تطبيقات تنظيم الوقت وزيادة الإنتاجية",
    "كيف تبدأ تعلم البرمجة من الصفر مجاناً",
    "أسرار التسويق الإلكتروني الناجح في 2025"
]

def get_blogger_service():
    """الاتصال بخدمة بلوجر"""
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
    titles = []
    try:
        posts = service.posts().list(
            blogId=blog_id, fetchBodies=False, maxResults=20
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
        if len(new_words) > 0 and len(common) / len(new_words) > 0.5:
            return True
    return False

def get_trends():
    urls = [
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=SA",
        "https://trends.google.com/trends/trendingsearches/daily/rss?geo=EG"
    ]
    trends = []
    print("Fetching trends...")
    for url in urls:
        try:
            feed = feedparser.parse(url)
            if not feed.entries: continue
            for entry in feed.entries[:2]:
                trends.append({'title': entry.title})
        except:
            continue
    
    # إضافة المواضيع الاحتياطية
    for topic in FALLBACK_TOPICS:
        trends.append({'title': topic})
        
    random.shuffle(trends)
    return trends

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def generate_content_gemini(topic_title):
    print(f"Generating content for: {topic_title} using Gemini Library...")
    
    # استخدام الموديل الرسمي والمستقر
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    اكتب مقالاً لمدونة تقنية عن: "{topic_title}".
    الشروط:
    1. العنوان يجب أن يكون جذاباً جداً.
    2. التنسيق: استخدم Markdown (عناوين h2, نقاط، عريض).
    3. اللغة: عربية فصحى سلسة وممتعة.
    4. الطول: حوالي 500-600 كلمة.
    5. لا تكتب مقدمات مثل "إليك المقال"، ابدأ بالعنوان مباشرة.
    """
    
    response = model.generate_content(prompt)
    
    # التأكد من وجود نص في الرد
    if response.text:
        return response.text
    else:
        raise Exception("Gemini returned empty response")

def get_ai_image(query):
    seed = random.randint(1, 9999)
    # استخدام صور تقنية عامة لضمان الجودة
    return f"https://image.pollinations.ai/prompt/modern technology futuristic minimal 4k wallpaper?width=800&height=450&nologo=true&seed={seed}"

def main():
    print("--- Starting Auto Post Bot ---")
    service = get_blogger_service()
    blog_id = get_blog_id(service)
    
    if not blog_id:
        print("❌ Error: Blog ID not found. Check BLOG_URL.")
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
        selected_topic = {'title': random.choice(FALLBACK_TOPICS)}

    print(f"✅ Selected Topic: {selected_topic['title']}")

    try:
        raw_md = generate_content_gemini(selected_topic['title'])
    except Exception as e:
        print(f"❌ Gemini API Error: {e}")
        return

    # معالجة النص لاستخراج العنوان
    lines = raw_md.split('\n')
    title = selected_topic['title']
    content_lines = []
    
    for line in lines:
        clean_line = line.strip().replace('#', '').strip()
        if not content_lines and len(clean_line) > 5 and len(clean_line) < 100:
            # افتراض أن السطر الأول هو العنوان
            title = clean_line
        else:
            content_lines.append(line)
            
    final_html = md.markdown("\n".join(content_lines))
    img_url = get_ai_image(title)
    
    post_body = f"""
    <div style="text-align: center; margin-bottom: 20px;">
        <img src="{img_url}" alt="{title}" style="max-width: 100%; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
    </div>
    <div style="font-family: Arial, sans-serif; line-height: 1.8; text-align: right; direction: rtl;">
        {final_html}
    </div>
    <hr>
    <p style="text-align:center; color: #666; font-size: 12px;">تم النشر بواسطة: المساعد الذكي</p>
    """
    
    body = {
        "kind": "blogger#post",
        "title": title,
        "content": post_body,
        "labels": ["تكنولوجيا", "AI"]
    }
    
    try:
        post = service.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
        print(f"🎉 SUCCESS! Published: {post.get('url')}")
    except Exception as e:
        print(f"❌ Publishing Error: {e}")

if __name__ == "__main__":
    main()
