"""
Тесты для обработчиков bot.py — /alert, /alerts, /unalert, /payment, /converted.
Telegram Update и Context мокируются.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import database as db
import bot


@pytest.fixture(autouse=True)
def in_memory_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db()
    yield


def make_update(user_id=42, args=None):
    """Создать фиктивный Update для тестов обработчиков."""
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = args or []
    return update, context


# ─── /alert ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alert_unknown_code_returns_error():
    update, ctx = make_update(args=["FAKECOIN", "100"])
    await bot.alert_cmd(update, ctx)
    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.call_args[0][0]
    assert "не найден" in text.lower() or "❓" in text


@pytest.mark.asyncio
async def test_alert_negative_price_returns_error():
    update, ctx = make_update(args=["USD", "-5"])
    await bot.alert_cmd(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "больше нуля" in text or "числом" in text.lower()


@pytest.mark.asyncio
async def test_alert_zero_price_returns_error():
    update, ctx = make_update(args=["USD", "0"])
    await bot.alert_cmd(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "больше нуля" in text


@pytest.mark.asyncio
async def test_alert_invalid_direction_returns_error():
    update, ctx = make_update(args=["USD", "95", "sideways"])
    await bot.alert_cmd(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "above" in text or "below" in text


@pytest.mark.asyncio
async def test_alert_valid_case_insensitive():
    """Код в нижнем регистре должен работать как в верхнем."""
    update, ctx = make_update(args=["usd", "95"])
    await bot.alert_cmd(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "установлен" in text.lower() or "🔔" in text

    active = db.get_active_alerts(user_id=42)
    assert len(active) == 1
    assert active[0]["code"] == "USD"


@pytest.mark.asyncio
async def test_alert_default_direction_is_above():
    update, ctx = make_update(args=["USD", "95"])
    await bot.alert_cmd(update, ctx)

    active = db.get_active_alerts(user_id=42)
    assert active[0]["direction"] == "above"


@pytest.mark.asyncio
async def test_alert_no_args_returns_usage():
    update, ctx = make_update(args=[])
    await bot.alert_cmd(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "/alert" in text


# ─── /alerts ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alerts_empty_list():
    update, ctx = make_update()
    await bot.alerts_list(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "нет" in text.lower() or "пуст" in text.lower()


@pytest.mark.asyncio
async def test_alerts_shows_active_alerts():
    db.add_alert(user_id=42, code="USD", target_price=95.0)

    update, ctx = make_update()
    with patch("bot.get_fiat_rates_batch", new=AsyncMock(return_value={"USD": 92.0})):
        with patch("bot.get_crypto_prices_batch", new=AsyncMock(return_value={})):
            await bot.alerts_list(update, ctx)

    # Первый вызов — "⏳ Получаю...", второй — список
    assert update.message.reply_text.await_count >= 2
    last_text = update.message.reply_text.call_args_list[-1][0][0]
    assert "USD" in last_text
    assert "95" in last_text


# ─── /unalert ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unalert_removes_alerts():
    db.add_alert(user_id=42, code="USD", target_price=95.0)
    db.add_alert(user_id=42, code="USD", target_price=90.0)

    update, ctx = make_update(args=["USD"])
    await bot.unalert(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "2" in text or "удалено" in text.lower()

    assert len(db.get_active_alerts(user_id=42)) == 0


@pytest.mark.asyncio
async def test_unalert_no_alerts_returns_message():
    update, ctx = make_update(args=["USD"])
    await bot.unalert(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "нет" in text.lower() or "не найден" in text.lower()


# ─── /payment ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_payment_valid_with_current_rate():
    update, ctx = make_update(args=["2000", "USD"])
    with patch("bot.get_exchange_rate", new=AsyncMock(return_value=90.5)):
        await bot.payment_cmd(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "2,000" in text or "2000" in text
    assert "USD" in text
    assert "90.50" in text

    conn = db._connect()
    rows = conn.execute("SELECT * FROM payments").fetchall()
    assert len(rows) == 1
    assert rows[0]["rate_at_add"] == pytest.approx(90.5)


@pytest.mark.asyncio
async def test_payment_warns_when_rate_unavailable():
    update, ctx = make_update(args=["2000", "USD"])
    with patch("bot.get_exchange_rate", new=AsyncMock(return_value=None)):
        await bot.payment_cmd(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "⚠️" in text or "P&L" in text


@pytest.mark.asyncio
async def test_payment_with_target_rate_creates_alert():
    update, ctx = make_update(args=["2000", "USD", "95"])
    with patch("bot.get_exchange_rate", new=AsyncMock(return_value=90.0)):
        await bot.payment_cmd(update, ctx)

    active = db.get_active_alerts(user_id=42)
    assert len(active) == 1
    assert active[0]["target_price"] == 95.0


@pytest.mark.asyncio
async def test_payment_unknown_currency_returns_error():
    update, ctx = make_update(args=["2000", "FAKECUR"])
    await bot.payment_cmd(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "не найден" in text.lower() or "❓" in text


@pytest.mark.asyncio
async def test_payment_zero_amount_returns_error():
    update, ctx = make_update(args=["0", "USD"])
    await bot.payment_cmd(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "больше нуля" in text


# ─── /converted ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_converted_with_pending_payment_shows_pnl():
    db.add_payment(user_id=42, amount=2000.0, from_cur="USD", rate_at_add=90.0)

    update, ctx = make_update(args=["2000", "USD", "at", "94.5"])
    await bot.converted_cmd(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "P&L" in text
    # P&L = (94.5 - 90.0) * 2000 = 9000
    assert "9,000" in text or "9000" in text


@pytest.mark.asyncio
async def test_converted_without_pending_payment_no_pnl():
    update, ctx = make_update(args=["2000", "USD", "at", "94.5"])
    await bot.converted_cmd(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "✅" in text
    assert "P&L" not in text  # нет pending-платежа → нет P&L


@pytest.mark.asyncio
async def test_converted_null_rate_at_add_no_pnl():
    """Если rate_at_add был NULL, P&L не показывается."""
    db.add_payment(user_id=42, amount=2000.0, from_cur="USD", rate_at_add=None)

    update, ctx = make_update(args=["2000", "USD", "at", "94.5"])
    await bot.converted_cmd(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "P&L" not in text


@pytest.mark.asyncio
async def test_converted_marks_payment_as_converted():
    db.add_payment(user_id=42, amount=2000.0, from_cur="USD", rate_at_add=90.0)

    update, ctx = make_update(args=["2000", "USD", "at", "94.5"])
    await bot.converted_cmd(update, ctx)

    pending = db.get_oldest_pending_payment(user_id=42, from_cur="USD")
    assert pending is None  # помечен как converted


@pytest.mark.asyncio
async def test_converted_invalid_syntax_returns_usage():
    update, ctx = make_update(args=["2000", "USD", "94.5"])  # пропущен "at"
    await bot.converted_cmd(update, ctx)
    text = update.message.reply_text.call_args[0][0]
    assert "at" in text.lower()


@pytest.mark.asyncio
async def test_converted_fifo_uses_oldest():
    """Из двух pending-платежей converted должен взять старейший."""
    id1 = db.add_payment(user_id=42, amount=1000.0, from_cur="USD", rate_at_add=88.0)
    id2 = db.add_payment(user_id=42, amount=2000.0, from_cur="USD", rate_at_add=90.0)

    update, ctx = make_update(args=["1000", "USD", "at", "95.0"])
    await bot.converted_cmd(update, ctx)

    # Первый (1000 USD, rate=88.0) должен быть помечен
    # P&L = (95.0 - 88.0) * 1000 = 7000
    text = update.message.reply_text.call_args[0][0]
    assert "7,000" in text or "7000" in text

    # Второй платёж по-прежнему pending
    pending = db.get_oldest_pending_payment(user_id=42, from_cur="USD")
    assert pending["id"] == id2


# ─── forward_payment_handler ──────────────────────────────────────────────────

def make_forward_update(user_id=42, text="You received $2,000 from Acme"):
    update = MagicMock()
    update.effective_user.id = user_id
    update.message.text = text
    update.message.caption = None
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.user_data = {}
    return update, context


def make_callback_update(user_id=42, callback_data="forward_confirm_abcd1234"):
    update = MagicMock()
    update.effective_user.id = user_id
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.callback_query.edit_message_text = AsyncMock()
    update.callback_query.data = callback_data
    context = MagicMock()
    context.user_data = {}
    return update, context


@pytest.mark.asyncio
async def test_forward_payment_handler_valid_message():
    update, ctx = make_forward_update()
    with patch("bot.parse_payment_from_text",
               new=AsyncMock(return_value={"amount": 2000.0, "currency": "USD"})):
        with patch("bot.get_exchange_rate", new=AsyncMock(return_value=90.5)):
            await bot.forward_payment_handler(update, ctx)

    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.call_args[0][0]
    assert "2,000" in text or "2000" in text
    assert "USD" in text
    # Проверить что pending_forward_* создан в user_data
    pending_keys = [k for k in ctx.user_data if k.startswith("pending_forward_")]
    assert len(pending_keys) == 1


@pytest.mark.asyncio
async def test_forward_payment_handler_parse_failure():
    """DeepSeek не смог распарсить — предложить /payment вручную."""
    update, ctx = make_forward_update()
    with patch("bot.parse_payment_from_text", new=AsyncMock(return_value=None)):
        await bot.forward_payment_handler(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "/payment" in text


@pytest.mark.asyncio
async def test_forward_payment_handler_unknown_currency():
    """Распознана неподдерживаемая валюта — отказ с подсказкой."""
    update, ctx = make_forward_update()
    with patch("bot.parse_payment_from_text",
               new=AsyncMock(return_value={"amount": 100.0, "currency": "FAKECUR"})):
        await bot.forward_payment_handler(update, ctx)

    text = update.message.reply_text.call_args[0][0]
    assert "/payment" in text or "не поддерживается" in text


@pytest.mark.asyncio
async def test_forward_confirm_callback_stores_payment():
    forward_id = "abcd1234"
    update, ctx = make_callback_update(callback_data=f"forward_confirm_{forward_id}")
    ctx.user_data[f"pending_forward_{forward_id}"] = {
        "amount": 2000.0,
        "currency": "USD",
        "rate_at_add": 90.5,
    }

    await bot.forward_confirm_callback(update, ctx)

    # Платёж должен быть в БД
    pending = db.get_oldest_pending_payment(user_id=42, from_cur="USD")
    assert pending is not None
    assert pending["amount"] == 2000.0
    assert pending["rate_at_add"] == pytest.approx(90.5)


@pytest.mark.asyncio
async def test_forward_cancel_callback_no_payment():
    forward_id = "abcd1234"
    update, ctx = make_callback_update(callback_data=f"forward_cancel_{forward_id}")
    ctx.user_data[f"pending_forward_{forward_id}"] = {
        "amount": 2000.0,
        "currency": "USD",
        "rate_at_add": 90.5,
    }

    await bot.forward_cancel_callback(update, ctx)

    # Ничего не должно быть в БД
    pending = db.get_oldest_pending_payment(user_id=42, from_cur="USD")
    assert pending is None
    update.callback_query.edit_message_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_forward_confirm_stale_session():
    """Кнопка нажата, но ключ уже истёк — вернуть сообщение об ошибке."""
    forward_id = "abcd1234"
    update, ctx = make_callback_update(callback_data=f"forward_confirm_{forward_id}")
    # user_data пустой — ключ отсутствует

    await bot.forward_confirm_callback(update, ctx)

    call_text = update.callback_query.edit_message_text.call_args[0][0]
    assert "истекла" in call_text.lower() or "попробуй" in call_text.lower()
