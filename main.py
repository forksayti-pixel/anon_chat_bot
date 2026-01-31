# bot.py
import telebot
from telebot import types
from datetime import datetime, date
import json
import os

# -------------------------------
# Настройки
# -------------------------------
TOKEN = "8184653705:AAFEqzSTc5vSPyhqSQ2jyfNY2z2_E_xJ1T8"  # Твой токен
MIN_AGE = 10
DATA_FILE = "users.json"
LOG_FILE = "chat_log.json"

bot = telebot.TeleBot(TOKEN)

# -------------------------------
# Хранилище
# -------------------------------
waiting = []
pairs = {}

# -------------------------------
# Загрузка пользователей и логов
# -------------------------------
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r") as f:
        users = json.load(f)
else:
    users = {}

if os.path.exists(LOG_FILE):
    with open(LOG_FILE, "r") as f:
        chat_log = json.load(f)
else:
    chat_log = []

def save_users():
    with open(DATA_FILE, "w") as f:
        json.dump(users, f)

def save_log():
    with open(LOG_FILE, "w") as f:
        json.dump(chat_log, f)

# -------------------------------
# Утилиты
# -------------------------------
def parse_birthdate(text):
    text = text.strip()
    if text.isdigit() and 1 <= int(text) <= 150:
        age = int(text)
        today = date.today()
        birth_year = today.year - age
        bd = date(birth_year, 1, 1)
        return bd.isoformat(), age
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(text, fmt).date()
            today = date.today()
            age = today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))
            return dt.isoformat(), age
        except:
            pass
    return None, None

def save_user(user_id, birthdate_iso, age, gender=None):
    users[str(user_id)] = {
        "birthdate": birthdate_iso,
        "age": age,
        "gender": gender,
        "banned": users.get(str(user_id), {}).get("banned", 0)
    }
    save_users()

def get_user(user_id):
    return users.get(str(user_id), None)

def log_message(sender_id, partner_id, content_type, content):
    chat_log.append({
        "sender": sender_id,
        "partner": partner_id,
        "type": content_type,
        "content": content,
        "timestamp": datetime.now().isoformat()
    })
    save_log()

# -------------------------------
# Команды
# -------------------------------
@bot.message_handler(commands=['start', 'help'])
def start(message):
    uid = message.chat.id
    user = get_user(uid)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🔎 Найти собеседника"))
    markup.add(types.KeyboardButton("🧾 Регистрация / Проверить возраст"))
    markup.add(types.KeyboardButton("🛑 Стоп чат"))
    markup.add(types.KeyboardButton("📢 Жалоба/Поддержка"))
    markup.add(types.KeyboardButton("📊 Статистика"))
    txt = "Привет! Анонимный чат. Сначала зарегистрируйся (10+)."
    if user and user.get("age"):
        txt += f"\nВозраст: {user['age']}"
        if user.get("gender"):
            txt += f", Пол: {user['gender']}"
    bot.send_message(uid, txt, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🧾 Регистрация / Проверить возраст")
def register_start(message):
    uid = message.chat.id
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("Мальчик"), types.KeyboardButton("Девочка"))
    bot.send_message(uid, "Введи дату рождения (дд.мм.гггг) или возраст, потом выбери пол:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "📢 Жалоба/Поддержка")
def support(message):
    bot.send_message(message.chat.id, "Привет, для подачи жалобы на пользователя напиши нашей модерации @Not3Rey")

@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def stats(message):
    online = len(waiting) + len(pairs)//2
    total = len(users)
    bot.send_message(message.chat.id, f"👥 Онлайн: {online}\n📋 Всего зарегистрировано: {total}")

# -------------------------------
# Основная логика
# -------------------------------
@bot.message_handler(func=lambda m: True, content_types=['text','photo','sticker'])
def handle_text(message):
    uid = message.chat.id
    text = message.text.strip() if message.content_type == 'text' else None
    user = get_user(uid)

    # Регистрация: дата или возраст
    if text:
        bd_iso, age = parse_birthdate(text)
        if bd_iso:
            save_user(uid, bd_iso, age, user.get("gender") if user else None)
            if age < MIN_AGE:
                bot.send_message(uid, f"❗ Минимальный возраст {MIN_AGE}+")
            else:
                bot.send_message(uid, f"Готово! Твой возраст: {age} лет. Можешь нажать '🔎 Найти собеседника'.")
            return
        if text in ["Мальчик", "Девочка"]:
            if not user:
                users[str(uid)] = {"age": None, "gender": text, "banned": 0}
            else:
                user["gender"] = text
            save_users()
            bot.send_message(uid, f"✅ Пол сохранён: {text}")
            return

    # 🔎 Найти собеседника
    if text == "🔎 Найти собеседника":
        if not user or not user.get("age"):
            bot.send_message(uid, "❗ Сначала зарегистрируйся.")
            return
        if user.get("banned") or user.get("age") < MIN_AGE:
            bot.send_message(uid, f"❗ Минимальный возраст {MIN_AGE}+ или заблокирован.")
            return
        if uid in pairs:
            bot.send_message(uid, "❗ Ты уже в чате.")
            return
        # поиск партнёра по возрасту и полу
        partner = None
        i = 0
        while i < len(waiting):
            cand = waiting[i]
            if cand == uid or cand in pairs:
                i += 1
                continue
            cand_user = get_user(cand)
            if not cand_user or cand_user.get("age",0) < MIN_AGE or cand_user.get("banned"):
                i += 1
                continue
            if user.get("gender") and cand_user.get("gender") and user["gender"] != cand_user["gender"]:
                i += 1
                continue
            partner = cand
            waiting.pop(i)
            break
        if partner:
            pairs[uid] = partner
            pairs[partner] = uid
            bot.send_message(uid, "✅ Собеседник найден!")
            bot.send_message(partner, "✅ Собеседник найден!")
        else:
            waiting.append(uid)
            bot.send_message(uid, "🔍 Ищем собеседника...")
        return

    # 🛑 Стоп чат
    if text == "🛑 Стоп чат":
        if uid in pairs:
            partner = pairs.pop(uid)
            if partner in pairs: pairs.pop(partner)
            bot.send_message(uid, "⛔ Чат остановлен.")
            bot.send_message(partner, "⛔ Собеседник отключился.")
        elif uid in waiting:
            waiting.remove(uid)
            bot.send_message(uid, "❗ Поиск отменён.")
        else:
            bot.send_message(uid, "❗ Ты не в чате.")
        return

    # Пересылка сообщений
    if uid in pairs:
        partner = pairs[uid]
        if partner not in pairs or pairs.get(partner) != uid:
            pairs.pop(uid, None)
            bot.send_message(uid, "❗ Собеседник отключился.")
            return
        if message.content_type == 'text':
            log_message(uid, partner, 'text', text)
            bot.send_message(partner, text)
        elif message.content_type == 'photo':
            log_message(uid, partner, 'photo', message.photo[-1].file_id)
            bot.send_photo(partner, message.photo[-1].file_id)
        elif message.content_type == 'sticker':
            log_message(uid, partner, 'sticker', message.sticker.file_id)
            bot.send_sticker(partner, message.sticker.file_id)
        return

    # Не понял
    bot.send_message(uid, "Не понял. Используй меню.")

# -------------------------------
# Render port (24/7)
# -------------------------------
PORT = int(os.environ.get("PORT", 5000))

if __name__ == "__main__":
    print("Bot started...")
    bot.infinity_polling()
