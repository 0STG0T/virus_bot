import aiohttp
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List, Tuple
from fake_useragent import UserAgent
from config import (WEBAPP_URL, GRAPHQL_URL, HEADERS, HIGH_VALUE_THRESHOLD,
                   HTTP_REQUEST_TIMEOUT, SUBSCRIPTION_DELAY, PRIZE_ACTIVATION_DELAY,
                   AUTO_GIFT_EXCHANGE_ENABLED, AUTO_GIFT_EXCHANGE_THRESHOLD,
                   INVENTORY_CACHE_ENABLED, INVENTORY_CACHE_TTL, REDUCED_LOGGING_MODE,
                   HTTP_CONNECTION_POOL_SIZE, BALANCE_CACHE_ENABLED, BALANCE_CACHE_TTL,
                   USER_DATA_CACHE_TTL, PERFORMANCE_MODE)

# Импортируем настройку логирования
try:
    from logging_config import setup_logging
    setup_logging()
except ImportError:
    # Если файл конфигурации логов не найден, используем базовую настройку
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)
graphql_logger = logging.getLogger('graphql_requests')
ua = UserAgent()

class VirusAPI:
    def __init__(self, session_name: str):
        self.session_name = session_name
        self.session: Optional[aiohttp.ClientSession] = None
        self.auth_data: Optional[str] = None
        self.auth_token: Optional[str] = None
        self.user_data: Optional[Dict] = None

        # Кэш инвентаря
        self._inventory_cache: Optional[Dict] = None
        self._inventory_cache_timestamp: Optional[datetime] = None

        # Кэш балансов и данных пользователей для максимальной производительности
        self._balance_cache: Optional[Dict] = None
        self._balance_cache_timestamp: Optional[datetime] = None
        self._user_data_cache: Optional[Dict] = None
        self._user_data_cache_timestamp: Optional[datetime] = None

    async def init_session(self):
        if not self.session:
            # МАКСИМАЛЬНАЯ ОПТИМИЗАЦИЯ: настраиваем соединения для производительности
            connector = aiohttp.TCPConnector(
                limit=HTTP_CONNECTION_POOL_SIZE,  # Максимум соединений (увеличено до 100)
                limit_per_host=20,  # Увеличено для лучшей производительности
                keepalive_timeout=60,  # Увеличено время жизни соединений
                enable_cleanup_closed=True,  # Очистка закрытых соединений
                ttl_dns_cache=300,  # Кэш DNS на 5 минут
                use_dns_cache=True  # Включить DNS кэш
            )

            self.session = aiohttp.ClientSession(
                headers={**HEADERS, 'User-Agent': ua.random},
                timeout=aiohttp.ClientTimeout(total=HTTP_REQUEST_TIMEOUT),
                connector=connector
            )

    async def close_session(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def set_auth_data(self, init_data: str):
        self.auth_data = init_data
        logger.debug(f"Установлены данные авторизации для {self.session_name}: {init_data[:50]}...")

        # Получаем JWT токен через authTelegramInitData
        await self.get_auth_token()

    async def get_auth_token(self) -> Optional[str]:
        """Получает JWT токен через authTelegramInitData"""
        if not self.auth_data:
            return None

        query = """
        mutation authTelegramInitData($initData: String!, $refCode: String) {
            authTelegramInitData(initData: $initData, refCode: $refCode) {
                token
                success
                __typename
            }
        }
        """

        variables = {
            'initData': self.auth_data,
            'refCode': None
        }

        if not self.session:
            await self.init_session()

        headers = self.session.headers.copy()
        headers['Content-Type'] = 'application/json'
        headers['Origin'] = WEBAPP_URL
        headers['Referer'] = f'{WEBAPP_URL}/roulette'

        payload = {
            'query': query,
            'variables': variables,
            'operationName': 'authTelegramInitData'
        }

        try:
            # Подробное логирование auth запроса
            graphql_logger.info(f"=== AUTH REQUEST {self.session_name} ===")
            graphql_logger.info(f"URL: {GRAPHQL_URL}")
            graphql_logger.info(f"Operation: authTelegramInitData")
            graphql_logger.info(f"Headers: {headers}")
            graphql_logger.info(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")

            async with self.session.post(GRAPHQL_URL, json=payload, headers=headers) as response:
                text = await response.text()

                # Подробное логирование auth ответа
                graphql_logger.info(f"=== AUTH RESPONSE {self.session_name} ===")
                graphql_logger.info(f"Status: {response.status}")
                graphql_logger.info(f"Response Headers: {dict(response.headers)}")

                # Логируем ответ, но скрываем токен для безопасности
                try:
                    response_json = json.loads(text)
                    # Маскируем токен в логах
                    if (response_json.get('data') and
                        response_json['data'].get('authTelegramInitData') and
                        response_json['data']['authTelegramInitData'].get('token')):
                        masked_response = json.loads(text)
                        token = masked_response['data']['authTelegramInitData']['token']
                        masked_response['data']['authTelegramInitData']['token'] = f"{token[:10]}...{token[-10:]}"
                        formatted_response = json.dumps(masked_response, indent=2, ensure_ascii=False)
                    else:
                        formatted_response = json.dumps(response_json, indent=2, ensure_ascii=False)

                    graphql_logger.info(f"Response Body:\n{formatted_response}")
                except:
                    graphql_logger.info(f"Response Body (raw): {text}")

                graphql_logger.info(f"=== END AUTH {self.session_name} ===\n")

                if response.status == 200:
                    json_response = await response.json()
                    if json_response.get('data') and json_response['data'].get('authTelegramInitData'):
                        auth_result = json_response['data']['authTelegramInitData']
                        if auth_result.get('success') and auth_result.get('token'):
                            self.auth_token = auth_result['token']
                            logger.info(f"Получен JWT токен для {self.session_name}")
                            return self.auth_token
                    elif json_response.get('errors'):
                        logger.error(f"Ошибка получения токена: {json_response['errors']}")
                else:
                    logger.error(f"Ошибка получения токена: {response.status} - {text}")

        except Exception as e:
            logger.error(f"Исключение при получении токена: {e}", exc_info=True)

        return None

    async def _make_graphql_request(self, query: str, variables: Dict = None, operation_name: str = None) -> Optional[Dict]:
        if not self.session:
            await self.init_session()

        headers = self.session.headers.copy()
        headers['Content-Type'] = 'application/json'
        headers['Origin'] = WEBAPP_URL
        headers['Referer'] = f'{WEBAPP_URL}/roulette'

        # Добавляем заголовки из DevTools
        headers['apollo-require-preflight'] = '*'
        headers['x-batch'] = 'true'
        headers['x-timezone'] = 'Europe/Moscow'

        if self.auth_token:
            # Используем JWT токен в заголовке Authorization
            headers['Authorization'] = f'Bearer {self.auth_token}'

        # Для x-batch: true отправляем как массив
        single_query = {
            'query': query,
            'variables': variables or {}
        }

        if operation_name:
            single_query['operationName'] = operation_name

        # API ожидает массив запросов для batch режима
        payload = [single_query]

        try:
            # Оптимизированное логирование запроса
            if not REDUCED_LOGGING_MODE:
                # Подробное логирование только если не в режиме производительности
                graphql_logger.info(f"=== GraphQL REQUEST {self.session_name} ===")
                graphql_logger.info(f"URL: {GRAPHQL_URL}")
                graphql_logger.info(f"Operation: {operation_name or 'unnamed'}")
                # Маскируем чувствительные данные для безопасности
                masked_headers = {k: v for k, v in headers.items()}
                if 'Authorization' in masked_headers:
                    token = masked_headers['Authorization']
                    if len(token) > 20:
                        masked_headers['Authorization'] = token[:10] + '...' + token[-10:]
                graphql_logger.info(f"Headers: {masked_headers}")
                graphql_logger.info(f"Payload: {json.dumps(payload, indent=2, ensure_ascii=False)}")
            else:
                # Краткое логирование для производительности
                graphql_logger.debug(f"GraphQL {operation_name or 'request'} -> {self.session_name}")

            async with self.session.post(GRAPHQL_URL, json=payload, headers=headers) as response:
                text = await response.text()

                if not REDUCED_LOGGING_MODE:
                    # Подробное логирование ответа
                    graphql_logger.info(f"=== GraphQL RESPONSE {self.session_name} ===")
                    graphql_logger.info(f"Status: {response.status}")
                    graphql_logger.info(f"Response Headers: {dict(response.headers)}")

                # Пытаемся красиво отформатировать JSON ответ (только если детальное логирование)
                if not REDUCED_LOGGING_MODE:
                    try:
                        response_json = json.loads(text)
                        formatted_response = json.dumps(response_json, indent=2, ensure_ascii=False)
                        graphql_logger.info(f"Response Body:\n{formatted_response}")
                    except:
                        graphql_logger.info(f"Response Body (raw): {text}")
                    graphql_logger.info(f"=== END GraphQL {self.session_name} ===\n")

                if response.status == 200:
                    try:
                        json_response = await response.json()
                        # Batch API возвращает массив, берем первый элемент
                        if isinstance(json_response, list) and len(json_response) > 0:
                            return json_response[0]
                        else:
                            return json_response
                    except:
                        logger.warning(f"Не удалось разобрать JSON ответ: {text}")
                        return {'raw_response': text}
                else:
                    logger.error(f"GraphQL request failed: {response.status} - {text}")
                    # Для статусов ошибки тоже попробуем распарсить JSON,
                    # так как API может возвращать структурированные ошибки
                    try:
                        json_response = await response.json()
                        if isinstance(json_response, list) and len(json_response) > 0:
                            # Добавляем информацию о HTTP статусе в ответ
                            result = json_response[0]
                            result['http_status'] = response.status
                            return result
                        else:
                            json_response['http_status'] = response.status
                            return json_response
                    except:
                        logger.warning(f"Не удалось разобрать JSON ответ ошибки: {text}")
                        return {
                            'error': f'HTTP {response.status}',
                            'raw_response': text,
                            'http_status': response.status
                        }
        except Exception as e:
            logger.error(f"GraphQL request error: {e}", exc_info=True)
            return None

    async def get_user_info(self, use_cache: bool = True) -> Optional[Dict]:
        """Получает информацию пользователя с кэшированием для максимальной производительности"""

        # Проверяем кэш если включен
        if (use_cache and self._user_data_cache is not None and self._user_data_cache_timestamp is not None):
            cache_age = (datetime.now() - self._user_data_cache_timestamp).total_seconds()
            if cache_age < USER_DATA_CACHE_TTL:
                if not REDUCED_LOGGING_MODE:
                    logger.debug(f"Используем кэш данных пользователя для {self.session_name} (возраст: {cache_age:.1f}s)")
                return self._user_data_cache

        query = """
        query me {
            me {
                id
                refCode
                userId
                firstName
                lastName
                userName
                photo
                balance
                starsBalance
                status
                miningSpeed
                deathDate
                languageCode
                isFirstInfection
                hidden
                onboardingCompleted
                invitedCount
                refsRecoveryPercent
                testSpin
                nextFreeSpin
                refBalance
                refHoldBalance
                refBalanceUsd
                refHoldBalanceUsd
                __typename
            }
        }
        """

        result = await self._make_graphql_request(query, operation_name="me")
        if result and 'data' in result and result['data'] and 'me' in result['data']:
            user_data = result['data']['me']
            self.user_data = user_data

            # Кэшируем результат
            self._user_data_cache = user_data
            self._user_data_cache_timestamp = datetime.now()

            if not REDUCED_LOGGING_MODE or PERFORMANCE_MODE:
                logger.debug(f"Обновлены данные пользователя для {self.session_name}")
            else:
                logger.info("Получена информация о пользователе через GraphQL")
            return user_data
        elif result and 'errors' in result:
            logger.error(f"GraphQL ошибки: {result['errors']}")
            return None
        else:
            logger.error("Не удалось получить информацию о пользователе")
            return None

    async def check_spin_availability(self) -> Tuple[bool, str]:
        user_info = await self.get_user_info()
        if not user_info:
            return False, "Не удалось получить информацию о пользователе"

        # Проверяем время следующего бесплатного спина
        next_free_spin = user_info.get('nextFreeSpin')
        if next_free_spin:
            # Если есть время следующего спина, значит еще рано
            return False, "с прошлого не прошло 24 часа"

        return True, "OK"

    async def can_perform_paid_spin(self, required_stars: int = 200) -> Tuple[bool, str]:
        """Проверяет может ли аккаунт сделать платный спин"""
        user_info = await self.get_user_info()
        if not user_info:
            return False, "Не удалось получить информацию о пользователе"

        stars_balance = user_info.get('starsBalance', 0)

        if stars_balance >= required_stars:
            return True, f"Баланс {stars_balance} звезд (достаточно для платного спина)"
        else:
            return False, f"Недостаточно звезд на балансе: {stars_balance}/{required_stars}"

    async def complete_referral_tasks(self) -> bool:
        query = """
        mutation CompleteReferralTasks {
            completeReferralTasks {
                success
                message
            }
        }
        """

        result = await self._make_graphql_request(query)
        return result and result.get('data', {}).get('completeReferralTasks', {}).get('success', False)

    async def subscribe_to_channel(self, channel: str) -> bool:
        query = """
        mutation SubscribeToChannel($channel: String!) {
            subscribeToChannel(channel: $channel) {
                success
                message
            }
        }
        """

        variables = {'channel': channel}
        result = await self._make_graphql_request(query, variables)
        return result and result.get('data', {}).get('subscribeToChannel', {}).get('success', False)

    async def complete_subscription_tasks(self) -> bool:
        user_info = await self.get_user_info()
        if not user_info:
            return False

        subscriptions = user_info.get('telegramSubscriptions', [])
        for subscription in subscriptions:
            if not subscription.get('isSubscribed', False):
                channel = subscription.get('channel')
                if channel:
                    await self.subscribe_to_channel(channel)
                    await asyncio.sleep(SUBSCRIPTION_DELAY)

        return True

    async def subscribe_to_required_channel(self, channel_info: Dict) -> bool:
        """Подписывается на обязательный канал для фри спина"""
        if not channel_info:
            return False

        username = channel_info.get('username')

        if username:
            # Пытаемся подписаться на канал
            # Здесь нужно использовать telethon клиент для подписки
            logger.info(f"Необходимо подписаться на канал @{username}")
            # TODO: Реализовать подписку через telethon
            return True

        return False

    async def perform_spin(self) -> Tuple[bool, str, Optional[Dict]]:
        query = """
        mutation startRouletteSpin($input: StartRouletteSpinInput!) {
            startRouletteSpin(input: $input) {
                success
                prize {
                    id
                    name
                    caption
                    animationUrl
                    photoUrl
                    exchangeCurrency
                    exchangePrice
                    prizeExchangePrice
                    isSpinSellable
                    isClaimable
                    isExchangeable
                    storyLinkAfterWin
                    __typename
                }
                userPrizeId
                balance
                isStoryRewardAvailable
                storyReward
                __typename
            }
        }
        """

        variables = {
            "input": {
                "type": "X1"
            }
        }

        result = await self._make_graphql_request(query, variables, operation_name="startRouletteSpin")

        if result and 'data' in result and result['data'] and 'startRouletteSpin' in result['data']:
            spin_data = result['data']['startRouletteSpin']
            if spin_data.get('success'):
                prize = spin_data.get('prize', {})
                return True, "Спин выполнен успешно", prize
            else:
                return False, "Спин не был успешным", None

        elif result and 'errors' in result:
            # Обрабатываем GraphQL ошибки
            error = result['errors'][0] if result['errors'] else {}
            message = error.get('message', 'Неизвестная ошибка')
            extensions = error.get('extensions', {})

            logger.warning(f"⚠️ [{self.session_name}] GraphQL ошибка при спине:")
            logger.warning(f"   📝 Message: {message}")
            logger.warning(f"   🔧 Extensions: {extensions}")

            # Особая обработка ошибки подписки
            if extensions.get('code') == 'TELEGRAM_SUBSCRIPTION_REQUIRED':
                channel_info = extensions
                channel_username = channel_info.get('username', 'неизвестный канал')
                url = channel_info.get('url', 'нет ссылки')
                logger.info(f"📡 [{self.session_name}] Требуется подписка на канал:")
                logger.info(f"   📛 Username: @{channel_username}")
                logger.info(f"   🔗 URL: {url}")
                logger.info(f"   📦 Полные данные: {channel_info}")
                return False, f"Требуется подписка на канал @{channel_username}", channel_info

            # Особая обработка ошибки клика по тестовой ссылке
            if extensions.get('code') == 'TEST_SPIN_URL_CLICK_REQUIRED':
                test_url = extensions.get('link', '')
                logger.info(f"🔗 [{self.session_name}] Требуется клик по тестовой ссылке:")
                logger.info(f"   🌐 URL: {test_url}")
                logger.info(f"   📦 Полные данные: {extensions}")
                return False, f"Требуется клик по тестовой ссылке", extensions

            # Проверяем сообщение об ошибке напрямую (для старых API)
            if "You must click the url before attempting a test spin" in message:
                logger.warning(f"🔗 [{self.session_name}] Обнаружена старая ошибка testSpin через message")
                logger.warning(f"   📝 Полное сообщение: {message}")
                logger.warning(f"   📦 Extensions (если есть): {extensions}")
                # Возвращаем как ошибку клика, даже если нет ссылки в extensions
                return False, f"Требуется клик по тестовой ссылке", extensions if extensions else {}

            return False, message, None

        else:
            return False, "Неожиданный формат ответа от API", None

    async def perform_paid_spin(self, spin_type: str = "PAID") -> Tuple[bool, str, Optional[Dict]]:
        """Выполняет платный спин (обычно за 200 звезд)"""
        query = """
        mutation startRouletteSpin($input: StartRouletteSpinInput!) {
            startRouletteSpin(input: $input) {
                success
                prize {
                    id
                    name
                    caption
                    animationUrl
                    photoUrl
                    exchangeCurrency
                    exchangePrice
                    prizeExchangePrice
                    isSpinSellable
                    isClaimable
                    isExchangeable
                    storyLinkAfterWin
                    __typename
                }
                userPrizeId
                balance
                isStoryRewardAvailable
                storyReward
                __typename
            }
        }
        """

        variables = {
            "input": {
                "type": spin_type  # Может быть "PAID", "X200" или другой тип
            }
        }

        result = await self._make_graphql_request(query, variables, operation_name="startRouletteSpin")

        if result and 'data' in result and result['data'] and 'startRouletteSpin' in result['data']:
            spin_data = result['data']['startRouletteSpin']
            if spin_data.get('success'):
                prize = spin_data.get('prize', {})
                return True, "Платный спин выполнен успешно", prize
            else:
                return False, "Платный спин не был успешным", None

        elif result and 'errors' in result:
            error = result['errors'][0] if result['errors'] else {}
            message = error.get('message', 'Неизвестная ошибка')
            return False, message, None

        else:
            return False, "Неожиданный формат ответа от API", None

    async def get_inventory(self) -> List[Dict]:
        query = """
        query GetInventory {
            inventory {
                items {
                    id
                    name
                    type
                    value
                    quantity
                }
            }
        }
        """

        result = await self._make_graphql_request(query)
        if result and 'data' in result and 'inventory' in result['data']:
            return result['data']['inventory'].get('items', [])
        return []

    async def activate_stars(self) -> bool:
        query = """
        mutation ActivateStars {
            activateStars {
                success
                message
                amount
            }
        }
        """

        result = await self._make_graphql_request(query)
        return result and result.get('data', {}).get('activateStars', {}).get('success', False)

    async def sell_item(self, item_id: str) -> Tuple[bool, int]:
        query = """
        mutation SellItem($itemId: String!) {
            sellItem(itemId: $itemId) {
                success
                message
                starsReceived
            }
        }
        """

        variables = {'itemId': item_id}
        result = await self._make_graphql_request(query, variables)

        if result and result.get('data', {}).get('sellItem', {}).get('success', False):
            stars = result['data']['sellItem'].get('starsReceived', 0)
            return True, stars
        return False, 0

    async def process_reward(self, reward: Dict) -> Tuple[bool, str, bool, bool]:
        """
        Обрабатывает награду из спина
        Возвращает: (success, description, is_high_value, is_gift)
        """
        # Новый формат наград из GraphQL
        item_name = reward.get('name', '').lower()
        original_name = reward.get('name', '')

        # Проверяем если это звезды
        if 'stars' in item_name or 'star' in item_name:
            # Извлекаем количество звезд из имени "7 Stars"
            try:
                stars_count = int(item_name.split()[0])
                return True, f"звезды ({stars_count})", False, False
            except:
                return True, f"звезды", False, False

        # Проверяем если это вирус
        if 'virus' in item_name:
            return True, f"вирус", False, False

        # Это подарок, если можно обменять или активировать
        if reward.get('isClaimable') or reward.get('isExchangeable'):
            exchange_price = reward.get('exchangePrice', 0)
            if exchange_price > 0:
                is_high_value = exchange_price > HIGH_VALUE_THRESHOLD
                return True, f"{original_name} ({exchange_price}⭐)", is_high_value, True
            else:
                return True, f"{original_name} (можно обменять)", False, True

        return True, f"{original_name}", False, True

    async def get_balance(self, use_cache: bool = True) -> Tuple[int, int]:
        """Получает баланс с кэшированием для максимальной производительности"""

        # Проверяем кэш если включен
        if (BALANCE_CACHE_ENABLED and use_cache and
            self._balance_cache is not None and self._balance_cache_timestamp is not None):

            cache_age = (datetime.now() - self._balance_cache_timestamp).total_seconds()
            if cache_age < BALANCE_CACHE_TTL:
                if not REDUCED_LOGGING_MODE:
                    logger.debug(f"Используем кэш баланса для {self.session_name} (возраст: {cache_age:.1f}s)")
                return self._balance_cache['starsBalance'], self._balance_cache['balance']

        # Получаем свежие данные
        user_info = await self.get_user_info(use_cache=use_cache)
        if user_info:
            stars_balance = user_info.get('starsBalance', 0)
            balance = user_info.get('balance', 0)

            # Кэшируем результат
            if BALANCE_CACHE_ENABLED:
                self._balance_cache = {
                    'starsBalance': stars_balance,
                    'balance': balance
                }
                self._balance_cache_timestamp = datetime.now()

            return stars_balance, balance
        return 0, 0

    async def get_roulette_inventory(self, cursor: Optional[int] = None, limit: int = 10, use_cache: bool = True) -> Optional[Dict]:
        """Получает инвентарь рулетки точно как в DevTools с кэшированием"""

        # Проверяем кэш если включен и запрашиваем первую страницу
        if (INVENTORY_CACHE_ENABLED and use_cache and cursor is None and
            self._inventory_cache is not None and self._inventory_cache_timestamp is not None):

            cache_age = (datetime.now() - self._inventory_cache_timestamp).total_seconds()
            if cache_age < INVENTORY_CACHE_TTL:
                if not REDUCED_LOGGING_MODE:
                    logger.debug(f"Используем кэш инвентаря для {self.session_name} (возраст: {cache_age:.1f}s)")
                return self._inventory_cache
        # Точно такой же запрос как в DevTools
        query = """
        query getRouletteInventory($limit: Int64!, $cursor: Int64!) {
            getRouletteInventory(cursor: $cursor, limit: $limit) {
                success
                prizes {
                    userRoulettePrizeId
                    status
                    name
                    prize {
                        id
                        name
                        caption
                        animationUrl
                        photoUrl
                        exchangeCurrency
                        exchangePrice
                        prizeExchangePrice
                        isSpinSellable
                        isClaimable
                        isExchangeable
                        storyLinkAfterWin
                        __typename
                    }
                    claimCost
                    unlockAt
                    source
                    specific {
                        externalId
                        model {
                            name
                            animationUrl
                            rarityPermille
                            __typename
                        }
                        background {
                            name
                            centerColor
                            edgeColor
                            patternColor
                            textColor
                            hex {
                                centerColor
                                edgeColor
                                patternColor
                                textColor
                                __typename
                            }
                            rarityPermille
                            __typename
                        }
                        symbol {
                            name
                            photoUrl
                            rarityPermille
                            __typename
                        }
                        __typename
                    }
                    __typename
                }
                nextCursor
                hasNextPage
                __typename
            }
        }
        """

        # Первый запрос начинается с cursor=0, последующие используют nextCursor
        variables = {
            'limit': limit,
            'cursor': cursor if cursor is not None else 0
        }

        result = await self._make_graphql_request(query, variables, operation_name="getRouletteInventory")

        # Добавляем отладочное логирование (только если включено подробное логирование)
        if not REDUCED_LOGGING_MODE:
            logger.debug(f"Inventory request cursor: {cursor}")
            logger.debug(f"Inventory response: {result}")

        if result and 'data' in result and result['data'] and 'getRouletteInventory' in result['data']:
            inventory_data = result['data']['getRouletteInventory']
            if inventory_data.get('success'):
                # Кэшируем данные если это первая страница и кэширование включено
                if INVENTORY_CACHE_ENABLED and cursor is None:
                    self._inventory_cache = inventory_data
                    self._inventory_cache_timestamp = datetime.now()
                    if not REDUCED_LOGGING_MODE:
                        logger.debug(f"Закэшировали инвентарь для {self.session_name}")

                return inventory_data
            else:
                logger.error(f"API returned success=false for inventory request")
                return None
        elif result and 'errors' in result:
            logger.error(f"GraphQL ошибки при получении инвентаря: {result['errors']}")
            return None
        else:
            logger.error("Не удалось получить инвентарь рулетки")
            return None

    async def claim_roulette_prize(self, user_roulette_prize_id: int) -> Tuple[bool, str]:
        """Активирует приз из инвентаря рулетки используя точную структуру из DevTools"""
        query = """
        mutation claimRoulettePrize($input: ClaimRoulettePrizeInput!) {
            claimRoulettePrize(input: $input) {
                success
                message
                telegramGift
                __typename
            }
        }
        """

        # Используем точную структуру из DevTools
        variables = {
            'input': {
                'userPrizeId': user_roulette_prize_id
            }
        }

        result = await self._make_graphql_request(query, variables, operation_name="claimRoulettePrize")

        # Добавляем отладочное логирование
        logger.debug(f"Claim prize request: userPrizeId={user_roulette_prize_id}")
        logger.debug(f"Claim prize response: {result}")

        if result and 'data' in result and result['data'] and 'claimRoulettePrize' in result['data']:
            claim_data = result['data']['claimRoulettePrize']
            if claim_data.get('success'):
                message = claim_data.get('message')
                telegram_gift = claim_data.get('telegramGift', False)
                response_msg = "Приз успешно активирован"
                if telegram_gift:
                    response_msg += " (Telegram Gift)"
                if message:
                    response_msg += f" - {message}"
                return True, response_msg
            else:
                message = claim_data.get('message', 'Не удалось активировать приз')
                return False, message
        elif result and 'errors' in result:
            error = result['errors'][0] if result['errors'] else {}
            message = error.get('message', 'Неизвестная ошибка')
            extensions = error.get('extensions', {})

            # Проверяем специфичную ошибку tunnel click required
            if extensions.get('code') == 'TEST_SPIN_TONNEL_CLICK_REQUIRED':
                logger.info(f"🔧 Требуется tunnel click для {self.session_name}, выполняем автоматически...")

                # Вызываем markTestSpinTonnelClick без параметров
                tunnel_success, tunnel_message = await self.mark_test_spin_tunnel_click()

                if tunnel_success:
                    logger.info(f"✅ Tunnel click выполнен для {self.session_name}, повторяем активацию приза")
                    # Повторяем попытку активации приза
                    return await self.claim_roulette_prize(user_roulette_prize_id)
                else:
                    return False, f"Не удалось выполнить tunnel click: {tunnel_message}"

            # Проверяем ошибку portal click required
            elif 'portal' in message.lower() and 'click' in message.lower():
                logger.info(f"🔧 Требуется portal click для {self.session_name}, выполняем автоматически...")

                # Вызываем markTestSpinPortalClick без параметров
                portal_success, portal_message = await self.mark_test_spin_portal_click()

                if portal_success:
                    logger.info(f"✅ Portal click выполнен для {self.session_name}, повторяем активацию приза")
                    # Повторяем попытку активации приза
                    return await self.claim_roulette_prize(user_roulette_prize_id)
                else:
                    return False, f"Не удалось выполнить portal click: {portal_message}"

            return False, f"Ошибка активации: {message}"
        else:
            return False, "Неожиданный формат ответа от API"

    async def activate_all_stars(self) -> Tuple[int, int]:
        """Активирует все звезды из инвентаря. Возвращает (активировано, всего_найдено)"""
        activated_count = 0
        total_stars_found = 0
        cursor = 0  # Начинаем с 0 как в DevTools

        # Проверяем статус аккаунта перед активацией
        try:
            account_status = await self.get_account_status()
            logger.info(f"Статус аккаунта {self.session_name}: ready={account_status['ready_for_automation']}, onboarding={account_status['onboarding_required']}")

            if not account_status['ready_for_automation']:
                if account_status['onboarding_required']:
                    logger.warning(f"🔧 Аккаунт {self.session_name} требует ручного onboarding: {account_status['required_actions']}")
                    logger.info(f"Ошибка: {account_status['error_message']}")
                    return 0, 0  # Возвращаем 0 звезд чтобы не пытаться активировать
                else:
                    logger.error(f"❌ Аккаунт {self.session_name} не готов к работе: {account_status['error_message']}")
                    return 0, 0

            logger.info(f"✅ Аккаунт {self.session_name} готов к активации звезд")

        except Exception as e:
            logger.warning(f"Ошибка проверки статуса аккаунта {self.session_name}: {e}")
            # Продолжаем попытку активации в случае ошибки проверки

        try:
            while True:
                # Получаем страницу инвентаря
                inventory = await self.get_roulette_inventory(cursor=cursor)
                if not inventory or not inventory.get('success'):
                    logger.warning(f"Не удалось получить инвентарь или success=false для {self.session_name}")
                    break

                prizes = inventory.get('prizes')
                if not prizes:
                    logger.info(f"Нет призов в инвентаре для {self.session_name}")
                    break

                # Обрабатываем каждый приз
                logger.debug(f"Обрабатываем {len(prizes)} призов на странице для {self.session_name}")
                for prize_item in prizes:
                    # Проверяем статус - только неактивированные призы (status: "NONE")
                    status = prize_item.get('status')
                    if status != 'NONE':
                        logger.debug(f"Пропускаем приз с статусом {status}: {prize_item.get('name')}")
                        continue

                    # Проверяем названия призов (и в корневом объекте, и в prize)
                    prize_name = prize_item.get('name', '').lower()
                    inner_prize = prize_item.get('prize', {})
                    inner_prize_name = inner_prize.get('name', '').lower()

                    # Проверяем что это звезды и что их можно активировать
                    is_stars = ('stars' in prize_name or 'star' in prize_name or
                               'stars' in inner_prize_name or 'star' in inner_prize_name)
                    is_claimable = inner_prize.get('isClaimable', False)

                    logger.debug(f"Проверяем приз: {prize_name or inner_prize_name} | is_stars={is_stars} | is_claimable={is_claimable}")

                    if is_stars and is_claimable:
                        total_stars_found += 1
                        user_roulette_prize_id = prize_item.get('userRoulettePrizeId')

                        logger.info(f"🌟 Найдены звезды для активации: {prize_name or inner_prize_name} (ID: {user_roulette_prize_id}) для {self.session_name}")

                        if user_roulette_prize_id:
                            success, message = await self.claim_roulette_prize(user_roulette_prize_id)
                            if success:
                                activated_count += 1
                                logger.info(f"Активированы звезды: {prize_name or inner_prize_name} для {self.session_name}")
                            else:
                                logger.warning(f"Не удалось активировать звезды {prize_name or inner_prize_name} для {self.session_name}: {message}")
                        else:
                            logger.error(f"Нет userRoulettePrizeId для приза {prize_name or inner_prize_name}")

                        await asyncio.sleep(PRIZE_ACTIVATION_DELAY)

                # Проверяем есть ли следующая страница
                if not inventory.get('hasNextPage', False):
                    break

                cursor = inventory.get('nextCursor')
                if not cursor:
                    logger.warning(f"hasNextPage=true но nextCursor пустой для {self.session_name}")
                    break

        except Exception as e:
            logger.error(f"Ошибка активации звезд для {self.session_name}: {e}")

        logger.info(f"Итого для {self.session_name}: найдено {total_stars_found} звезд, активировано {activated_count}")
        return activated_count, total_stars_found

    async def auto_exchange_cheap_gifts(self) -> Tuple[int, int, List[str]]:
        """
        Автоматически продает подарки ≤ пороговой стоимости
        Возвращает: (продано_подарков, всего_найдено, список_проданных)
        """
        if not AUTO_GIFT_EXCHANGE_ENABLED:
            return 0, 0, []

        exchanged_count = 0
        total_gifts_found = 0
        exchanged_gifts = []
        cursor = 0

        try:
            logger.info(f"🔍 Начинаем автопродажу подарков для {self.session_name} (порог: {AUTO_GIFT_EXCHANGE_THRESHOLD}⭐)")

            while True:
                # Получаем страницу инвентаря
                inventory = await self.get_roulette_inventory(cursor=cursor, limit=50, use_cache=True)
                if not inventory or not inventory.get('success'):
                    logger.debug(f"Не удалось получить инвентарь для продажи подарков {self.session_name}")
                    break

                prizes = inventory.get('prizes')
                if not prizes:
                    logger.debug(f"Нет призов в инвентаре для {self.session_name}")
                    break

                logger.info(f"📦 Обрабатываем {len(prizes)} призов в инвентаре для {self.session_name}")

                # Обрабатываем каждый приз
                for prize_item in prizes:
                    status = prize_item.get('status')
                    prize = prize_item.get('prize', {})
                    prize_name = prize.get('name', 'Неизвестный приз')

                    # Пропускаем звезды и вирусы сразу
                    if prize_name.endswith('Stars') or prize_name.endswith('Viruses'):
                        continue

                    # Логируем информацию о каждом подарке
                    exchange_price = prize.get('exchangePrice', 0)
                    is_claimable = prize.get('isClaimable', False)
                    is_exchangeable = prize.get('isExchangeable', False)
                    unlock_at = prize_item.get('unlockAt')
                    user_roulette_prize_id = prize_item.get('userRoulettePrizeId')

                    logger.info(f"🎁 Найден подарок: {prize_name}")
                    logger.info(f"  📊 Статус: {status}, Цена: {exchange_price}⭐, ID: {user_roulette_prize_id}")
                    logger.info(f"  ✅ Можно забрать: {is_claimable}, Можно обменять: {is_exchangeable}")
                    logger.info(f"  🔓 Время разблокировки: {unlock_at}")

                    # Логируем полную структуру данных подарка для отладки
                    logger.info(f"  🔍 Полная структура prize_item: {prize_item}")
                    logger.info(f"  🔍 Полная структура prize: {prize}")

                    # Подарки могут быть в статусе IN_PROGRESS и готовы к продаже
                    if status not in ['IN_PROGRESS', 'active']:
                        logger.info(f"  ❌ Пропускаем из-за статуса: {status} (нужен IN_PROGRESS или active)")
                        continue

                    total_gifts_found += 1

                    # Проверяем, можно ли продать по стоимости и доступности для обмена
                    if exchange_price <= AUTO_GIFT_EXCHANGE_THRESHOLD and (is_claimable or is_exchangeable):
                        logger.info(f"  💰 Подарок {prize_name} подходит для продажи ({exchange_price}⭐ ≤ {AUTO_GIFT_EXCHANGE_THRESHOLD}⭐)")

                        # Примечание: unlock_at - это время для вывода в Telegram, НЕ для продажи за звезды
                        if unlock_at:
                            try:
                                unlock_time = datetime.fromisoformat(unlock_at.replace('Z', '+00:00'))
                                logger.info(f"  📅 Время разблокировки для вывода: {unlock_time} (НЕ влияет на продажу за звезды)")
                            except Exception as e:
                                logger.warning(f"Ошибка парсинга времени разблокировки {unlock_at}: {e}")

                        # Подарки можно продавать за звезды сразу, независимо от времени разблокировки для вывода
                        if user_roulette_prize_id:
                            logger.info(f"  🔄 Попытка продать {prize_name} (ID: {user_roulette_prize_id})")

                            # Стратегия 1: Прямой обмен через exchangeRoulettePrizeToStarsBalance
                            success, message = await self.exchange_roulette_prize_to_stars(user_roulette_prize_id)

                            if success:
                                exchanged_count += 1
                                exchanged_gifts.append(f"{prize_name} ({exchange_price}⭐)")
                                logger.info(f"💰 ✅ ПРОДАН подарок {prize_name} за {exchange_price} звезд для {self.session_name}")
                                await asyncio.sleep(1)
                            else:
                                logger.warning(f"  ❌ Прямой обмен не удался: {message}")

                                # Стратегия 2: Fallback - попробуем claim, возможно автоматически обменяется
                                if "internal server error" in message.lower() or "422" in message:
                                    logger.info(f"  🔄 Пробуем fallback: claim подарка {prize_name}")

                                    claim_success, claim_message = await self.claim_roulette_prize(user_roulette_prize_id)
                                    if claim_success:
                                        # Проверяем, увеличился ли баланс звезд (возможно автоматический обмен)
                                        logger.info(f"  ✅ Claim успешен для {prize_name}: {claim_message}")

                                        # Считаем это успешным обменом через claim
                                        exchanged_count += 1
                                        exchanged_gifts.append(f"{prize_name} ({exchange_price}⭐) [via claim]")
                                        logger.info(f"💰 ✅ ОБМЕНЯН через claim: {prize_name} за {exchange_price} звезд для {self.session_name}")
                                        await asyncio.sleep(1)
                                    else:
                                        logger.warning(f"  ❌ И fallback claim не удался: {claim_message}")
                        else:
                            logger.warning(f"  ❌ Нет userRoulettePrizeId для {prize_name}")
                    else:
                        if exchange_price > AUTO_GIFT_EXCHANGE_THRESHOLD:
                            logger.info(f"  💸 Подарок {prize_name} слишком дорогой ({exchange_price}⭐ > {AUTO_GIFT_EXCHANGE_THRESHOLD}⭐)")
                        elif not (is_claimable or is_exchangeable):
                            logger.info(f"  🚫 Подарок {prize_name} недоступен для обмена (claimable={is_claimable}, exchangeable={is_exchangeable})")
                        else:
                            logger.info(f"  ❓ Подарок {prize_name} не подходит по неизвестной причине")

                # Проверяем есть ли еще страницы
                if not inventory.get('hasNextPage'):
                    break

                next_cursor = inventory.get('nextCursor')
                if next_cursor is None:
                    break

                cursor = next_cursor

        except Exception as e:
            logger.error(f"Ошибка автопродажи подарков для {self.session_name}: {e}")

        if exchanged_count > 0:
            logger.info(f"Автопродажа подарков для {self.session_name}: продано {exchanged_count} из {total_gifts_found}")

        return exchanged_count, total_gifts_found, exchanged_gifts

    async def exchange_roulette_prize_to_stars(self, user_roulette_prize_id: int) -> Tuple[bool, str]:
        """Обменивает приз из рулетки на звезды используя правильную мутацию точно как в DevTools"""
        query = """
        mutation exchangeRoulettePrizeToStarsBalance($input: ExchangeRoulettePrizeToStarsBalanceInput!) {
            exchangeRoulettePrizeToStarsBalance(input: $input) {
                success
                __typename
            }
        }
        """

        # ID должен быть числом, как в DevTools
        variables = {
            'input': {
                'userPrizeId': user_roulette_prize_id
            }
        }

        # Детальное логирование запроса перед отправкой
        logger.info(f"🔄 Exchange prize request для {self.session_name}:")
        logger.info(f"  📤 Query: {query.strip()}")
        logger.info(f"  📤 Variables: {variables}")
        logger.info(f"  📤 userPrizeId: {user_roulette_prize_id} (type: {type(user_roulette_prize_id)}) - как в DevTools")

        result = await self._make_graphql_request(query, variables, operation_name="exchangeRoulettePrizeToStarsBalance")

        # Детальное логирование ответа
        logger.info(f"📨 Exchange prize response: {result}")

        if result and 'data' in result and result['data'] and 'exchangeRoulettePrizeToStarsBalance' in result['data']:
            exchange_data = result['data']['exchangeRoulettePrizeToStarsBalance']
            if exchange_data.get('success'):
                message = f"Успешно обменян на звезды (ID: {user_roulette_prize_id})"
                logger.info(f"✅ Обмен успешен для {self.session_name}: {message}")
                return True, message
            else:
                # success = false, но без message поля
                message = f"Обмен неуспешен (success=false) для ID {user_roulette_prize_id}"
                logger.warning(f"❌ Ошибка обмена для {self.session_name}: {message}")
                return False, message
        elif result and 'errors' in result:
            error_msg = "; ".join([e.get('message', 'Неизвестная ошибка') for e in result['errors']])
            http_status = result.get('http_status', 'unknown')
            logger.warning(f"❌ GraphQL ошибка обмена для {self.session_name} (HTTP {http_status}): {error_msg}")
            return False, f"GraphQL ошибка (HTTP {http_status}): {error_msg}"
        elif result and 'http_status' in result:
            # Обрабатываем HTTP ошибки (например, 422)
            http_status = result['http_status']
            error_msg = result.get('error', result.get('raw_response', 'Неизвестная ошибка'))
            logger.warning(f"❌ HTTP ошибка обмена для {self.session_name}: {http_status} - {error_msg}")
            return False, f"HTTP {http_status}: {error_msg}"
        elif result is None:
            logger.warning(f"❌ Нет ответа от API при обмене для {self.session_name}")
            return False, "Нет ответа от API"
        else:
            logger.warning(f"❌ Неожиданный формат ответа API при обмене для {self.session_name}: {result}")
            return False, "Неожиданный формат ответа от API при обмене"

    async def click_tunnel(self) -> Tuple[bool, str]:
        """Пытается выполнить действие 'click tunnel' перед активацией призов"""
        # Попробуем несколько возможных вариантов
        possible_mutations = [
            "clickTunnel",
            "enterTunnel",
            "activateTunnel",
            "initTunnel",
            "startTunnel"
        ]

        for mutation_name in possible_mutations:
            try:
                # Простая мутация без параметров
                query = f"""
                mutation {mutation_name} {{
                    {mutation_name} {{
                        success
                        message
                        __typename
                    }}
                }}
                """

                result = await self._make_graphql_request(query, {}, operation_name=mutation_name)
                logger.debug(f"Попытка {mutation_name}: {result}")

                if result and 'data' in result and result['data'] and mutation_name in result['data']:
                    response_data = result['data'][mutation_name]
                    if response_data.get('success'):
                        logger.info(f"✅ Успешно выполнен {mutation_name} для {self.session_name}")
                        return True, f"Tunnel clicked via {mutation_name}"

                # Если нет ошибок - значит мутация существует, но возможно требует параметры
                if result and 'errors' in result:
                    errors = result['errors']
                    # Проверяем есть ли ошибка о том что мутация не найдена
                    for error in errors:
                        message = error.get('message', '').lower()
                        if 'cannot query field' in message or 'unknown field' in message:
                            continue  # Мутация не существует, пробуем следующую
                        else:
                            # Мутация существует, но есть другая ошибка
                            logger.info(f"Найдена мутация {mutation_name}, но есть ошибка: {message}")

            except Exception as e:
                logger.debug(f"Ошибка при попытке {mutation_name}: {e}")
                continue

        # Попробуем также queries
        possible_queries = [
            "getTunnel",
            "checkTunnel",
            "tunnelStatus"
        ]

        for query_name in possible_queries:
            try:
                query = f"""
                query {query_name} {{
                    {query_name} {{
                        success
                        message
                        __typename
                    }}
                }}
                """

                result = await self._make_graphql_request(query, {}, operation_name=query_name)
                logger.debug(f"Попытка query {query_name}: {result}")

                if result and 'data' in result and result['data'] and query_name in result['data']:
                    logger.info(f"✅ Найден query {query_name} для {self.session_name}")
                    return True, f"Tunnel checked via {query_name}"

            except Exception as e:
                logger.debug(f"Ошибка при попытке query {query_name}: {e}")
                continue

        # Попробуем простой HTTP запрос к roulette странице
        try:
            headers = self.session.headers.copy()
            headers['Referer'] = f'{WEBAPP_URL}/'

            async with self.session.get(f'{WEBAPP_URL}/roulette', headers=headers) as response:
                if response.status == 200:
                    logger.info(f"✅ Выполнен HTTP запрос к /roulette для {self.session_name}")
                    return True, "Tunnel accessed via HTTP request"
        except Exception as e:
            logger.debug(f"Ошибка HTTP запроса к roulette: {e}")

        # Попробуем получить информацию о состоянии игры
        try:
            # Возможно нужно просто получить пользователя чтобы "войти в игру"
            user_info = await self.get_user_info()
            if user_info:
                logger.info(f"✅ Получена информация о пользователе для {self.session_name}")
                return True, "Tunnel accessed via user info"
        except Exception as e:
            logger.debug(f"Ошибка получения user info: {e}")

        return False, "Не удалось найти tunnel action"

    async def detect_onboarding_required(self) -> Tuple[bool, List[str]]:
        """Определяет требуется ли onboarding для аккаунта и какие действия нужны"""
        required_actions = []

        try:
            # Пробуем активировать одну звезду чтобы получить ошибки onboarding
            inventory = await self.get_roulette_inventory(cursor=0, limit=5)
            if inventory and inventory.get('success') and inventory.get('prizes'):
                for prize_item in inventory['prizes']:
                    if (prize_item.get('status') == 'NONE' and
                        prize_item.get('prize', {}).get('isClaimable', False)):

                        user_roulette_prize_id = prize_item.get('userRoulettePrizeId')
                        if user_roulette_prize_id:
                            success, message = await self.claim_roulette_prize(user_roulette_prize_id)
                            if not success and message:
                                message_lower = message.lower()
                                if 'tunnel' in message_lower or 'tonnel' in message_lower:
                                    required_actions.append('tunnel')
                                if 'mini' in message_lower or 'app' in message_lower:
                                    required_actions.append('miniapp')
                                if 'portal' in message_lower:
                                    required_actions.append('portal')
                                logger.info(f"Обнаружено требование onboarding для {self.session_name}: {message}")
                            break

            # Проверяем статус пользователя
            user_info = await self.get_user_info()
            if user_info:
                # Проверяем флаги которые могут указывать на новых пользователей
                is_first_infection = user_info.get('isFirstInfection', False)
                onboarding_completed = user_info.get('onboardingCompleted', True)

                if is_first_infection or not onboarding_completed:
                    required_actions.append('user_onboarding')
                    logger.info(f"Пользователь {self.session_name} требует onboarding: first_infection={is_first_infection}, onboarding_completed={onboarding_completed}")

        except Exception as e:
            logger.error(f"Ошибка детекции onboarding для {self.session_name}: {e}")

        return len(required_actions) > 0, required_actions

    async def complete_tunnel_onboarding(self) -> Tuple[bool, str]:
        """Пытается автоматически пройти tunnel onboarding"""

        # Список возможных действий для прохождения tunnel onboarding
        tunnel_actions = [
            # Мутации для активации tunnel
            ("openTunnel", {}),
            ("activateTunnel", {}),
            ("startTunnel", {}),
            ("completeTutorial", {"step": "tunnel"}),
            ("completeOnboarding", {"action": "tunnel"}),

            # Мутации с параметрами
            ("updateUserProgress", {"action": "tunnel_opened"}),
            ("setUserFlag", {"flag": "tunnel_visited", "value": True}),
            ("markTutorialStep", {"step": "tunnel", "completed": True}),
        ]

        for action_name, variables in tunnel_actions:
            try:
                # Формируем GraphQL мутацию
                if variables:
                    # Генерируем переменные для GraphQL
                    var_declarations = []
                    for key, value in variables.items():
                        if isinstance(value, str):
                            var_declarations.append(f"${key}: String!")
                        elif isinstance(value, bool):
                            var_declarations.append(f"${key}: Boolean!")
                        else:
                            var_declarations.append(f"${key}: String!")

                    var_string = ", ".join(var_declarations)
                    args_string = ", ".join([f"{k}: ${k}" for k in variables.keys()])

                    query = f"""
                    mutation {action_name}({var_string}) {{
                        {action_name}({args_string}) {{
                            success
                            message
                            __typename
                        }}
                    }}
                    """
                else:
                    query = f"""
                    mutation {action_name} {{
                        {action_name} {{
                            success
                            message
                            __typename
                        }}
                    }}
                    """

                result = await self._make_graphql_request(query, variables, operation_name=action_name)
                logger.debug(f"Попытка {action_name}: {result}")

                if result and 'data' in result and result['data'] and action_name in result['data']:
                    response_data = result['data'][action_name]
                    if response_data.get('success'):
                        logger.info(f"✅ Tunnel onboarding завершен через {action_name} для {self.session_name}")
                        return True, f"Onboarding completed via {action_name}"

                # Проверяем есть ли полезная информация в ошибках
                if result and 'errors' in result:
                    for error in result['errors']:
                        message = error.get('message', '').lower()
                        if 'unknown field' not in message and 'cannot query field' not in message:
                            logger.info(f"Мутация {action_name} существует но требует других параметров: {message}")

            except Exception as e:
                logger.debug(f"Ошибка при попытке {action_name}: {e}")
                continue

        return False, "Не удалось автоматически завершить tunnel onboarding"

    async def launch_required_miniapps(self) -> Tuple[bool, str]:
        """Пытается запустить требуемые мини-приложения"""

        miniapp_actions = [
            # Попытки запуска различных мини-приложений
            ("launchMiniApp", {"app": "portals"}),
            ("launchMiniApp", {"app": "market"}),
            ("launchMiniApp", {"app": "portals_market"}),
            ("openPortal", {}),
            ("initializePortals", {}),
            ("activatePortals", {}),
        ]

        for action_name, variables in miniapp_actions:
            try:
                if variables:
                    var_declarations = []
                    for key, value in variables.items():
                        var_declarations.append(f"${key}: String!")

                    var_string = ", ".join(var_declarations)
                    args_string = ", ".join([f"{k}: ${k}" for k in variables.keys()])

                    query = f"""
                    mutation {action_name}({var_string}) {{
                        {action_name}({args_string}) {{
                            success
                            message
                            __typename
                        }}
                    }}
                    """
                else:
                    query = f"""
                    mutation {action_name} {{
                        {action_name} {{
                            success
                            message
                            __typename
                        }}
                    }}
                    """

                result = await self._make_graphql_request(query, variables, operation_name=action_name)
                logger.debug(f"Попытка miniapp {action_name}: {result}")

                if result and 'data' in result and result['data'] and action_name in result['data']:
                    response_data = result['data'][action_name]
                    if response_data.get('success'):
                        logger.info(f"✅ Miniapp запущен через {action_name} для {self.session_name}")
                        return True, f"Miniapp launched via {action_name}"

            except Exception as e:
                logger.debug(f"Ошибка при запуске miniapp {action_name}: {e}")
                continue

        return False, "Не удалось запустить требуемые мини-приложения"

    async def complete_full_onboarding(self) -> Tuple[bool, List[str]]:
        """Пытается автоматически пройти весь onboarding процесс"""
        completed_actions = []

        # 1. Определяем что нужно сделать
        requires_onboarding, required_actions = await self.detect_onboarding_required()

        if not requires_onboarding:
            return True, ["No onboarding required"]

        logger.info(f"Обнаружен onboarding для {self.session_name}: {required_actions}")

        # 2. Пытаемся выполнить tunnel actions
        if 'tunnel' in required_actions:
            success, message = await self.complete_tunnel_onboarding()
            if success:
                completed_actions.append(f"tunnel: {message}")
            else:
                logger.warning(f"Не удалось завершить tunnel onboarding для {self.session_name}: {message}")

        # 3. Пытаемся запустить мини-приложения
        if any(action in required_actions for action in ['miniapp', 'portal']):
            success, message = await self.launch_required_miniapps()
            if success:
                completed_actions.append(f"miniapps: {message}")
            else:
                logger.warning(f"Не удалось запустить miniapps для {self.session_name}: {message}")

        # 4. Общий onboarding
        if 'user_onboarding' in required_actions:
            # Пытаемся завершить общий onboarding
            try:
                query = """
                mutation completeOnboarding {
                    completeOnboarding {
                        success
                        message
                        __typename
                    }
                }
                """
                result = await self._make_graphql_request(query, {}, operation_name="completeOnboarding")
                if result and result.get('data', {}).get('completeOnboarding', {}).get('success'):
                    completed_actions.append("user_onboarding: completed")
            except Exception as e:
                logger.debug(f"Ошибка завершения общего onboarding: {e}")

        return len(completed_actions) > 0, completed_actions

    async def get_account_status(self) -> Dict[str, any]:
        """Получает подробный статус аккаунта для категоризации"""
        status = {
            'session_name': self.session_name,
            'ready_for_automation': False,
            'onboarding_required': False,
            'required_actions': [],
            'error_message': None,
            'user_flags': {},
            'can_access_inventory': False,
            'can_activate_prizes': False
        }

        try:
            # 1. Проверяем базовую информацию пользователя
            user_info = await self.get_user_info()
            if user_info:
                status['user_flags'] = {
                    'isFirstInfection': user_info.get('isFirstInfection', False),
                    'onboardingCompleted': user_info.get('onboardingCompleted', True),
                    'starsBalance': user_info.get('starsBalance', 0),
                    'balance': user_info.get('balance', 0)
                }

            # 2. Проверяем доступ к инвентарю
            try:
                inventory = await self.get_roulette_inventory(cursor=0, limit=5)
                if inventory and inventory.get('success'):
                    status['can_access_inventory'] = True

                    # 3. Проверяем возможность активации призов
                    prizes = inventory.get('prizes', [])
                    for prize_item in prizes:
                        if (prize_item.get('status') == 'NONE' and
                            prize_item.get('prize', {}).get('isClaimable', False)):

                            user_roulette_prize_id = prize_item.get('userRoulettePrizeId')
                            if user_roulette_prize_id:
                                success, message = await self.claim_roulette_prize(user_roulette_prize_id)
                                if success:
                                    status['can_activate_prizes'] = True
                                    status['ready_for_automation'] = True
                                    break
                                else:
                                    # Анализируем ошибку
                                    message_lower = message.lower() if message else ''
                                    if any(keyword in message_lower for keyword in ['tunnel', 'tonnel', 'mini', 'app', 'portal']):
                                        status['onboarding_required'] = True
                                        if 'tunnel' in message_lower or 'tonnel' in message_lower:
                                            status['required_actions'].append('tunnel')
                                        if 'mini' in message_lower or 'app' in message_lower:
                                            status['required_actions'].append('miniapp')
                                        if 'portal' in message_lower:
                                            status['required_actions'].append('portal')
                                    status['error_message'] = message
                                    break

                    # Если нет призов для проверки, но инвентарь доступен
                    if not prizes and status['can_access_inventory']:
                        status['ready_for_automation'] = True
                        status['can_activate_prizes'] = True

            except Exception as e:
                status['error_message'] = f"Ошибка доступа к инвентарю: {str(e)}"

            # 4. Проверяем флаги пользователя для onboarding
            if status['user_flags'].get('isFirstInfection') or not status['user_flags'].get('onboardingCompleted'):
                status['onboarding_required'] = True
                status['required_actions'].append('user_onboarding')

            # 5. Финальная оценка готовности
            if status['can_access_inventory'] and status['can_activate_prizes'] and not status['onboarding_required']:
                status['ready_for_automation'] = True
            elif status['onboarding_required'] and status['error_message']:
                status['ready_for_automation'] = False

        except Exception as e:
            status['error_message'] = f"Критическая ошибка: {str(e)}"
            status['ready_for_automation'] = False

        return status

    async def mark_test_spin_url_click(self, init_data: Optional[str] = None) -> Tuple[bool, str]:
        """Выполняет markTestSpinUrlClick мутацию для регистрации клика по testSpin ссылке"""
        query = """
        mutation markTestSpinUrlClick($initData: String) {
            markTestSpinUrlClick(initData: $initData) {
                success
                __typename
            }
        }
        """

        variables = {}
        if init_data:
            variables['initData'] = init_data

        result = await self._make_graphql_request(query, variables, operation_name="markTestSpinUrlClick")

        logger.debug(f"markTestSpinUrlClick response: {result}")

        if result and 'data' in result and result['data'] and 'markTestSpinUrlClick' in result['data']:
            click_data = result['data']['markTestSpinUrlClick']
            if click_data.get('success'):
                logger.info(f"✅ markTestSpinUrlClick выполнен успешно для {self.session_name}")
                return True, "URL click marked successfully"
            else:
                logger.warning(f"⚠️ markTestSpinUrlClick вернул success=false для {self.session_name}")
                return False, "API returned success=false"
        elif result and 'errors' in result:
            error = result['errors'][0] if result['errors'] else {}
            message = error.get('message', 'Неизвестная ошибка')
            logger.warning(f"⚠️ markTestSpinUrlClick не поддерживается или ошибка для {self.session_name}: {message}")
            return False, f"GraphQL error: {message}"
        else:
            logger.error(f"❌ Неожиданный формат ответа markTestSpinUrlClick для {self.session_name}")
            return False, "Unexpected response format"

    async def mark_test_spin_tunnel_click(self) -> Tuple[bool, str]:
        """Выполняет markTestSpinTonnelClick мутацию для прохождения tunnel onboarding"""
        query = """
        mutation markTestSpinTonnelClick {
            markTestSpinTonnelClick {
                success
                __typename
            }
        }
        """

        result = await self._make_graphql_request(query, {}, operation_name="markTestSpinTonnelClick")

        logger.debug(f"markTestSpinTonnelClick response: {result}")

        if result and 'data' in result and result['data'] and 'markTestSpinTonnelClick' in result['data']:
            tunnel_data = result['data']['markTestSpinTonnelClick']
            if tunnel_data.get('success'):
                logger.info(f"✅ markTestSpinTonnelClick выполнен успешно для {self.session_name}")
                return True, "Tunnel click marked successfully"
            else:
                logger.warning(f"⚠️ markTestSpinTonnelClick вернул success=false для {self.session_name}")
                return False, "API returned success=false"
        elif result and 'errors' in result:
            error = result['errors'][0] if result['errors'] else {}
            message = error.get('message', 'Неизвестная ошибка')
            logger.error(f"❌ Ошибка markTestSpinTonnelClick для {self.session_name}: {message}")
            return False, f"GraphQL error: {message}"
        else:
            logger.error(f"❌ Неожиданный формат ответа markTestSpinTonnelClick для {self.session_name}")
            return False, "Unexpected response format"

    async def mark_test_spin_portal_click(self) -> Tuple[bool, str]:
        """Выполняет markTestSpinPortalClick мутацию для прохождения portal onboarding"""
        query = """
        mutation markTestSpinPortalClick {
            markTestSpinPortalClick {
                success
                __typename
            }
        }
        """

        result = await self._make_graphql_request(query, {}, operation_name="markTestSpinPortalClick")

        logger.debug(f"markTestSpinPortalClick response: {result}")

        if result and 'data' in result and result['data'] and 'markTestSpinPortalClick' in result['data']:
            portal_data = result['data']['markTestSpinPortalClick']
            if portal_data.get('success'):
                logger.info(f"✅ markTestSpinPortalClick выполнен успешно для {self.session_name}")
                return True, "Portal click marked successfully"
            else:
                logger.warning(f"⚠️ markTestSpinPortalClick вернул success=false для {self.session_name}")
                return False, "API returned success=false"
        elif result and 'errors' in result:
            error = result['errors'][0] if result['errors'] else {}
            message = error.get('message', 'Неизвестная ошибка')
            logger.error(f"❌ Ошибка markTestSpinPortalClick для {self.session_name}: {message}")
            return False, f"GraphQL error: {message}"
        else:
            logger.error(f"❌ Неожиданный формат ответа markTestSpinPortalClick для {self.session_name}")
            return False, "Unexpected response format"