import os
from typing import Dict, List, Optional

BOT_TOKEN: Optional[str] = None

# Telegram API credentials
API_ID = 21724019
API_HASH = "41c33dd2533d2dbe6fabe102831c8f208"

VIRUS_BOT_USERNAME = "@virus_play_bot"
WEBAPP_URL = "https://virusgift.pro"
GRAPHQL_URL = "https://virusgift.pro/api/graphql/query"
ROULETTE_URL = "https://virusgift.pro/roulette"

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
    'Accept': 'application/json',
    'Content-Type': 'application/json',
    'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'cross-site'
}


HIGH_VALUE_THRESHOLD = 200

SESSIONS_DIR = "./sessions"
LOG_CHAT_ID: Optional[int] = None

# Конфигурация для работы с 500+ аккаунтами (МАКСИМАЛЬНО ОПТИМИЗИРОВАНО)
MAX_CONCURRENT_SESSIONS = 100  # Увеличено для максимальной производительности
REQUESTS_PER_MINUTE = 60  # Увеличено для быстрой обработки
DELAY_BETWEEN_ACCOUNTS = 0.3  # Минимальная задержка для скорости

# Дополнительные таймауты для массовой обработки (МАКСИМАЛЬНО ОПТИМИЗИРОВАНЫ)
HTTP_REQUEST_TIMEOUT = 20  # Сокращено для быстрого отклика
TELEGRAM_CONNECT_TIMEOUT = 20  # Сокращено для быстрого отклика
MIN_REQUEST_INTERVAL = 0.5  # Минимальный интервал для максимальной скорости
SUBSCRIPTION_DELAY = 1  # Сокращено для быстроты
PRIZE_ACTIVATION_DELAY = 0.2  # Минимальная задержка
ONBOARDING_RETRY_DELAY = 0.5  # Сокращено для быстроты

# Настройки автоматических платных спинов
AUTO_SPIN_THRESHOLD = 200  # Минимальный баланс звезд для автоспина
AUTO_SPIN_CHECK_INTERVAL = 300  # Интервал проверки баланса (5 минут)
AUTO_SPIN_ENABLED = True  # Включить автоматические платные спины

# Настройки автоматической продажи подарков
AUTO_GIFT_EXCHANGE_ENABLED = True  # Включить автопродажу подарков
AUTO_GIFT_EXCHANGE_THRESHOLD = 200  # Автопродажа подарков ≤200 звезд
GIFT_EXCHANGE_AFTER_SPIN = True  # Продавать подарки после каждого спина
GIFT_EXCHANGE_ON_BALANCE_CHECK = True  # Продавать подарки при проверке баланса

# Настройки производительности (МАКСИМАЛЬНО ОПТИМИЗИРОВАНО)
BATCH_INVENTORY_REQUESTS = True  # Батчинг запросов инвентаря
HTTP_CONNECTION_POOL_SIZE = 100  # Увеличен размер пула для производительности
REDUCED_LOGGING_MODE = False  # Уменьшенное логирование для производительности
VALIDATION_SEMAPHORE_LIMIT = 15  # Увеличено для параллельной валидации
PERFORMANCE_MODE = True  # Режим максимальной производительности

# Настройки Telegram Bot API для стабильности
TELEGRAM_READ_TIMEOUT = 60.0  # Время чтения ответов от Telegram API
TELEGRAM_WRITE_TIMEOUT = 60.0  # Время отправки запросов к Telegram API
TELEGRAM_CONNECT_TIMEOUT = 60.0  # Время подключения к Telegram API
TELEGRAM_POOL_TIMEOUT = 30.0  # Время ожидания соединения из пула