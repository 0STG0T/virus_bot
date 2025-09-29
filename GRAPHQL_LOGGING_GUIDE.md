# 📝 Подробное Логирование GraphQL Запросов

## ✨ Новая Функция: Детальное Логирование API

Теперь все GraphQL запросы и ответы логируются в отдельные файлы с полной детализацией для диагностики и мониторинга.

### 📊 Структура Логирования

```
logs/
├── general_2025-01-15.log          # Общие логи системы
├── graphql_2025-01-15.log          # Детальные GraphQL логи (по дням)
├── debug_2025-01-15.log            # Debug информация
├── virus_bot.log                   # Ротирующий общий лог (50MB)
└── graphql_requests.log            # Ротирующий GraphQL лог (100MB)
```

### 🔍 Что Логируется

#### 1. Каждый GraphQL Запрос:
```
=== GraphQL REQUEST +573181322034 ===
URL: https://virusgift.pro/api/graphql/query
Operation: startRouletteSpin
Headers: {
  "Authorization": "Bearer jwt_token_here",
  "Content-Type": "application/json",
  ...
}
Payload: [
  {
    "query": "mutation startRouletteSpin($input: StartRouletteSpinInput!) { ... }",
    "variables": {
      "input": {
        "type": "X1"
      }
    },
    "operationName": "startRouletteSpin"
  }
]
```

#### 2. Каждый GraphQL Ответ:
```
=== GraphQL RESPONSE +573181322034 ===
Status: 200
Response Headers: {
  "content-type": "application/json",
  "x-request-id": "abc123",
  ...
}
Response Body:
{
  "data": {
    "startRouletteSpin": {
      "success": true,
      "prize": {
        "id": "prize_123",
        "name": "5 Stars",
        "isClaimable": true
      }
    }
  }
}
=== END GraphQL +573181322034 ===
```

### 🔐 Безопасность

**JWT токены маскируются** в логах авторизации:
```
"token": "eyJhbGciOi...JV_UyUi" -> "token": "eyJhbGciOi...V_UyUi"
                                           ^^^^^^^^^^    ^^^^^^
                                           первые 10    последние 10
```

### 📁 Типы Логов

#### **GraphQL Логи** (`logs/graphql_*.log`)
- Все запросы к GraphQL API
- Полные заголовки и тела запросов/ответов
- Красивое форматирование JSON
- Отдельно от основных логов

#### **Общие Логи** (`logs/general_*.log`)
- Работа бота и системы
- Успехи и ошибки операций
- Статистика выполнения

#### **Debug Логи** (`logs/debug_*.log`)
- Подробная отладочная информация
- Трассировка выполнения
- Только для модулей virus_api и spin_worker

### ⚙️ Настройка

#### Автоматическая Инициализация:
Логирование настраивается автоматически при импорте:
```python
# В virus_api.py и telegram_bot.py
from logging_config import setup_logging
setup_logging()
```

#### Конфигурация:
```python
# logging_config.py
logs_dir = "./logs"              # Папка логов
maxBytes=50*1024*1024           # Размер ротации общих логов (50MB)
maxBytes=100*1024*1024          # Размер ротации GraphQL логов (100MB)
backupCount=5                   # Количество backup файлов
```

### 🔧 Использование

#### Просмотр GraphQL Логов:
```bash
# Последние GraphQL запросы
tail -f logs/graphql_requests.log

# Поиск конкретных операций
grep "startRouletteSpin" logs/graphql_*.log

# Поиск ошибок в API
grep "ERROR\|error" logs/graphql_*.log
```

#### Просмотр Общих Логов:
```bash
# Последние общие события
tail -f logs/general_*.log

# Статистика автоспинов
grep "Автоматические Платные Спины" logs/general_*.log
```

### 📈 Преимущества

1. **Полная Прозрачность**: видны все запросы и ответы API
2. **Диагностика**: легко найти причину проблем
3. **Мониторинг**: отслеживание производительности API
4. **Отладка**: детальная информация для разработки
5. **Аудит**: полная история взаимодействий с API

### 🎯 Практические Примеры

#### Поиск Ошибок Конкретного Аккаунта:
```bash
grep "+573181322034" logs/graphql_*.log | grep -A 10 -B 5 "error"
```

#### Анализ Времени Ответа:
```bash
grep "Response Headers" logs/graphql_*.log | grep "x-response-time"
```

#### Статистика по Операциям:
```bash
grep "Operation:" logs/graphql_*.log | sort | uniq -c
```

### 🚨 Важные Моменты

1. **Размер Логов**: GraphQL логи могут быть большими (100MB+ при 500 аккаунтах)
2. **Производительность**: Логирование добавляет ~5-10ms к каждому запросу
3. **Конфиденциальность**: JWT токены маскируются для безопасности
4. **Ротация**: Старые логи автоматически архивируются

### 🧪 Тестирование

```bash
# Тест логирования
python test_graphql_logging.py

# Результат:
# ✅ Созданы тестовые GraphQL запросы
# ✅ Логи записаны в logs/graphql_*.log
# ✅ Проверена маскировка токенов
```

### 📊 Ожидаемый Размер Логов

Для 500 аккаунтов в день:
- **GraphQL логи**: 20-50 MB (зависит от активности)
- **Общие логи**: 5-10 MB
- **Debug логи**: 10-20 MB

### ✅ Готово к Использованию!

Подробное логирование GraphQL:
- ✅ Автоматически активируется
- ✅ Отдельные файлы по типам логов
- ✅ Ротация для экономии места
- ✅ Безопасная маскировка токенов
- ✅ Красивое форматирование JSON
- ✅ Полная трассировка запросов/ответов

**Все готово для диагностики и мониторинга 500+ аккаунтов!** 🚀