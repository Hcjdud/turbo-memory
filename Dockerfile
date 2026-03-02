# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код бота
COPY main.py .
COPY keep_alive.py .

# Открываем порт (для Flask)
EXPOSE 8080

# Запускаем бота
CMD ["python", "main.py"]
