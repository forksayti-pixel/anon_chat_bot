# bot.py
import telebot
from telebot import types
import sqlite3
from datetime import datetime, date

TOKEN = "8184653705:AAFEqzSTc5vSPyhqSQ2jyfNY2z2_E_xJ1T8"
MIN_AGE = 10  # минимальный возраст

bot = telebot.TeleBot(TOKEN)

# --- База данных ---
conn = sqlite3.connect('users.db', check_same_thread=False)
cur = conn.cursor()
cur.execute('''
CREATE TABLE IF NOT EXISTS users(
    user_id INTEGER PRIMARY KEY,
    birthdate TEXT,    -- в формате YYYY-MM-DD
    age INTEGER,
    gender TEXT,
    banned INTEGER DEFAULT 0
)
''')
conn.commit()

# --- Хранилища для поиска/пар ---
waiting = []  # список user_id ожидающих
pairs = {}    # user_id -> partner_id

# --- Утилиты ---
def parse_birthdate(text):
    """
    Принимает строку: dd.mm.yyyy или yyyy-mm-dd или просто число возраста.
    Возвращает (birthdate_str YYYY-MM-DD, age) или (None, None) при ошибке.
    """
    text = text.strip()
    # попытка: возраст как число
    if text.isdigit() and 1 <= int(text) <= 150:
        age = int(text)
        # приблизительная дата рождения: год = текущий - age, месяц/день = 1-1
        today = date.today()
        birth_year = today.year - age
        bd = date(birth_year, 1, 1)
        return bd.isoformat(), age
    # попытка: dd.mm.yyyy
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(text, fmt).date()
            today = date.today()
            # вычисляем возраст точно
            age = today.year - dt.year - ((today.month, today.day) < (dt.month, dt.day))
            return dt.isoformat(), age
        except:
            pass
    return None, None

def save_user(user_id, birthdate_iso, age, gender=None):
    cur.execute('REPLACE INTO users(user_id, birthdate, age, gender, banned) VALUES(?,?,?,?, COALESCE((SELECT banned FROM users WHERE user_id=?),0))',
                (user_id, birthdate_iso, age, gender, user_id))
    conn.commit()

def get_user(user_id):
    cur.execute('SELECT user_id, birthdate, age, gender, banned FROM users WHERE user_id=?', (user_id,))
    row = cur.fetchone()
    if row:
        return {"user_id":row[0], "birthdate":row[1], "age":row[2], "gender":row[3], "banned":row[4]}
    return None

# --- Команды ---
@bot.message_handler(commands=['start', 'help'])
def start(message):
    uid = message.chat.id
    user = get_user(uid)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add(types.KeyboardButton("🔎 Найти собеседника"))
    markup.add(types.KeyboardButton("🧾 Регистрация / Проверить возраст"))
    markup.add(types.KeyboardButton("🛑 Стоп чат"))
    markup.add(types.KeyboardButton("📢 Жалоба/Поддержка"))
    txt = "Привет! Это анонимный чат. Перед поиском собеседника нужно пройти регистрацию и подтвердить свой возраст (10+)."
    if user and user.get("age") is not None:
        txt += f"\n\nТекущий возраст: {user['age']} лет."
    bot.send_message(uid, txt, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🧾 Регистрация / Проверить возраст")
def register_start(message):
    uid = message.chat.id
    bot.send_message(uid, "Введи дату рождения в формате `дд.мм.гггг` или просто напиши свой возраст (например `15`).", parse_mode="Markdown")

@bot.message_handler(func=lambda m: True)
def handle_text(message):
    uid = message.chat.id
    text = message.text.strip()

    # Если пользователь нажал найти
    if text == "🔎 Найти собеседника":
        user = get_user(uid)
        if not user or user.get("age") is None:
            bot.send_message(uid, "❗ Сначала зарегистрируйся и укажи свой возраст (меню → Регистрация).")
            return
        if user.get("banned"):
            bot.send_message(uid, "🚫 Ты заблокирован и не можешь пользоваться чатом.")
            return
        if user.get("age") < MIN_AGE:
            bot.send_message(uid, f"❗ Извини, минимальный возраст — {MIN_AGE}+ (по твоим данным {user.get('age')}).")
            return

        # поиск партнёра
        if uid in pairs:
            bot.send_message(uid, "❗ Ты уже в чате. Нажми '🛑 Стоп чат' чтобы завершить.")
            return
        # ищем в ожидании — берём только тех, у кого возраст >= MIN_AGE и не заблокированы
        partner = None
        while waiting:
            cand = waiting.pop(0)
            # пропускаем самого себя или если уже в паре или заблокирован
            if cand == uid or cand in pairs:
                continue
            cand_user = get_user(cand)
            if not cand_user or cand_user.get("age") is None or cand_user.get("age") < MIN_AGE or cand_user.get("banned"):
                continue
            partner = cand
            break

        if partner:
            # соединяем
            pairs[uid] = partner
            pairs[partner] = uid
            bot.send_message(uid, "✅ Собеседник найден! Можешь писать. (Анонимно)")
            bot.send_message(partner, "✅ Собеседник найден! Можешь писать. (Анонимно)")
        else:
            waiting.append(uid)
            bot.send_message(uid, "🔍 Ищем собеседника... (жди или нажми '🛑 Стоп чат' чтобы отменить)")

        return

    # Стоп чат
    if text == "🛑 Стоп чат":
        if uid in pairs:
            partner = pairs.pop(uid)
            # удаляем обратную ссылку
            if partner in pairs:
                pairs.pop(partner)
                bot.send_message(partner, "⛔ Собеседник прервал чат.")
            bot.send_message(uid, "⛔ Чат остановлен.")
        else:
            # убрать из очереди, если ожидает
            if uid in waiting:
                waiting.remove(uid)
                bot.send_message(uid, "Поиск отменён.")
            else:
                bot.send_message(uid, "Ты не в чате.")
        return

    # Жалоба / поддержка
    if text == "📢 Жалоба/Поддержка":
        bot.send_message(uid, "Если нужно пожаловаться — напиши ID собеседника (если есть) или опиши проблему. Админы проверят.")
        return

    # Если сообщение похоже на дату/возраст — обработаем как регистрацию
    bd_iso, age = parse_birthdate(text)
    if bd_iso is not None:
        save_user(uid, bd_iso, age)
        if age < MIN_AGE:
            bot.send_message(uid, f"Извини, минимальный возраст для использования этого чата — {MIN_AGE}+.\nЕсли ты ошибся, перешли точную дату рождения.")
        else:
            bot.send_message(uid, f"Готово! Твой возраст: {age} лет. Можешь нажать '🔎 Найти собеседника'.")
        return

    # Если пользователь в паре — пересылаем как аноним
    if uid in pairs:
        partner = pairs[uid]
        # защита: если партнёр исчез — разорвать
        if partner not in pairs or pairs.get(partner) != uid:
            pairs.pop(uid, None)
            bot.send_message(uid, "❗ Собеседник отключился.")
            return
        # Пересылаем только текст (можно расширить на фото/стикеры)
        bot.send_message(partner, text)
        return

    # Для прочих сообщений — подсказка
    bot.send_message(uid, "Не понял. Используй меню: '🧾 Регистрация' или '🔎 Найти собеседника'.")

# Запуск бота
if __name__ == "__main__":
    print("Bot started...")
    bot.infinity_polling()
