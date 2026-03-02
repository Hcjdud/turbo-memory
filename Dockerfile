# Используем официальный образ с предустановленным Rust
FROM rust:1.81-slim-bookworm AS builder

# Устанавливаем Python и зависимости
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Создаем виртуальное окружение
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем pydantic-core с компиляцией
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir pydantic==2.12.2 --no-binary pydantic-core

# Устанавливаем остальные зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Финальный образ
FROM python:3.11-slim

# Копируем установленные пакеты из builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Копируем код бота
COPY main.py .

# Открываем порт
EXPOSE 8080

# Запускаем бота
CMD ["python", "main.py"]
