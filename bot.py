import os
import telebot
import requests

# جلب التوكنات بأمان من إعدادات Railway (وليس كتابتها هنا)
BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
AI_API_KEY = os.environ.get('AI_API_KEY')

# التحقق من وجود المتغيرات
if not BOT_TOKEN or not AI_API_KEY:
    raise ValueError("⚠️ خطأ: تأكد من إضافة TELEGRAM_TOKEN و AI_API_KEY في إعدادات Railway!")

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "مرحباً بك! أنا بوت الذكاء الاصطناعي الخاص بك. أرسل لي أي سؤال وسأقوم بالرد عليك فوراً.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_text = message.text
    
    # إظهار حالة "يكتب الآن..." في التيليجرام
    bot.send_chat_action(message.chat.id, 'typing')
    
    # رابط الـ API الخاص بنموذج فيبل (تأكد من تعديل الرابط إذا كان مختلفاً في توثيقهم الرسمي)
    # غالباً ما تكون النماذج متوافقة مع صيغة OpenAI أو لها مسار خاص مثل /v1/chat/completions
    api_url = "https://api.vable.ai/v1/chat/completions" 
    
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    # الهيكل القياسي لإرسال الطلب للذكاء الاصطناعي
    payload = {
        "model": "vable-model", # اسم النموذج الافتراضي
        "messages": [
            {"role": "user", "content": user_text}
        ]
    }
    
    try:
        response = requests.post(api_url, json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            # استخراج رد الذكاء الاصطناعي (تلقائياً حسب الصيغ المشهورة)
            ai_response = data['choices'][0]['message']['content']
            bot.reply_to(message, ai_response)
        else:
            # إذا فشل، نحاول فحص إذا كانت صيغة البيانات مختلفة
            try:
                data = response.json()
                ai_response = data.get('reply') or data.get('response') or f"حدث خطأ في الرد من السيرفر: {response.status_code}"
                bot.reply_to(message, ai_response)
            except:
                bot.reply_to(message, f"❌ واجهت مشكلة في الاتصال بالذكاء الاصطناعي. رمز الخطأ: {response.status_code}")
                
    except Exception as e:
        bot.reply_to(message, f"⚠️ حدث خطأ غير متوقع في النظام: {str(e)}")

if __name__ == "__main__":
    print("البوت يعمل الآن بنجاح...")
    bot.infinity_polling()
  
