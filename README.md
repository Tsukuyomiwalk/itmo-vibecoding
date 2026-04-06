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
| `/popular` | Показать кнопки популярных запросов | `/popular` |
| `/lang <ru|en>` | Переключить язык интерфейса | `/lang en` |

## Источники данных

- **Фиатные валюты:** [open.er-api.com](https://open.er-api.com) — бесплатно, без API-ключа
- **Криптовалюты:** [CoinGecko API](https://www.coingecko.com/en/api) — бесплатно, без API-ключа

## Стек технологий

- **Python 3.11**
- **python-telegram-bot 21** — асинхронная работа с Telegram Bot API
- **httpx** — асинхронные HTTP-запросы к внешним API
- **SQLite** — хранение списков наблюдения пользователей
- **python-dotenv** — управление переменными окружения
- **Локализация RU/EN** — сообщения бота на двух языках

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

## Скриншоты работы бота

### Основные сценарии

![Скриншот 1](<Снимок экрана 2026-04-06 в 17.09.22.png>)
![Скриншот 2](<Снимок экрана 2026-04-06 в 17.09.25.png>)
![Скриншот 3](<Снимок экрана 2026-04-06 в 17.09.32.png>)
![Скриншот 4](<Снимок экрана 2026-04-06 в 17.09.39.png>)

### Деплой и улучшения

![Скриншот 5](<Снимок экрана 2026-04-06 в 17.44.04.png>)
![Скриншот 6](<Снимок экрана 2026-04-06 в 18.12.47.png>)
![Скриншот 7](<Снимок экрана 2026-04-06 в 18.13.50.png>)
![Скриншот 8](<Снимок экрана 2026-04-06 в 18.16.01.png>)

## Отчеты по лабораторным

- `lab1/lab1_report.md`
- `lab2/lab2_report.md`
- `lab3/lab3_report.md`

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
