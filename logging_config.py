#!/usr/bin/env python3
"""
Конфигурация логирования для проекта (ОПТИМИЗИРОВАНО ДЛЯ ПРОИЗВОДИТЕЛЬНОСТИ)
Настраивает отдельные логи для GraphQL запросов и общей работы системы
"""

import logging
import logging.handlers
import os
from datetime import datetime

def setup_logging():
    """Настраивает логирование для всего проекта с фокусом на производительность"""

    # Проверяем режим производительности
    try:
        from config import PERFORMANCE_MODE, REDUCED_LOGGING_MODE
    except ImportError:
        PERFORMANCE_MODE = False
        REDUCED_LOGGING_MODE = False

    # Создаем папку для логов если её нет
    logs_dir = "./logs"
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir)

    # Получаем текущую дату для имен файлов
    date_str = datetime.now().strftime("%Y-%m-%d")

    # === ОБЩЕЕ ЛОГИРОВАНИЕ (ОПТИМИЗИРОВАНО) ===

    # Основной логгер
    root_logger = logging.getLogger()

    # В режиме производительности только WARNING+ для минимизации нагрузки
    if PERFORMANCE_MODE:
        root_logger.setLevel(logging.WARNING)
    else:
        root_logger.setLevel(logging.INFO)

    # Убираем старые хэндлеры если есть
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Общий форматтер
    general_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Хэндлер для общих логов в файл
    general_file_handler = logging.FileHandler(
        f'{logs_dir}/general_{date_str}.log',
        encoding='utf-8'
    )
    general_file_handler.setLevel(logging.INFO)
    general_file_handler.setFormatter(general_formatter)
    root_logger.addHandler(general_file_handler)

    # Хэндлер для консоли (менее подробный)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(levelname)s - %(name)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # === GRAPHQL ЛОГИРОВАНИЕ (УСЛОВНОЕ ДЛЯ ПРОИЗВОДИТЕЛЬНОСТИ) ===

    # Специальный логгер для GraphQL запросов
    graphql_logger = logging.getLogger('graphql_requests')

    # В режиме производительности отключаем детальное GraphQL логирование
    if PERFORMANCE_MODE:
        graphql_logger.setLevel(logging.CRITICAL)  # Практически отключено
    else:
        graphql_logger.setLevel(logging.INFO)

    graphql_logger.propagate = False  # Не передавать в родительский логгер

    # Подробный форматтер для GraphQL (только если логирование включено)
    if not PERFORMANCE_MODE:
        graphql_formatter = logging.Formatter(
            '%(asctime)s - GraphQL - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        # Хэндлер для GraphQL логов в отдельный файл
        graphql_file_handler = logging.FileHandler(
            f'{logs_dir}/graphql_{date_str}.log',
            encoding='utf-8'
        )
        graphql_file_handler.setLevel(logging.INFO)
        graphql_file_handler.setFormatter(graphql_formatter)
        graphql_logger.addHandler(graphql_file_handler)

    # === РОТАЦИЯ ЛОГОВ ===

    # Настраиваем ротацию для больших логов (для production)
    rotating_handler = logging.handlers.RotatingFileHandler(
        f'{logs_dir}/virus_bot.log',
        maxBytes=50*1024*1024,  # 50MB
        backupCount=5,
        encoding='utf-8'
    )
    rotating_handler.setLevel(logging.INFO)
    rotating_handler.setFormatter(general_formatter)
    root_logger.addHandler(rotating_handler)

    # GraphQL ротация (только если не в режиме производительности)
    if not PERFORMANCE_MODE:
        graphql_rotating_handler = logging.handlers.RotatingFileHandler(
            f'{logs_dir}/graphql_requests.log',
            maxBytes=100*1024*1024,  # 100MB (GraphQL логи больше)
            backupCount=3,
            encoding='utf-8'
        )
        graphql_rotating_handler.setLevel(logging.INFO)
        graphql_rotating_handler.setFormatter(graphql_formatter)
        graphql_logger.addHandler(graphql_rotating_handler)

    # === ДЕБАГ ЛОГИРОВАНИЕ (ТОЛЬКО В ОБЫЧНОМ РЕЖИМЕ) ===

    # Отдельный файл для debug логов (только если не в режиме производительности)
    if not PERFORMANCE_MODE:
        debug_handler = logging.FileHandler(
            f'{logs_dir}/debug_{date_str}.log',
            encoding='utf-8'
        )
        debug_handler.setLevel(logging.DEBUG)
        debug_formatter = logging.Formatter(
            '%(asctime)s - %(name)s:%(lineno)d - %(levelname)s - %(message)s'
        )
        debug_handler.setFormatter(debug_formatter)

        # Добавляем debug хэндлер только к определенным логгерам
        logging.getLogger('virus_api').addHandler(debug_handler)
        logging.getLogger('spin_worker').addHandler(debug_handler)

    # В режиме производительности выводим информацию
    if PERFORMANCE_MODE:
        print("🚀 PERFORMANCE MODE ACTIVATED - Минимальное логирование для максимальной скорости")
    else:
        print("📊 NORMAL MODE - Полное логирование для диагностики")

    # Устанавливаем уровни для конкретных модулей
    logging.getLogger('virus_api').setLevel(logging.DEBUG)
    logging.getLogger('spin_worker').setLevel(logging.INFO)
    logging.getLogger('telegram_bot').setLevel(logging.INFO)

    # Уменьшаем болтливость сторонних библиотек
    logging.getLogger('aiohttp').setLevel(logging.WARNING)
    logging.getLogger('telethon').setLevel(logging.WARNING)
    logging.getLogger('telegram').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)

    print(f"📝 Логирование настроено:")
    print(f"   • Общие логи: {logs_dir}/general_{date_str}.log")
    print(f"   • GraphQL логи: {logs_dir}/graphql_{date_str}.log")
    print(f"   • Debug логи: {logs_dir}/debug_{date_str}.log")
    print(f"   • Ротирующие логи: {logs_dir}/virus_bot.log + {logs_dir}/graphql_requests.log")

def get_graphql_logger():
    """Возвращает настроенный GraphQL логгер"""
    return logging.getLogger('graphql_requests')

def get_api_logger():
    """Возвращает настроенный API логгер"""
    return logging.getLogger('virus_api')

if __name__ == "__main__":
    # Тест настройки логирования
    setup_logging()

    logger = logging.getLogger(__name__)
    graphql_logger = get_graphql_logger()

    logger.info("Тестовое сообщение в общий лог")
    graphql_logger.info("Тестовое сообщение в GraphQL лог")

    print("✅ Тест логирования завершен, проверьте папку logs/")