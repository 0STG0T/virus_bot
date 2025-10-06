#!/usr/bin/env python3
"""
Тестовый скрипт для проверки WebApp логики
"""
import asyncio
import sys
import os
from telethon import TelegramClient
from webapp_auth import WebAppAuth
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_webapp():
    """Тестируем WebApp клик"""

    # Берем первую сессию
    session_file = "sessions/+573181322034.session"
    session_name = "+573181322034"

    logger.info(f"🔧 Загружаю сессию: {session_file}")

    # API credentials (замени на свои если нужно)
    api_id = 21724019
    api_hash = "41c33dd533d2dbe6fabe102831c8f208"

    client = TelegramClient(
        session_file.replace('.session', ''),
        api_id,
        api_hash,
        system_version="4.16.30-vxCUSTOM"
    )

    try:
        logger.info(f"🔌 Подключаюсь к Telegram...")
        await client.connect()

        if not await client.is_user_authorized():
            logger.error(f"❌ Сессия не авторизована!")
            return

        logger.info(f"✅ Сессия авторизована")

        # Создаем WebAppAuth
        auth = WebAppAuth(client, session_name)

        # Тестовая ссылка (замени на реальную из логов)
        test_url = "https://t.me/jet_diceclub_bot/dapp?startapp=cfSbzBT4KPk"

        logger.info(f"\n{'='*70}")
        logger.info(f"🔗 ТЕСТ КЛИКА ПО WEBAPP")
        logger.info(f"🌐 URL: {test_url}")
        logger.info(f"{'='*70}\n")

        # Кликаем
        success, init_data = await auth.click_test_spin_url(test_url)

        logger.info(f"\n{'='*70}")
        logger.info(f"📊 РЕЗУЛЬТАТ: {'✅ Успех' if success else '❌ Неудача'}")
        if init_data:
            logger.info(f"📝 INIT_DATA: {init_data[:100]}...")
        else:
            logger.info(f"ℹ️ INIT_DATA: Не получен")
        logger.info(f"{'='*70}\n")

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
    finally:
        await client.disconnect()
        logger.info(f"👋 Отключен от Telegram")

if __name__ == "__main__":
    asyncio.run(test_webapp())
