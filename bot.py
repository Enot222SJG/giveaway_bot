import asyncio
import os
import random
import time
import cv2

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import API_TOKEN, ADMIN_ID, BONUS_PER_WIN, PRIZE_PRICE, SEND_INTERVAL_MIN, SEND_INTERVAL_MAX
from logic import BASE_DIR, IMG_DIR, HIDDEN_IMG_DIR, DATABASE, DatabaseManager, create_collage, hide_img

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

DB_PATH = os.path.join(BASE_DIR, DATABASE)
manager = DatabaseManager(DB_PATH)


class AddPrize(StatesGroup):
    waiting_for_photo = State()


def gen_markup(prize_id):
    builder = InlineKeyboardBuilder()
    builder.button(text="Получить!", callback_data=str(prize_id))
    builder.adjust(1)
    return builder.as_markup()


@dp.callback_query(F.data)
async def callback_query(callback: CallbackQuery):
    prize_id = int(callback.data)
    user_id = callback.message.chat.id

    if manager.get_winners_count() >= 3:
        await callback.answer("Увы, призы уже закончились!")
        return

    if manager.add_winner(user_id, prize_id) == 0:
        await callback.answer("Ты уже получал этот приз!")
        return

    img = manager.get_prize_img(prize_id)
    await callback.message.answer_photo(photo=FSInputFile(os.path.join(IMG_DIR, img)))
    manager.add_balance(user_id, BONUS_PER_WIN)
    await callback.answer(f"Поздравляем! Ты выиграл приз! +{BONUS_PER_WIN} монет")


@dp.message(Command("rating"))
async def handle_rating(message: Message):
    rating = manager.get_rating()
    if not rating:
        await message.answer("Пока никто не получил призов.")
        return
    text = "Рейтинг пользователей:\n"
    for i, (user_name, count) in enumerate(rating, 1):
        name = f"@{user_name}" if user_name else "Без имени"
        text += f"{i}. {name} — {count} приз(ов)\n"
    await message.answer(text)


@dp.message(Command("my_score"))
async def get_my_score(message: Message):
    user_id = message.chat.id
    won = {x[0] for x in manager.get_winners_img(user_id)}
    if not won:
        await message.answer("Ты пока не выиграл ни одного приза!")
        return

    collage_path = os.path.join(BASE_DIR, "collage.png")
    image_paths = [os.path.join(IMG_DIR, name) if name in won
                   else os.path.join(HIDDEN_IMG_DIR, name)
                   for name in os.listdir(IMG_DIR)]
    collage = create_collage(image_paths)
    cv2.imwrite(collage_path, collage)
    await message.answer_photo(photo=FSInputFile(collage_path))


@dp.message(Command("balance"))
async def handle_balance(message: Message):
    balance = manager.get_balance(message.chat.id)
    await message.answer(f"Твой баланс: {balance} монет.\n"
                         f"Потратить их можно в команде /buy_prize (стоимость {PRIZE_PRICE} монет).")


@dp.message(Command("buy_prize"))
async def buy_prize(message: Message):
    user_id = message.chat.id
    balance = manager.get_balance(user_id)
    if balance < PRIZE_PRICE:
        await message.answer(f"Недостаточно монет! Нужно {PRIZE_PRICE}, у тебя {balance}.")
        return
    prize = manager.get_random_prize()
    if not prize:
        await message.answer("Все призы уже разыграны!")
        return
    prize_id, img = prize
    manager.spend_balance(user_id, PRIZE_PRICE)
    manager.mark_prize_used(prize_id)
    manager.add_winner(user_id, prize_id)
    await message.answer_photo(photo=FSInputFile(os.path.join(IMG_DIR, img)),
                               caption="Бонусный приз за монеты!")


@dp.message(Command("set_interval"))
async def set_interval(message: Message):
    if message.from_user.id not in ADMIN_ID:
        await message.answer("Нет доступа.")
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Использование: /set_interval <мин_сек> <макс_сек>")
        return
    try:
        lo, hi = int(parts[1]), int(parts[2])
    except ValueError:
        await message.answer("Введи два числа, например: /set_interval 120 300")
        return
    if lo <= 0 or hi < lo:
        await message.answer("Минимум должен быть > 0 и не больше максимума.")
        return
    manager.set_setting("send_interval_min", lo)
    manager.set_setting("send_interval_max", hi)
    await message.answer(f"Интервал отправки установлен: {lo}–{hi} секунд.")


@dp.message(Command("add_prize"))
async def add_prize_start(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_ID:
        await message.answer("Нет доступа.")
        return
    await state.set_state(AddPrize.waiting_for_photo)
    await message.answer("Отправь картинку-приз.")


@dp.message(AddPrize.waiting_for_photo, F.photo)
async def add_prize_photo(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_ID:
        await state.clear()
        return
    file = await bot.get_file(message.photo[-1].file_id)
    ext = os.path.splitext(file.file_path)[1] or ".jpg"
    name = f"prize_{int(time.time())}{ext}"
    dest = os.path.join(IMG_DIR, name)
    data = await bot.download_file(file.file_path)
    with open(dest, "wb") as out:
        out.write(data.read())
    manager.add_prize([(name,)])
    hide_img(name)
    await state.clear()
    await message.answer(f"Приз добавлен: {name}")


@dp.message(Command("start"))
async def handle_start(message: Message):
    user_id = message.chat.id
    if user_id in manager.get_users():
        await message.answer("Ты уже зарегистрирован!")
    else:
        manager.add_user(user_id, message.from_user.username)
        await message.answer(
            "Привет! Добро пожаловать!\n"
            "Тебя успешно зарегистрировали!\n"
            "Каждый час тебе будут приходить новые картинки и у тебя будет шанс их получить!\n"
            "Точное время прихода — сюрприз, следи за новыми сообщениями!\n"
            "Для этого нужно быстрее всех нажать на кнопку 'Получить!'\n\n"
            "Только три первых пользователя получат картинку!)"
        )


async def send_message():
    prize = manager.get_random_prize()
    if not prize:
        return
    prize_id, img = prize[:2]
    manager.mark_prize_used(prize_id)
    hide_img(img)
    for user in manager.get_users():
        await bot.send_photo(
            chat_id=user,
            photo=FSInputFile(os.path.join(HIDDEN_IMG_DIR, img)),
            reply_markup=gen_markup(prize_id),
        )


async def scheduler():
    while True:
        await send_message()
        lo = int(manager.get_setting("send_interval_min", SEND_INTERVAL_MIN))
        hi = int(manager.get_setting("send_interval_max", SEND_INTERVAL_MAX))
        await asyncio.sleep(random.uniform(lo, hi))


async def main():
    manager.create_tables()
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())