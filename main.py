#!/usr/bin/env python3
"""
Virus Bot Manager - Автоматизация фри спинов в @virus_play_bot

Основные функции:
- Автоматический прокрут ежедневных фри спинов
- Выполнение условий для получения спинов (рефки, подписки)
- Обработка наград и автопродажа предметов
- Управление через Telegram бота
- Поддержка 500+ аккаунтов

Использование:
    python main.py
"""

import asyncio
import logging
import os
import sys
from telegram_bot import VirusBotManager

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,  # Включаем DEBUG для отладки инвентаря
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('virus_bot.log', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def print_banner():
    """Выводит красивый баннер"""
    banner = """
    ╔════════════════════════════════════════════════════════════════╗
    ║                     VIRUS BOT MANAGER                         ║
    ║                Автоматизация @virus_play_bot                   ║
    ║                                                                ║
    ║  ⚡ Автоматический прокрут фри спинов                          ║
    ║  🎯 Выполнение условий (рефки, подписки)                      ║
    ║  💰 Обработка наград и автопродажа                            ║
    ║  🤖 Управление через Telegram бота                            ║
    ║  📊 Поддержка 500+ аккаунтов                                  ║
    ╚════════════════════════════════════════════════════════════════╝
    """
    print(banner)

def check_requirements():
    """Проверяет наличие необходимых файлов и папок"""
    sessions_dir = "./sessions"

    if not os.path.exists(sessions_dir):
        print(f"📁 Создаю папку {sessions_dir}")
        os.makedirs(sessions_dir)

    session_files = [f for f in os.listdir(sessions_dir) if f.endswith('.session')]
    print(f"📊 Найдено {len(session_files)} сессий в папке {sessions_dir}")

    if len(session_files) == 0:
        print("⚠️  Сессии не найдены. Добавьте .session файлы в папку sessions/")
        print("📋 Формат: имя_аккаунта.session")

    return len(session_files) > 0

async def main():
    """Главная функция"""
    print_banner()

    # Проверяем требования
    if not check_requirements():
        print("❌ Для работы необходимы сессии в папке sessions/")
        input("Нажмите Enter для выхода...")
        return

    # Запрашиваем токен бота
    print("\n🔑 Введите токен Telegram бота для управления:")
    print("   (получите токен у @BotFather)")

    bot_token = input("🤖 Токен бота: ").strip()

    if not bot_token:
        print("❌ Токен не может быть пустым")
        input("Нажмите Enter для выхода...")
        return

    if not bot_token.count(':') == 1 or len(bot_token) < 40:
        print("❌ Неверный формат токена")
        input("Нажмите Enter для выхода...")
        return

    # Создаем и запускаем бота
    bot_manager = VirusBotManager()

    try:
        print("\n🔧 Настройка бота...")
        await bot_manager.setup(bot_token)

        print("✅ Бот настроен успешно!")
        print("🚀 Запуск бота...")
        print("📱 Найдите своего бота в Telegram и нажмите /start")
        print("🛑 Для остановки нажмите Ctrl+C")

        await bot_manager.run()

    except KeyboardInterrupt:
        print("\n🛑 Получен сигнал остановки...")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
    finally:
        print("🔄 Остановка бота...")
        await bot_manager.stop()
        print("✅ Бот остановлен")
        print("👋 До свидания!")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Работа завершена пользователем")
    except Exception as e:
        print(f"❌ Ошибка запуска: {e}")
        input("Нажмите Enter для выхода...")