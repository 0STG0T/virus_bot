#!/usr/bin/env python3
"""
Скрипт для получения последнего кода от Telegram для +573116959470
"""
import asyncio
from telethon import TelegramClient
import os

# API credentials
API_ID = 21724019
API_HASH = "41c33dd2533d2dbe6fabe102831c8f208"

async def get_telegram_code():
    print("=" * 70)
    print("🔑 ПОЛУЧЕНИЕ КОДА ОТ TELEGRAM ДЛЯ +573116959470")
    print("=" * 70)
    print()

    # Путь к сессии
    session_file = "sessions/+573116959470"

    print(f"📁 Загружаю сессию: {session_file}.session")

    # Создаем клиент
    client = TelegramClient(
        session_file,
        API_ID,
        API_HASH,
        system_version="4.16.30-vxCUSTOM"
    )

    try:
        await client.connect()
        print("🔌 Подключен к Telegram")

        if not await client.is_user_authorized():
            print("❌ Сессия не авторизована!")
            return

        me = await client.get_me()
        print(f"✅ Авторизован как: {me.phone}")
        print()

        # Получаем сообщения от Telegram (777000)
        print("📨 Читаю сообщения от Telegram...")

        # ID официального Telegram - 777000
        telegram_id = 777000

        # Получаем последние 10 сообщений
        messages = await client.get_messages(telegram_id, limit=10)

        if not messages:
            print("❌ Нет сообщений от Telegram")
            return

        print()
        print("=" * 70)
        print("📩 ПОСЛЕДНИЕ СООБЩЕНИЯ ОТ TELEGRAM")
        print("=" * 70)
        print()

        for msg in messages:
            if msg.text:
                print(f"📅 Дата: {msg.date}")
                print(f"💬 Текст:")
                print(msg.text)
                print("-" * 70)

        # Последнее сообщение
        latest = messages[0]
        print()
        print("=" * 70)
        print("✅ ПОСЛЕДНЕЕ СООБЩЕНИЕ")
        print("=" * 70)
        print()
        print(latest.text)
        print()
        print("=" * 70)

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await client.disconnect()
        print()
        print("👋 Отключен от Telegram")

if __name__ == "__main__":
    asyncio.run(get_telegram_code())
