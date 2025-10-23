"""
Скрипт для автоматической реакции эмодзи на пост в Telegram канале.
Использует все сессии из папки sessions/ для отправки реакции.
"""

import asyncio
import os
import logging
from telethon import TelegramClient
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import ReactionEmoji
from config import API_ID, API_HASH

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация
CHANNEL_USERNAME = "pelikangik"  # Канал
MESSAGE_ID = 275  # ID сообщения
EMOJI = "💋"  # Эмодзи губ (красные губы)
SESSIONS_DIR = "sessions"
DELAY_BETWEEN_REACTIONS = 2  # Задержка между реакциями (секунды)


async def send_reaction(session_file: str) -> bool:
    """
    Отправляет реакцию на пост от одной сессии.

    Args:
        session_file: Путь к .session файлу

    Returns:
        True если успешно, False если ошибка
    """
    session_name = os.path.splitext(os.path.basename(session_file))[0]
    session_path = os.path.join(SESSIONS_DIR, session_name)

    client = None
    try:
        # Создаем клиент
        client = TelegramClient(session_path, API_ID, API_HASH)
        await client.connect()

        if not await client.is_user_authorized():
            logger.warning(f"❌ {session_name}: Сессия не авторизована")
            return False

        # Отправляем реакцию
        await client(SendReactionRequest(
            peer=CHANNEL_USERNAME,
            msg_id=MESSAGE_ID,
            reaction=[ReactionEmoji(emoticon=EMOJI)]
        ))

        logger.info(f"✅ {session_name}: Реакция {EMOJI} отправлена")
        return True

    except Exception as e:
        logger.error(f"❌ {session_name}: Ошибка - {e}")
        return False

    finally:
        if client:
            await client.disconnect()


async def main():
    """
    Основная функция: проходит по всем сессиям и отправляет реакции.
    """
    # Проверяем существование папки сессий
    if not os.path.exists(SESSIONS_DIR):
        logger.error(f"❌ Папка {SESSIONS_DIR}/ не найдена!")
        return

    # Получаем список всех .session файлов
    session_files = []
    for file in os.listdir(SESSIONS_DIR):
        if file.lower().endswith('.session'):
            session_files.append(file)

    if not session_files:
        logger.error(f"❌ Не найдено .session файлов в папке {SESSIONS_DIR}/")
        return

    logger.info(f"📊 Найдено сессий: {len(session_files)}")
    logger.info(f"🎯 Канал: @{CHANNEL_USERNAME}")
    logger.info(f"📨 Сообщение ID: {MESSAGE_ID}")
    logger.info(f"❤️ Эмодзи: {EMOJI}")
    logger.info(f"⏱️ Задержка между реакциями: {DELAY_BETWEEN_REACTIONS}s")
    logger.info("=" * 60)

    # Счетчики
    success_count = 0
    error_count = 0

    # Отправляем реакции от всех сессий
    for i, session_file in enumerate(session_files, 1):
        logger.info(f"[{i}/{len(session_files)}] Обрабатываю {session_file}...")

        success = await send_reaction(session_file)

        if success:
            success_count += 1
        else:
            error_count += 1

        # Задержка между реакциями
        if i < len(session_files):
            await asyncio.sleep(DELAY_BETWEEN_REACTIONS)

    # Итоговая статистика
    logger.info("=" * 60)
    logger.info(f"✅ Успешно: {success_count}")
    logger.info(f"❌ Ошибки: {error_count}")
    logger.info(f"📊 Всего обработано: {len(session_files)}")
    logger.info("🎉 Готово!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("\n⚠️ Прервано пользователем")
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}")
