#!/usr/bin/env python3
"""
Тест подписки на канал viruspub
"""
import asyncio
from telethon import TelegramClient
from webapp_auth import WebAppAuth
from virus_api import VirusAPI
from spin_worker import SpinWorker
from session_manager import SessionManager
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    session_name = "+573116959470"  # Аккаунт из логов
    session_file = f"sessions/{session_name}"

    api_id = 21724019
    api_hash = "41c33dd2533d2dbe6fabe102831c8f208"

    client = TelegramClient(
        session_file,
        api_id,
        api_hash,
        system_version="4.16.30-vxCUSTOM"
    )

    try:
        logger.info("🔌 Подключаюсь к Telegram...")
        await client.connect()

        if not await client.is_user_authorized():
            logger.error("❌ Сессия не авторизована!")
            return

        logger.info("✅ Авторизован")

        # Создаем SessionManager и SpinWorker
        session_manager = SessionManager()
        worker = SpinWorker(session_manager)

        # Пробуем выполнить спин
        logger.info("\n" + "="*70)
        logger.info("🎰 Выполняю спин через perform_single_spin")
        logger.info("="*70)

        result = await worker.perform_single_spin(session_name)

        logger.info("\n" + "="*70)
        logger.info("📊 РЕЗУЛЬТАТ")
        logger.info("="*70)
        logger.info(f"Success: {result['success']}")
        logger.info(f"Message: {result['message']}")
        logger.info(f"Reward: {result.get('reward')}")
        logger.info("="*70)

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)
    finally:
        await client.disconnect()
        logger.info("👋 Отключен")

if __name__ == "__main__":
    asyncio.run(main())
