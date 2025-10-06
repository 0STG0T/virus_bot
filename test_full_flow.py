#!/usr/bin/env python3
"""
Полный тест фри спина с testSpin обработкой
"""
import asyncio
from telethon import TelegramClient
from webapp_auth import WebAppAuth
from virus_api import VirusAPI
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def main():
    session_name = "+573181344870"  # Новый аккаунт для теста
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

        # Получаем auth data
        auth = WebAppAuth(client, session_name)
        logger.info("🔐 Получаю auth данные...")
        auth_data = await auth.get_webapp_data()

        if not auth_data:
            logger.error("❌ Не удалось получить auth_data")
            return

        logger.info(f"✅ Auth data получен: {auth_data[:50]}...")

        # Создаем API клиент
        api = VirusAPI(session_name)
        await api.set_auth_data(auth_data)

        # Пробуем спин
        logger.info("\n" + "="*70)
        logger.info("🎰 ПОПЫТКА #1: Первый спин")
        logger.info("="*70)

        success, message, reward = await api.perform_spin()
        logger.info(f"📊 Результат: success={success}, message='{message}'")
        logger.info(f"📦 Reward type: {type(reward)}, reward: {reward}")

        print(f"\n=== DEBUG ===")
        print(f"success: {success}")
        print(f"message: '{message}'")
        print(f"reward: {reward}")
        print(f"Проверка строки: {'Требуется клик по тестовой ссылке' in message}")
        print(f"=== END DEBUG ===\n")

        if not success and "Требуется клик по тестовой ссылке" in message:
            logger.info("\n" + "="*70)
            logger.info("🔗 Обнаружена ошибка testSpin - выполняю клик")
            logger.info("="*70)

            test_url = reward.get('link') if isinstance(reward, dict) else None
            if test_url:
                logger.info(f"🌐 URL: {test_url}")

                # Кликаем
                click_success, init_data = await auth.click_test_spin_url(test_url)
                logger.info(f"📊 Клик: success={click_success}")

                if init_data:
                    logger.info(f"📝 Init data (50 символов): {init_data[:50]}...")

                if click_success:
                    logger.info("\n" + "="*70)
                    logger.info("🎰 ПОПЫТКА #2: Повторный спин после клика")
                    logger.info("="*70)

                    await asyncio.sleep(3)
                    success2, message2, reward2 = await api.perform_spin()
                    logger.info(f"📊 Результат: success={success2}, message='{message2}'")

                    if success2:
                        logger.info(f"\n🎉 УСПЕХ! Приз: {reward2}")
                    else:
                        logger.error(f"\n❌ Все еще ошибка: {message2}")
            else:
                logger.error("❌ Нет ссылки в reward")

        elif success:
            logger.info(f"\n🎉 УСПЕХ С ПЕРВОГО РАЗА! Приз: {reward}")

        await api.close_session()

    finally:
        await client.disconnect()
        logger.info("👋 Отключен")

if __name__ == "__main__":
    asyncio.run(main())
