#!/usr/bin/env python3
"""
Telegram бот для временных почт
Версия для Python 3.14 и pydantic 2.12+
"""

import os
import sys
import asyncio
import logging
import random
import string
import imaplib
import email
import re
from datetime import datetime
from email.header import decode_header

from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import Response, PlainTextResponse
import uvicorn

# Загружаем переменные окружения
load_dotenv()

# ========== НАСТРОЙКИ ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ ==========
BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не найден в переменных окружения!")
    sys.exit(1)

EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
IMAP_SERVER = os.getenv('IMAP_SERVER', 'imap.mail.ru')
IMAP_PORT = int(os.getenv('IMAP_PORT', 993))

WEBHOOK_PATH = "/webhook"
WEBHOOK_URL = os.getenv('RENDER_EXTERNAL_URL') + WEBHOOK_PATH
PORT = int(os.getenv('PORT', 8000))

# ========== НАСТРОЙКА ЛОГИРОВАНИЯ ==========
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ========== ИНИЦИАЛИЗАЦИЯ БОТА ==========
# Для aiogram 3.17 parse_mode передаётся напрямую
bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.MARKDOWN)
dp = Dispatcher()

# Хранилище для временных email пользователей
user_emails = {}

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========

def generate_temp_email():
    """
    Генерирует случайный email на основе вашего домена
    """
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{random_str}@walle.ndjp.net"

def extract_verification_code(email_body):
    """
    Извлекает код подтверждения из текста письма
    """
    patterns = [
        r'\b(\d{3}-\d{3})\b',           # 666-263 (ваш формат)
        r'\b(\d{6})\b',                  # 123456
        r'\b(\d{4})\b',                   # 1234
        r'код[:\s]*(\d+)',                # код: 123456
        r'code[:\s]*(\d+)',               # code: 123456
        r'verification[:\s]*(\d+)',       # verification: 123456
        r'pin[:\s]*(\d+)',                 # pin: 123456
        r'otp[:\s]*(\d+)',                  # otp: 123456
    ]
    
    for pattern in patterns:
        match = re.search(pattern, email_body, re.IGNORECASE)
        if match:
            return match.group(1) if match.groups() else match.group(0)
    return None

async def check_email_for_code(user_id, temp_email):
    """
    Проверяет почту для конкретного пользователя
    Ищет код подтверждения
    """
    try:
        logger.info(f"🔍 Проверка почты для пользователя {user_id}, email: {temp_email}")
        
        # Подключаемся к IMAP серверу
        imap = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        imap.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        
        # Выбираем папку входящие
        imap.select('INBOX')
        
        # Ищем непрочитанные письма
        status, messages = imap.search(None, 'UNSEEN')
        
        if status != 'OK':
            imap.close()
            imap.logout()
            return None
        
        mail_ids = messages[0].split()
        logger.info(f"📬 Найдено {len(mail_ids)} непрочитанных писем")
        
        # Проверяем последние 20 писем
        for mail_id in reversed(mail_ids[-20:]):
            status, msg_data = imap.fetch(mail_id, '(RFC822)')
            if status != 'OK':
                continue
            
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            # Получаем тему
            subject = decode_header(msg['Subject'])[0][0]
            if isinstance(subject, bytes):
                subject = subject.decode(errors='ignore')
            
            # Получаем отправителя
            from_addr = msg.get('From', '')
            
            # Получаем текст письма
            body = ''
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == 'text/plain':
                        try:
                            body = part.get_payload(decode=True).decode(errors='ignore')
                            break
                        except:
                            continue
            else:
                body = msg.get_payload(decode=True).decode(errors='ignore')
            
            # Проверяем, относится ли письмо к нашему пользователю
            if temp_email in subject or temp_email in body:
                logger.info(f"📧 Найдено письмо для {temp_email}: {subject}")
                code = extract_verification_code(body)
                if code:
                    logger.info(f"✅ Найден код: {code}")
                    # Помечаем письмо как прочитанное
                    imap.store(mail_id, '+FLAGS', '\\Seen')
                    imap.close()
                    imap.logout()
                    return {
                        'code': code,
                        'from': from_addr,
                        'subject': subject
                    }
        
        imap.close()
        imap.logout()
        return None
        
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке почты: {e}")
        return None

# ========== ОБРАБОТЧИКИ КОМАНД ==========

@dp.message(Command('start'))
async def cmd_start(message: Message):
    """
    Обработчик команды /start
    """
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} запустил бота")
    
    welcome_text = (
        "👋 *Добро пожаловать в бота временных почт!*\n\n"
        "Этот бот поможет вам получать коды подтверждения "
        "на временный email.\n\n"
        "📋 *Доступные команды:*\n"
        "/new — создать новый временный email\n"
        "/check — проверить новые письма\n"
        "/help — показать эту справку\n\n"
        "🔐 Все данные защищены и не передаются третьим лицам."
    )
    
    builder = InlineKeyboardBuilder()
    builder.add(
        InlineKeyboardButton(text="📧 Новый email", callback_data="new_email"),
        InlineKeyboardButton(text="📨 Проверить", callback_data="check_mail")
    )
    builder.adjust(2)
    
    await message.answer(welcome_text, reply_markup=builder.as_markup())

@dp.message(Command('new'))
async def cmd_new_email(message: Message):
    """
    Создает новый временный email для пользователя
    """
    user_id = message.from_user.id
    
    # Генерируем новый email
    temp_email = generate_temp_email()
    
    # Сохраняем для пользователя
    user_emails[user_id] = {
        'email': temp_email,
        'created_at': datetime.now()
    }
    
    logger.info(f"Пользователь {user_id} создал email: {temp_email}")
    
    response = (
        f"✅ *Новый временный email создан!*\n\n"
        f"📧 *Адрес:* `{temp_email}`\n\n"
        f"📋 Используйте этот адрес для регистрации на сайтах.\n"
        f"Когда придет письмо с кодом, используйте команду /check"
    )
    
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📨 Проверить письма", callback_data="check_mail"))
    
    await message.answer(response, reply_markup=builder.as_markup())

@dp.message(Command('check'))
async def cmd_check_mail(message: Message):
    """
    Проверяет почту для пользователя
    """
    user_id = message.from_user.id
    logger.info(f"Пользователь {user_id} проверяет почту")
    
    if user_id not in user_emails:
        await message.answer(
            "❌ У вас нет активного временного email.\n"
            "Используйте /new чтобы создать новый."
        )
        return
    
    temp_email = user_emails[user_id]['email']
    
    await message.answer("🔍 *Проверяю почту...*\nЭто может занять несколько секунд.")
    
    # Проверяем почту
    result = await check_email_for_code(user_id, temp_email)
    
    if result:
        response = (
            f"✅ *Найдено письмо с кодом!*\n\n"
            f"🔢 *Код:* `{result['code']}`\n"
            f"📧 *От:* {result['from']}\n"
            f"📧 *Тема:* {result['subject']}\n\n"
            f"Код можно скопировать из сообщения выше."
        )
    else:
        response = "📭 *Новых писем с кодами не найдено.*\n\nПопробуйте позже или запросите код повторно на сайте."
    
    await message.answer(response)

@dp.message(Command('help'))
async def cmd_help(message: Message):
    """
    Показывает справку
    """
    help_text = (
        "📚 *Справка по командам:*\n\n"
        "/start — начать работу с ботом\n"
        "/new — создать новый временный email\n"
        "/check — проверить новые письма\n"
        "/help — показать эту справку\n\n"
        "*Как это работает:*\n"
        "1. Создайте временный email через /new\n"
        "2. Используйте его для регистрации на сайте\n"
        "3. Когда придет код, используйте /check\n"
        "4. Бот покажет код подтверждения\n\n"
        "🔒 *Безопасность:*\n"
        "Все данные хранятся только во время сессии "
        "и не передаются третьим лицам."
    )
    await message.answer(help_text)

# ========== ОБРАБОТЧИКИ КОЛЛБЭКОВ ==========

@dp.callback_query(lambda c: c.data == 'new_email')
async def callback_new_email(callback: CallbackQuery):
    """
    Обработчик нажатия на кнопку "Новый email"
    """
    await callback.answer()
    await cmd_new_email(callback.message)

@dp.callback_query(lambda c: c.data == 'check_mail')
async def callback_check_mail(callback: CallbackQuery):
    """
    Обработчик нажатия на кнопку "Проверить"
    """
    await callback.answer()
    await cmd_check_mail(callback.message)

# ========== WEBHOOK ==========

async def webhook_handler(request: Request) -> Response:
    """
    Принимает обновления от Telegram
    """
    try:
        update_data = await request.json()
        await dp.feed_update(bot, update_data)
        return Response()
    except Exception as e:
        logger.error(f"Ошибка webhook: {e}")
        return Response(status_code=500)

async def health_check(request: Request) -> PlainTextResponse:
    """
    Для health check Render
    """
    return PlainTextResponse("OK")

async def setup_webhook():
    """
    Устанавливает webhook при старте
    """
    await bot.delete_webhook()
    await bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"✅ Webhook установлен на {WEBHOOK_URL}")

async def on_startup():
    """
    Действия при запуске
    """
    logger.info("=" * 50)
    logger.info("🚀 Бот запускается...")
    logger.info(f"📧 Почтовый сервер: {IMAP_SERVER}")
    logger.info(f"📧 Email: {EMAIL_ADDRESS}")
    logger.info("=" * 50)
    await setup_webhook()

async def on_shutdown():
    """
    Действия при остановке
    """
    logger.info("🛑 Бот останавливается...")
    await bot.session.close()

async def main():
    """
    Главная функция запуска
    """
    # Создаем Starlette приложение
    app = Starlette(routes=[
        Route(WEBHOOK_PATH, webhook_handler, methods=["POST"]),
        Route("/healthcheck", health_check, methods=["GET"]),
    ])

    # Запускаем веб-сервер
    config = uvicorn.Config(
        app, 
        host="0.0.0.0", 
        port=PORT, 
        log_level="info",
        timeout_keep_alive=5
    )
    server = uvicorn.Server(config)
    
    # Выполняем действия при запуске
    await on_startup()
    
    # Запускаем сервер
    await server.serve()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
