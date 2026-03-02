#!/usr/bin/env python3
import os
import sys
import asyncio
import logging
import imaplib
import email
import re
import random
import string
from datetime import datetime
from email.header import decode_header

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dotenv import load_dotenv
from flask import Flask
from threading import Thread
import requests
import time

load_dotenv()

# Настройки
BOT_TOKEN = os.getenv('BOT_TOKEN')
EMAIL_ADDRESS = os.getenv('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
IMAP_SERVER = os.getenv('IMAP_SERVER', 'imap.mail.ru')
IMAP_PORT = int(os.getenv('IMAP_PORT', 993))

if not BOT_TOKEN or not EMAIL_PASSWORD:
    print("❌ Ошибка: BOT_TOKEN и EMAIL_PASSWORD обязательны")
    sys.exit(1)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Бот
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()
user_emails = {}

# Keep-alive Flask
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Бот работает!"

@app.route('/ping')
def ping():
    return "pong", 200

def run_keep_alive():
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def self_ping():
    url = os.getenv('RENDER_URL', 'http://localhost:8080')
    while True:
        try:
            requests.get(f"{url}/ping", timeout=5)
            logger.info("✅ Self-ping успешен")
        except Exception as e:
            logger.error(f"❌ Self-ping ошибка: {e}")
        time.sleep(240)  # 4 минуты

def generate_temp_email():
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"{random_str}@walle.ndjp.net"

def extract_code(text):
    patterns = [
        r'\b(\d{3}-\d{3})\b',
        r'\b(\d{6})\b',
        r'код[:\s]*(\d+)',
        r'code[:\s]*(\d+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1) if match.groups() else match.group(0)
    return None

async def check_mail(user_id, temp_email):
    try:
        imap = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        imap.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        imap.select('INBOX')
        
        status, messages = imap.search(None, 'UNSEEN')
        if status != 'OK':
            imap.close()
            imap.logout()
            return None
        
        for mail_id in reversed(messages[0].split()[-10:]):
            status, msg_data = imap.fetch(mail_id, '(RFC822)')
            if status != 'OK':
                continue
            
            msg = email.message_from_bytes(msg_data[0][1])
            subject = decode_header(msg['Subject'])[0][0]
            if isinstance(subject, bytes):
                subject = subject.decode(errors='ignore')
            
            from_addr = msg.get('From', '')
            
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
            
            if temp_email in subject or temp_email in body:
                code = extract_code(body)
                if code:
                    imap.store(mail_id, '+FLAGS', '\\Seen')
                    imap.close()
                    imap.logout()
                    return {'code': code, 'from': from_addr, 'subject': subject}
        
        imap.close()
        imap.logout()
        return None
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        return None

@dp.message(Command('start'))
async def cmd_start(message: Message):
    welcome = "👋 *Бот временных почт*\n\n/new — создать email\n/check — проверить код"
    keyboard = InlineKeyboardBuilder()
    keyboard.add(
        InlineKeyboardButton(text="📧 Новый email", callback_data="new"),
        InlineKeyboardButton(text="📨 Проверить", callback_data="check")
    )
    await message.answer(welcome, reply_markup=keyboard.as_markup())

@dp.message(Command('new'))
async def cmd_new(message: Message):
    user_id = message.from_user.id
    email = generate_temp_email()
    user_emails[user_id] = {'email': email, 'created': datetime.now()}
    await message.answer(f"✅ *Ваш email:*\n`{email}`\n\nИспользуйте /check когда придет код")

@dp.message(Command('check'))
async def cmd_check(message: Message):
    user_id = message.from_user.id
    if user_id not in user_emails:
        await message.answer("❌ Сначала создайте email через /new")
        return
    
    await message.answer("🔍 *Проверяю почту...*")
    result = await check_mail(user_id, user_emails[user_id]['email'])
    
    if result:
        await message.answer(f"✅ *Код:* `{result['code']}`")
    else:
        await message.answer("📭 Писем с кодами не найдено")

@dp.callback_query(lambda c: c.data == 'new')
async def callback_new(callback):
    await callback.answer()
    await cmd_new(callback.message)

@dp.callback_query(lambda c: c.data == 'check')
async def callback_check(callback):
    await callback.answer()
    await cmd_check(callback.message)

async def main():
    # Запускаем keep-alive в фоне
    Thread(target=self_ping, daemon=True).start()
    Thread(target=run_keep_alive, daemon=True).start()
    
    logger.info("🚀 Бот запущен")
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
