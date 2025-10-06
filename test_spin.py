#!/usr/bin/env python3
"""
Тестовый скрипт для проверки фри спина с обработкой testSpin клика
"""
import asyncio
import sys
from spin_worker import SpinWorker
from session_manager import SessionManager
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_spin():
    """Тестируем фри спин с обработкой testSpin"""

    # Берем первую сессию
    session_file = "sessions/+573181322034.session"
    session_name = "+573181322034"

    logger.info(f"🎰 Тестирую фри спин для сессии: {session_name}")
    logger.info(f"=" * 70)

    # Создаем SessionManager
    session_manager = SessionManager()

    worker = SpinWorker(session_manager)

    try:
        result = await worker.perform_single_spin(session_name)

        logger.info(f"\n{'=' * 70}")
        logger.info(f"📊 РЕЗУЛЬТАТ СПИНА")
        logger.info(f"={'=' * 70}")
        logger.info(f"✅ Успех: {result['success']}")
        logger.info(f"📝 Сообщение: {result['message']}")
        if result.get('prize'):
            logger.info(f"🎁 Приз: {result['prize']}")
        logger.info(f"{'=' * 70}\n")

    except Exception as e:
        logger.error(f"❌ Ошибка: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_spin())
