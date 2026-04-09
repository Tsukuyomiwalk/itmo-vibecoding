"""
Фоновые задачи бота (Application.job_queue — native asyncio).

Задачи:
  check_alerts()       — каждые 5 минут, проверяет пороговые алерты
  seed_rate_history()  — один раз при старте, заполняет rate_history для активных кодов
  daily_record_close() — ежедневно в 00:00:00 UTC, записывает дневной курс в rate_history
  daily_cleanup()      — ежедневно в 00:00:30 UTC, удаляет устаревшие алерты и историю

check_alerts() flow:
  ┌─────────────────────────────────────────┐
  │ SELECT DISTINCT code, kind FROM alerts  │
  │ WHERE was_triggered=0                   │
  └──────────────┬──────────────────────────┘
                 │
         ┌───────┴────────┐
         ▼                ▼
    [fiat codes]    [crypto codes]
   get_fiat_rates   get_crypto_prices
   _batch() ×1      _batch() ×1
         │                │
         └───────┬────────┘
                 ▼
    FOR each alert WHERE was_triggered=0:
      compare current_price vs target + direction
           │
      ┌────┴─────┐
      │ TRIGGERED │
      └────┬─────┘
           ▼
    fetch trend context from rate_history
    send_message (async)
    UPDATE was_triggered=1
"""

import logging
from datetime import datetime, timezone

from telegram.ext import ContextTypes

from api_client import get_fiat_rates_batch, get_crypto_prices_batch
from database import (
    get_active_alerts,
    get_active_alert_codes,
    mark_triggered,
    get_rate_history,
    upsert_rate_history,
    cleanup_old_alerts,
    cleanup_old_rate_history,
)

logger = logging.getLogger(__name__)


def _build_trend_context(code: str, current_rate: float) -> str:
    """
    Построить строку контекста тренда для сообщения об алерте.
    Возвращает пустую строку если данных недостаточно.
    """
    history = get_rate_history(code, limit=14)
    if len(history) < 2:
        return ""

    yesterday_rate = history[0]  # последняя записанная (вчерашний close)
    pct_change = (current_rate - yesterday_rate) / yesterday_rate * 100
    sign = "+" if pct_change >= 0 else ""
    arrow = "↑" if pct_change >= 0 else "↓"

    lines = [f"{arrow} {sign}{pct_change:.1f}% vs вчерашний курс"]

    if len(history) >= 14:
        is_highest = current_rate >= max(history)
        is_lowest = current_rate <= min(history)
        if is_highest:
            lines.append("📈 Максимум за 14 дней")
        elif is_lowest:
            lines.append("📉 Минимум за 14 дней")

    return "\n".join(lines)


async def check_alerts(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Проверить все активные алерты. Запускается каждые 5 минут.
    При ошибке API — пропускает цикл, не помечает алерты.
    """
    alerts = get_active_alerts()
    if not alerts:
        return

    # Разделить коды по типу
    fiat_codes = list({a["code"] for a in alerts if a["kind"] == "fiat"})
    crypto_codes = list({a["code"] for a in alerts if a["kind"] == "crypto"})

    fiat_rates: dict[str, float] = {}
    crypto_prices: dict[str, tuple[float, float]] = {}

    if fiat_codes:
        fiat_rates = await get_fiat_rates_batch(fiat_codes)
    if crypto_codes:
        crypto_prices = await get_crypto_prices_batch(crypto_codes)

    for alert in alerts:
        code = alert["code"]
        kind = alert["kind"]
        target = alert["target_price"]
        direction = alert["direction"]

        # Получить текущую цену
        if kind == "fiat":
            current = fiat_rates.get(code)
        else:
            pair = crypto_prices.get(code)
            current = pair[0] if pair else None

        if current is None:
            continue  # API не вернул данные — пропустить, не трогать алерт

        # Проверить условие
        triggered = (
            (direction == "above" and current >= target)
            or (direction == "below" and current <= target)
        )
        if not triggered:
            continue

        # Собрать сообщение
        unit = "₽" if kind == "fiat" else "$"
        trend = _build_trend_context(code, current)
        text = f"💱 *{code}/RUB* достиг {unit}{current:,.2f}\nЦель: {unit}{target:,.2f}"
        if trend:
            text += f"\n{trend}"
        text += f"\n\nУстановить снова? /alert {code} {target:.2f}"

        try:
            await context.bot.send_message(
                chat_id=alert["user_id"],
                text=text,
                parse_mode="Markdown",
            )
        except Exception as exc:
            logger.warning("Не удалось отправить алерт user=%s: %s", alert["user_id"], exc)

        mark_triggered(alert["id"])


async def seed_rate_history(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Засеять rate_history текущими курсами для всех активных кодов.
    Запускается один раз при старте. Не падает при ошибке API.
    """
    try:
        codes = get_active_alert_codes()
        if not codes:
            return

        fiat_codes = [c for c, k in codes if k == "fiat"]
        crypto_codes = [c for c, k in codes if k == "crypto"]

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if fiat_codes:
            rates = await get_fiat_rates_batch(fiat_codes)
            for code, rate in rates.items():
                upsert_rate_history(code, rate, "RUB", today)

        if crypto_codes:
            prices = await get_crypto_prices_batch(crypto_codes)
            for code, (price, _) in prices.items():
                upsert_rate_history(code, price, "USD", today)

        logger.info("seed_rate_history: записано %d кодов за %s", len(codes), today)
    except Exception as exc:
        logger.error("seed_rate_history ошибка (некритично): %s", exc)


async def daily_record_close(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Записать дневной курс для всех активных кодов. 00:00:00 UTC."""
    try:
        codes = get_active_alert_codes()
        if not codes:
            return

        fiat_codes = [c for c, k in codes if k == "fiat"]
        crypto_codes = [c for c, k in codes if k == "crypto"]

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if fiat_codes:
            rates = await get_fiat_rates_batch(fiat_codes)
            for code, rate in rates.items():
                upsert_rate_history(code, rate, "RUB", today)

        if crypto_codes:
            prices = await get_crypto_prices_batch(crypto_codes)
            for code, (price, _) in prices.items():
                upsert_rate_history(code, price, "USD", today)

        logger.info("daily_record_close: записано %d кодов", len(codes))
    except Exception as exc:
        logger.error("daily_record_close ошибка: %s", exc)


async def daily_cleanup(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Удалить устаревшие данные. 00:00:30 UTC."""
    try:
        cleanup_old_alerts(days=7)
        cleanup_old_rate_history(days=14)
        logger.info("daily_cleanup: очистка выполнена")
    except Exception as exc:
        logger.error("daily_cleanup ошибка: %s", exc)
