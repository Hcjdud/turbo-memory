# Используем официальный образ Python
FROM python:3.11-slim

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем только requirements сначала (для кэширования)
COPY requirements.txt .

# Устанавливаем переменные окружения для Rust/Cargo в пользовательскую директорию
ENV CARGO_HOME=/app/.cargo
ENV RUSTUP_HOME=/app/.rustup
ENV PATH="/app/.cargo/bin:${PATH}"

# Устанавливаем системные зависимости, включая Rust
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && . $CARGO_HOME/env

# Устанавливаем Python зависимости (теперь Rust может писать в /app/.cargo)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Копируем остальной код
COPY main.py .
COPY keep_alive.py .

# Открываем порт
EXPOSE 8080

# Запускаем бота
CMD ["python", "main.py"]
