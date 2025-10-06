import asyncio
import logging
from typing import Optional, Dict
from telethon import TelegramClient
from telethon.tl.functions.messages import RequestWebViewRequest
from telethon.tl.types import InputBotAppShortName
from urllib.parse import unquote, parse_qs
import json
import base64
import aiohttp

logger = logging.getLogger(__name__)

class WebAppAuth:
    def __init__(self, client: TelegramClient, session_name: str):
        self.client = client
        self.session_name = session_name

    async def get_webapp_data(self) -> Optional[str]:
        try:
            bot = await self.client.get_entity("@virus_play_bot")

            web_view = await self.client(RequestWebViewRequest(
                peer=bot,
                bot=bot,
                platform='web',
                from_bot_menu=False,
                url='https://virusgift.pro/'
            ))

            if hasattr(web_view, 'url') and web_view.url:
                return self._extract_init_data(web_view.url)

            return None

        except Exception as e:
            logger.error(f"Ошибка получения WebApp данных для {self.session_name}: {e}")
            return None

    def _extract_init_data(self, url: str) -> Optional[str]:
        try:
            if '#tgWebAppData=' in url:
                tg_data = url.split('#tgWebAppData=')[1].split('&')[0]
                return unquote(tg_data)

            return None
        except Exception as e:
            logger.error(f"Ошибка извлечения init data: {e}")
            return None

    async def get_auth_token(self) -> Optional[str]:
        init_data = await self.get_webapp_data()
        if not init_data:
            return None

        try:
            params = parse_qs(init_data)

            if 'user' in params:
                user_data = json.loads(params['user'][0])

                auth_payload = {
                    'initData': init_data,
                    'user': user_data
                }

                return base64.b64encode(json.dumps(auth_payload).encode()).decode()

        except Exception as e:
            logger.error(f"Ошибка создания auth токена для {self.session_name}: {e}")

        return None

    async def validate_auth(self, auth_token: str) -> bool:
        try:
            decoded = base64.b64decode(auth_token.encode()).decode()
            auth_data = json.loads(decoded)

            return 'initData' in auth_data and 'user' in auth_data
        except:
            return False

    async def click_test_spin_url(self, url: str) -> tuple[bool, Optional[str]]:
        """Открывает WebApp по специальной ссылке для testSpin и ждет полной загрузки

        Returns:
            tuple[bool, Optional[str]]: (успех, init_data или None)
        """
        try:
            logger.info(f"🔗 [{self.session_name}] Обрабатываю тестовую ссылку: {url}")

            # Парсим ссылку: https://t.me/jet_diceclub_bot/dapp?startapp=cfSbzBT4KPk
            if 't.me/' not in url:
                logger.warning(f"[{self.session_name}] URL не содержит t.me/")
                return False, None

            parts = url.split('t.me/')[1].split('/')
            if len(parts) < 2:
                logger.warning(f"[{self.session_name}] Неверный формат URL: {url}")
                return False, None

            bot_username = parts[0]
            app_short_name = parts[1].split('?')[0]

            # Извлекаем параметр startapp
            start_param = None
            if '?startapp=' in url:
                start_param = url.split('?startapp=')[1].split('&')[0]

            logger.info(f"🔗 [{self.session_name}] Бот: @{bot_username}, Приложение: {app_short_name}, Параметр: {start_param}")

            # Получаем entity бота
            logger.info(f"🔗 [{self.session_name}] Получаю entity бота @{bot_username}...")
            bot = await self.client.get_entity(f"@{bot_username}")
            logger.info(f"✅ [{self.session_name}] Entity бота получен: {bot.id}")

            # Формируем URL для WebApp
            webapp_url = f"https://t.me/{bot_username}/{app_short_name}"
            if start_param:
                webapp_url += f"?startapp={start_param}"

            logger.info(f"🔗 [{self.session_name}] Открываю WebApp по URL: {webapp_url}")
            logger.info(f"⏳ [{self.session_name}] Жду полной загрузки WebApp (это может занять 20-30 секунд)...")

            # Открываем WebApp через RequestWebViewRequest и ЖДЕМ ответа
            try:
                # Увеличиваем timeout и ждем полного ответа
                logger.info(f"🔧 [{self.session_name}] Отправляю RequestWebViewRequest...")
                logger.info(f"   📍 peer: {bot.id}")
                logger.info(f"   📍 bot: {bot.id}")
                logger.info(f"   📍 platform: android")
                logger.info(f"   📍 url: {webapp_url}")
                logger.info(f"   📍 from_bot_menu: False")

                web_view = await asyncio.wait_for(
                    self.client(RequestWebViewRequest(
                        peer=bot,
                        bot=bot,
                        platform='android',
                        from_bot_menu=False,
                        url=webapp_url
                    )),
                    timeout=45.0  # Увеличил до 45 секунд
                )

                logger.info(f"✅ [{self.session_name}] WebApp ответил!")
                logger.info(f"📦 [{self.session_name}] Тип ответа: {type(web_view)}")
                logger.info(f"📦 [{self.session_name}] Ответ WebApp (repr): {repr(web_view)}")
                logger.info(f"📦 [{self.session_name}] Ответ WebApp (str): {str(web_view)}")
                logger.info(f"📦 [{self.session_name}] Атрибуты ответа: {dir(web_view)}")

                # Проверяем что получили URL с данными
                if hasattr(web_view, 'url'):
                    logger.info(f"✅ [{self.session_name}] Атрибут 'url' найден")
                    logger.info(f"🌐 [{self.session_name}] URL ответа (тип): {type(web_view.url)}")
                    logger.info(f"🌐 [{self.session_name}] URL ответа (полный): {web_view.url}")
                else:
                    logger.warning(f"⚠️ [{self.session_name}] Атрибут 'url' НЕ найден в ответе!")

                if hasattr(web_view, 'url') and web_view.url:
                    webapp_full_url = web_view.url

                    # Извлекаем init data если есть
                    if '#tgWebAppData=' in webapp_full_url:
                        init_data = self._extract_init_data(webapp_full_url)
                        if init_data:
                            logger.info(f"✅ [{self.session_name}] WebApp вернул init_data!")
                            logger.info(f"📝 [{self.session_name}] Init data (первые 100 символов): {init_data[:100]}...")

                            # КРИТИЧЕСКИ ВАЖНО: Делаем HTTP запрос к WebApp URL чтобы получить cookies
                            logger.info(f"🌐 [{self.session_name}] Открываю WebApp URL для регистрации клика...")

                            # Извлекаем базовый URL без хэша
                            base_url = webapp_full_url.split('#')[0]
                            logger.info(f"🌐 [{self.session_name}] Base URL: {base_url}")

                            try:
                                # Создаем HTTP клиент с правильными заголовками
                                headers = {
                                    'User-Agent': 'Mozilla/5.0 (Linux; Android 6.0; Nexus 5 Build/MRA58N) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Mobile Safari/537.36',
                                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                                    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                                    'Accept-Encoding': 'gzip, deflate, br',
                                    'Referer': 'https://web.telegram.org/',
                                    'sec-ch-ua': '"Chromium";v="140", "Not=A?Brand";v="24"',
                                    'sec-ch-ua-mobile': '?1',
                                    'sec-ch-ua-platform': '"Android"',
                                    'sec-fetch-dest': 'iframe',
                                    'sec-fetch-mode': 'navigate',
                                    'sec-fetch-site': 'cross-site',
                                    'sec-fetch-user': '?1',
                                    'upgrade-insecure-requests': '1'
                                }

                                async with aiohttp.ClientSession() as http_session:
                                    logger.info(f"📡 [{self.session_name}] Отправляю GET запрос к {base_url}...")

                                    async with http_session.get(
                                        base_url,
                                        headers=headers,
                                        allow_redirects=True,
                                        timeout=aiohttp.ClientTimeout(total=30)
                                    ) as response:
                                        logger.info(f"✅ [{self.session_name}] HTTP ответ: {response.status}")
                                        logger.info(f"🍪 [{self.session_name}] Cookies: {response.cookies}")

                                        # Читаем немного контента чтобы убедиться что страница загрузилась
                                        content = await response.text()
                                        logger.info(f"📄 [{self.session_name}] Получено {len(content)} байт контента")

                                        # Если есть редирект, следуем ему
                                        if response.status in [301, 302, 307, 308]:
                                            redirect_url = str(response.url)
                                            logger.info(f"🔄 [{self.session_name}] Редирект на: {redirect_url}")

                            except Exception as e_http:
                                logger.warning(f"⚠️ [{self.session_name}] Ошибка HTTP запроса (не критично): {e_http}")

                            # Дополнительно отправляем /start в бот
                            if start_param:
                                try:
                                    logger.info(f"📨 [{self.session_name}] Отправляю /start {start_param} в бот для регистрации...")
                                    await self.client.send_message(bot, f'/start {start_param}')
                                    logger.info(f"✅ [{self.session_name}] /start отправлен")
                                except Exception as e_start:
                                    logger.warning(f"⚠️ [{self.session_name}] Ошибка отправки /start: {e_start}")

                            # Даем БОЛЬШЕ времени на обработку - возможно jetcloudapp делает асинхронные запросы
                            logger.info(f"⏳ [{self.session_name}] Жду 10 секунд для полной обработки WebApp на сервере...")
                            await asyncio.sleep(10)

                            logger.info(f"✅ [{self.session_name}] Возвращаю init_data для отправки на сервер")
                            return True, init_data
                        else:
                            logger.warning(f"⚠️ [{self.session_name}] Не удалось извлечь init_data из URL")
                            return False, None
                    else:
                        logger.warning(f"⚠️ [{self.session_name}] WebApp открылся, но не вернул tgWebAppData")
                        # Все равно считаем успехом, возможно сервер это зарегистрирует
                        logger.info(f"⏳ [{self.session_name}] Жду 5 секунд для обработки на сервере...")
                        await asyncio.sleep(5)
                        return True, None
                else:
                    logger.warning(f"⚠️ [{self.session_name}] WebApp открылся, но нет URL в ответе")
                    return False, None

            except asyncio.TimeoutError:
                logger.error(f"❌ [{self.session_name}] Timeout при ожидании ответа от WebApp (45 сек)")
                logger.info(f"ℹ️ [{self.session_name}] Пробую отправить /start как fallback...")
                # Fallback - отправляем /start
                if start_param:
                    try:
                        logger.info(f"📨 [{self.session_name}] Отправляю /start {start_param}")
                        await self.client.send_message(bot, f'/start {start_param}')
                        logger.info(f"⏳ [{self.session_name}] Жду 10 секунд после /start...")
                        await asyncio.sleep(10)
                        logger.info(f"✅ [{self.session_name}] /start fallback завершен")
                        return True, None
                    except Exception as e_fallback:
                        logger.error(f"❌ [{self.session_name}] Ошибка в /start fallback: {e_fallback}")
                        pass
                return False, None
            except Exception as e:
                logger.error(f"❌ [{self.session_name}] Ошибка открытия WebApp: {e}")
                logger.info(f"🔄 [{self.session_name}] Пробую альтернативный метод...")

                # Альтернативный метод - отправить /start с параметром
                try:
                    if start_param:
                        logger.info(f"📨 [{self.session_name}] Отправляю /start {start_param}")
                        await self.client.send_message(bot, f'/start {start_param}')
                        logger.info(f"⏳ [{self.session_name}] Жду 5 секунд...")
                        await asyncio.sleep(5)
                        logger.info(f"✅ [{self.session_name}] /start отправлен")
                        return True, None
                except Exception as e2:
                    logger.error(f"❌ [{self.session_name}] Альтернативный метод не сработал: {e2}")
                    return False, None

        except Exception as e:
            logger.error(f"❌ [{self.session_name}] Критическая ошибка в click_test_spin_url: {e}")
            return False, None