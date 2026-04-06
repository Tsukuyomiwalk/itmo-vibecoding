# CryptoRates Bot

Telegram-бот для отслеживания курсов фиатных валют и криптовалют в реальном времени.

**Username:** `@itmoftmi_daniil_latanov_bot`

**Видео-демо:** [Запись экрана 2026-04-06](https://drive.google.com/file/d/1h6lvpD1okxm-TsB4WntWQDWn21SDBVPz/view?usp=sharing)

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

### Lab1 — базовый бот и команды

<img src="./Снимок экрана 2026-04-06 в 17.09.22.png" alt="Скриншот 1" width="380" />
<img src="./Снимок экрана 2026-04-06 в 17.09.25.png" alt="Скриншот 2" width="380" />

### Lab2 — интеграция с данными (API/БД)

<img src="./Снимок экрана 2026-04-06 в 17.09.32.png" alt="Скриншот 3" width="380" />
<img src="./Снимок экрана 2026-04-06 в 17.09.39.png" alt="Скриншот 4" width="380" />

### Lab3 — деплой, фидбек и улучшения

<img src="./Снимок экрана 2026-04-06 в 17.44.04.png" alt="Скриншот 5" width="380" />
<img src="./Снимок экрана 2026-04-06 в 18.12.47.png" alt="Скриншот 6" width="380" />
<img src="./Снимок экрана 2026-04-06 в 18.13.50.png" alt="Скриншот 7" width="380" />
<img src="./Снимок экрана 2026-04-06 в 18.16.01.png" alt="Скриншот 8" width="380" />

## Что улучшено по отзывам

- Добавлена мультиязычность RU/EN и команда `/lang <ru|en>`.
- Улучшены тексты ошибок, стали более понятные и дружелюбные.
- Команды публикуются в Telegram Menu при запуске бота.
- Добавлена команда `/popular` с кнопками популярных валют и криптовалют.
- Устранены ложные ошибки по популярным тикерам (ретрай при rate limit API).

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
