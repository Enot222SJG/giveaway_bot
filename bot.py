import asyncio
import os
import cv2

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import API_TOKEN
from logic import BASE_DIR, IMG_DIR, HIDDEN_IMG_DIR, DATABASE, DatabaseManager, create_collage, hide_img

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

DB_PATH = os.path.join(BASE_DIR, DATABASE)
manager = DatabaseManager(DB_PATH)


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
    await callback.answer("Поздравляем! Ты выиграл приз!")


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
        await asyncio.sleep(60)


async def main():
    manager.create_tables()
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())