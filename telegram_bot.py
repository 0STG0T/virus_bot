import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from session_manager import SessionManager
from spin_worker import SpinWorker
import config

# Импортируем настройку логирования
try:
    from logging_config import setup_logging
    setup_logging()
except ImportError:
    # Если файл конфигурации логов не найден, используем базовую настройку
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

logger = logging.getLogger(__name__)

class VirusBotManager:
    def __init__(self):
        self.session_manager = SessionManager()
        self.spin_worker = None
        self.app = None
        self.is_running = False
        self.main_message_id = None
        self.main_chat_id = None
        self.update_task = None
        self.cached_stats = None
        self.last_operation_results = None
        self.auto_spin_task = None
        self.auto_spin_enabled = config.AUTO_SPIN_ENABLED

    async def setup(self, bot_token: str):
        config.BOT_TOKEN = bot_token

        # Настраиваем таймауты для стабильной работы
        from telegram.request import HTTPXRequest
        request = HTTPXRequest(
            connection_pool_size=20,
            read_timeout=config.TELEGRAM_READ_TIMEOUT,
            write_timeout=config.TELEGRAM_WRITE_TIMEOUT,
            connect_timeout=config.TELEGRAM_CONNECT_TIMEOUT,
            pool_timeout=config.TELEGRAM_POOL_TIMEOUT
        )

        self.app = Application.builder().token(bot_token).request(request).build()

        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CallbackQueryHandler(self.button_callback))

        # Добавляем обработчик ошибок
        self.app.add_error_handler(self.error_handler)

        # Создаем SpinWorker с callback для уведомлений
        self.spin_worker = SpinWorker(
            self.session_manager,
            notification_callback=self.send_notification
        )

        # Загружаем сессии
        loaded_count = await self.session_manager.load_sessions()
        logger.info(f"Загружено {loaded_count} сессий")

    async def send_notification(self, message: str):
        """Отправляет уведомление о дорогом призе"""
        if self.app and config.LOG_CHAT_ID:
            try:
                await self.app.bot.send_message(
                    chat_id=config.LOG_CHAT_ID,
                    text=f"💎 ЦЕННЫЙ ПРИЗ: {message}"
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления: {e}")

    async def get_account_stats(self) -> Dict[str, Any]:
        """Получает быструю статистику по аккаунтам"""
        try:
            session_names = await self.session_manager.get_session_names()
            total_accounts = len(session_names)

            if total_accounts == 0:
                return {
                    'total': 0,
                    'ready': 0,
                    'issues': 0,
                    'ready_percent': 0,
                    'issues_percent': 0,
                    'last_update': datetime.now().strftime("%H:%M")
                }

            # Для быстрой статистики проверяем только доступность сессий
            # Полная проверка будет при вызове конкретных операций
            valid_count, invalid_count = await self.session_manager.validate_all_sessions()

            ready_percent = int((valid_count / total_accounts) * 100) if total_accounts > 0 else 0
            issues_percent = int((invalid_count / total_accounts) * 100) if total_accounts > 0 else 0

            stats = {
                'total': total_accounts,
                'ready': valid_count,
                'issues': invalid_count,
                'ready_percent': ready_percent,
                'issues_percent': issues_percent,
                'last_update': datetime.now().strftime("%H:%M")
            }

            # Добавляем информацию о подарках из последней операции проверки баланса, если есть
            if (hasattr(self, 'last_operation_results') and
                self.last_operation_results and
                self.last_operation_results.get('action') == 'balance'):

                balance_results = self.last_operation_results.get('results', [])
                total_gifts = sum(r.get('gifts_count', 0) for r in balance_results if r.get('success'))
                accounts_with_gifts = sum(1 for r in balance_results if r.get('success') and r.get('gifts_count', 0) > 0)

                if total_gifts > 0:
                    stats['total_gifts'] = total_gifts
                    stats['accounts_with_gifts'] = accounts_with_gifts

            return stats
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {
                'total': 0,
                'ready': 0,
                'issues': 0,
                'ready_percent': 0,
                'issues_percent': 0,
                'last_update': datetime.now().strftime("%H:%M"),
                'error': str(e)
            }

    def format_main_message(self, stats: Dict[str, Any]) -> str:
        """Форматирует главное сообщение с статистикой"""
        if stats.get('error'):
            return f"🤖 Virus Bot Manager\n\n❌ Ошибка: {stats['error']}\n\nПоследнее обновление: {stats['last_update']}"

        if stats['total'] == 0:
            return f"🤖 Virus Bot Manager\n\n📭 Нет загруженных аккаунтов\n\nПоследнее обновление: {stats['last_update']}"

        status_emoji = "🟢" if stats['ready_percent'] >= 90 else "🟡" if stats['ready_percent'] >= 70 else "🔴"

        message = f"🤖 Virus Bot Manager\n\n"
        message += f"{status_emoji} Статус аккаунтов:\n"
        message += f"✅ Готово: {stats['ready']}/{stats['total']} ({stats['ready_percent']}%)\n"

        if stats['issues'] > 0:
            message += f"⚠️ Проблемы: {stats['issues']}/{stats['total']} ({stats['issues_percent']}%)\n"

        # Добавляем информацию о подарках если есть
        if stats.get('total_gifts', 0) > 0:
            message += f"🎁 Подарков: {stats['total_gifts']} (у {stats.get('accounts_with_gifts', 0)} аккаунтов)\n"

        message += f"\n⏰ Обновлено: {stats['last_update']}"

        return message

    def get_main_keyboard(self) -> InlineKeyboardMarkup:
        """Создает основную клавиатуру с улучшенным UX"""
        keyboard = [
            # Основные действия в одну строку для быстрого доступа
            [InlineKeyboardButton("🎰 Фри спины", callback_data="action_spin"),
             InlineKeyboardButton("💰 Баланс", callback_data="action_balance")],
            [InlineKeyboardButton("✅ Проверить валидность", callback_data="action_validate")],
            # Быстрые действия
            [InlineKeyboardButton("🔄 Обновить статистику", callback_data="action_refresh")]
        ]
        return InlineKeyboardMarkup(keyboard)

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        if not config.LOG_CHAT_ID:
            config.LOG_CHAT_ID = update.effective_chat.id

        self.main_chat_id = update.effective_chat.id

        # Получаем начальную статистику
        stats = await self.get_account_stats()
        self.cached_stats = stats

        message_text = self.format_main_message(stats)
        reply_markup = self.get_main_keyboard()

        # Отправляем главное сообщение
        sent_message = await update.message.reply_text(
            message_text,
            reply_markup=reply_markup
        )

        self.main_message_id = sent_message.message_id

        # Запускаем объединенную задачу автообновления и автоспинов (каждый час)
        if self.update_task:
            self.update_task.cancel()
        self.update_task = asyncio.create_task(self.auto_update_and_spins_monitor())

        # Отменяем старую задачу автоспинов, так как теперь все в одном месте
        if self.auto_spin_task:
            self.auto_spin_task.cancel()
            self.auto_spin_task = None

    async def auto_update_and_spins_monitor(self):
        """Объединенный мониторинг: обновление статистики + автоспины (каждый час)"""
        while self.is_running and self.main_message_id and self.main_chat_id:
            try:
                await asyncio.sleep(3600)  # Ждем 1 час

                logger.info("🔄 Ежечасная проверка: статистика + автоспины")

                # 1. Проверяем и делаем автоматические платные спины
                if self.auto_spin_enabled:
                    await self.perform_hourly_auto_spins()

                # 2. Получаем обновленную статистику
                new_stats = await self.get_account_stats()

                # 3. Обновляем главное сообщение только если есть изменения
                if new_stats != self.cached_stats:
                    self.cached_stats = new_stats

                    message_text = self.format_main_message(new_stats)
                    reply_markup = self.get_main_keyboard()

                    await self.app.bot.edit_message_text(
                        chat_id=self.main_chat_id,
                        message_id=self.main_message_id,
                        text=message_text,
                        reply_markup=reply_markup
                    )

            except Exception as e:
                logger.error(f"Ошибка ежечасной проверки: {e}")
                await asyncio.sleep(30)  # При ошибке ждем меньше

    async def perform_hourly_auto_spins(self):
        """Выполняет автоматические платные спины (встроено в ежечасную проверку)"""
        try:
            session_names = await self.session_manager.get_session_names()
            if not session_names:
                return

            logger.info("🔍 Ежечасная проверка аккаунтов для платных спинов...")

            # Проверяем баланс всех аккаунтов
            rich_accounts = []
            for session_name in session_names:
                try:
                    balance_result = await self.spin_worker.check_single_account_balance(session_name)
                    if balance_result.get('success') and balance_result.get('stars_balance', 0) >= config.AUTO_SPIN_THRESHOLD:
                        rich_accounts.append(session_name)
                        logger.info(f"💰 {session_name} имеет {balance_result['stars_balance']} звезд - готов к платному спину")
                except Exception as e:
                    logger.error(f"Ошибка проверки баланса {session_name}: {e}")

            if rich_accounts:
                logger.info(f"🎰 Найдено {len(rich_accounts)} аккаунтов для ежечасных автоспинов")

                # Выполняем платные спины для богатых аккаунтов
                results = await self.spin_worker.perform_paid_spins_batch(rich_accounts)

                # Отправляем уведомление о результатах
                await self.send_auto_spin_notification(results)
            else:
                logger.info("💸 Нет аккаунтов с достаточным балансом для автоспинов")

        except Exception as e:
            logger.error(f"Ошибка выполнения ежечасных автоспинов: {e}")

    async def auto_update_main_message(self):
        """УСТАРЕВШИЙ: Автоматически обновляет главное сообщение каждый час (заменен на auto_update_and_spins_monitor)"""
        while self.is_running and self.main_message_id and self.main_chat_id:
            try:
                await asyncio.sleep(3600)  # Ждем 1 час (изменено с 1 минуты для производительности)

                # Получаем новую статистику
                new_stats = await self.get_account_stats()

                # Обновляем только если есть изменения
                if new_stats != self.cached_stats:
                    self.cached_stats = new_stats

                    message_text = self.format_main_message(new_stats)
                    reply_markup = self.get_main_keyboard()

                    await self.app.bot.edit_message_text(
                        chat_id=self.main_chat_id,
                        message_id=self.main_message_id,
                        text=message_text,
                        reply_markup=reply_markup
                    )

            except Exception as e:
                logger.error(f"Ошибка автообновления: {e}")
                await asyncio.sleep(30)  # При ошибке ждем меньше

    async def auto_paid_spins_monitor(self):
        """Автоматически мониторит баланс и делает платные спины при 200+ звездах"""
        while self.is_running and self.auto_spin_enabled:
            try:
                await asyncio.sleep(config.AUTO_SPIN_CHECK_INTERVAL)

                session_names = await self.session_manager.get_session_names()
                if not session_names:
                    continue

                logger.info("🔍 Автоматическая проверка аккаунтов для платных спинов...")

                # Проверяем баланс всех аккаунтов
                rich_accounts = []
                for session_name in session_names:
                    try:
                        balance_result = await self.spin_worker.check_single_account_balance(session_name)
                        if balance_result.get('success') and balance_result.get('stars_balance', 0) >= config.AUTO_SPIN_THRESHOLD:
                            rich_accounts.append(session_name)
                            logger.info(f"💰 {session_name} имеет {balance_result['stars_balance']} звезд - готов к платному спину")
                    except Exception as e:
                        logger.error(f"Ошибка проверки баланса {session_name}: {e}")

                if rich_accounts:
                    logger.info(f"🎰 Найдено {len(rich_accounts)} аккаунтов для автоматических платных спинов")

                    # Выполняем платные спины для богатых аккаунтов
                    results = await self.spin_worker.perform_paid_spins_batch(rich_accounts)

                    # Отправляем уведомление о результатах
                    await self.send_auto_spin_notification(results)

            except Exception as e:
                logger.error(f"Ошибка автоматического мониторинга платных спинов: {e}")
                await asyncio.sleep(60)  # При ошибке ждем меньше

    async def send_auto_spin_notification(self, results):
        """Отправляет уведомление о результатах автоматических платных спинов"""
        if not results or not self.main_chat_id:
            return

        successful_spins = sum(1 for r in results if r.get('success', False))
        total_spins = len(results)
        total_stars_activated = sum(r.get('stars_activated', 0) for r in results)
        high_value_prizes = sum(1 for r in results if r.get('high_value_prize', False))

        # Формируем уведомление
        notification = f"🤖 **Автоматические Платные Спины**\n\n"
        notification += f"🎰 Выполнено: {successful_spins}/{total_spins} спинов\n"

        if total_stars_activated > 0:
            notification += f"⭐ Активировано звезд: {total_stars_activated}\n"

        if high_value_prizes > 0:
            notification += f"💎 Ценные призы: {high_value_prizes}\n"

        # Добавляем детали по самым интересным результатам
        interesting_results = []
        for result in results:
            if result.get('success'):
                session_name = result['session_name']
                stars = result.get('stars_activated', 0)
                high_value = result.get('high_value_prize', False)

                if high_value or stars > 0:
                    detail = f"• {session_name}"
                    if high_value:
                        detail += " 💎"
                    if stars > 0:
                        detail += f" (+{stars} звезд)"
                    interesting_results.append(detail)

        if interesting_results:
            notification += f"\n**Интересные результаты:**\n"
            # Показываем первые 10 результатов
            for detail in interesting_results[:10]:
                notification += detail + "\n"

            if len(interesting_results) > 10:
                notification += f"... и еще {len(interesting_results) - 10} результатов"

        try:
            await self.app.bot.send_message(
                chat_id=self.main_chat_id,
                text=notification,
                parse_mode='Markdown'
            )
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления об автоспинах: {e}")
            # Пробуем без markdown
            try:
                await self.app.bot.send_message(
                    chat_id=self.main_chat_id,
                    text=notification.replace('*', '').replace('`', '')
                )
            except Exception as e2:
                logger.error(f"Ошибка отправки упрощенного уведомления: {e2}")

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик нажатий кнопок"""
        query = update.callback_query
        try:
            await query.answer()
        except Exception as e:
            logger.warning(f"Не удалось ответить на callback query: {e}")

        if query.data.startswith("action_"):
            action = query.data.replace("action_", "")
            await self.handle_action(query, action)
        elif query.data == "show_details":
            await self.show_detailed_results(query)
        elif query.data == "back_to_main":
            await self.back_to_main_menu(query)
        else:
            logger.warning(f"Неизвестный callback: {query.data}")

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик ошибок приложения"""
        logger.error(f"Exception while handling an update: {context.error}")

        # Для сетевых ошибок просто логируем, не падаем
        if "NetworkError" in str(context.error) or "ConnectError" in str(context.error):
            logger.warning("Сетевая ошибка, продолжаем работу...")
            return

        # Для других критических ошибок можем что-то предпринять
        logger.error(f"Неожиданная ошибка: {context.error}")

    async def handle_action(self, query, action: str):
        """Обрабатывает основные действия с улучшенным UX"""
        # Быстрая проверка сессий
        session_names = await self.session_manager.get_session_names()
        if not session_names:
            await query.edit_message_text(
                "❌ Нет загруженных сессий\n\nДобавьте .session файлы в папку sessions/",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
                ]])
            )
            return

        # Специальная обработка быстрого обновления
        if action == "refresh":
            await self.handle_refresh(query)
            return

        # Показываем начальное сообщение с кнопкой отмены
        start_message = f"⏳ {self.get_action_name(action)}...\n\n" \
                       f"📊 Аккаунтов: {len(session_names)}\n" \
                       f"⏱️ Ожидайте, операция выполняется..."

        cancel_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 Отменить и вернуться", callback_data="back_to_main")
        ]])

        await query.edit_message_text(start_message, reply_markup=cancel_keyboard)

        # Создаем callback для обновления прогресса
        last_update_time = [0]  # Используем список чтобы изменять в замыкании
        total_sessions = len(session_names)

        async def progress_callback(completed: int, total: int):
            current_time = asyncio.get_event_loop().time()
            # Обновляем не чаще чем раз в 1.5 секунды
            if current_time - last_update_time[0] >= 1.5 or completed == 0 or completed == total:
                last_update_time[0] = current_time

                # Вычисляем процент
                percent = int((completed / total) * 100) if total > 0 else 0

                # Создаем прогресс бар
                bar_length = 10
                filled = int((completed / total) * bar_length) if total > 0 else 0
                bar = "█" * filled + "░" * (bar_length - filled)

                progress_message = f"⏳ {self.get_action_name(action)}...\n\n" \
                                 f"📊 Прогресс: {completed}/{total} ({percent}%)\n" \
                                 f"{bar}\n\n" \
                                 f"⏱️ Обработка аккаунтов..."

                try:
                    await query.edit_message_text(progress_message, reply_markup=cancel_keyboard)
                except Exception as e:
                    # Игнорируем ошибки обновления (например, если сообщение не изменилось)
                    pass

        try:
            # Показываем начальный прогресс
            await progress_callback(0, total_sessions)

            # Выполняем операцию с прогресс колбэком
            if action == "spin":
                results = await self.spin_worker.perform_spins_batch(session_names, progress_callback)
            elif action == "validate":
                results = await self.spin_worker.validate_all_accounts_batch(session_names, progress_callback)
            elif action == "balance":
                results = await self.spin_worker.check_all_balances_batch(session_names, progress_callback=progress_callback)
            else:
                await query.edit_message_text(
                    "❌ Неизвестная операция",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")
                    ]])
                )
                return

            # Сохраняем результаты для детального просмотра
            self.last_operation_results = {
                'action': action,
                'results': results,
                'timestamp': datetime.now().strftime("%H:%M:%S")
            }

            # Показываем результаты с быстрыми действиями
            summary = self.format_operation_summary(action, results)

            # Улучшенная клавиатура с быстрыми действиями
            keyboard = []

            # Предлагаем быстрые действия на основе текущей операции
            quick_actions = []
            if action == "balance":
                quick_actions = [
                    InlineKeyboardButton("🎰 Фри спины", callback_data="action_spin"),
                    InlineKeyboardButton("🔄 Обновить", callback_data="action_balance")
                ]
            elif action == "spin":
                quick_actions = [
                    InlineKeyboardButton("💰 Проверить баланс", callback_data="action_balance"),
                    InlineKeyboardButton("🔄 Ещё спины", callback_data="action_spin")
                ]
            elif action == "validate":
                quick_actions = [
                    InlineKeyboardButton("🎰 Фри спины", callback_data="action_spin"),
                    InlineKeyboardButton("💰 Баланс", callback_data="action_balance")
                ]

            if quick_actions:
                keyboard.append(quick_actions)

            keyboard.extend([
                [InlineKeyboardButton("📋 Подробности", callback_data="show_details")],
                [InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")]
            ])

            await query.edit_message_text(
                summary,
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        except Exception as e:
            logger.error(f"Ошибка в операции {action}: {e}")
            await query.edit_message_text(
                f"❌ Ошибка {self.get_action_name(action).lower()}:\n{str(e)}\n\n🔄 Можете попробовать снова",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"🔄 Повторить {self.get_action_name(action).lower()}", callback_data=f"action_{action}")],
                    [InlineKeyboardButton("🏠 Меню", callback_data="back_to_main")]
                ])
            )

    async def handle_refresh(self, query):
        """Обрабатывает быстрое обновление статистики"""
        try:
            await query.edit_message_text("🔄 Обновление статистики...")

            # Обновляем статистику
            new_stats = await self.get_account_stats()
            self.cached_stats = new_stats

            message_text = self.format_main_message(new_stats)
            reply_markup = self.get_main_keyboard()

            await query.edit_message_text(
                message_text,
                reply_markup=reply_markup
            )

            # Обновляем ID главного сообщения
            self.main_message_id = query.message.message_id

        except Exception as e:
            logger.error(f"Ошибка обновления: {e}")
            await query.edit_message_text(
                f"❌ Ошибка обновления: {str(e)}",
                reply_markup=InlineKeyboardMarkup([[
                    InlineKeyboardButton("🏠 Главное меню", callback_data="back_to_main")
                ]])
            )

    def estimate_operation_time(self, action: str, account_count: int) -> str:
        """Оценивает время выполнения операции"""
        # Приблизительное время на один аккаунт (секунды)
        time_per_account = {
            'spin': 8,  # Фри спины - дольше всего
            'balance': 3,  # Проверка баланса - средне
            'validate': 2,  # Проверка валидности - быстрее
            'refresh': 1   # Обновление - мгновенно
        }

        total_seconds = account_count * time_per_account.get(action, 5)

        if total_seconds < 60:
            return f"{total_seconds} сек"
        else:
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            if seconds > 0:
                return f"{minutes} мин {seconds} сек"
            else:
                return f"{minutes} мин"

    def get_action_name(self, action: str) -> str:
        """Возвращает человекочитаемое название операции"""
        names = {
            'spin': 'Фри спины',
            'validate': 'Проверка валидности',
            'balance': 'Проверка баланса',
            'refresh': 'Обновление статистики'
        }
        return names.get(action, action)

    def format_operation_summary(self, action: str, results: list) -> str:
        """Форматирует краткую статистику операции"""
        total = len(results)
        if total == 0:
            return f"📊 {self.get_action_name(action)} - Результаты\n\nНет данных для отображения"

        success_count = sum(1 for r in results if r.get('success', False))
        error_count = total - success_count

        success_percent = int((success_count / total) * 100) if total > 0 else 0
        error_percent = int((error_count / total) * 100) if total > 0 else 0

        summary = f"📊 {self.get_action_name(action)} - Результаты\n\n"
        summary += f"✅ Успешно: {success_count}/{total} ({success_percent}%)\n"

        if error_count > 0:
            summary += f"❌ Ошибки: {error_count}/{total} ({error_percent}%)\n"

        # Добавляем специфичную для операции статистику
        if action == "spin":
            total_stars = sum(r.get('stars_activated', 0) for r in results)
            if total_stars > 0:
                summary += f"⭐ Активировано звезд: {total_stars}\n"

            # Подсчитываем дорогие призы
            high_value_prizes = sum(1 for r in results if r.get('high_value_prize', False))
            if high_value_prizes > 0:
                summary += f"💎 Ценные призы: {high_value_prizes}\n"

        elif action == "balance":
            total_balance = sum(r.get('stars_balance', 0) for r in results if r.get('success'))
            total_gifts = sum(r.get('gifts_count', 0) for r in results if r.get('success'))
            summary += f"💰 Общий баланс звезд: {total_balance}\n"

            if total_gifts > 0:
                summary += f"🎁 Всего подарков: {total_gifts}\n"

            rich_accounts = sum(1 for r in results if r.get('stars_balance', 0) >= 200)
            if rich_accounts > 0:
                summary += f"💎 Готовы к платным спинам: {rich_accounts}\n"

        summary += f"\n⏰ Завершено: {datetime.now().strftime('%H:%M:%S')}"
        return summary

    async def show_detailed_results(self, query):
        """Показывает детальные результаты операции"""
        if not self.last_operation_results:
            await query.edit_message_text("❌ Нет сохраненных результатов")
            return

        action = self.last_operation_results['action']
        results = self.last_operation_results['results']
        timestamp = self.last_operation_results['timestamp']

        # Формируем детальный отчет
        report_lines = []
        for result in results:
            session_name = result['session_name']
            if result.get('success', False):
                message = result.get('message', 'Успешно')

                # Добавляем дополнительную информацию в зависимости от операции
                if action == "spin":
                    stars = result.get('stars_activated', 0)
                    stars_value = result.get('stars_value_activated', 0)
                    if stars > 0:
                        if stars_value > 0:
                            message += f" (активировано {stars} звезд на сумму ~{stars_value}⭐)"
                        else:
                            message += f" (активировано {stars} звезд)"
                    if result.get('high_value_prize', False):
                        message += " 💎"
                elif action == "balance":
                    stars_balance = result.get('stars_balance', 0)
                    inventory_stars_value = result.get('inventory_stars_value', 0)
                    inventory_stars_count = result.get('inventory_stars_count', 0)
                    gifts_count = result.get('gifts_count', 0)
                    gifts_details = result.get('gifts_details', [])

                    # Формируем информацию о звездах с деталями
                    balance_parts = []

                    if inventory_stars_value > 0:
                        # Показываем отдельно баланс и инвентарь
                        balance_parts.append(f"💰 Баланс: {stars_balance}⭐")
                        balance_parts.append(f"📦 Инвентарь: {inventory_stars_value}⭐ ({inventory_stars_count} шт)")
                        balance_parts.append(f"📊 Всего: {stars_balance + inventory_stars_value}⭐")
                    else:
                        balance_parts.append(f"💰 Баланс: {stars_balance}⭐")

                    if gifts_count > 0:
                        balance_parts.append(f"🎁 Подарки: {gifts_count}")

                    balance_info = "\n      ".join(balance_parts)
                    message += f"\n      {balance_info}"

                    # Добавляем детальную информацию о подарках
                    if gifts_details:
                        gift_lines = []
                        for gift in gifts_details:
                            gift_lines.append(f"    🎁 {gift['formatted']}")

                        # Ограничиваем количество подарков в одной строке для экономии места
                        if len(gift_lines) <= 3:
                            message += "\n" + "\n".join(gift_lines)
                        else:
                            message += f"\n    🎁 {len(gift_lines)} подарков: {', '.join([g['name'] for g in gifts_details[:3]])}{'...' if len(gifts_details) > 3 else ''}"

                report_lines.append(f"✅ {session_name}: {message}")
            else:
                error_msg = result.get('message', 'Неизвестная ошибка')
                report_lines.append(f"❌ {session_name}: {error_msg}")

        # Разбиваем отчет на части если он слишком длинный
        report = f"📋 {self.get_action_name(action)} - Детальные результаты\n"
        report += f"⏰ {timestamp}\n\n"

        max_length = 3800  # Оставляем место для кнопок
        current_report = report

        for line in report_lines:
            if len(current_report + line + "\n") > max_length:
                newline_count = len(current_report.split('\n'))
                remaining = len(report_lines) - newline_count + 3
                current_report += f"\n... и еще {remaining} результатов"
                break
            current_report += line + "\n"

        keyboard = [[InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]]

        await query.edit_message_text(
            current_report,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    async def back_to_main_menu(self, query):
        """Быстро возвращается к главному меню"""
        try:
            # Обновляем статистику только если она старая
            if not self.cached_stats or (datetime.now().minute % 5 == 0):  # Обновляем каждые 5 минут
                stats = await self.get_account_stats()
                self.cached_stats = stats
            else:
                stats = self.cached_stats

            message_text = self.format_main_message(stats)
            reply_markup = self.get_main_keyboard()

            await query.edit_message_text(
                message_text,
                reply_markup=reply_markup
            )

            # Обновляем ID главного сообщения
            self.main_message_id = query.message.message_id
        except Exception as e:
            logger.error(f"Ошибка возврата к главному меню: {e}")
            # Пробуем просто создать сообщение
            simple_stats = {
                'total': 0,
                'ready': 0,
                'issues': 0,
                'ready_percent': 0,
                'issues_percent': 0,
                'last_update': datetime.now().strftime("%H:%M")
            }
            message_text = self.format_main_message(simple_stats)
            reply_markup = self.get_main_keyboard()
            await query.edit_message_text(message_text, reply_markup=reply_markup)

    async def _check_network_connectivity(self):
        """Проверяет доступность Telegram API"""
        import aiohttp
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
                async with session.get('https://api.telegram.org') as response:
                    if response.status == 200:
                        logger.info("✅ Telegram API доступен")
                        return True
        except Exception as e:
            logger.warning(f"⚠️ Проблемы с доступом к Telegram API: {e}")
            raise ConnectionError("Telegram API недоступен")

    async def run(self):
        """Запуск бота с retry логикой"""
        self.is_running = True

        # Пытаемся запустить приложение с retry
        max_retries = 5
        retry_delay = 10

        for attempt in range(max_retries):
            try:
                logger.info(f"Попытка запуска бота #{attempt + 1}")

                # Проверяем сетевое подключение
                await self._check_network_connectivity()

                # Запускаем приложение
                await self.app.initialize()
                await self.app.start()
                await self.app.updater.start_polling()

                logger.info("Бот запущен и готов к работе")
                break

            except Exception as e:
                logger.error(f"Ошибка запуска бота (попытка {attempt + 1}/{max_retries}): {e}")

                # Проверяем, не таймаут ли это
                if "TimedOut" in str(e) or "timeout" in str(e).lower():
                    logger.warning("Обнаружен таймаут, увеличиваем задержку")

                if attempt < max_retries - 1:
                    logger.info(f"Ждем {retry_delay} секунд перед следующей попыткой...")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 2, 120)  # Максимум 2 минуты
                else:
                    logger.error("Превышено количество попыток запуска бота")
                    raise

        # Ожидаем завершения
        try:
            while self.is_running:
                await asyncio.sleep(3)  # Увеличиваем задержку для 500+ аккаунтов
        except KeyboardInterrupt:
            pass
        finally:
            # Останавливаем задачи автообновления и автоспинов
            if self.update_task:
                self.update_task.cancel()
            if self.auto_spin_task:
                self.auto_spin_task.cancel()

            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            await self.session_manager.close_all_clients()

    def stop(self):
        """Остановка бота"""
        self.is_running = False