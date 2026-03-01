"""
Модуль для поддержания бота в живом состоянии на Render
Создает веб-сервер и пингует себя каждые 5 минут
"""
from flask import Flask
from threading import Thread
import requests
import time
import os
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Бот работает! Я жив!"

@app.route('/ping')
def ping():
    return "pong", 200

def run_http_server():
    """Запускает Flask сервер"""
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)

def self_ping(url, interval=300):
    """
    Пингует сам себя каждые interval секунд
    Чтобы Render не усыплял бота
    """
    while True:
        try:
            # Пингуем свой же сервер
            response = requests.get(f"{url}/ping")
            logger.info(f"✅ Self-ping успешен: {response.status_code}")
        except Exception as e:
            logger.error(f"❌ Ошибка self-ping: {e}")
        
        # Ждем interval секунд
        time.sleep(interval)

def start_ping(url, interval=300):
    """
    Запускает self-ping в отдельном потоке
    """
    ping_thread = Thread(target=self_ping, args=(url, interval))
    ping_thread.daemon = True
    ping_thread.start()
    logger.info(f"🔄 Self-ping запущен с интервалом {interval} сек")

def start_server(ping_url=None, ping_interval=300):
    """
    Запускает веб-сервер и self-ping
    """
    # Запускаем self-ping если указан URL
    if ping_url:
        start_ping(ping_url, ping_interval)
    
    # Запускаем Flask сервер
    run_http_server()

if __name__ == "__main__":
    # Для теста
    port = int(os.environ.get('PORT', 8080))
    url = f"http://localhost:{port}"
    start_server(url, 10)  # тест с интервалом 10 сек
