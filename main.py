# -*- coding: utf-8 -*-
import os
import json
import random
import re
import feedparser
import backoff
import markdown as md
import google.generativeai as genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# ================= إعدادات البيئة =================
# تأكد أنك وضعت هذه المفاتيح في GitHub Secrets
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
BLOGGER_TOKEN_STR = os.environ["BLOGGER_TOKEN"] # التوكن الطويل (JSON)

# إعداد مكتبة Gemini
genai.configure(api_key=GEMINI_API_KEY)

# مواضيع احتياطية في حال فشل جلب الترند
FALLBACK_TOPICS = [
    "مستقبل الذكاء الاصطناعي في التعليم 2025",
    "أفضل طرق حماية الخصوصية على الإنترنت",
    "كيف تبدأ العمل الحر Freelancing خطوة بخطوة",
    "تطبيقات لا غنى عنها لزيادة الإنتاجية",
    "شرح تقنية البلوك تشين للمبتدئين"
]

def get_blogger_service():
    """الاتصال ببلوجر باستخدام التوكن المحفوظ"""
    try:
        # تحويل نص التوكن من GitHub Secret إلى كائن اعتماد
        token_info = json.loads(BLOGGER_TOKEN_STR)
        creds = Credentials.from_authorized_user_info(token_info)
        return build("blogger", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        print(f"Auth Error: تأكد من صحة BLOGGER_TOKEN في الأسرار. الخطأ: {e}")
        raise e

def get_blog_id(service):
    """جلب معرف المدونة تلقائياً"""
    try:
        # يجلب أول مدونة في الحساب
        blogs = service.blogs().listByUser(userId='self').execute()
        blog_item = blogs['items'][0]
        return blog_item['id'], blog_item['name']
    except Exception as e:
        print(f"Error getting blog: {e}")
        return None, None

def get_recent_titles(service, blog_id):
    """جلب آخر العناوين لمنع التكرار"""
    titles = []
    try:
        posts = service.posts().list(
            blogId=blog_id, fetchBodies=False, maxResults=15
        ).execute()
        for item in posts.get("items", []):
            titles.append(item.get("title", ""))
    except Exception as e:
        print(f"Warning (History): {e}")
    return titles

def check_duplication(new_topic, old_titles):
    """فحص تشابه العناوين"""
    def clean(text): return re.sub(r'[^\w\s]', '', text).lower()
    
    nt = clean(new_topic)
    new_words = set(nt.split())
    
    for title in old_titles:
        ot = clean(title)
        common = new_words.intersection(set(ot.split()))
        # إذا تشابهت أكثر من 50% من الكلمات نعتبره مكرراً
        if len(new_words) > 0 and len(common) / len(new_words) > 0.5:
            return True
    return False

def get_trends():
    """جلب ترندات تقنية"""
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
            for entry in feed.entries[:2]: # نأخذ أول 2 من كل دولة
                trends.append({'title': entry.title})
        except:
            continue
    
    # دمج الاحتياطي
    for topic in FALLBACK_TOPICS:
        trends.append({'title': topic})
        
    random.shuffle(trends)
    return trends

@backoff.on_exception(backoff.expo, Exception, max_tries=3)
def generate_content_gemini(topic_title):
    """توليد المقال باستخدام مكتبة Gemini الرسمية"""
    print(f"Writing article about: {topic_title}...")
    
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    اكتب مقالاً لمدونة تقنية بعنوان يدور حول: "{topic_title}".
    الشروط:
    1. تنسيق Markdown احترافي (عناوين h2، نقاط، نص عريض).
    2. لا تكتب مقدمة للمقال مثل "إليك المقال"، ابدأ بالعنوان مباشرة.
    3. اللغة عربية فصحى وجذابة.
    4. الطول: لا يقل عن 500 كلمة.
    """
    
    response = model.generate_content(prompt)
    if response.text:
        return response.text
    else:
        raise Exception("Empty response from Gemini")

def get_ai_image(query):
    """صورة تقنية عشوائية"""
    seed = random.randint(1, 9999)
    # نستخدم كلمات مفتاحية عامة للتكنولوجيا لضمان جودة الصورة
    return f"https://image.pollinations.ai/prompt/futuristic high tech abstract background 8k wallpaper?width=800&height=450&nologo=true&seed={seed}"

def main():
    print("--- Starting Auto Post Bot ---")
    
    # 1. الاتصال
    try:
        service = get_blogger_service()
        blog_id, blog_name = get_blog_id(service)
    except Exception as e:
        print(f"❌ Connection Failed: {e}")
        return

    if not blog_id:
        print("❌ No blog found linked to this account.")
        return

    print(f"✅ Connected to Blog: {blog_name}")

    # 2. اختيار الموضوع
    history = get_recent_titles(service, blog_id)
    candidates = get_trends()
    
    selected_topic = None
    for cand in candidates:
        if not check_duplication(cand['title'], history):
            selected_topic = cand
            break
            
    if not selected_topic:
        print("Using random fallback topic...")
        selected_topic = {'title': random.choice(FALLBACK_TOPICS)}

    print(f"📝 Selected Topic: {selected_topic['title']}")

    # 3. الكتابة (Gemini)
    try:
        raw_md = generate_content_gemini(selected_topic['title'])
    except Exception as e:
        print(f"❌ Gemini Error: {e}")
        return

    # 4. التنسيق والنشر
    # محاولة استخراج العنوان من النص أو استخدام موضوع الترند
    lines = raw_md.split('\n')
    title = selected_topic['title']
    content_lines = []
    
    for line in lines:
        clean = line.strip().replace('#', '').strip()
        # إذا وجدنا سطراً قصيراً في البداية يشبه العنوان نعتمد عليه
        if not content_lines and len(clean) > 5 and len(clean) < 100:
            title = clean
        else:
            content_lines.append(line)
            
    final_html = md.markdown("\n".join(content_lines))
    img_url = get_ai_image(title)
    
    post_body = f"""
    <div style="text-align: center; margin-bottom: 20px;">
        <img src="{img_url}" alt="{title}" style="max-width: 100%; border-radius: 10px; box-shadow: 0 4px 15px rgba(0,0,0,0.2);">
    </div>
    <div dir="rtl" style="text-align: right; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.8; color: #333;">
        {final_html}
    </div>
    <hr>
    <p style="text-align:center; color: #888; font-size: 0.8em;">تم النشر بواسطة: الذكاء الاصطناعي (Gemini)</p>
    """
    
    body = {
        "kind": "blogger#post",
        "title": title,
        "content": post_body,
        "labels": ["تكنولوجيا", "AI News"]
    }
    
    try:
        post = service.posts().insert(blogId=blog_id, body=body, isDraft=False).execute()
        print(f"🎉 SUCCESS! Post published: {post.get('url')}")
    except Exception as e:
        print(f"❌ Publishing Error: {e}")

if __name__ == "__main__":
    main()
