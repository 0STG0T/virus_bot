# Virus Gift Bot

Бот для автоматизации игры VirusGift.pro с поддержкой Docker.

## Особенности

- ✅ Автоматические фри-спины (каждые 24 часа)
- ✅ Автоматические платные спины при достижении порога
- ✅ Автоматический обмен дешевых подарков на звезды
- ✅ Умная активация звезд (оставляет минимум 100⭐ в инвентаре для ценных подарков)
- ✅ Проверка валидности аккаунтов
- ✅ Уведомления о ценных призах
- ✅ Поддержка 500+ аккаунтов одновременно
- ✅ Удобный Telegram интерфейс

## Системные требования

- Python 3.11+ (для локального запуска)
- Docker и Docker Compose (для Docker запуска)
- Linux/macOS/Windows
- Минимум 2GB RAM для 500+ аккаунтов

---

## 🐳 Установка через Docker (рекомендуется)

### 1. Клонирование репозитория

```bash
git clone https://github.com/0STG0T/virus_bot.git
cd virus_bot
git checkout docker-setup
```

### 2. Настройка переменных окружения

Скопируйте пример конфигурации:

```bash
cp .env.example .env
```

Отредактируйте `.env` файл и укажите свои данные:

```bash
nano .env  # или любой другой текстовый редактор
```

**Обязательные параметры:**
- `VIRUS_BOT_TOKEN` - токен вашего Telegram бота (получить у [@BotFather](https://t.me/BotFather))
- `LOG_CHAT_ID` - ваш Telegram ID для уведомлений (узнать у [@userinfobot](https://t.me/userinfobot))
- `API_ID` и `API_HASH` - получить на [my.telegram.org/apps](https://my.telegram.org/apps)

### 3. Подготовка сессий

Поместите `.session` файлы ваших Telegram аккаунтов в папку `sessions/`:

```bash
# Пример структуры
sessions/
├── account1.session
├── account2.session
└── account3.session
```

### 4. Запуск бота

```bash
# Сборка и запуск в фоновом режиме
docker-compose up -d

# Просмотр логов
docker-compose logs -f

# Остановка бота
docker-compose down
```

### 5. Управление

```bash
# Перезапуск бота
docker-compose restart

# Просмотр статуса
docker-compose ps

# Обновление кода и перезапуск
git pull
docker-compose up -d --build
```

---

## 💻 Установка для локального запуска

### 1. Клонирование и установка зависимостей

```bash
git clone https://github.com/0STG0T/virus_bot.git
cd virus_bot
pip install -r requirements.txt
```

### 2. Подготовка

Поместите `.session` файлы ваших Telegram аккаунтов в папку `sessions/`.

### 3. Запуск

```bash
python main.py
```

При запуске бот запросит токен Telegram бота (получить у [@BotFather](https://t.me/BotFather)).

---

## ⚙️ Конфигурация

### Docker конфигурация

Основные настройки задаются в `.env` файле:

```bash
# Обязательные
VIRUS_BOT_TOKEN=ваш_токен
LOG_CHAT_ID=ваш_chat_id
API_ID=ваш_api_id
API_HASH=ваш_api_hash

# Опциональные
MAX_CONCURRENT_SESSIONS=100
AUTO_SPIN_ENABLED=true
AUTO_SPIN_THRESHOLD=200
AUTO_GIFT_EXCHANGE_ENABLED=true
AUTO_GIFT_EXCHANGE_THRESHOLD=50
```

### Локальная конфигурация

Настройки находятся в файле `config.py`:

```python
# Автоматические платные спины
AUTO_SPIN_ENABLED = True
AUTO_SPIN_THRESHOLD = 200  # Звезд для автоспина

# Автообмен подарков
AUTO_GIFT_EXCHANGE_ENABLED = True
AUTO_GIFT_EXCHANGE_THRESHOLD = 50  # Максимальная стоимость для обмена
```

---

## 📊 Использование

После запуска бота отправьте команду `/start` в Telegram.

### Доступные команды через интерфейс:

- **🎰 Фри спины** - выполнить бесплатные спины на всех аккаунтах
- **💰 Баланс** - проверить баланс звезд и подарков
- **✅ Проверить валидность** - проверить работоспособность аккаунтов
- **🔄 Обновить статистику** - обновить данные по аккаунтам

### Автоматические операции:

- **Автоспины** - бот автоматически проверяет баланс каждый час и делает платные спины при ≥200⭐
- **Автообмен** - дешевые подарки (≤50⭐) автоматически обмениваются на звезды
- **Активация звезд** - автоматически активирует звезды, оставляя минимум 100⭐ в инвентаре для ценных подарков

---

## 🔧 Логика активации звезд

Бот использует умную логику активации:

- ❌ Не активирует звезды если в инвентаре < 100⭐
- ✅ При ≥100⭐ активирует только избыток: `(inventory - 100)⭐`
- 📦 Всегда оставляет минимум **100⭐ в инвентаре** для лучшей вероятности ценных подарков

**Примеры:**
- 50⭐ в инвентаре → 0⭐ активируется (недостаточно)
- 150⭐ в инвентаре → 50⭐ активируется (оставляет 100⭐)
- 300⭐ в инвентаре → 200⭐ активируется (оставляет 100⭐)

---

## 📝 Мониторинг

### Docker логи

```bash
# Все логи
docker-compose logs -f

# Последние 100 строк
docker-compose logs --tail=100

# Логи с временными метками
docker-compose logs -f -t
```

### Локальные логи

Логи сохраняются в папке `logs/`:
- `main.log` - основной лог
- `graphql_requests.log` - GraphQL запросы (если включено детальное логирование)

---

## 🐛 Устранение неполадок

### Docker проблемы

**Бот не запускается:**
```bash
# Проверьте логи
docker-compose logs

# Пересоберите образ
docker-compose down
docker-compose up -d --build
```

**Сессии не загружаются:**
```bash
# Проверьте права доступа
ls -la sessions/

# Исправьте права если нужно
chmod 644 sessions/*.session
```

### Локальные проблемы

**ModuleNotFoundError:**
```bash
pip install -r requirements.txt --upgrade
```

**Ошибки сессий:**
- Убедитесь что `.session` файлы созданы через Telethon
- Проверьте что API_ID и API_HASH корректны

---

## 📁 Структура проекта

```
virus_bot/
├── Dockerfile              # Docker образ
├── docker-compose.yml      # Docker Compose конфигурация
├── .env.example            # Пример переменных окружения
├── .dockerignore           # Исключения для Docker
├── requirements.txt        # Python зависимости
├── config.py               # Конфигурация
├── main.py                 # Точка входа
├── telegram_bot.py         # Telegram интерфейс
├── spin_worker.py          # Логика спинов
├── virus_api.py            # API клиент
├── session_manager.py      # Управление сессиями
└── sessions/               # Telegram сессии
    └── *.session
```

---

## 🤝 Участие в разработке

1. Fork репозитория
2. Создайте ветку для фичи (`git checkout -b feature/amazing-feature`)
3. Закоммитьте изменения (`git commit -m 'Add amazing feature'`)
4. Запушьте ветку (`git push origin feature/amazing-feature`)
5. Откройте Pull Request

---

## 📜 Лицензия

Этот проект предназначен только для образовательных целей.

---

## ⚠️ Дисклеймер

Используйте этот бот на свой страх и риск. Авторы не несут ответственности за возможные последствия использования бота, включая, но не ограничиваясь, блокировкой аккаунтов.
