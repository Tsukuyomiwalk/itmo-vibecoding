"""
CryptoRates Bot — Telegram-бот для отслеживания курсов валют и криптовалют.
Username: @itmoftmi_daniil_latanov_bot

Команды:
  /start          — приветствие
  /help           — список команд
  /rate <код>     — курс валюты (USD, EUR, GBP, JPY ...)
  /crypto <код>   — цена криптовалюты (BTC, ETH, SOL ...)
  /convert <сумма> <из> <в> — конвертация
  /watch <код>    — добавить в список наблюдения
  /unwatch <код>  — удалить из списка наблюдения
  /watchlist      — показать список с текущими ценами
"""

import logging
import os

from dotenv import load_dotenv
from telegram import BotCommand, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

from api_client import get_crypto_price, get_crypto_prices_batch, get_exchange_rate, convert_currency, is_known_ticker
from database import (
    init_db,
    add_to_watchlist,
    remove_from_watchlist,
    get_watchlist,
    get_user_language,
    set_user_language,
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
SUPPORTED_LANGS = {"ru", "en"}

MESSAGES = {
    "ru": {
        "start": (
            "👋 Привет! Я *CryptoRates Bot* — слежу за курсами валют и крипты.\n\n"
            "Попробуй:\n"
            "  /rate USD\n"
            "  /crypto BTC\n"
            "  /convert 100 USD EUR\n"
            "  /help — полный список команд"
        ),
        "help": (
            "📖 *Команды бота:*\n\n"
            "/rate `<код>` — курс валюты к RUB\n"
            "  Пример: `/rate USD`\n\n"
            "/crypto `<код>` — цена криптовалюты в USD\n"
            "  Пример: `/crypto BTC`\n\n"
            "/convert `<сумма> <из> <в>` — конвертация\n"
            "  Пример: `/convert 100 USD EUR`\n\n"
            "/watch `<код>` — добавить в список наблюдения\n"
            "/unwatch `<код>` — удалить из списка\n"
            "/watchlist — текущие цены по списку\n"
            "/popular — кнопки популярных валют и крипты\n"
            "/lang `<ru|en>` — сменить язык"
        ),
        "lang_usage": "Использование: /lang ru или /lang en",
        "lang_saved": "✅ Язык переключен на *{language}*.",
        "rate_usage": "Укажи код валюты. Пример: /rate USD",
        "rate_fail": "❌ Не удалось получить курс для «{code}». Проверь код валюты.",
        "rate_ok": "💱 *{code} → RUB*\n1 {code} = *{result:.2f} ₽*",
        "crypto_usage": "Укажи тикер. Пример: /crypto BTC",
        "crypto_fail": "❌ Не удалось найти «{symbol}». Попробуй полное название (например, bitcoin).",
        "crypto_temp_fail": "⚠️ Временная ошибка источника цен для «{symbol}». Попробуй еще раз через пару секунд.",
        "crypto_ok": "{arrow} *{symbol}*\nЦена: *${price:,.2f}*\nЗа 24ч: {sign}{change:.2f}%",
        "convert_usage": "Пример: /convert 100 USD EUR",
        "convert_amount_error": "Первый аргумент должен быть числом. Пример: /convert 100 USD EUR",
        "convert_fail": "❌ Не удалось конвертировать {from_cur} → {to_cur}.",
        "convert_ok": "💱 *{amount:,.2f} {from_cur}* = *{result:,.2f} {to_cur}*",
        "watch_usage": "Укажи код. Пример: /watch BTC или /watch USD",
        "watch_unknown": "❓ Тикер «{code}» не найден. Попробуй: /watch BTC, /watch USD, /watch ETH",
        "watch_added": "✅ *{code}* добавлен в список наблюдения.",
        "watch_exists": "«{code}» уже в твоем списке.",
        "unwatch_usage": "Укажи код. Пример: /unwatch BTC",
        "unwatch_removed": "🗑 *{code}* удален из списка.",
        "unwatch_missing": "«{code}» не найден в твоем списке.",
        "watchlist_empty": "Список пуст. Добавь тикеры командой /watch BTC или /watch USD",
        "watchlist_loading": "⏳ Получаю цены...",
        "watchlist_title": "📋 *Список наблюдения:*",
        "popular_title": "⭐ Выбери популярный запрос кнопкой ниже:",
    },
    "en": {
        "start": (
            "👋 Hi! I am *CryptoRates Bot* and I track fiat and crypto prices.\n\n"
            "Try:\n"
            "  /rate USD\n"
            "  /crypto BTC\n"
            "  /convert 100 USD EUR\n"
            "  /help — full command list"
        ),
        "help": (
            "📖 *Bot commands:*\n\n"
            "/rate `<code>` — fiat rate to RUB\n"
            "  Example: `/rate USD`\n\n"
            "/crypto `<ticker>` — crypto price in USD\n"
            "  Example: `/crypto BTC`\n\n"
            "/convert `<amount> <from> <to>` — convert currencies\n"
            "  Example: `/convert 100 USD EUR`\n\n"
            "/watch `<code>` — add to watchlist\n"
            "/unwatch `<code>` — remove from watchlist\n"
            "/watchlist — current watchlist prices\n"
            "/popular — quick buttons for popular symbols\n"
            "/lang `<ru|en>` — change language"
        ),
        "lang_usage": "Usage: /lang ru or /lang en",
        "lang_saved": "✅ Language switched to *{language}*.",
        "rate_usage": "Provide currency code. Example: /rate USD",
        "rate_fail": "❌ Failed to get rate for '{code}'. Please check the code.",
        "rate_ok": "💱 *{code} → RUB*\n1 {code} = *{result:.2f} ₽*",
        "crypto_usage": "Provide ticker. Example: /crypto BTC",
        "crypto_fail": "❌ Failed to find '{symbol}'. Try full coin name (for example, bitcoin).",
        "crypto_temp_fail": "⚠️ Temporary price source error for '{symbol}'. Please try again in a few seconds.",
        "crypto_ok": "{arrow} *{symbol}*\nPrice: *${price:,.2f}*\n24h: {sign}{change:.2f}%",
        "convert_usage": "Example: /convert 100 USD EUR",
        "convert_amount_error": "First argument must be a number. Example: /convert 100 USD EUR",
        "convert_fail": "❌ Failed to convert {from_cur} → {to_cur}.",
        "convert_ok": "💱 *{amount:,.2f} {from_cur}* = *{result:,.2f} {to_cur}*",
        "watch_usage": "Provide code. Example: /watch BTC or /watch USD",
        "watch_unknown": "❓ Ticker '{code}' not found. Try: /watch BTC, /watch USD, /watch ETH",
        "watch_added": "✅ *{code}* added to watchlist.",
        "watch_exists": "'{code}' is already in your watchlist.",
        "unwatch_usage": "Provide code. Example: /unwatch BTC",
        "unwatch_removed": "🗑 *{code}* removed from watchlist.",
        "unwatch_missing": "'{code}' not found in your watchlist.",
        "watchlist_empty": "Watchlist is empty. Add symbols with /watch BTC or /watch USD",
        "watchlist_loading": "⏳ Fetching prices...",
        "watchlist_title": "📋 *Watchlist:*",
        "popular_title": "⭐ Tap a popular query button below:",
    },
}


def _resolve_lang(update: Update) -> str:
    user = update.effective_user
    if not user:
        return "ru"

    stored = get_user_language(user.id)
    if stored in SUPPORTED_LANGS:
        return stored

    tg_lang = (user.language_code or "").lower()
    auto_lang = "en" if tg_lang.startswith("en") else "ru"
    set_user_language(user.id, auto_lang)
    return auto_lang


def _t(lang: str, key: str, **kwargs: object) -> str:
    template = MESSAGES.get(lang, MESSAGES["ru"]).get(key, "")
    return template.format(**kwargs)


async def _set_bot_commands(app: Application) -> None:
    """Публикуем команды в меню Telegram при запуске бота."""
    commands = [
        BotCommand("start", "Start / Начать"),
        BotCommand("help", "Help / Помощь"),
        BotCommand("rate", "Fiat rate / Курс валюты"),
        BotCommand("crypto", "Crypto price / Курс крипты"),
        BotCommand("convert", "Convert currency / Конвертация"),
        BotCommand("watch", "Add to watchlist / Добавить"),
        BotCommand("unwatch", "Remove from watchlist / Удалить"),
        BotCommand("watchlist", "Show watchlist / Список"),
        BotCommand("popular", "Popular quick buttons / Популярное"),
        BotCommand("lang", "Language ru|en / Язык"),
    ]
    await app.bot.set_my_commands(commands)
    logger.info("Команды бота опубликованы в Telegram меню.")


# ─── Handlers ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _resolve_lang(update)
    await update.message.reply_text(_t(lang, "start"), parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lang = _resolve_lang(update)
    await update.message.reply_text(_t(lang, "help"), parse_mode="Markdown")


async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    current_lang = _resolve_lang(update)
    if not update.effective_user:
        return
    if not context.args:
        await update.message.reply_text(_t(current_lang, "lang_usage"))
        return

    candidate = context.args[0].lower().strip()
    if candidate not in SUPPORTED_LANGS:
        await update.message.reply_text(_t(current_lang, "lang_usage"))
        return

    set_user_language(update.effective_user.id, candidate)
    await update.message.reply_text(
        _t(candidate, "lang_saved", language=candidate.upper()),
        parse_mode="Markdown",
    )


async def popular(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать быстрые кнопки популярных валют и криптовалют."""
    lang = _resolve_lang(update)
    keyboard = [
        ["/rate USD", "/rate EUR", "/rate CNY"],
        ["/crypto BTC", "/crypto ETH", "/crypto SOL"],
        ["/watch USD", "/watch BTC", "/watchlist"],
    ]
    markup = ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=True,
    )
    await update.message.reply_text(_t(lang, "popular_title"), reply_markup=markup)


async def rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать курс валюты к RUB."""
    lang = _resolve_lang(update)
    if not context.args:
        await update.message.reply_text(_t(lang, "rate_usage"))
        return

    code = context.args[0].upper()
    result = await get_exchange_rate(code)

    if result is None:
        await update.message.reply_text(_t(lang, "rate_fail", code=code))
        return

    await update.message.reply_text(
        _t(lang, "rate_ok", code=code, result=result),
        parse_mode="Markdown",
    )


async def crypto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать цену криптовалюты в USD."""
    lang = _resolve_lang(update)
    if not context.args:
        await update.message.reply_text(_t(lang, "crypto_usage"))
        return

    symbol = context.args[0].upper()
    result = await get_crypto_price(symbol)

    if result is None:
        if is_known_ticker(symbol):
            await update.message.reply_text(_t(lang, "crypto_temp_fail", symbol=symbol))
        else:
            await update.message.reply_text(_t(lang, "crypto_fail", symbol=symbol))
        return

    price, change_24h = result
    arrow = "📈" if change_24h >= 0 else "📉"
    sign = "+" if change_24h >= 0 else ""

    await update.message.reply_text(
        _t(lang, "crypto_ok", arrow=arrow, symbol=symbol, price=price, sign=sign, change=change_24h),
        parse_mode="Markdown",
    )


async def convert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Конвертировать сумму из одной валюты в другую."""
    lang = _resolve_lang(update)
    if len(context.args) < 3:
        await update.message.reply_text(_t(lang, "convert_usage"))
        return

    try:
        amount = float(context.args[0].replace(",", "."))
    except ValueError:
        await update.message.reply_text(_t(lang, "convert_amount_error"))
        return

    from_cur = context.args[1].upper()
    to_cur = context.args[2].upper()

    result = await convert_currency(amount, from_cur, to_cur)

    if result is None:
        await update.message.reply_text(_t(lang, "convert_fail", from_cur=from_cur, to_cur=to_cur))
        return

    await update.message.reply_text(
        _t(lang, "convert_ok", amount=amount, from_cur=from_cur, result=result, to_cur=to_cur),
        parse_mode="Markdown",
    )


async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавить тикер в список наблюдения."""
    lang = _resolve_lang(update)
    if not context.args:
        await update.message.reply_text(_t(lang, "watch_usage"))
        return

    code = context.args[0].upper()

    if not is_known_ticker(code):
        await update.message.reply_text(_t(lang, "watch_unknown", code=code))
        return

    user_id = update.effective_user.id
    added = add_to_watchlist(user_id, code)

    if added:
        await update.message.reply_text(_t(lang, "watch_added", code=code), parse_mode="Markdown")
    else:
        await update.message.reply_text(_t(lang, "watch_exists", code=code))


async def unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удалить тикер из списка наблюдения."""
    lang = _resolve_lang(update)
    if not context.args:
        await update.message.reply_text(_t(lang, "unwatch_usage"))
        return

    code = context.args[0].upper()
    user_id = update.effective_user.id
    removed = remove_from_watchlist(user_id, code)

    if removed:
        await update.message.reply_text(_t(lang, "unwatch_removed", code=code), parse_mode="Markdown")
    else:
        await update.message.reply_text(_t(lang, "unwatch_missing", code=code))


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать список наблюдения с актуальными ценами."""
    lang = _resolve_lang(update)
    user_id = update.effective_user.id
    items = get_watchlist(user_id)

    if not items:
        await update.message.reply_text(_t(lang, "watchlist_empty"))
        return

    await update.message.reply_text(_t(lang, "watchlist_loading"))

    # Batch-запрос для всех крипто-тикеров за один HTTP-вызов
    crypto_symbols = [code for code, kind in items if kind == "crypto"]
    crypto_prices = await get_crypto_prices_batch(crypto_symbols)

    lines = []
    for code, kind in items:
        if kind == "crypto":
            result = crypto_prices.get(code)
            if result:
                price, change = result
                sign = "+" if change >= 0 else ""
                lines.append(f"• *{code}* — ${price:,.2f}  ({sign}{change:.1f}%)")
            else:
                lines.append(f"• *{code}* — н/д")
        else:
            rate_val = await get_exchange_rate(code)
            if rate_val:
                lines.append(f"• *{code}* — {rate_val:.2f} ₽")
            else:
                lines.append(f"• *{code}* — н/д")

    text = _t(lang, "watchlist_title") + "\n\n" + "\n".join(lines)
    await update.message.reply_text(text, parse_mode="Markdown")


# ─── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан! Создай файл .env и добавь BOT_TOKEN=<токен>.")

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rate", rate))
    app.add_handler(CommandHandler("crypto", crypto))
    app.add_handler(CommandHandler("convert", convert))
    app.add_handler(CommandHandler("watch", watch))
    app.add_handler(CommandHandler("unwatch", unwatch))
    app.add_handler(CommandHandler("watchlist", watchlist))
    app.add_handler(CommandHandler("popular", popular))
    app.add_handler(CommandHandler("lang", set_language))
    app.post_init = _set_bot_commands

    logger.info("Бот запущен (polling mode)...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
