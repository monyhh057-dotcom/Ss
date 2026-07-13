import os
import telebot
import requests

# جلب التوكنات بأمان من إعدادات Railway التي قمت بضبطها مسبقاً
BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
AI_API_KEY = os.environ.get('AI_API_KEY')

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
    
    # الرابط الصحيح الموحد لمنصة inference.sh
    api_url = "https://api.inference.sh/apps/run"
    
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
        "X-API-Version": "2"
    }
    
    # لقد اخترت لك هنا نموذج (Kimi K2 Thinking) وهو ممتاز جداً ومتاح في حسابك
    payload = {
        "app": "openrouter/kimi-k2-thinking", 
        "input": {
            "text": user_text
        }
    }
    
    try:
        response = requests.post(api_url, json=payload, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            
            # استخراج رد الذكاء الاصطناعي حسب طريقة عرض منصة inference
            output = data.get("output", "")
            if isinstance(output, dict):
                ai_response = output.get("text", str(output))
            else:
                ai_response = str(output)
            
            if ai_response.strip():
                bot.reply_to(message, ai_response)
            else:
                bot.reply_to(message, "⚠️ استلمت رداً فارغاً من الذكاء الاصطناعي.")
        else:
            bot.reply_to(message, f"❌ واجهت مشكلة في الاتصال. رمز الخطأ: {response.status_code}")
                
    except Exception as e:
        bot.reply_to(message, f"⚠️ حدث خطأ غير متوقع في النظام: {str(e)}")

if __name__ == "__main__":
    print("البوت يعمل الآن بنجاح...")
    bot.infinity_polling()
    
