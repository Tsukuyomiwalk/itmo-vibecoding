# CryptoRates Bot

Telegram-бот для отслеживания курсов фиатных валют и криптовалют в реальном времени.

**Username:** `@itmoftmi_daniil_latanov_bot`

## Функционал

| Команда | Описание | Пример |
|---------|----------|--------|
| `/start` | Приветствие | `/start` |
| `/help` | Список команд | `/help` |
| `/rate <код>` | Курс валюты к рублю | `/rate USD` |
| `/crypto <тикер>` | Цена криптовалюты в USD + изменение за 24ч | `/crypto BTC` |
| `/convert <сумма> <из> <в>` | Конвертация | `/convert 100 USD EUR` |
| `/watch <код>` | Добавить в список наблюдения | `/watch ETH` |
| `/unwatch <код>` | Удалить из списка | `/unwatch ETH` |
| `/watchlist` | Показать список с актуальными ценами | `/watchlist` |

## Источники данных

- **Фиатные валюты:** [open.er-api.com](https://open.er-api.com) — бесплатно, без API-ключа
- **Криптовалюты:** [CoinGecko API](https://www.coingecko.com/en/api) — бесплатно, без API-ключа

## Стек технологий

- **Python 3.11**
- **python-telegram-bot 21** — асинхронная работа с Telegram Bot API
- **httpx** — асинхронные HTTP-запросы к внешним API
- **SQLite** — хранение списков наблюдения пользователей
- **python-dotenv** — управление переменными окружения

## Локальный запуск

### 1. Создай бота в Telegram

Открой [@BotFather](https://t.me/BotFather), отправь `/newbot` и следуй инструкциям.  
Username бота должен быть: `itmoftmi_daniil_latanov_bot`

### 2. Установи зависимости

```bash
pip install -r requirements.txt
```

### 3. Настрой переменные окружения

```bash
cp .env.example .env
# Открой .env и вставь свой токен от BotFather
```

### 4. Запусти бота

```bash
python bot.py
```

## Запуск через Docker (Lab 3)

```bash
# Убедись, что .env файл создан
cp .env.example .env
# Вставь токен в .env

# Запуск
docker-compose up -d

# Логи
docker-compose logs -f

# Остановка
docker-compose down
```

## Деплой на Railway

1. Запушь код на GitHub
2. Зайди на [railway.app](https://railway.app) → New Project → Deploy from GitHub repo
3. В настройках проекта добавь переменную окружения `BOT_TOKEN`
4. Railway автоматически запустит бота через `Procfile`

## Структура проекта

```
├── bot.py            # Основной файл бота (обработчики команд)
├── api_client.py     # Интеграция с внешними API (CoinGecko, open.er-api)
├── database.py       # Работа с SQLite (список наблюдения)
├── requirements.txt  # Зависимости
├── .env.example      # Пример файла конфигурации
├── .gitignore        # Исключения для Git
├── Dockerfile        # Docker-образ
├── docker-compose.yml
└── Procfile          # Для деплоя на Railway/Heroku
```
