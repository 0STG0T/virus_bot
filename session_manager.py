import os
import asyncio
from telethon import TelegramClient
from typing import List, Dict, Optional, Tuple
import logging
from config import SESSIONS_DIR, TELEGRAM_CONNECT_TIMEOUT, VALIDATION_SEMAPHORE_LIMIT, SESSION_VALIDATION_CACHE_TTL
from datetime import datetime
import time

logger = logging.getLogger(__name__)

class SessionManager:
    def __init__(self):
        self.clients: Dict[str, TelegramClient] = {}
        self.sessions_data: Dict[str, str] = {}

        # Кэш валидации сессий для максимальной производительности
        self._validation_cache: Dict[str, bool] = {}
        self._validation_cache_timestamp: Optional[datetime] = None

        # Семафор для предотвращения одновременного доступа к SQLite базам
        self._db_access_semaphore = asyncio.Semaphore(5)  # Максимум 5 одновременных подключений к БД

    async def load_sessions(self) -> int:
        if not os.path.exists(SESSIONS_DIR):
            os.makedirs(SESSIONS_DIR)
            return 0

        session_files = [f for f in os.listdir(SESSIONS_DIR) if f.endswith('.session')]
        loaded_count = 0

        for session_file in session_files:
            session_path = os.path.join(SESSIONS_DIR, session_file)
            session_name = session_file.replace('.session', '')

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
                # Используем стандартные API ID/Hash или загружаем из env
                api_id = int(os.environ.get('TG_API_ID', '20632491'))
                api_hash = os.environ.get('TG_API_HASH', '6b19ce4f2d8b4246b5c68c64a5c8e27e')

                # Добавляем небольшую случайную задержку для избежания конфликтов
                await asyncio.sleep(0.1 + (hash(session_name) % 100) / 1000.0)

                client = TelegramClient(
                    session_path,
                    api_id=api_id,
                    api_hash=api_hash,
                    timeout=TELEGRAM_CONNECT_TIMEOUT,
                    connection_retries=3,  # Уменьшено для скорости
                    retry_delay=1  # Уменьшена задержка
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
                    await asyncio.sleep(0.5 + (hash(session_name) % 10) / 10.0)
                    try:
                        client = TelegramClient(
                            self.sessions_data[session_name],
                            api_id=int(os.environ.get('TG_API_ID', '20632491')),
                            api_hash=os.environ.get('TG_API_HASH', '6b19ce4f2d8b4246b5c68c64a5c8e27e'),
                            timeout=TELEGRAM_CONNECT_TIMEOUT
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

    async def validate_all_sessions(self, use_cache: bool = True) -> Tuple[int, int]:
        """Валидирует все сессии с кэшированием для максимальной производительности"""

        # Проверяем кэш если включен
        if (use_cache and self._validation_cache_timestamp is not None):
            cache_age = (datetime.now() - self._validation_cache_timestamp).total_seconds()
            if cache_age < SESSION_VALIDATION_CACHE_TTL:
                logger.debug(f"Используем кэш валидации сессий (возраст: {cache_age:.1f}s)")
                valid_count = sum(1 for is_valid in self._validation_cache.values() if is_valid)
                invalid_count = len(self._validation_cache) - valid_count
                return valid_count, invalid_count

        valid_count = 0
        invalid_count = 0

        # Увеличенный семафор для максимальной производительности
        semaphore = asyncio.Semaphore(VALIDATION_SEMAPHORE_LIMIT)

        async def validate_single(session_name: str):
            nonlocal valid_count, invalid_count
            async with semaphore:
                try:
                    is_valid = await self.validate_session(session_name)
                    self._validation_cache[session_name] = is_valid
                    if is_valid:
                        valid_count += 1
                    else:
                        invalid_count += 1
                except:
                    self._validation_cache[session_name] = False
                    invalid_count += 1

        tasks = [validate_single(name) for name in self.sessions_data.keys()]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Обновляем время кэша
        self._validation_cache_timestamp = datetime.now()

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