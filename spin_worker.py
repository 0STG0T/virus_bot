import asyncio
import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime, timedelta
from session_manager import SessionManager
from virus_api import VirusAPI
from webapp_auth import WebAppAuth
from config import (MAX_CONCURRENT_SESSIONS, DELAY_BETWEEN_ACCOUNTS, HIGH_VALUE_THRESHOLD,
                   MIN_REQUEST_INTERVAL, SUBSCRIPTION_DELAY,
                   GIFT_EXCHANGE_ON_BALANCE_CHECK, AUTO_GIFT_EXCHANGE_ENABLED,
                   GIFT_EXCHANGE_AFTER_SPIN, REDUCED_LOGGING_MODE)
import config
from telethon.tl.functions.channels import JoinChannelRequest
import time

logger = logging.getLogger(__name__)

class SpinWorker:
    def __init__(self, session_manager: SessionManager, notification_callback=None):
        self.session_manager = session_manager
        self.notification_callback = notification_callback
        self.last_request_time = {}
        self.min_request_interval = MIN_REQUEST_INTERVAL

    async def complete_prerequisites(self, api: VirusAPI, session_name: str, client) -> Tuple[bool, str]:
        try:
            # Попробуем выполнить задачи по рефералам
            await api.complete_referral_tasks()
            await asyncio.sleep(1)  # Уменьшено для скорости

            # Попробуем выполнить задачи по подпискам
            await api.complete_subscription_tasks()
            await asyncio.sleep(1)

            # Проверим еще раз доступность спина
            can_spin, reason = await api.check_spin_availability()
            if not can_spin:
                return False, reason

            return True, "Все условия выполнены"

        except Exception as e:
            logger.error(f"Ошибка выполнения предварительных условий для {session_name}: {e}")
            return False, f"Ошибка: {str(e)}"

    async def handle_subscription_requirement(self, client, channel_info: Dict) -> bool:
        """Обрабатывает требование подписки на канал"""
        try:
            username = channel_info.get('username')
            url = channel_info.get('url')

            # СНАЧАЛА пробуем по ссылке (важно для приватных каналов)
            if url and 't.me/' in url:
                try:
                    logger.info(f"Подписываюсь по ссылке: {url}")

                    # Проверяем тип ссылки
                    if '/+' in url or '/joinchat/' in url:
                        # Приватная ссылка-инвайт
                        logger.info(f"Обнаружена приватная ссылка-инвайт")

                        # Извлекаем хэш из ссылки
                        # Формат: https://t.me/+HASH или https://t.me/joinchat/HASH
                        if '/+' in url:
                            invite_hash = url.split('/+')[1].split('?')[0]
                        else:
                            invite_hash = url.split('/joinchat/')[1].split('?')[0]

                        logger.info(f"Инвайт хэш: {invite_hash}")

                        # Импортируем функцию для присоединения по инвайту
                        from telethon.tl.functions.messages import ImportChatInviteRequest

                        # Присоединяемся по инвайт-ссылке
                        result = await client(ImportChatInviteRequest(invite_hash))
                        logger.info(f"Успешно присоединился по инвайт-ссылке: {result}")
                        await asyncio.sleep(SUBSCRIPTION_DELAY)
                        return True
                    else:
                        # Публичная ссылка типа t.me/channel_name
                        channel_name = url.split('t.me/')[1].split('?')[0].split('/')[0]
                        if channel_name.startswith('@'):
                            entity = await client.get_entity(channel_name)
                        else:
                            entity = await client.get_entity(f"@{channel_name}")
                        await client(JoinChannelRequest(entity))
                        logger.info(f"Успешно подписался через публичную ссылку: {channel_name}")
                        await asyncio.sleep(SUBSCRIPTION_DELAY)
                        return True
                except Exception as e:
                    logger.error(f"Не удалось подписаться по ссылке {url}: {e}")

            # Если ссылка не сработала, пробуем по username
            if username:
                logger.info(f"Подписываюсь на канал @{username}")
                try:
                    entity = await client.get_entity(f"@{username}")
                    await client(JoinChannelRequest(entity))
                    logger.info(f"Успешно подписался на @{username}")
                    await asyncio.sleep(SUBSCRIPTION_DELAY)
                    return True
                except Exception as e:
                    logger.error(f"Не удалось подписаться на @{username}: {e}")

            return False

        except Exception as e:
            logger.error(f"Ошибка обработки требования подписки: {e}")
            return False

    async def perform_single_spin(self, session_name: str) -> Dict[str, any]:
        result = {
            'session_name': session_name,
            'success': False,
            'message': '',
            'reward': None,
            'high_value_item': False,
            'stars_activated': 0
        }

        try:
            # Простое ограничение частоты запросов
            current_time = time.time()
            if session_name in self.last_request_time:
                time_diff = current_time - self.last_request_time[session_name]
                if time_diff < self.min_request_interval:
                    await asyncio.sleep(self.min_request_interval - time_diff)

            self.last_request_time[session_name] = time.time()

            client = await self.session_manager.create_client(session_name)
            if not client:
                result['message'] = 'Не удалось создать клиент'
                return result

            auth = WebAppAuth(client, session_name)
            auth_data = await auth.get_webapp_data()

            if not auth_data:
                result['message'] = 'Не удалось получить данные авторизации'
                await client.disconnect()
                return result

            api = VirusAPI(session_name)
            await api.set_auth_data(auth_data)

            can_spin, reason = await api.check_spin_availability()
            if not can_spin:
                if "24 часа" in reason:
                    result['message'] = 'нельзя сделать фри спин так как с прошлого не прошло 24 часа'
                elif "рефки" in reason or "подписки" in reason:
                    prerequisites_ok, _ = await self.complete_prerequisites(api, session_name, client)
                    if not prerequisites_ok:
                        result['message'] = f'нельзя сделать фри спин так как не выполнены какие либо условия ({reason})'
                        await api.close_session()
                        await client.disconnect()
                        return result

                    can_spin, reason = await api.check_spin_availability()
                    if not can_spin:
                        result['message'] = f'нельзя сделать фри спин ({reason})'
                        await api.close_session()
                        await client.disconnect()
                        return result
                else:
                    result['message'] = f'нельзя сделать фри спин ({reason})'
                    await api.close_session()
                    await client.disconnect()
                    return result

            # === ОСНОВНАЯ ЛОГИКА ФРИ СПИНА ===
            logger.info(f"🎰 [{session_name}] === НАЧАЛО ПРОЦЕССА ФРИ СПИНА ===")

            # Попытка 1: Первый спин
            logger.info(f"🎰 [{session_name}] Попытка #1: Выполняю первый спин...")
            spin_success, spin_message, reward = await api.perform_spin()
            logger.info(f"📊 [{session_name}] Попытка #1 результат: success={spin_success}, message='{spin_message}', reward={reward}")

            # Если спин неуспешен - пытаемся исправить и повторить до 3 раз
            attempt = 1
            while not spin_success and attempt < 4:
                attempt += 1
                logger.warning(f"⚠️ [{session_name}] Попытка #{attempt}: Спин неуспешен, анализирую ошибку...")

                handled = False

                # Обработка 1: Требуется клик по тестовой ссылке
                if "Требуется клик по тестовой ссылке" in spin_message:
                    logger.info(f"🔗 [{session_name}] Попытка #{attempt}: Обнаружена ошибка 'Требуется клик по тестовой ссылке'")

                    if isinstance(reward, dict) and 'link' in reward:
                        test_url = reward['link']
                        logger.info(f"🔗 [{session_name}] Попытка #{attempt}: Извлечена ссылка: {test_url}")

                        # Проверяем тип ссылки: канал или WebApp
                        if '/dapp' in test_url or 'startapp=' in test_url:
                            # Это WebApp - открываем через click_test_spin_url
                            logger.info(f"🔗 [{session_name}] Попытка #{attempt}: Обнаружен WebApp - выполняю клик по ссылке...")
                            click_success, init_data = await auth.click_test_spin_url(test_url)
                            logger.info(f"🔗 [{session_name}] Попытка #{attempt}: Клик завершен: {click_success}")

                            if click_success:
                                if init_data:
                                    logger.info(f"📡 [{session_name}] Попытка #{attempt}: Получен init_data от WebApp")
                                    logger.info(f"📝 [{session_name}] Попытка #{attempt}: Init data (первые 50 символов): {init_data[:50]}...")
                                else:
                                    logger.info(f"ℹ️ [{session_name}] Попытка #{attempt}: WebApp открылся без init_data")

                                # Регистрируем клик через GraphQL API (как для каналов)
                                task_id = reward.get('task_id') if isinstance(reward, dict) else None

                                if task_id:
                                    logger.info(f"🌐 [{session_name}] Попытка #{attempt}: Регистрирую клик WebApp для задачи {task_id}...")
                                    click_registered, click_message = await api.mark_test_spin_task_click(task_id)

                                    if click_registered:
                                        logger.info(f"✅ [{session_name}] Попытка #{attempt}: Клик WebApp зарегистрирован: {click_message}")
                                    else:
                                        logger.warning(f"⚠️ [{session_name}] Попытка #{attempt}: Не удалось зарегистрировать клик WebApp: {click_message}")
                                else:
                                    logger.warning(f"⚠️ [{session_name}] Попытка #{attempt}: task_id не найден в reward для WebApp")

                                logger.info(f"🔗 [{session_name}] Попытка #{attempt}: Жду 2 секунды перед повторным спином...")
                                await asyncio.sleep(2)
                                logger.info(f"🎰 [{session_name}] Попытка #{attempt}: Повторяю спин после клика...")
                                spin_success, spin_message, reward = await api.perform_spin()
                                logger.info(f"📊 [{session_name}] Попытка #{attempt} результат: success={spin_success}, message='{spin_message}', reward={reward}")
                                handled = True
                            else:
                                logger.error(f"❌ [{session_name}] Попытка #{attempt}: Не удалось выполнить клик на WebApp")
                        else:
                            # Это обычная ссылка на канал - подписываемся
                            logger.info(f"📡 [{session_name}] Попытка #{attempt}: Обнаружен канал - подписываюсь...")

                            # Формируем данные канала для handle_subscription_requirement
                            channel_info = {
                                'url': test_url,
                                'username': None  # Извлечем из URL
                            }

                            # Извлекаем username из URL если есть
                            if 't.me/' in test_url:
                                username = test_url.split('t.me/')[1].split('?')[0].split('/')[0]
                                if username and not username.startswith('+'):
                                    channel_info['username'] = username
                                    logger.info(f"📡 [{session_name}] Попытка #{attempt}: Извлечен username канала: @{username}")

                            subscription_success = await self.handle_subscription_requirement(client, channel_info)
                            logger.info(f"📡 [{session_name}] Попытка #{attempt}: Подписка завершена: {subscription_success}")

                            if subscription_success:
                                # Регистрируем клик через GraphQL API
                                task_id = reward.get('task_id') if isinstance(reward, dict) else None

                                if task_id:
                                    logger.info(f"🌐 [{session_name}] Попытка #{attempt}: Регистрирую клик для задачи {task_id}...")
                                    click_success, click_message = await api.mark_test_spin_task_click(task_id)

                                    if click_success:
                                        logger.info(f"✅ [{session_name}] Попытка #{attempt}: Клик зарегистрирован: {click_message}")
                                    else:
                                        logger.warning(f"⚠️ [{session_name}] Попытка #{attempt}: Не удалось зарегистрировать клик: {click_message}")
                                else:
                                    logger.warning(f"⚠️ [{session_name}] Попытка #{attempt}: task_id не найден в reward")

                                logger.info(f"📡 [{session_name}] Попытка #{attempt}: Жду 2 секунды после регистрации клика...")
                                await asyncio.sleep(2)
                                logger.info(f"🎰 [{session_name}] Попытка #{attempt}: Повторяю спин после подписки...")
                                spin_success, spin_message, reward = await api.perform_spin()
                                logger.info(f"📊 [{session_name}] Попытка #{attempt} результат: success={spin_success}, message='{spin_message}', reward={reward}")
                                handled = True
                            else:
                                logger.error(f"❌ [{session_name}] Попытка #{attempt}: Не удалось подписаться на канал")
                    else:
                        logger.error(f"❌ [{session_name}] Попытка #{attempt}: reward не содержит ссылку: {reward}")

                # Обработка 2: Требуется подписка на канал
                elif "Требуется подписка на канал" in spin_message:
                    logger.info(f"📡 [{session_name}] Попытка #{attempt}: Обнаружена ошибка 'Требуется подписка на канал'")

                    if isinstance(reward, dict):
                        logger.info(f"📡 [{session_name}] Попытка #{attempt}: Данные подписки: {reward}")
                        logger.info(f"📡 [{session_name}] Попытка #{attempt}: Выполняю подписку на канал...")

                        subscription_success = await self.handle_subscription_requirement(client, reward)
                        logger.info(f"📡 [{session_name}] Попытка #{attempt}: Подписка завершена: {subscription_success}")

                        if subscription_success:
                            logger.info(f"📡 [{session_name}] Попытка #{attempt}: Жду 3 секунды для применения подписки...")
                            await asyncio.sleep(3)
                            logger.info(f"🎰 [{session_name}] Попытка #{attempt}: Повторяю спин после подписки...")
                            spin_success, spin_message, reward = await api.perform_spin()
                            logger.info(f"📊 [{session_name}] Попытка #{attempt} результат: success={spin_success}, message='{spin_message}', reward={reward}")
                            handled = True
                        else:
                            logger.error(f"❌ [{session_name}] Попытка #{attempt}: Не удалось подписаться на канал")
                    else:
                        logger.error(f"❌ [{session_name}] Попытка #{attempt}: reward не является dict: {reward}")

                # Если ошибка не была обработана - выходим
                if not handled:
                    logger.error(f"❌ [{session_name}] Попытка #{attempt}: Ошибка не может быть обработана: '{spin_message}'")
                    logger.error(f"❌ [{session_name}] Попытка #{attempt}: Прерываю цикл попыток")
                    break

            # Финальная проверка результата
            if not spin_success:
                logger.error(f"❌ [{session_name}] === ФИНАЛ: Спин неуспешен после {attempt} попыток ===")
                logger.error(f"❌ [{session_name}] Финальная ошибка: '{spin_message}'")
                result['message'] = f'нельзя сделать фри спин ({spin_message})'
                await api.close_session()
                await client.disconnect()
                return result

            logger.info(f"✅ [{session_name}] === УСПЕХ: Спин выполнен успешно! ===")

            if reward:
                _, reward_desc, high_value, is_gift = await api.process_reward(reward)
                result['reward'] = reward_desc
                result['high_value_item'] = high_value

                # Уведомляем о ВСЕХ подарках из фри спинов в формате: сессия - подарок - ценность
                if is_gift and self.notification_callback:
                    # Извлекаем стоимость подарка из reward
                    exchange_price = reward.get('exchangePrice', 0)
                    gift_name = reward.get('name', 'Неизвестный подарок')

                    if high_value:
                        await self.notification_callback(
                            f"💎 ФРИ СПИН | {session_name} | {gift_name} | {exchange_price}⭐"
                        )
                    else:
                        await self.notification_callback(
                            f"🎁 ФРИ СПИН | {session_name} | {gift_name} | {exchange_price}⭐"
                        )

            # Проверяем и логируем решение об активации звезд
            try:
                should_activate, balance_stars, inventory_stars, can_activate, reason = await api.should_activate_stars()
                if should_activate:
                    logger.info(f"✅ [{session_name}] АКТИВАЦИЯ НУЖНА: баланс {balance_stars}⭐, инвентарь {inventory_stars}⭐, можно активировать ~{can_activate}⭐ ({reason})")
                else:
                    logger.info(f"⏸️ [{session_name}] АКТИВАЦИЯ НЕ НУЖНА: баланс {balance_stars}⭐, инвентарь {inventory_stars}⭐ ({reason})")
            except Exception as e:
                logger.error(f"Ошибка проверки активации для {session_name}: {e}")

            # Активируем все звезды из инвентаря после успешного спина
            try:
                activated_count, total_found, stars_value = await api.activate_all_stars()
                if activated_count > 0:
                    logger.info(f"✅ Активировано {activated_count} из {total_found} звезд (~{stars_value}⭐) для {session_name}")
                    result['stars_activated'] = activated_count
                    result['stars_value_activated'] = stars_value
                elif total_found > 0:
                    logger.info(f"⏸️ Найдено {total_found} звезд (~{stars_value}⭐), но активировано 0 для {session_name} (в инвентаре <= 100⭐)")
            except Exception as e:
                logger.error(f"Ошибка активации звезд для {session_name}: {e}")

            # Автоматическая продажа дешевых подарков после спина
            if config.GIFT_EXCHANGE_AFTER_SPIN and config.AUTO_GIFT_EXCHANGE_ENABLED:
                try:
                    exchanged_count, total_gifts, exchanged_list = await api.auto_exchange_cheap_gifts()
                    if exchanged_count > 0:
                        logger.info(f"Автопродажа после спина {session_name}: продано {exchanged_count} из {total_gifts} подарков")
                        result['gifts_exchanged'] = exchanged_count
                        result['gifts_exchanged_list'] = exchanged_list
                except Exception as e:
                    logger.error(f"Ошибка автопродажи подарков после спина {session_name}: {e}")

            result['success'] = True
            result['message'] = f'фри спин был успешен. выпало: {result["reward"] or "ничего"}'

            await api.close_session()
            await client.disconnect()

        except Exception as e:
            logger.error(f"Ошибка выполнения спина для {session_name}: {e}")
            result['message'] = f'нельзя сделать фри спин (ошибка: {str(e)})'

        return result

    async def perform_spins_batch(self, session_names: List[str], progress_callback=None) -> List[Dict]:
        # Убираем семафор - выполняем все спины параллельно без ограничений
        results = []
        completed = [0]  # Счетчик завершенных операций
        total = len(session_names)

        async def spin_without_limit(session_name: str):
            result = await self.perform_single_spin(session_name)
            await asyncio.sleep(DELAY_BETWEEN_ACCOUNTS)

            # Обновляем прогресс
            completed[0] += 1
            if progress_callback:
                await progress_callback(completed[0], total)

            return result

        tasks = [spin_without_limit(name) for name in session_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    'session_name': session_names[i],
                    'success': False,
                    'message': f'Ошибка: {str(result)}',
                    'reward': None,
                    'high_value_item': False,
                    'stars_activated': 0
                })
            else:
                processed_results.append(result)

        return processed_results

    async def get_all_balances(self) -> List[Tuple[str, int]]:
        session_names = await self.session_manager.get_session_names()
        balances = []

        async def get_balance_without_limit(session_name: str):
            try:
                # Простое ограничение частоты запросов
                current_time = time.time()
                if session_name in self.last_request_time:
                    time_diff = current_time - self.last_request_time[session_name]
                    if time_diff < self.min_request_interval:
                        await asyncio.sleep(self.min_request_interval - time_diff)

                self.last_request_time[session_name] = time.time()

                client = await self.session_manager.create_client(session_name)
                if not client:
                    return session_name, 0

                auth = WebAppAuth(client, session_name)
                auth_data = await auth.get_webapp_data()

                if not auth_data:
                    await client.disconnect()
                    return session_name, 0

                api = VirusAPI(session_name)
                await api.set_auth_data(auth_data)

                stars, _ = await api.get_balance()

                await api.close_session()
                await client.disconnect()

                return session_name, stars

            except Exception as e:
                logger.error(f"Ошибка получения баланса для {session_name}: {e}")
                return session_name, 0

        tasks = [get_balance_without_limit(name) for name in session_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, tuple):
                balances.append(result)
            else:
                logger.error(f"Ошибка получения баланса: {result}")

        balances.sort(key=lambda x: x[1], reverse=True)
        return balances

    async def activate_all_stars_batch(self) -> List[Dict]:
        """Активирует все звезды из инвентаря для всех аккаунтов"""
        session_names = await self.session_manager.get_session_names()
        # Убираем семафор - все операции параллельно
        results = []

        async def activate_stars_without_limit(session_name: str):
            
                result = {
                    'session_name': session_name,
                    'success': False,
                    'message': '',
                    'activated_count': 0,
                    'total_found': 0
                }

                try:
                    # Простое ограничение частоты запросов
                    current_time = time.time()
                    if session_name in self.last_request_time:
                        time_diff = current_time - self.last_request_time[session_name]
                        if time_diff < self.min_request_interval:
                            await asyncio.sleep(self.min_request_interval - time_diff)

                    self.last_request_time[session_name] = time.time()

                    client = await self.session_manager.create_client(session_name)
                    if not client:
                        result['message'] = 'Не удалось создать клиент'
                        return result

                    auth = WebAppAuth(client, session_name)
                    auth_data = await auth.get_webapp_data()

                    if not auth_data:
                        result['message'] = 'Не удалось получить данные авторизации'
                        await client.disconnect()
                        return result

                    api = VirusAPI(session_name)
                    await api.set_auth_data(auth_data)

                    # Активируем все звезды
                    activated_count, total_found, stars_value = await api.activate_all_stars()

                    result['success'] = True
                    result['activated_count'] = activated_count
                    result['total_found'] = total_found
                    result['stars_value'] = stars_value
                    if activated_count > 0:
                        result['message'] = f'Активировано {activated_count} из {total_found} звезд (~{stars_value}⭐)'
                    else:
                        if total_found > 0:
                            result['message'] = f'Найдено {total_found} звезд (~{stars_value}⭐), но активировано 0 (в инвентаре < 100⭐)'
                        else:
                            result['message'] = 'Нет звезд в инвентаре для активации'

                    await api.close_session()
                    await client.disconnect()

                except Exception as e:
                    logger.error(f"Ошибка активации звезд для {session_name}: {e}")
                    result['message'] = f'Ошибка: {str(e)}'

                return result

        tasks = [activate_stars_without_limit(name) for name in session_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    'session_name': session_names[i],
                    'success': False,
                    'message': f'Ошибка: {str(result)}',
                    'activated_count': 0,
                    'total_found': 0
                })
            else:
                processed_results.append(result)

        return processed_results

    async def perform_paid_spins_batch(self, session_names: List[str]) -> List[Dict]:
        """Выполняет платные спины для аккаунтов с балансом >= 225 звезд"""
        # Убираем семафор - все операции параллельно
        results = []

        async def paid_spin_without_limit(session_name: str):
            
                result = await self.perform_single_paid_spin(session_name)
                await asyncio.sleep(DELAY_BETWEEN_ACCOUNTS)
                return result

        tasks = [paid_spin_without_limit(name) for name in session_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    'session_name': session_names[i],
                    'success': False,
                    'message': f'Ошибка: {str(result)}',
                    'reward': None,
                    'high_value_item': False,
                    'stars_activated': 0
                })
            else:
                processed_results.append(result)

        return processed_results

    async def perform_single_paid_spin(self, session_name: str) -> Dict[str, any]:
        """Выполняет платный спин для одного аккаунта если баланс >= 225 звезд"""
        result = {
            'session_name': session_name,
            'success': False,
            'message': '',
            'reward': None,
            'high_value_item': False,
            'stars_activated': 0
        }

        try:
            # Простое ограничение частоты запросов
            current_time = time.time()
            if session_name in self.last_request_time:
                time_diff = current_time - self.last_request_time[session_name]
                if time_diff < self.min_request_interval:
                    await asyncio.sleep(self.min_request_interval - time_diff)

            self.last_request_time[session_name] = time.time()

            client = await self.session_manager.create_client(session_name)
            if not client:
                result['message'] = 'Не удалось создать клиент'
                return result

            auth = WebAppAuth(client, session_name)
            auth_data = await auth.get_webapp_data()

            if not auth_data:
                result['message'] = 'Не удалось получить данные авторизации'
                await client.disconnect()
                return result

            api = VirusAPI(session_name)
            await api.set_auth_data(auth_data)

            # Проверяем баланс для платного спина
            can_spin, reason = await api.can_perform_paid_spin(225)  # Требуем 225 звезд для страховки
            if not can_spin:
                result['message'] = f'пропущен - {reason}'
                await api.close_session()
                await client.disconnect()
                return result

            # Пытаемся сделать платный спин
            # Попробуем разные типы спинов
            for spin_type in ["PAID", "X200", "PREMIUM"]:
                spin_success, spin_message, reward = await api.perform_paid_spin(spin_type)
                if spin_success:
                    break
                # Если первый тип не сработал, логируем и пробуем следующий
                logger.debug(f"Не удалось сделать платный спин типа {spin_type} для {session_name}: {spin_message}")

            if not spin_success:
                result['message'] = f'не удалось сделать платный спин ({spin_message})'
                await api.close_session()
                await client.disconnect()
                return result

            if reward:
                _, reward_desc, high_value, is_gift = await api.process_reward(reward)
                result['reward'] = reward_desc
                result['high_value_item'] = high_value

                # Уведомляем о всех подарках с платных спинов в формате: сессия - подарок - ценность
                if is_gift and self.notification_callback:
                    # Извлекаем стоимость подарка из reward
                    exchange_price = reward.get('exchangePrice', 0)
                    gift_name = reward.get('name', 'Неизвестный подарок')

                    if high_value:
                        await self.notification_callback(
                            f"💎 ПЛАТНЫЙ СПИН | {session_name} | {gift_name} | {exchange_price}⭐"
                        )
                    else:
                        await self.notification_callback(
                            f"🎁 ПЛАТНЫЙ СПИН | {session_name} | {gift_name} | {exchange_price}⭐"
                        )

            # Проверяем и логируем решение об активации звезд
            try:
                should_activate, balance_stars, inventory_stars, can_activate, reason = await api.should_activate_stars()
                if should_activate:
                    logger.info(f"✅ [{session_name}] ПЛАТНЫЙ СПИН - АКТИВАЦИЯ НУЖНА: баланс {balance_stars}⭐, инвентарь {inventory_stars}⭐, можно активировать ~{can_activate}⭐ ({reason})")
                else:
                    logger.info(f"⏸️ [{session_name}] ПЛАТНЫЙ СПИН - АКТИВАЦИЯ НЕ НУЖНА: баланс {balance_stars}⭐, инвентарь {inventory_stars}⭐ ({reason})")
            except Exception as e:
                logger.error(f"Ошибка проверки активации для {session_name}: {e}")

            # Активируем все звезды из инвентаря после успешного платного спина
            try:
                activated_count, total_found, stars_value = await api.activate_all_stars()
                if activated_count > 0:
                    logger.info(f"✅ Активировано {activated_count} из {total_found} звезд (~{stars_value}⭐) для {session_name} (платный спин)")
                    result['stars_activated'] = activated_count
                    result['stars_value_activated'] = stars_value
                elif total_found > 0:
                    logger.info(f"⏸️ Найдено {total_found} звезд (~{stars_value}⭐), но активировано 0 для {session_name} (в инвентаре <= 100⭐)")
            except Exception as e:
                logger.error(f"Ошибка активации звезд после платного спина для {session_name}: {e}")

            # Автоматическая продажа дешевых подарков после платного спина
            if config.GIFT_EXCHANGE_AFTER_SPIN and config.AUTO_GIFT_EXCHANGE_ENABLED:
                try:
                    exchanged_count, total_gifts, exchanged_list = await api.auto_exchange_cheap_gifts()
                    if exchanged_count > 0:
                        logger.info(f"Автопродажа после платного спина {session_name}: продано {exchanged_count} из {total_gifts} подарков")
                        result['gifts_exchanged'] = exchanged_count
                        result['gifts_exchanged_list'] = exchanged_list
                except Exception as e:
                    logger.error(f"Ошибка автопродажи подарков после платного спина {session_name}: {e}")

            result['success'] = True
            result['message'] = f'платный спин успешен. выпало: {result["reward"] or "ничего"}'

            await api.close_session()
            await client.disconnect()

        except Exception as e:
            logger.error(f"Ошибка выполнения платного спина для {session_name}: {e}")
            result['message'] = f'не удалось сделать платный спин (ошибка: {str(e)})'

        return result

    async def prepare_all_accounts_batch(self) -> List[Dict]:
        """Проверяет и подготавливает все аккаунты (проходит onboarding)"""
        session_names = await self.session_manager.get_session_names()
        # Убираем семафор - все операции параллельно
        results = []

        async def prepare_account_without_limit(session_name: str):
            
                result = await self.prepare_single_account(session_name)
                await asyncio.sleep(DELAY_BETWEEN_ACCOUNTS)
                return result

        tasks = [prepare_account_without_limit(name) for name in session_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        processed_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                processed_results.append({
                    'session_name': session_names[i],
                    'success': False,
                    'message': f'Ошибка: {str(result)}',
                    'onboarding_actions': []
                })
            else:
                processed_results.append(result)

        return processed_results

    async def prepare_single_account(self, session_name: str) -> Dict[str, any]:
        """Подготавливает один аккаунт (проходит onboarding если нужно)"""
        result = {
            'session_name': session_name,
            'success': False,
            'message': '',
            'onboarding_actions': []
        }

        try:
            # Простое ограничение частоты запросов
            current_time = time.time()
            if session_name in self.last_request_time:
                time_diff = current_time - self.last_request_time[session_name]
                if time_diff < self.min_request_interval:
                    await asyncio.sleep(self.min_request_interval - time_diff)

            self.last_request_time[session_name] = time.time()

            client = await self.session_manager.create_client(session_name)
            if not client:
                result['message'] = 'Не удалось создать клиент'
                return result

            auth = WebAppAuth(client, session_name)
            auth_data = await auth.get_webapp_data()

            if not auth_data:
                result['message'] = 'Не удалось получить данные авторизации'
                await client.disconnect()
                return result

            api = VirusAPI(session_name)
            await api.set_auth_data(auth_data)

            # Получаем подробный статус аккаунта
            account_status = await api.get_account_status()

            if account_status['ready_for_automation']:
                result['success'] = True
                result['message'] = 'Аккаунт готов к автоматизации'
                result['onboarding_actions'] = []
                result['account_status'] = 'ready'
            elif account_status['onboarding_required']:
                result['success'] = False
                result['message'] = f"Требуется ручной onboarding: {', '.join(account_status['required_actions'])}"
                result['onboarding_actions'] = account_status['required_actions']
                result['account_status'] = 'needs_onboarding'
                result['detailed_error'] = account_status['error_message']
            else:
                result['success'] = False
                result['message'] = f"Проблема с аккаунтом: {account_status['error_message']}"
                result['onboarding_actions'] = []
                result['account_status'] = 'error'

            await api.close_session()
            await client.disconnect()

        except Exception as e:
            logger.error(f"Ошибка подготовки аккаунта {session_name}: {e}")
            result['message'] = f'Ошибка: {str(e)}'

        return result

    async def validate_all_accounts_batch(self, session_names: List[str], progress_callback=None) -> List[Dict]:
        """Валидирует все аккаунты батчами"""
        logger.info(f"Начинаю валидацию {len(session_names)} аккаунтов")

        results = []
        completed = [0]
        total = len(session_names)

        async def validate_single_account(session_name: str):
            try:
                result = await self.validate_single_account(session_name)
                results.append(result)

                # Обновляем прогресс
                completed[0] += 1
                if progress_callback:
                    await progress_callback(completed[0], total)

                return result
            except Exception as e:
                logger.error(f"Критическая ошибка валидации {session_name}: {e}")
                error_result = {
                    'session_name': session_name,
                    'success': False,
                    'message': f'Критическая ошибка: {str(e)}',
                    'account_status': 'error'
                }
                results.append(error_result)

                # Обновляем прогресс
                completed[0] += 1
                if progress_callback:
                    await progress_callback(completed[0], total)

                return error_result

        tasks = [validate_single_account(name) for name in session_names]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"Валидация завершена. Проверено {len(results)} аккаунтов")
        return results

    async def validate_single_account(self, session_name: str) -> Dict:
        """Валидирует один аккаунт"""
        result = {
            'session_name': session_name,
            'success': False,
            'message': '',
            'account_status': 'unknown'
        }

        try:
            # Ограничение частоты запросов
            current_time = time.time()
            if session_name in self.last_request_time:
                time_diff = current_time - self.last_request_time[session_name]
                if time_diff < self.min_request_interval:
                    await asyncio.sleep(self.min_request_interval - time_diff)

            self.last_request_time[session_name] = time.time()

            # Проверяем Telegram сессию
            client = await self.session_manager.create_client(session_name)
            if not client:
                result['message'] = 'Не удалось создать Telegram клиент'
                result['account_status'] = 'telegram_error'
                return result

            # Проверяем авторизацию в Telegram
            try:
                me = await client.get_me()
                if not me:
                    result['message'] = 'Telegram сессия недействительна'
                    result['account_status'] = 'telegram_invalid'
                    await client.disconnect()
                    return result
            except Exception as e:
                result['message'] = f'Ошибка Telegram авторизации: {str(e)}'
                result['account_status'] = 'telegram_auth_error'
                await client.disconnect()
                return result

            # Проверяем WebApp данные
            auth = WebAppAuth(client, session_name)
            auth_data = await auth.get_webapp_data()

            if not auth_data:
                result['message'] = 'Не удалось получить WebApp данные'
                result['account_status'] = 'webapp_error'
                await client.disconnect()
                return result

            # Проверяем API доступ
            api = VirusAPI(session_name)
            await api.set_auth_data(auth_data)

            user_info = await api.get_user_info()
            if user_info:
                result['success'] = True
                result['message'] = f"Валиден (ID: {user_info.get('id')}, Баланс: {user_info.get('starsBalance', 0)} звезд)"
                result['account_status'] = 'valid'
                result['user_id'] = user_info.get('id')
                result['stars_balance'] = user_info.get('starsBalance', 0)
            else:
                result['message'] = 'Не удалось получить информацию о пользователе'
                result['account_status'] = 'api_error'

            await api.close_session()
            await client.disconnect()

        except Exception as e:
            logger.error(f"Ошибка валидации {session_name}: {e}")
            result['message'] = f'Ошибка валидации: {str(e)}'
            result['account_status'] = 'error'

        return result

    async def check_all_balances_batch(self, session_names: List[str], batch_size: int = 20, progress_callback=None) -> List[Dict]:
        """Проверяет баланс всех аккаунтов супер-быстрыми батчами"""
        logger.info(f"БЫСТРАЯ проверка баланса {len(session_names)} аккаунтов (батчи по {batch_size})")

        all_results = []
        completed = [0]
        total = len(session_names)

        # Обрабатываем батчами для максимальной производительности
        for i in range(0, len(session_names), batch_size):
            batch = session_names[i:i + batch_size]
            batch_results = []

            async def check_single_balance_fast(session_name: str):
                try:
                    result = await self.check_single_account_balance(session_name)
                    batch_results.append(result)

                    # Обновляем прогресс
                    completed[0] += 1
                    if progress_callback:
                        await progress_callback(completed[0], total)

                    # Минимальная задержка только если нужно
                    if DELAY_BETWEEN_ACCOUNTS > 0.1:
                        await asyncio.sleep(DELAY_BETWEEN_ACCOUNTS)
                    return result
                except Exception as e:
                    logger.error(f"Ошибка быстрой проверки баланса {session_name}: {e}")
                    error_result = {
                        'session_name': session_name,
                        'success': False,
                        'message': f'Ошибка: {str(e)}',
                        'stars_balance': 0,
                        'balance': 0,
                        'gifts_count': 0
                    }
                    batch_results.append(error_result)

                    # Обновляем прогресс
                    completed[0] += 1
                    if progress_callback:
                        await progress_callback(completed[0], total)

                    return error_result

            # Параллельная обработка батча
            tasks = [check_single_balance_fast(name) for name in batch]
            await asyncio.gather(*tasks, return_exceptions=True)

            all_results.extend(batch_results)
            logger.debug(f"Батч {i//batch_size + 1}/{(len(session_names)-1)//batch_size + 1} завершен")

        # Сортируем результаты: сначала акки с подарками, потом по убыванию баланса звезд
        all_results.sort(key=lambda x: (x.get('gifts_count', 0) == 0, -x.get('stars_balance', 0)))

        logger.info(f"БЫСТРАЯ проверка баланса завершена. Проверено {len(all_results)} аккаунтов (отсортировано по балансу)")
        return all_results

    async def check_single_account_balance(self, session_name: str) -> Dict:
        """Проверяет баланс одного аккаунта"""
        result = {
            'session_name': session_name,
            'success': False,
            'message': '',
            'stars_balance': 0,
            'balance': 0,
            'gifts_count': 0,
            'gifts_list': [],
            'gifts_details': []  # Детальная информация о каждом подарке
        }

        try:
            # Ограничение частоты запросов
            current_time = time.time()
            if session_name in self.last_request_time:
                time_diff = current_time - self.last_request_time[session_name]
                if time_diff < self.min_request_interval:
                    await asyncio.sleep(self.min_request_interval - time_diff)

            self.last_request_time[session_name] = time.time()

            client = await self.session_manager.create_client(session_name)
            if not client:
                result['message'] = 'Не удалось создать клиент'
                return result

            auth = WebAppAuth(client, session_name)
            auth_data = await auth.get_webapp_data()

            if not auth_data:
                result['message'] = 'Не удалось получить данные авторизации'
                await client.disconnect()
                return result

            api = VirusAPI(session_name)
            await api.set_auth_data(auth_data)

            # Получаем информацию о пользователе
            user_info = await api.get_user_info()
            if user_info:
                stars_balance = user_info.get('starsBalance', 0)
                balance = user_info.get('balance', 0)

                # Получаем инвентарь для подсчета подарков и звезд с кэшированием
                gifts_count = 0
                gifts_list = []
                gifts_details = []
                inventory_stars_count = 0  # Количество звезд в инвентаре
                inventory_stars_value = 0  # Сумма звезд в инвентаре
                try:
                    inventory = await api.get_roulette_inventory(cursor=0, limit=50)

                    # Упрощенное логирование для производительности
                    if not config.REDUCED_LOGGING_MODE:
                        logger.info(f"🔍 ИНВЕНТАРЬ {session_name}:")
                        logger.info(f"   Полный ответ: {inventory}")

                    if inventory and inventory.get('success') and inventory.get('prizes') is not None:
                        if not config.REDUCED_LOGGING_MODE:
                            logger.info(f"   Найдено призов: {len(inventory['prizes'])}")

                        for i, prize_item in enumerate(inventory['prizes']):
                            status = prize_item.get('status')
                            prize = prize_item.get('prize', {})
                            prize_name = prize.get('name', 'Неизвестный приз')
                            exchange_price = prize.get('exchangePrice', 0)
                            unlock_at = prize_item.get('unlockAt')

                            if not config.REDUCED_LOGGING_MODE:
                                logger.info(f"   Приз #{i+1}: {prize_name} (статус: {status}, цена: {exchange_price}⭐)")

                            # Считаем неактивированные звезды в инвентаре (status NONE)
                            if status == 'NONE' and ('Stars' in prize_name or 'stars' in prize_name.lower()):
                                inventory_stars_count += 1
                                # Извлекаем значение звезд из названия
                                import re
                                numbers = re.findall(r'\d+', prize_name)
                                if numbers:
                                    inventory_stars_value += int(numbers[0])

                            # Подарки могут быть в статусе IN_PROGRESS
                            if status in ['active', 'IN_PROGRESS']:
                                # Определяем, является ли это подарком (не звезды и не вирусы)
                                if not prize_name.endswith('Stars') and not prize_name.endswith('Viruses'):
                                    gifts_count += 1
                                    gifts_list.append(prize_name)

                                    # Форматируем дату разблокировки
                                    unlock_date_str = "готов"
                                    if unlock_at:
                                        try:
                                            from datetime import datetime
                                            unlock_time = datetime.fromisoformat(unlock_at.replace('Z', '+00:00'))
                                            unlock_date_str = unlock_time.strftime("до %d.%m.%Y %H:%M")
                                        except:
                                            unlock_date_str = "неизвестно"

                                    # Добавляем детальную информацию
                                    gift_detail = {
                                        'name': prize_name,
                                        'price': exchange_price,
                                        'unlock_date': unlock_date_str,
                                        'status': status,
                                        'formatted': f"{prize_name} ({exchange_price}⭐, {unlock_date_str})"
                                    }
                                    gifts_details.append(gift_detail)

                                    if not config.REDUCED_LOGGING_MODE:
                                        logger.info(f"     ✅ НАЙДЕН ПОДАРОК: {gift_detail['formatted']}")

                    else:
                        if not config.REDUCED_LOGGING_MODE:
                            prizes_status = "None" if inventory.get('prizes') is None else f"список из {len(inventory.get('prizes', []))} элементов"
                            logger.info(f"   ❌ Нет призов в инвентаре: prizes={prizes_status}, success={inventory.get('success') if inventory else None}")

                except Exception as e:
                    logger.error(f"Ошибка получения инвентаря для {session_name}: {e}")

                # Автоматическая продажа дешевых подарков при проверке баланса
                if config.GIFT_EXCHANGE_ON_BALANCE_CHECK and config.AUTO_GIFT_EXCHANGE_ENABLED:
                    try:
                        exchanged_count, _, exchanged_list = await api.auto_exchange_cheap_gifts()
                        if exchanged_count > 0:
                            logger.info(f"Автопродажа при проверке баланса {session_name}: продано {exchanged_count} подарков")
                    except Exception as e:
                        logger.error(f"Ошибка автопродажи подарков при проверке баланса {session_name}: {e}")

                result['success'] = True
                result['stars_balance'] = stars_balance
                result['balance'] = balance
                result['gifts_count'] = gifts_count
                result['gifts_list'] = gifts_list
                result['gifts_details'] = gifts_details
                result['inventory_stars_count'] = inventory_stars_count
                result['inventory_stars_value'] = inventory_stars_value

                # Формируем сообщение
                message_parts = []

                # Активированные звезды на балансе
                if inventory_stars_value > 0:
                    message_parts.append(f"Звезды: {stars_balance} (баланс) + {inventory_stars_value} (инвентарь)")
                else:
                    message_parts.append(f"Звезды: {stars_balance}")

                message_parts.append(f"Вирусы: {balance}")

                if gifts_count > 0:
                    message_parts.append(f"Подарки: {gifts_count}")

                result['message'] = ", ".join(message_parts)

                # Добавляем информацию о готовности к платным спинам
                if stars_balance >= 200:
                    result['message'] += " (готов к платным спинам)"
            else:
                result['message'] = 'Не удалось получить информацию о балансе'

            await api.close_session()
            await client.disconnect()

        except Exception as e:
            logger.error(f"Ошибка проверки баланса {session_name}: {e}")
            result['message'] = f'Ошибка: {str(e)}'

        return result

    async def perform_paid_spins_batch(self, session_names: List[str]) -> List[Dict]:
        """Выполняет платные спины для списка аккаунтов"""
        logger.info(f"Начинаю платные спины для {len(session_names)} аккаунтов")

        results = []
        # Убираем семафор - все операции параллельно

        async def perform_single_paid_spin_task(session_name: str):
            
                try:
                    result = await self.perform_single_paid_spin(session_name)
                    results.append(result)
                    await asyncio.sleep(DELAY_BETWEEN_ACCOUNTS)
                    return result
                except Exception as e:
                    logger.error(f"Критическая ошибка платного спина {session_name}: {e}")
                    results.append({
                        'session_name': session_name,
                        'success': False,
                        'message': f'Критическая ошибка: {str(e)}',
                        'stars_activated': 0,
                        'high_value_prize': False
                    })

        tasks = [perform_single_paid_spin_task(name) for name in session_names]
        await asyncio.gather(*tasks, return_exceptions=True)

        logger.info(f"Платные спины завершены. Обработано {len(results)} аккаунтов")
        return results

    async def perform_single_paid_spin(self, session_name: str) -> Dict:
        """Выполняет платный спин для одного аккаунта"""
        result = {
            'session_name': session_name,
            'success': False,
            'message': '',
            'stars_activated': 0,
            'high_value_prize': False,
            'prize_name': ''
        }

        try:
            # Ограничение частоты запросов
            current_time = time.time()
            if session_name in self.last_request_time:
                time_diff = current_time - self.last_request_time[session_name]
                if time_diff < self.min_request_interval:
                    await asyncio.sleep(self.min_request_interval - time_diff)

            self.last_request_time[session_name] = time.time()

            client = await self.session_manager.create_client(session_name)
            if not client:
                result['message'] = 'Не удалось создать клиент'
                return result

            auth = WebAppAuth(client, session_name)
            auth_data = await auth.get_webapp_data()

            if not auth_data:
                result['message'] = 'Не удалось получить данные авторизации'
                await client.disconnect()
                return result

            api = VirusAPI(session_name)
            await api.set_auth_data(auth_data)

            # Проверяем баланс перед спином
            user_info = await api.get_user_info()
            if not user_info:
                result['message'] = 'Не удалось получить информацию о пользователе'
                await api.close_session()
                await client.disconnect()
                return result

            stars_balance = user_info.get('starsBalance', 0)
            if stars_balance < 200:
                result['message'] = f'Недостаточно звезд: {stars_balance}/200'
                await api.close_session()
                await client.disconnect()
                return result

            # Выполняем платный спин (тип "PAID" стоит 200 звезд)
            spin_success, spin_message, prize = await api.perform_paid_spin("PAID")

            if spin_success and prize:
                # Обрабатываем полученный приз
                is_processed, prize_description, is_high_value, is_gift = await api.process_reward(prize)

                result['success'] = True
                result['message'] = f"Получил {prize.get('name', 'приз')}"
                result['prize_name'] = prize.get('name', '')
                result['high_value_prize'] = is_high_value

                # Уведомляем о подарках с автоматических платных спинов в формате: сессия - подарок - ценность
                if is_gift and self.notification_callback:
                    exchange_price = prize.get('exchangePrice', 0)
                    gift_name = prize.get('name', 'Неизвестный подарок')

                    if is_high_value:
                        await self.notification_callback(
                            f"💎 АВТО ПЛАТНЫЙ СПИН | {session_name} | {gift_name} | {exchange_price}⭐"
                        )
                    else:
                        await self.notification_callback(
                            f"🎁 АВТО ПЛАТНЫЙ СПИН | {session_name} | {gift_name} | {exchange_price}⭐"
                        )

                # Проверяем и логируем решение об активации звезд
                try:
                    should_activate, balance_stars, inventory_stars, can_activate, reason = await api.should_activate_stars()
                    if should_activate:
                        logger.info(f"✅ [{session_name}] АВТО ПЛАТНЫЙ СПИН - АКТИВАЦИЯ НУЖНА: баланс {balance_stars}⭐, инвентарь {inventory_stars}⭐, можно активировать ~{can_activate}⭐ ({reason})")
                    else:
                        logger.info(f"⏸️ [{session_name}] АВТО ПЛАТНЫЙ СПИН - АКТИВАЦИЯ НЕ НУЖНА: баланс {balance_stars}⭐, инвентарь {inventory_stars}⭐ ({reason})")
                except Exception as e:
                    logger.error(f"Ошибка проверки активации для {session_name}: {e}")

                # Активируем звезды из инвентаря после спина
                activated_stars, total_found, stars_value = await api.activate_all_stars()
                result['stars_activated'] = activated_stars
                result['stars_value_activated'] = stars_value

                if activated_stars > 0:
                    result['message'] += f" (активировано {activated_stars} звезд на сумму ~{stars_value}⭐)"
                elif total_found > 0:
                    result['message'] += f" (найдено {total_found} звезд на сумму ~{stars_value}⭐, но не активировано - в инвентаре <= 100⭐)"

                logger.info(f"✅ Платный спин {session_name}: {result['message']}")

            else:
                result['message'] = f'Спин неудачен: {spin_message}'
                logger.warning(f"❌ Платный спин {session_name}: {spin_message}")

            await api.close_session()
            await client.disconnect()

        except Exception as e:
            logger.error(f"Ошибка платного спина {session_name}: {e}")
            result['message'] = f'Ошибка: {str(e)}'

        return result