import os
import telebot
import requests
import json

BOT_TOKEN = os.environ.get('TELEGRAM_TOKEN')
AI_API_KEY = os.environ.get('AI_API_KEY')

if not BOT_TOKEN or not AI_API_KEY:
    raise ValueError("⚠️ خطأ: تأكد من إضافة TELEGRAM_TOKEN و AI_API_KEY في إعدادات Railway!")

bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, "مرحباً بك! أرسل لي أي سؤال وسأكشف لك تفاصيل الاتصال الآن.")

@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_text = message.text
    bot.send_chat_action(message.chat.id, 'typing')
    
    # سنحاول إرسال الطلب بالصيغة المخصصة لمنصة inference.sh
    api_url = "https://api.inference.sh/apps/run"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
        "X-API-Version": "2"
    }
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
            output = data.get("output", "")
            if isinstance(output, dict):
                ai_response = output.get("text", str(output))
            else:
                ai_response = str(output)
            bot.reply_to(message, ai_response)
            
        else:
            # 💡 هنا السحر: الكود سيخبرك في تيليجرام بالسيرفر ماذا يقول بالضبط!
            try:
                server_reply = response.text
            except:
                server_reply = "لا توجد تفاصيل نصية من السيرفر."
                
            error_msg = (
                f"❌ فشل الاتصال!\n"
                f"• رمز الخطأ (Status Code): {response.status_code}\n"
                f"• رد السيرفر بالكامل:\n`{server_reply}`"
            )
            bot.reply_to(message, error_msg, parse_mode="Markdown")
                
    except Exception as e:
        bot.reply_to(message, f"⚠️ حدث خطأ غير متوقع في الكود: {str(e)}")

if __name__ == "__main__":
    print("بوت فحص الأخطاء يعمل الآن...")
    bot.infinity_polling()
    
