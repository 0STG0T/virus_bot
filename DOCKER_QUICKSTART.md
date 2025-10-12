# 🐳 Docker Quick Start

Быстрый старт для запуска Virus Bot в Docker.

## Предварительные требования

- Docker и Docker Compose установлены
- `.session` файлы ваших Telegram аккаунтов
- Telegram Bot Token от [@BotFather](https://t.me/BotFather)
- API credentials от [my.telegram.org/apps](https://my.telegram.org/apps)

## Запуск за 5 минут

### 1. Клонирование репозитория

```bash
git clone https://github.com/0STG0T/virus_bot.git
cd virus_bot
git checkout docker-setup
```

### 2. Настройка переменных окружения

```bash
# Скопируйте пример
cp .env.example .env

# Отредактируйте .env файл
nano .env
```

Минимально необходимые параметры в `.env`:

```bash
VIRUS_BOT_TOKEN=ваш_токен_от_BotFather
LOG_CHAT_ID=ваш_telegram_id
API_ID=ваш_api_id
API_HASH=ваш_api_hash
```

### 3. Добавьте сессии

Поместите `.session` файлы в папку `sessions/`:

```bash
# Пример
cp ~/ваши_сессии/*.session ./sessions/
```

### 4. Запуск

```bash
# Запуск в фоновом режиме
docker-compose up -d

# Просмотр логов
docker-compose logs -f
```

### 5. Использование

Отправьте `/start` в Telegram бот и используйте интерфейс для управления.

## Основные команды

```bash
# Запуск
docker-compose up -d

# Остановка
docker-compose down

# Перезапуск
docker-compose restart

# Логи
docker-compose logs -f

# Логи последние 100 строк
docker-compose logs --tail=100

# Статус
docker-compose ps

# Обновление
git pull
docker-compose up -d --build
```

## Структура папок

```
virus_bot/
├── .env                    # Ваши настройки (создать из .env.example)
├── docker-compose.yml      # Docker Compose конфигурация
├── Dockerfile              # Docker образ
└── sessions/               # Telegram сессии
    ├── account1.session
    ├── account2.session
    └── ...
```

## Важные моменты

1. **Безопасность**: Файл `.env` содержит чувствительные данные - не коммитьте его в git
2. **Сессии**: Папка `sessions/` монтируется как volume - сессии сохраняются между перезапусками
3. **Логи**: Папка `logs/` тоже монтируется для персистентности логов
4. **Ресурсы**: По умолчанию ограничение 2GB RAM и 2 CPU (настраивается в docker-compose.yml)

## Устранение проблем

### Бот не запускается

```bash
# Проверьте логи
docker-compose logs

# Проверьте переменные окружения
docker-compose config

# Пересоберите образ
docker-compose down
docker-compose up -d --build
```

### Сессии не загружаются

```bash
# Проверьте права
ls -la sessions/

# Исправьте если нужно
chmod 644 sessions/*.session
```

### Контейнер постоянно перезапускается

```bash
# Смотрите логи для выявления ошибки
docker-compose logs --tail=50

# Проверьте что все переменные окружения заполнены
cat .env
```

## Полная документация

Смотрите [README.md](README.md) для полной документации.

## Поддержка

Если возникли проблемы:
1. Проверьте логи: `docker-compose logs -f`
2. Убедитесь что все переменные окружения заполнены
3. Проверьте права доступа к сессиям
4. Откройте issue на GitHub

---

✨ **Готово!** Бот должен быть запущен и готов к работе.
