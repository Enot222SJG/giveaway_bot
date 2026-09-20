from telebot import TeleBot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from logic import *
import schedule
import threading
import time
import os
from config import *

bot = TeleBot(API_TOKEN)
DB_PATH = os.path.join(BASE_DIR, DATABASE)

def gen_markup(id):
    markup = InlineKeyboardMarkup()
    markup.row_width = 1
    markup.add(InlineKeyboardButton("Получить!", callback_data=id))
    return markup

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):

    prize_id = call.data
    user_id = call.message.chat.id

    if manager.get_winners_count() >= 3:
        bot.answer_callback_query(call.id, "Увы, призы уже закончились!")
        return

    if manager.add_winner(user_id, prize_id) == 0:
        bot.answer_callback_query(call.id, "Ты уже получал этот приз!")
        return

    img = manager.get_prize_img(prize_id)
    with open(os.path.join(IMG_DIR, img), 'rb') as photo:
        bot.send_photo(user_id, photo)
    bot.answer_callback_query(call.id, "Поздравляем! Ты выиграл приз!")


@bot.message_handler(commands=['rating'])
def handle_rating(message):
    rating = manager.get_rating()
    if not rating:
        bot.reply_to(message, "Пока никто не получил призов.")
        return
    text = "Рейтинг пользователей:\n"
    for i, (user_name, count) in enumerate(rating, 1):
        name = f"@{user_name}" if user_name else "Без имени"
        text += f"{i}. {name} — {count} приз(ов)\n"
    bot.reply_to(message, text)


def send_message():
    prize_id, img = manager.get_random_prize()[:2]
    manager.mark_prize_used(prize_id)
    hide_img(img)
    for user in manager.get_users():
        with open(os.path.join(HIDDEN_IMG_DIR, img), 'rb') as photo:
            bot.send_photo(user, photo, reply_markup=gen_markup(id = prize_id))
        

def shedule_thread():
    schedule.every().minute.do(send_message) # Здесь ты можешь задать периодичность отправки картинок
    while True:
        schedule.run_pending()
        time.sleep(1)

@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.chat.id
    if user_id in manager.get_users():
        bot.reply_to(message, "Ты уже зарегестрирован!")
    else:
        manager.add_user(user_id, message.from_user.username)
        bot.reply_to(message, """Привет! Добро пожаловать! 
Тебя успешно зарегистрировали!
Каждый час тебе будут приходить новые картинки и у тебя будет шанс их получить!
Для этого нужно быстрее всех нажать на кнопку 'Получить!'

Только три первых пользователя получат картинку!)""")
        


def polling_thread():
    bot.polling(none_stop=True)

if __name__ == '__main__':
    manager = DatabaseManager(DB_PATH)
    manager.create_tables()

    polling_thread = threading.Thread(target=polling_thread)
    polling_shedule  = threading.Thread(target=shedule_thread)

    polling_thread.start()
    polling_shedule.start()
  
