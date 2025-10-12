# Multi-stage build для уменьшения размера образа
FROM python:3.11-slim as builder

# Установка зависимостей для сборки
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# Создание виртуального окружения
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Копирование и установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Финальный образ
FROM python:3.11-slim

# Установка минимальных системных зависимостей
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Копирование виртуального окружения из builder
COPY --from=builder /opt/venv /opt/venv

# Активация виртуального окружения
ENV PATH="/opt/venv/bin:$PATH"

# Создание рабочей директории
WORKDIR /app

# Создание директорий для данных
RUN mkdir -p /app/sessions /app/logs

# Копирование исходного кода
COPY *.py /app/
COPY config.py /app/
COPY logging_config.py /app/

# Создание непривилегированного пользователя
RUN useradd -m -u 1000 botuser && \
    chown -R botuser:botuser /app

# Переключение на непривилегированного пользователя
USER botuser

# Переменные окружения (будут переопределены в docker-compose.yml)
ENV VIRUS_BOT_TOKEN="" \
    LOG_CHAT_ID="" \
    API_ID="" \
    API_HASH="" \
    PYTHONUNBUFFERED=1

# Healthcheck для мониторинга состояния контейнера
HEALTHCHECK --interval=60s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import os; exit(0 if os.path.exists('/app/sessions') else 1)"

# Запуск бота
CMD ["python", "main.py"]
