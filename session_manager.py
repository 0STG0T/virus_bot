import os
import asyncio
from telethon import TelegramClient
from typing import List, Dict, Optional, Tuple
import logging
import config
from datetime import datetime
import time

logger = logging.getLogger(__name__)

class SessionManager:
    def __init__(self):
        self.clients: Dict[str, TelegramClient] = {}
        self.sessions_data: Dict[str, str] = {}

        # Семафор для предотвращения одновременного доступа к SQLite базам
        self._db_access_semaphore = asyncio.Semaphore(10)  # Увеличено для скорости

    async def load_sessions(self) -> int:
        if not os.path.exists(config.SESSIONS_DIR):
            os.makedirs(config.SESSIONS_DIR)
            return 0

        session_files = [f for f in os.listdir(config.SESSIONS_DIR) if f.lower().endswith('.session')]
        loaded_count = 0

        for session_file in session_files:
            session_path = os.path.join(config.SESSIONS_DIR, session_file)
            session_name = session_file[:-8] if session_file.lower().endswith('.session') else session_file

            try:
                # Для .session файлов Telethon используем путь к файлу напрямую
                if os.path.getsize(session_path) > 0:
                    self.sessions_data[session_name] = session_path
                    loaded_count += 1
                    logger.info(f"Загружена сессия: {session_name}")

            except Exception as e:
                logger.error(f"Ошибка загрузки сессии {session_file}: {e}")

        return loaded_count

    async def create_client(self, session_name: str) -> Optional[TelegramClient]:
        if session_name not in self.sessions_data:
            return None

        # Используем семафор для предотвращения одновременного доступа к SQLite
        async with self._db_access_semaphore:
            try:
                # Для .session файлов используем путь напрямую
                session_path = self.sessions_data[session_name]

                # Добавляем небольшую случайную задержку для избежания конфликтов
                await asyncio.sleep(0.05 + (hash(session_name) % 50) / 1000.0)  # Уменьшено для скорости

                client = TelegramClient(
                    session_path,
                    api_id=config.API_ID,
                    api_hash=config.API_HASH,
                    timeout=config.TELEGRAM_CONNECT_TIMEOUT,
                    connection_retries=2,  # Уменьшено для скорости
                    retry_delay=0.5  # Уменьшена задержка
                )
                await client.connect()

                if await client.is_user_authorized():
                    self.clients[session_name] = client
                    return client
                else:
                    logger.warning(f"Сессия {session_name} не авторизована")
                    await client.disconnect()
                    return None

            except Exception as e:
                # Если это ошибка блокировки БД, ждем немного и пробуем еще раз
                if "database is locked" in str(e).lower():
                    logger.warning(f"БД заблокирована для {session_name}, повторная попытка...")
                    await asyncio.sleep(0.3 + (hash(session_name) % 10) / 10.0)
                    try:
                        client = TelegramClient(
                            self.sessions_data[session_name],
                            api_id=config.API_ID,
                            api_hash=config.API_HASH,
                            timeout=config.TELEGRAM_CONNECT_TIMEOUT
                        )
                        await client.connect()
                        if await client.is_user_authorized():
                            self.clients[session_name] = client
                            return client
                        await client.disconnect()
                    except:
                        pass

                logger.error(f"Ошибка создания клиента для {session_name}: {e}")
                return None

    async def validate_session(self, session_name: str) -> bool:
        client = await self.create_client(session_name)
        if client:
            try:
                me = await client.get_me()
                await client.disconnect()
                return True
            except:
                await client.disconnect()
                return False
        return False

    async def validate_all_sessions(self) -> Tuple[int, int]:
        """Валидирует все сессии"""

        valid_count = 0
        invalid_count = 0

        # Убираем семафор - выполняем все операции параллельно без ограничений
        # для максимальной скорости

        async def validate_single(session_name: str):
            nonlocal valid_count, invalid_count
            try:
                is_valid = await self.validate_session(session_name)
                if is_valid:
                    valid_count += 1
                else:
                    invalid_count += 1
            except:
                invalid_count += 1

        tasks = [validate_single(name) for name in self.sessions_data.keys()]
        await asyncio.gather(*tasks, return_exceptions=True)

        return valid_count, invalid_count

    async def get_session_names(self) -> List[str]:
        return list(self.sessions_data.keys())

    async def close_all_clients(self):
        for client in self.clients.values():
            try:
                await client.disconnect()
            except:
                pass
        self.clients.clear()

    def get_client(self, session_name: str) -> Optional[TelegramClient]:
        return self.clients.get(session_name)