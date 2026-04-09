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
  /alert <код> <цена> [above|below] — установить пороговый алерт
  /alerts         — список активных алертов
  /unalert <код>  — удалить алерты для кода
  /payment <сумма> <валюта> [целевой_курс] — зафиксировать входящий платёж
  /converted <сумма> <валюта> at <курс>    — зафиксировать конвертацию
"""

import logging
import os
import re as _re
import uuid

from datetime import date, time as dt_time, timezone
from dotenv import load_dotenv
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from api_client import (
    KNOWN_FIAT_CODES,
    _COINGECKO_IDS,
    get_crypto_price,
    get_crypto_prices_batch,
    get_exchange_rate,
    get_fiat_rates_batch,
    convert_currency,
    is_known_ticker,
)
from database import (
    init_db,
    add_to_watchlist,
    remove_from_watchlist,
    get_watchlist,
    add_alert,
    get_active_alerts,
    remove_alerts_for_code,
    add_payment,
    get_oldest_pending_payment,
    get_all_pending_payments,
    mark_payment_converted,
    add_conversion,
    get_rate_history,
)
from deepseek_client import (
    answer_rate_question,
    explain_pnl,
    parse_payment_from_text,
)
from scheduler import (
    check_alerts,
    seed_rate_history,
    daily_record_close,
    daily_cleanup,
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
        "  /alert USD 95 — уведомить когда USD/RUB выше 95\n"
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
        "/watchlist — текущие цены по списку\n\n"
        "💱 *Алерты:*\n"
        "/alert `<код> <цена> [above|below]` — уведомить при достижении цены\n"
        "  Пример: `/alert USD 95` или `/alert BTC 60000 below`\n"
        "/alerts — список активных алертов\n"
        "/unalert `<код>` — удалить алерты для кода\n\n"
        "💼 *Учёт платежей:*\n"
        "/payment `<сумма> <валюта> [целевой_курс]` — зафиксировать платёж\n"
        "  Пример: `/payment 2000 USD 95`\n"
        "/converted `<сумма> <валюта> at <курс>` — зафиксировать конвертацию\n"
        "  Пример: `/converted 2000 USD at 94.5`"
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


# ─── Alert handlers ──────────────────────────────────────────────────────────

async def alert_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Установить пороговый алерт. Пример: /alert USD 95 [above|below]"""
    if len(context.args) < 2:
        await update.message.reply_text(
            "Пример: `/alert USD 95` или `/alert BTC 60000 below`",
            parse_mode="Markdown",
        )
        return

    code = context.args[0].upper()
    if not is_known_ticker(code):
        await update.message.reply_text(
            f"❓ Тикер «{code}» не найден. Попробуй USD, EUR, BTC, ETH..."
        )
        return

    try:
        target_price = float(context.args[1].replace(",", "."))
    except ValueError:
        await update.message.reply_text("Цена должна быть числом. Пример: /alert USD 95")
        return

    if target_price <= 0:
        await update.message.reply_text("Цена должна быть больше нуля.")
        return

    direction = "above"
    if len(context.args) >= 3:
        d = context.args[2].lower()
        if d not in ("above", "below"):
            await update.message.reply_text(
                "Направление: `above` (выше) или `below` (ниже).", parse_mode="Markdown"
            )
            return
        direction = d

    user_id = update.effective_user.id
    add_alert(user_id, code, target_price, direction)

    direction_text = "поднимется выше" if direction == "above" else "опустится ниже"
    await update.message.reply_text(
        f"🔔 Алерт установлен: уведомлю когда *{code}* {direction_text} *{target_price:,.2f}*",
        parse_mode="Markdown",
    )


async def alerts_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Список активных алертов пользователя."""
    user_id = update.effective_user.id
    rows = get_active_alerts(user_id)

    if not rows:
        await update.message.reply_text("Нет активных алертов. Установи: /alert USD 95")
        return

    await update.message.reply_text("⏳ Получаю текущие курсы...")

    fiat_codes = list({r["code"] for r in rows if r["kind"] == "fiat"})
    crypto_codes = list({r["code"] for r in rows if r["kind"] == "crypto"})

    fiat_rates = await get_fiat_rates_batch(fiat_codes) if fiat_codes else {}
    crypto_prices = await get_crypto_prices_batch(crypto_codes) if crypto_codes else {}

    lines = []
    for row in rows:
        code = row["code"]
        target = row["target_price"]
        direction = row["direction"]

        if row["kind"] == "fiat":
            current = fiat_rates.get(code)
        else:
            pair = crypto_prices.get(code)
            current = pair[0] if pair else None

        dir_arrow = "↑" if direction == "above" else "↓"
        if current is not None:
            pct = (target - current) / current * 100
            sign = "+" if pct >= 0 else ""
            lines.append(
                f"• *{code}* {dir_arrow} {target:,.2f}  "
                f"(сейчас {current:,.2f}, {sign}{pct:.1f}%)"
            )
        else:
            lines.append(f"• *{code}* {dir_arrow} {target:,.2f}  (курс н/д)")

    text = "🔔 *Активные алерты:*\n\n" + "\n".join(lines)
    await update.message.reply_text(text, parse_mode="Markdown")


async def unalert(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удалить все активные алерты для кода."""
    if not context.args:
        await update.message.reply_text("Укажи код. Пример: /unalert USD")
        return

    code = context.args[0].upper()
    user_id = update.effective_user.id
    count = remove_alerts_for_code(user_id, code)

    if count > 0:
        await update.message.reply_text(f"🗑 Удалено алертов для *{code}*: {count}", parse_mode="Markdown")
    else:
        await update.message.reply_text(f"Нет активных алертов для «{code}».")


# ─── Payment handlers ────────────────────────────────────────────────────────

async def payment_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Зафиксировать входящий платёж.
    Пример: /payment 2000 USD  или  /payment 2000 USD 95
    """
    if len(context.args) < 2:
        await update.message.reply_text(
            "Пример: `/payment 2000 USD` или `/payment 2000 USD 95`",
            parse_mode="Markdown",
        )
        return

    try:
        amount = float(context.args[0].replace(",", "."))
    except ValueError:
        await update.message.reply_text("Сумма должна быть числом. Пример: /payment 2000 USD")
        return

    if amount <= 0:
        await update.message.reply_text("Сумма должна быть больше нуля.")
        return

    currency = context.args[1].upper()
    if not is_known_ticker(currency):
        await update.message.reply_text(
            f"❓ Валюта «{currency}» не найдена. Попробуй USD, EUR, USDT..."
        )
        return

    target_rate: float | None = None
    if len(context.args) >= 3:
        try:
            target_rate = float(context.args[2].replace(",", "."))
            if target_rate <= 0:
                await update.message.reply_text("Целевой курс должен быть больше нуля.")
                return
        except ValueError:
            await update.message.reply_text("Целевой курс должен быть числом.")
            return

    # Получить текущий курс до транзакции (async API call, before transaction)
    rate_at_add = await get_exchange_rate(currency)
    rate_warning = ""
    if rate_at_add is None:
        rate_warning = "\n⚠️ Не удалось получить текущий курс — P&L будет недоступен."

    user_id = update.effective_user.id
    add_payment(user_id, amount, currency, rate_at_add, target_rate)

    rate_line = f"\nКурс на момент получения: *{rate_at_add:.2f} ₽*" if rate_at_add else ""
    alert_line = f"\n🔔 Алерт установлен на *{target_rate:.2f} ₽*" if target_rate else ""

    await update.message.reply_text(
        f"✅ Платёж зафиксирован: *{amount:,.2f} {currency}*{rate_line}{alert_line}{rate_warning}",
        parse_mode="Markdown",
    )


async def converted_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Зафиксировать конвертацию.
    Пример: /converted 2000 USD at 94.5
    """
    if len(context.args) < 4 or context.args[2].lower() != "at":
        await update.message.reply_text(
            "Пример: `/converted 2000 USD at 94.5`",
            parse_mode="Markdown",
        )
        return

    try:
        amount = float(context.args[0].replace(",", "."))
    except ValueError:
        await update.message.reply_text("Сумма должна быть числом.")
        return

    if amount <= 0:
        await update.message.reply_text("Сумма должна быть больше нуля.")
        return

    currency = context.args[1].upper()
    if not is_known_ticker(currency):
        await update.message.reply_text(f"❓ Валюта «{currency}» не найдена.")
        return

    try:
        conv_rate = float(context.args[3].replace(",", "."))
    except ValueError:
        await update.message.reply_text("Курс конвертации должен быть числом.")
        return

    if conv_rate <= 0:
        await update.message.reply_text("Курс конвертации должен быть больше нуля.")
        return

    user_id = update.effective_user.id
    rub_received = amount * conv_rate

    # FIFO: найти старейший pending-платёж
    pending = get_oldest_pending_payment(user_id, currency)

    pnl_rub: float | None = None
    pnl_line = ""
    payment_id: int | None = None

    if pending:
        payment_id = pending["id"]
        mark_payment_converted(payment_id)
        if pending["rate_at_add"] is not None:
            pnl_rub = (conv_rate - pending["rate_at_add"]) * amount
            sign = "+" if pnl_rub >= 0 else ""
            pnl_line = f"\nP&L vs курс получения: *{sign}{pnl_rub:,.0f} ₽*"
            history_14d = get_rate_history(currency, limit=14)
            ai_comment = await explain_pnl(
                current_rate=conv_rate,
                rate_at_add=pending["rate_at_add"],
                pnl_rub=pnl_rub,
                history_14d=history_14d,
            )
            if ai_comment:
                pnl_line += f"\n💬 {ai_comment}"

    add_conversion(user_id, amount, currency, conv_rate, rub_received, pnl_rub, payment_id)

    await update.message.reply_text(
        f"✅ Конвертация зафиксирована:\n"
        f"*{amount:,.2f} {currency}* × {conv_rate:.2f} = *{rub_received:,.0f} ₽*{pnl_line}",
        parse_mode="Markdown",
    )


# ─── Use Case 1: Forward message parser ──────────────────────────────────────

async def forward_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle forwarded messages — attempt to parse as payment notification."""
    text = update.message.text or update.message.caption or ""
    if not text:
        return

    parsed = await parse_payment_from_text(text)
    if parsed is None:
        await update.message.reply_text(
            "Не смог распарсить сумму и валюту.\n"
            "Используй /payment <сумма> <валюта> вручную."
        )
        return

    amount, currency = parsed["amount"], parsed["currency"]

    if not is_known_ticker(currency):
        await update.message.reply_text(
            f"Валюта {currency} не поддерживается.\n"
            "Используй /payment <сумма> <валюта> вручную."
        )
        return

    rate = await get_exchange_rate(currency)
    rate_str = f"{rate:.2f} RUB" if rate else "курс недоступен"

    forward_id = str(uuid.uuid4())[:8]
    context.user_data[f"pending_forward_{forward_id}"] = {
        "amount": amount,
        "currency": currency,
        "rate_at_add": rate,
    }

    await update.message.reply_text(
        f"Вижу: {amount:,.0f} {currency}\n"
        f"Текущий курс: {rate_str}\n"
        "Залогировать как входящий платёж?",
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Да", callback_data=f"forward_confirm_{forward_id}"),
            InlineKeyboardButton("❌ Отмена", callback_data=f"forward_cancel_{forward_id}"),
        ]]),
    )


async def forward_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    forward_id = query.data.split("_")[-1]
    pending = context.user_data.pop(f"pending_forward_{forward_id}", None)
    if not pending:
        await query.edit_message_text("Сессия истекла. Попробуй снова.")
        return
    add_payment(
        user_id=update.effective_user.id,
        amount=pending["amount"],
        from_cur=pending["currency"],
        rate_at_add=pending["rate_at_add"],
    )
    await query.edit_message_text(
        f"✅ Платёж залогирован: {pending['amount']:,.0f} {pending['currency']}\n"
        "Используй /alerts для просмотра алертов или /payment для добавления цели."
    )


async def forward_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    forward_id = query.data.split("_")[-1]
    context.user_data.pop(f"pending_forward_{forward_id}", None)
    await query.edit_message_text("Отменено.")


# ─── Use Case 3: /ask command ─────────────────────────────────────────────────

async def ask_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = " ".join(context.args).strip()
    if not question:
        await update.message.reply_text(
            "Использование: /ask <вопрос>\n"
            "Пример: /ask стоит ли конвертировать USD сейчас?"
        )
        return

    thinking_msg = await update.message.reply_text("⏳ Думаю...")

    user_id = update.effective_user.id
    question_upper = question.upper()
    mentioned_fiat = [c for c in KNOWN_FIAT_CODES if _re.search(rf"\b{c}\b", question_upper)]
    mentioned_crypto = [c for c in _COINGECKO_IDS if _re.search(rf"\b{c}\b", question_upper)]
    mentioned = mentioned_fiat + mentioned_crypto

    rates = await get_fiat_rates_batch(mentioned_fiat) if mentioned_fiat else {}
    crypto_prices = await get_crypto_prices_batch(mentioned_crypto) if mentioned_crypto else {}
    history = {c: get_rate_history(c, limit=14) for c in mentioned}
    all_pending = get_all_pending_payments(user_id=user_id)
    pending_data = [
        {
            "currency": row["from_cur"],
            "amount": row["amount"],
            "rate_at_add": row["rate_at_add"],
            "added_at": row["added_at"],
        }
        for row in all_pending
    ]

    ctx = {
        "current_rates_rub": rates,
        "crypto_prices_usd": {k: v[0] for k, v in crypto_prices.items()},
        "rate_history_14d": history,
        "pending_payments": pending_data,
        "today": date.today().isoformat(),
    }

    answer = await answer_rate_question(question, ctx)
    if answer is None:
        await thinking_msg.edit_text("⚠️ AI временно недоступен. Попробуй позже.")
        return
    await thinking_msg.edit_text(answer)


# ─── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан! Создай файл .env и добавь BOT_TOKEN=<токен>.")

    init_db()

    app = Application.builder().token(BOT_TOKEN).build()

    # Существующие команды
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("rate", rate))
    app.add_handler(CommandHandler("crypto", crypto))
    app.add_handler(CommandHandler("convert", convert))
    app.add_handler(CommandHandler("watch", watch))
    app.add_handler(CommandHandler("unwatch", unwatch))
    app.add_handler(CommandHandler("watchlist", watchlist))

    # Алерты
    app.add_handler(CommandHandler("alert", alert_cmd))
    app.add_handler(CommandHandler("alerts", alerts_list))
    app.add_handler(CommandHandler("unalert", unalert))

    # Платежи
    app.add_handler(CommandHandler("payment", payment_cmd))
    app.add_handler(CommandHandler("converted", converted_cmd))

    # AI: форвард-парсер и /ask
    app.add_handler(MessageHandler(filters.FORWARDED & filters.TEXT, forward_payment_handler))
    app.add_handler(CallbackQueryHandler(forward_confirm_callback, pattern=r"^forward_confirm_[a-f0-9]{8}$"))
    app.add_handler(CallbackQueryHandler(forward_cancel_callback, pattern=r"^forward_cancel_[a-f0-9]{8}$"))
    app.add_handler(CommandHandler("ask", ask_cmd))

    # Фоновые задачи
    job_queue = app.job_queue
    job_queue.run_repeating(check_alerts, interval=300, first=10)
    job_queue.run_once(seed_rate_history, when=5)
    job_queue.run_daily(daily_record_close, time=dt_time(0, 0, 0, tzinfo=timezone.utc))
    job_queue.run_daily(daily_cleanup, time=dt_time(0, 0, 30, tzinfo=timezone.utc))

    logger.info("Бот запущен (polling mode)...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
