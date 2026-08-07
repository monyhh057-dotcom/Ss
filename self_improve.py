"""
self_improve.py — البوت يعدّل نفسه فعلياً على GitHub

شنو يسوي بالضبط (3 خطوات بس):
1. يقرا bot.py من GitHub (عن طريق API، مو ملف على القرص)
2. يبعته لـ Groq ويقول له "حسّن هذا الكود"
3. يرفع النسخة المحسّنة لـ GitHub (commit جديد)
   → Railway يشوف تغيير جديد بالريبو وينشره لحاله تلقائياً

يحتاج GITHUB_TOKEN و GITHUB_REPO (اشرحلك تحت كيف تجيبهم).
"""

import os
import base64
import logging
import requests

log = logging.getLogger("self-improve")

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")
GITHUB_REPO = os.environ.get("GITHUB_REPO")  # شكله: "username/repo-name"
FILE_PATH = "bot.py"  # الملف اللي بيتعدل

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
GITHUB_API = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{FILE_PATH}"


# ------------------------------------------------------------ خطوة 1: اقرا --

def read_code_from_github():
    """يجيب محتوى bot.py الحالي من GitHub + sha (رقم النسخة الحالية)."""
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    r = requests.get(GITHUB_API, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data["content"]).decode("utf-8")
    return content, data["sha"]


# --------------------------------------------------------- خطوة 2: حسّن --

def ask_groq_to_improve(code):
    """يطلب من Groq نسخة محسّنة من الكود كامل."""
    system = (
        "انت مبرمج Python خبير. بتستلم كود بوت تيليكرام كامل. "
        "مهمتك: حسّن تحسين واحد بسيط وآمن فقط (مثلاً: تحسين أداء، إصلاح "
        "خطأ محتمل، تنظيف كود). لا تحذف أي وظيفة موجودة. لا تغيّر أشياء "
        "كثيرة دفعة وحدة. رد بالكود الكامل المعدّل فقط، بدون أي شرح "
        "قبله أو بعده، بدون ```python أو ``` في البداية والنهاية."
    )
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": code},
        ],
        "temperature": 0.3,
        "max_tokens": 8000,
    }
    headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
    r = requests.post(GROQ_URL, json=payload, headers=headers, timeout=60)
    r.raise_for_status()
    new_code = r.json()["choices"][0]["message"]["content"]
    return new_code.strip()


# --------------------------------------------------------- خطوة 3: ارفع --

def push_code_to_github(new_code, old_sha, message="🤖 auto-improve"):
    """يرفع الكود المعدّل كـ commit جديد على GitHub."""
    headers = {"Authorization": f"Bearer {GITHUB_TOKEN}"}
    payload = {
        "message": message,
        "content": base64.b64encode(new_code.encode("utf-8")).decode("utf-8"),
        "sha": old_sha,  # لازم رقم النسخة الحالية عشان GitHub يعرف ما تكتب فوق تعديل ثاني
    }
    r = requests.put(GITHUB_API, headers=headers, json=payload, timeout=15)
    r.raise_for_status()
    return r.json()


# ------------------------------------------------------------------ تحقق --

def is_valid_python(code):
    """تأكد إن الكود المعدّل ما فيه خطأ إملائي بالصياغة قبل ما نرفعه."""
    try:
        compile(code, "<string>", "exec")
        return True
    except SyntaxError as e:
        log.error(f"الكود المقترح فيه خطأ صياغة: {e}")
        return False


# ------------------------------------------------------------------ الكل --

def run_self_improvement():
    """ينفذ الدورة كاملة: اقرا → حسّن → تحقق → ارفع."""
    if not (GROQ_API_KEY and GITHUB_TOKEN and GITHUB_REPO):
        return "❌ ناقص GROQ_API_KEY أو GITHUB_TOKEN أو GITHUB_REPO بالإعدادات"

    try:
        code, sha = read_code_from_github()
    except Exception as e:
        return f"❌ ما قدرت أقرا الكود من GitHub: {e}"

    try:
        new_code = ask_groq_to_improve(code)
    except Exception as e:
        return f"❌ Groq ما قدر يحسّن الكود: {e}"

    if not is_valid_python(new_code):
        return "❌ الكود المقترح فيه خطأ صياغة، ما تم الرفع (آمن، ما صار تغيير)"

    if len(new_code) < len(code) * 0.5:
        # لو النسخة الجديدة أقصر من نصف الأصلية، شي غلط أكيد (حذف كبير بالغلط)
        return "❌ الكود المقترح قصير بشكل مريب، ما تم الرفع (حماية إضافية)"

    try:
        push_code_to_github(new_code, sha)
    except Exception as e:
        return f"❌ ما قدرت أرفع الكود لـ GitHub: {e}"

    return "✅ تم! رفعت نسخة محسّنة لـ GitHub. Railway رح ينشرها تلقائياً خلال دقايق."


# --------------------------------------------------- أمر تيليكرام /self_improve --

async def cmd_self_improve(update, context):
    await update.message.reply_text("🤖 بقرا كودي، بحسّنه، وبرفعه لـ GitHub... (تاخذ حوالي دقيقة)")
    import asyncio
    result = await asyncio.to_thread(run_self_improvement)
    await update.message.reply_text(result)
