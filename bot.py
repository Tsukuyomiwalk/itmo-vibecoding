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
from telegram import Update
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
)

load_dotenv()

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")


# ─── Handlers ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "👋 Привет! Я *CryptoRates Bot* — слежу за курсами валют и крипты.\n\n"
        "Попробуй:\n"
        "  /rate USD\n"
        "  /crypto BTC\n"
        "  /convert 100 USD EUR\n"
        "  /help — полный список команд",
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "📖 *Команды бота:*\n\n"
        "/rate `<код>` — курс валюты к RUB\n"
        "  Пример: `/rate USD`\n\n"
        "/crypto `<код>` — цена криптовалюты в USD\n"
        "  Пример: `/crypto BTC`\n\n"
        "/convert `<сумма> <из> <в>` — конвертация\n"
        "  Пример: `/convert 100 USD EUR`\n\n"
        "/watch `<код>` — добавить в список наблюдения\n"
        "/unwatch `<код>` — удалить из списка\n"
        "/watchlist — текущие цены по списку"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать курс валюты к RUB."""
    if not context.args:
        await update.message.reply_text("Укажи код валюты. Пример: /rate USD")
        return

    code = context.args[0].upper()
    result = await get_exchange_rate(code)

    if result is None:
        await update.message.reply_text(f"❌ Не удалось получить курс для «{code}». Проверь код валюты.")
        return

    await update.message.reply_text(
        f"💱 *{code} → RUB*\n"
        f"1 {code} = *{result:.2f} ₽*",
        parse_mode="Markdown",
    )


async def crypto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать цену криптовалюты в USD."""
    if not context.args:
        await update.message.reply_text("Укажи тикер. Пример: /crypto BTC")
        return

    symbol = context.args[0].upper()
    result = await get_crypto_price(symbol)

    if result is None:
        await update.message.reply_text(
            f"❌ Не удалось найти «{symbol}». Попробуй полное название (например, bitcoin)."
        )
        return

    price, change_24h = result
    arrow = "📈" if change_24h >= 0 else "📉"
    sign = "+" if change_24h >= 0 else ""

    await update.message.reply_text(
        f"{arrow} *{symbol}*\n"
        f"Цена: *${price:,.2f}*\n"
        f"За 24ч: {sign}{change_24h:.2f}%",
        parse_mode="Markdown",
    )


async def convert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Конвертировать сумму из одной валюты в другую."""
    if len(context.args) < 3:
        await update.message.reply_text("Пример: /convert 100 USD EUR")
        return

    try:
        amount = float(context.args[0].replace(",", "."))
    except ValueError:
        await update.message.reply_text("Первый аргумент должен быть числом. Пример: /convert 100 USD EUR")
        return

    from_cur = context.args[1].upper()
    to_cur = context.args[2].upper()

    result = await convert_currency(amount, from_cur, to_cur)

    if result is None:
        await update.message.reply_text(f"❌ Не удалось конвертировать {from_cur} → {to_cur}.")
        return

    await update.message.reply_text(
        f"💱 *{amount:,.2f} {from_cur}* = *{result:,.2f} {to_cur}*",
        parse_mode="Markdown",
    )


async def watch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Добавить тикер в список наблюдения."""
    if not context.args:
        await update.message.reply_text("Укажи код. Пример: /watch BTC или /watch USD")
        return

    code = context.args[0].upper()

    if not is_known_ticker(code):
        await update.message.reply_text(
            f"❓ Тикер «{code}» не найден. Попробуй: /watch BTC, /watch USD, /watch ETH"
        )
        return

    user_id = update.effective_user.id
    added = add_to_watchlist(user_id, code)

    if added:
        await update.message.reply_text(f"✅ *{code}* добавлен в список наблюдения.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"«{code}» уже в твоём списке.")


async def unwatch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удалить тикер из списка наблюдения."""
    if not context.args:
        await update.message.reply_text("Укажи код. Пример: /unwatch BTC")
        return

    code = context.args[0].upper()
    user_id = update.effective_user.id
    removed = remove_from_watchlist(user_id, code)

    if removed:
        await update.message.reply_text(f"🗑 *{code}* удалён из списка.", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"«{code}» не найден в твоём списке.")


async def watchlist(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показать список наблюдения с актуальными ценами."""
    user_id = update.effective_user.id
    items = get_watchlist(user_id)

    if not items:
        await update.message.reply_text(
            "Список пуст. Добавь тикеры командой /watch BTC или /watch USD"
        )
        return

    await update.message.reply_text("⏳ Получаю цены...")

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

    text = "📋 *Список наблюдения:*\n\n" + "\n".join(lines)
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

    logger.info("Бот запущен (polling mode)...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
