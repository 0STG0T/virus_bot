import asyncio
import logging
from typing import Optional, Dict
from telethon import TelegramClient
from telethon.tl.functions.messages import RequestWebViewRequest
from telethon.tl.types import InputBotAppShortName
from urllib.parse import unquote, parse_qs
import json
import base64

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