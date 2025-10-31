# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Virus Bot - автоматизация игры VirusGift.pro через Telegram бот. Система поддерживает 500+ аккаунтов, выполняет фри спины, обрабатывает награды, управляет инвентарем и автоматизирует платные спины.

## Running the Bot

```bash
# Установка зависимостей
pip install -r requirements.txt

# Запуск (требуется токен Telegram бота от @BotFather)
python main.py
```

Бот запрашивает токен при запуске. Сессионные файлы должны находиться в папке `sessions/` (формат: `имя_аккаунта.session`, Telethon format).

## Architecture Overview

### Core Components

**main.py** - Entry point. Создает VirusBotManager и запускает Telegram бота. Проверяет наличие сессий, запрашивает токен бота.

**telegram_bot.py (VirusBotManager)** - Telegram bot UI. Управляет интерфейсом бота, обрабатывает команды (/start), callback кнопки (фри спины, баланс, валидация). Запускает ежечасные автоматические платные спины для аккаунтов с балансом >= 200 звезд. Содержит progress callbacks для отображения прогресса операций.

**session_manager.py (SessionManager)** - Управление Telegram сессиями. Загружает .session файлы из `sessions/`, создает TelegramClient для каждого аккаунта, использует семафоры для предотвращения SQLite database lock conflicts. Кэширует валидацию сессий (TTL: 5 минут).

**spin_worker.py (SpinWorker)** - Основная логика автоматизации. Выполняет фри спины и платные спины, обрабатывает требования подписок на каналы, автоматически кликает по тестовым ссылкам (WebApp и channels), активирует звезды из инвентаря, автоматически продает дешевые подарки (≤200 звезд). Поддерживает batch обработку с progress callbacks.

**virus_api.py (VirusAPI)** - GraphQL API клиент для virusgift.pro. Выполняет авторизацию через authTelegramInitData, получает JWT токены, делает спины (фри и платные), управляет инвентарем (getRouletteInventory), активирует звезды (claimRoulettePrize), обменивает подарки (exchangeRoulettePrizeToStarsBalance). Поддерживает кэширование (инвентарь, балансы, данные пользователей) для производительности.

**webapp_auth.py (WebAppAuth)** - Авторизация в WebApp. Получает init_data от Telegram WebApp (@virus_play_bot), обрабатывает клики по тестовым ссылкам через requestWebView.

**config.py** - Конфигурация. Telegram API credentials, GraphQL endpoints, таймауты, лимиты конкурентности (MAX_CONCURRENT_SESSIONS: 100), пороги автоматизации (AUTO_SPIN_THRESHOLD: 200 звезд), настройки кэширования.

**logging_config.py** - Настройка логирования. Создает отдельные логи для GraphQL запросов/ответов, общих событий, debug информации. Маскирует JWT токены в логах. Ротация логов (50MB для общих, 100MB для GraphQL).

### Key Workflows

**Фри спин (perform_single_spin)**:
1. Создает TelegramClient через SessionManager
2. Получает WebApp auth data через WebAppAuth
3. Создает VirusAPI и авторизуется (получает JWT)
4. Проверяет доступность спина (check_spin_availability)
5. Выполняет спин (perform_spin), до 4 попыток с автоматической обработкой ошибок:
   - **TEST_SPIN_URL_CLICK_REQUIRED**: Определяет тип ссылки (WebApp/channel), кликает, регистрирует через API, повторяет спин
   - **TELEGRAM_SUBSCRIPTION_REQUIRED**: Извлекает username из сообщения об ошибке, подписывается (публичный канал или invite link), повторяет спин
   - **BALANCE_REPLENISHMENT_REQUIRED**: Пробует tunnel/portal clicks, task clicks, WebApp ссылки из reward, повторяет спин
6. Обрабатывает награду (process_reward)
7. Активирует звезды из инвентаря (activate_all_stars)
8. Автоматически продает дешевые подарки если GIFT_EXCHANGE_AFTER_SPIN=True

**Платный спин (perform_single_paid_spin)**:
1. Проверяет баланс >= 200 звезд (can_perform_paid_spin)
2. Выполняет платный спин (perform_paid_spin)
3. Активирует звезды и продает дешевые подарки

**Проверка баланса (check_single_account_balance)**:
1. Получает user info (get_user_info) с кэшированием
2. Получает инвентарь (get_roulette_inventory) с кэшированием
3. Подсчитывает подарки (status IN_PROGRESS/active, не Stars/Viruses)
4. Подсчитывает неактивированные звезды в инвентаре (status NONE)
5. Автоматически продает дешевые подарки если GIFT_EXCHANGE_ON_BALANCE_CHECK=True

**Автоматические платные спины (perform_hourly_auto_spins)**:
Запускается каждый час из auto_update_and_spins_monitor:
1. Проверяет баланс всех аккаунтов
2. Фильтрует аккаунты с балансом >= AUTO_SPIN_THRESHOLD (200 звезд)
3. Выполняет платные спины батчами (perform_paid_spins_batch)
4. Отправляет уведомление с результатами

## GraphQL API Structure

API endpoint: `https://virusgift.pro/api/graphql/query`

**Авторизация**: JWT токен в заголовке `Authorization: Bearer <token>`

**Batch mode**: API ожидает массив запросов с заголовком `x-batch: true`

**Ключевые мутации**:
- `authTelegramInitData(initData, refCode)` - получить JWT токен
- `startRouletteSpin(input: {type})` - сделать спин (type: "X1" для фри, "PAID" для платного)
- `claimRoulettePrize(input: {userPrizeId})` - активировать приз из инвентаря
- `exchangeRoulettePrizeToStarsBalance(input: {userPrizeId})` - продать приз за звезды
- `markTestSpinUrlClick(initData)` - зарегистрировать клик по тестовой ссылке
- `markTestSpinTonnelClick` - пройти tunnel onboarding
- `markTestSpinPortalClick` - пройти portal onboarding
- `markTestSpinTaskClick(taskId)` - зарегистрировать клик по задаче

**Ключевые запросы**:
- `me` - информация о пользователе (баланс, звезды, настройки)
- `getRouletteInventory(cursor, limit)` - получить инвентарь (пагинация)

## Important Implementation Details

### Session Management
- Telethon .session файлы загружаются из `sessions/` (case-insensitive: .session, .Session, .SESSION)
- SessionManager использует семафор (limit: 10) для предотвращения SQLite database lock conflicts
- При "database is locked" ошибке - автоматический retry с задержкой
- Валидация сессий кэшируется (TTL: SESSION_VALIDATION_CACHE_TTL = 300s)

### Performance Optimization
- **Кэширование**: Инвентарь (180s), балансы (120s), user data (600s)
- **Параллельная обработка**: Все batch операции выполняются параллельно без семафоров для максимальной скорости
- **Rate limiting**: MIN_REQUEST_INTERVAL = 0.5s между запросами для каждого аккаунта
- **Connection pooling**: HTTP_CONNECTION_POOL_SIZE = 100, keepalive_timeout = 60s

### Error Handling Patterns

**Спин ошибки (perform_spin)** - Автоматическая обработка с до 4 попыток:

1. **TEST_SPIN_URL_CLICK_REQUIRED** - Требуется клик по ссылке:
   - Извлекает ссылку из reward['link']
   - Определяет тип: WebApp (/dapp, startapp=) или канал
   - WebApp: открывает через requestWebView, получает init_data, регистрирует через mark_test_spin_task_click
   - Канал: подписывается через handle_subscription_requirement, регистрирует клик
   - Ждет 2-5 секунд, повторяет спин

2. **TELEGRAM_SUBSCRIPTION_REQUIRED** - Требуется подписка на канал:
   - Извлекает @username из сообщения об ошибке через regex
   - Берет данные из reward (username, url) если есть
   - Пробует подписку по username (быстрее для публичных каналов)
   - Fallback: подписка по ссылке (поддерживает приватные invite links)
   - Ждет 5 секунд, повторяет спин
   - **Улучшенная обработка**: детальное логирование всех попыток подписки с traceback

3. **BALANCE_REPLENISHMENT_REQUIRED** - Требуется пополнение баланса (НОВОЕ):
   - Метод 1: Пробует onboarding действия (tunnel click, portal click)
   - Метод 2: Ищет task_id в reward, вызывает mark_test_spin_task_click
   - Метод 3: Ищет link в reward, обрабатывает как WebApp
   - Если успешно - повторяет спин
   - Если неудачно - логирует детальную информацию для обновления логики

4. **TEST_SPIN_TONNEL_CLICK_REQUIRED** - Требуется tunnel click:
   - Автоматически обрабатывается в claim_roulette_prize

5. **Portal click required** - Требуется portal click:
   - Автоматически обрабатывается в claim_roulette_prize

**Обработка ссылок (click_test_spin_url)**:
- WebApp ссылки (/dapp, startapp=) - открываются через requestWebView, возвращают init_data
- Канал ссылки (t.me/username) - подписываются через JoinChannelRequest
- Приватные ссылки (t.me/+hash, t.me/joinchat/hash) - подписываются через ImportChatInviteRequest

**Обработка подписок (handle_subscription_requirement)** - ПРОБУЕТ ВСЕ МЕТОДЫ:
- **ВАЖНО**: Пробует ВСЕ возможные действия, не останавливается на первой ошибке
- Возвращает True если хотя бы один метод сработал

**МЕТОД 1 - Обработка по username**:
- Получает entity по @username
- Если Channel → подписывается через JoinChannelRequest
- Если User/Bot → отправляет `/start`
- Не падает при ошибках, продолжает следующие методы

**МЕТОД 2 - Обработка по URL** (3 варианта):
- **Вариант 2.1**: Приватная invite ссылка (t.me/+hash, t.me/joinchat/hash)
  - Извлекает hash, использует ImportChatInviteRequest
- **Вариант 2.2**: Ссылка на бота с параметром start (t.me/bot?start=param)
  - Извлекает bot username и start параметр
  - Отправляет `/start параметр` боту
- **Вариант 2.3**: Публичная ссылка на канал (t.me/channel_name)
  - Получает entity по username из URL
  - Если Channel → подписывается
  - Если User/Bot → отправляет `/start`

**Логирование**: Детальное логирование каждого метода с эмодзи (📡 Метод X, ✅ успех, ⚠️ предупреждение)

**Стратегия**: Разработчики API могут менять требования → бот пробует ВСЕ возможные действия

### Inventory Logic

**Активация звезд (activate_all_stars)** - ЛОГИКА ДЛЯ ПЛАТНЫХ СПИНОВ:
- **КРИТИЧНО**: Активируем ТОЛЬКО если в инвентаре >= 200⭐
- **Стратегия**: Копим 200⭐ в инвентаре → активируем ВСЕ → платный спин → повторяем с 0
- **Проверка 1**: Уже есть >= 200⭐ на балансе?
  - Если ДА - активация не нужна (уже готовы к платному спину)
- **Проверка 2**: Есть >= 200⭐ в инвентаре?
  - Если НЕТ - активация отложена, продолжаем копить
  - Если ДА - активируем **ВСЕ** звезды из инвентаря
- **После активации**: Автоматически делается платный спин (стоит 200⭐)
- **Уведомление**: Отправляется уведомление об активации и автоспине в Telegram
- Сканирует весь инвентарь по страницам (pagination via cursor/nextCursor)
- Активирует только звезды со status="NONE" и isClaimable=True
- Активирует **ВСЕ** звезды, не оставляя ничего в инвентаре

**Пример цикла активации**:
1. Баланс: 0⭐, Инвентарь: 50⭐ → ❌ НЕ активируем (< 200⭐)
2. Баланс: 0⭐, Инвентарь: 150⭐ → ❌ НЕ активируем (< 200⭐)
3. Баланс: 0⭐, Инвентарь: 250⭐ → ✅ Активируем ВСЕ 250⭐
4. Баланс становится: 250⭐, Инвентарь: 0⭐
5. 🎰 Автоматический платный спин → Баланс: 50⭐ (остаток)
6. Продолжаем копить в инвентарь до 200⭐...

**Автопродажа подарков (auto_exchange_cheap_gifts)**:
- Продает дешевые подарки автоматически без ограничений
- Продает подарки со status IN_PROGRESS/active (не NONE!)
- Фильтрует по цене <= AUTO_GIFT_EXCHANGE_THRESHOLD (200 звезд)
- Проверяет isClaimable или isExchangeable
- Пропускает Stars и Viruses (определяется по имени)
- Стратегия: сначала прямой обмен (exchangeRoulettePrizeToStarsBalance), fallback - claim
- unlock_at - это время для вывода в Telegram, НЕ влияет на продажу за звезды

**Уведомления**:
- Активация звезд: "💎 АКТИВАЦИЯ | сессия | Активировано ВСЕ: N⭐ | 🎰 Автоматический платный спин..."
- Фри спин подарки: "🎁 ФРИ СПИН | сессия | название | ценность⭐"
- Дорогие подарки (> HIGH_VALUE_THRESHOLD): "💎 ФРИ СПИН | сессия | название | ценность⭐"
- Платные спины: "🎁 ПЛАТНЫЙ СПИН | сессия | название | ценность⭐"
- Автоматические платные спины после активации: "🎁 АВТО ПЛАТНЫЙ СПИН | сессия | название"

## Configuration

**Ключевые параметры в config.py**:

```python
# Производительность
MAX_CONCURRENT_SESSIONS = 100  # Параллельные сессии
DELAY_BETWEEN_ACCOUNTS = 0.3   # Задержка между аккаунтами
HTTP_CONNECTION_POOL_SIZE = 100

# Автоматизация
AUTO_SPIN_ENABLED = True
AUTO_SPIN_THRESHOLD = 200      # Минимум звезд для автоспина
AUTO_SPIN_CHECK_INTERVAL = 300 # Интервал проверки (устарело, теперь 1 час)

AUTO_GIFT_EXCHANGE_ENABLED = True
AUTO_GIFT_EXCHANGE_THRESHOLD = 200  # Автопродажа подарков ≤200 звезд
GIFT_EXCHANGE_AFTER_SPIN = True
GIFT_EXCHANGE_ON_BALANCE_CHECK = True

# Кэширование
INVENTORY_CACHE_TTL = 180      # 3 минуты
BALANCE_CACHE_TTL = 120        # 2 минуты
USER_DATA_CACHE_TTL = 600      # 10 минут
SESSION_VALIDATION_CACHE_TTL = 300  # 5 минут
```

## Common Tasks

### Testing a Single Account
```python
# Используйте test_*.py файлы для тестирования
python test_spin.py           # Тест одного спина
python test_full_flow.py      # Полный flow
python test_activation_logic.py  # Тест логики активации
```

### Debugging GraphQL Requests
Все GraphQL запросы/ответы логируются в `logs/graphql_*.log` с полными заголовками, payload и ответами. JWT токены маскируются (первые 10 + последние 10 символов).

### Adding New GraphQL Operations
1. Добавьте метод в VirusAPI класс
2. Используйте `_make_graphql_request(query, variables, operation_name)`
3. API ожидает массив для batch режима: `payload = [single_query]`
4. Парсите ответ: `if isinstance(json_response, list): return json_response[0]`

### Working with Large Account Counts
- Batch операции (perform_spins_batch, validate_all_accounts_batch) поддерживают progress_callback
- Progress callback вызывается с (completed, total) для обновления UI
- Telegram UI обновляется не чаще чем раз в 1.5 секунды для производительности
- Используйте REDUCED_LOGGING_MODE = True для минимизации логов

## Testing Infrastructure

**test_activation_logic.py** - тестирует логику клика по ссылкам (WebApp vs channels)
**test_channel_subscription.py** - тестирует подписку на каналы
**test_full_flow.py** - полный flow: auth, user info, spin, inventory
**test_spin.py** - простой тест спина
**test_webapp.py** - тест WebApp авторизации

## Logging

Логи разделены по типам (см. GRAPHQL_LOGGING_GUIDE.md):
- `logs/general_*.log` - общие события
- `logs/graphql_*.log` - GraphQL запросы/ответы (детально)
- `logs/debug_*.log` - debug информация (virus_api, spin_worker)
- `virus_bot.log` - ротирующий общий лог (50MB)
- `logs/graphql_requests.log` - ротирующий GraphQL лог (100MB)

## Important Notes

- **Не коммитить .env и .session файлы** (они в .gitignore)
- **JWT токены** всегда маскируются в логах для безопасности
- **SQLite locks**: SessionManager автоматически обрабатывает database lock conflicts
- **Case-insensitive sessions**: Поддерживаются .session, .Session, .SESSION
- **Ежечасные автоспины**: Запускаются из auto_update_and_spins_monitor каждый час (не AUTO_SPIN_CHECK_INTERVAL)
- **Инвентарь минимум**: Всегда оставляется 100 звезд в инвентаре (для ценных подарков)
