"""
Тесты для scheduler.py — check_alerts(), seed_rate_history(), trend context.
API-вызовы мокируются, Telegram bot.send_message — тоже.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import database as db
import scheduler


@pytest.fixture(autouse=True)
def in_memory_db(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db()
    yield


def make_context(send_message_mock=None):
    """Создать фиктивный ContextTypes.DEFAULT_TYPE для job_queue callback."""
    ctx = MagicMock()
    ctx.bot = MagicMock()
    ctx.bot.send_message = send_message_mock or AsyncMock()
    return ctx


# ─── check_alerts ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_alert_fires_when_rate_above_target():
    """Алерт срабатывает когда rate >= target_price (direction='above')."""
    db.add_alert(user_id=42, code="USD", target_price=95.0, direction="above")

    send_mock = AsyncMock()
    ctx = make_context(send_mock)

    with patch("scheduler.get_fiat_rates_batch", new=AsyncMock(return_value={"USD": 95.5})):
        with patch("scheduler.get_crypto_prices_batch", new=AsyncMock(return_value={})):
            await scheduler.check_alerts(ctx)

    send_mock.assert_awaited_once()
    call_kwargs = send_mock.call_args
    assert call_kwargs.kwargs["chat_id"] == 42
    assert "95" in call_kwargs.kwargs["text"]

    # Алерт помечен как сработавший
    active = db.get_active_alerts(user_id=42)
    assert len(active) == 0


@pytest.mark.asyncio
async def test_alert_does_not_fire_when_rate_below_target():
    """Алерт (above) не срабатывает если rate < target_price."""
    db.add_alert(user_id=42, code="USD", target_price=95.0, direction="above")

    send_mock = AsyncMock()
    ctx = make_context(send_mock)

    with patch("scheduler.get_fiat_rates_batch", new=AsyncMock(return_value={"USD": 94.9})):
        with patch("scheduler.get_crypto_prices_batch", new=AsyncMock(return_value={})):
            await scheduler.check_alerts(ctx)

    send_mock.assert_not_awaited()
    active = db.get_active_alerts(user_id=42)
    assert len(active) == 1  # алерт не тронут


@pytest.mark.asyncio
async def test_alert_fires_when_rate_below_target_direction_below():
    """Алерт (direction='below') срабатывает когда rate <= target_price."""
    db.add_alert(user_id=42, code="USD", target_price=85.0, direction="below")

    send_mock = AsyncMock()
    ctx = make_context(send_mock)

    with patch("scheduler.get_fiat_rates_batch", new=AsyncMock(return_value={"USD": 84.5})):
        with patch("scheduler.get_crypto_prices_batch", new=AsyncMock(return_value={})):
            await scheduler.check_alerts(ctx)

    send_mock.assert_awaited_once()
    active = db.get_active_alerts(user_id=42)
    assert len(active) == 0


@pytest.mark.asyncio
async def test_alert_does_not_double_fire():
    """Алерт с was_triggered=1 не должен повторно срабатывать."""
    alert_id = db.add_alert(user_id=42, code="USD", target_price=95.0)
    db.mark_triggered(alert_id)

    send_mock = AsyncMock()
    ctx = make_context(send_mock)

    with patch("scheduler.get_fiat_rates_batch", new=AsyncMock(return_value={"USD": 96.0})):
        with patch("scheduler.get_crypto_prices_batch", new=AsyncMock(return_value={})):
            await scheduler.check_alerts(ctx)

    send_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_check_alerts_api_failure_no_crash():
    """Ошибка API → check_alerts() не падает, алерт не помечается."""
    db.add_alert(user_id=42, code="USD", target_price=95.0)

    send_mock = AsyncMock()
    ctx = make_context(send_mock)

    # API возвращает пустой dict (ошибка поглощена внутри get_fiat_rates_batch)
    with patch("scheduler.get_fiat_rates_batch", new=AsyncMock(return_value={})):
        with patch("scheduler.get_crypto_prices_batch", new=AsyncMock(return_value={})):
            await scheduler.check_alerts(ctx)

    send_mock.assert_not_awaited()
    active = db.get_active_alerts(user_id=42)
    assert len(active) == 1  # алерт не тронут


@pytest.mark.asyncio
async def test_check_alerts_crypto_alert():
    """Алерт для крипты срабатывает по USD-цене."""
    db.add_alert(user_id=42, code="BTC", target_price=65000.0, direction="above")

    send_mock = AsyncMock()
    ctx = make_context(send_mock)

    with patch("scheduler.get_fiat_rates_batch", new=AsyncMock(return_value={})):
        with patch("scheduler.get_crypto_prices_batch", new=AsyncMock(return_value={"BTC": (65100.0, 1.5)})):
            await scheduler.check_alerts(ctx)

    send_mock.assert_awaited_once()
    active = db.get_active_alerts(user_id=42)
    assert len(active) == 0


@pytest.mark.asyncio
async def test_check_alerts_mixed_fiat_and_crypto():
    """Один цикл обрабатывает и фиат, и крипту за два batch-запроса."""
    db.add_alert(user_id=1, code="USD", target_price=95.0)
    db.add_alert(user_id=2, code="BTC", target_price=60000.0)

    send_mock = AsyncMock()
    ctx = make_context(send_mock)

    fiat_mock = AsyncMock(return_value={"USD": 96.0})
    crypto_mock = AsyncMock(return_value={"BTC": (61000.0, 2.0)})

    with patch("scheduler.get_fiat_rates_batch", new=fiat_mock):
        with patch("scheduler.get_crypto_prices_batch", new=crypto_mock):
            await scheduler.check_alerts(ctx)

    # Оба вызова были сделаны ровно по одному разу
    fiat_mock.assert_awaited_once()
    crypto_mock.assert_awaited_once()
    assert send_mock.await_count == 2


@pytest.mark.asyncio
async def test_check_alerts_send_failure_marks_triggered():
    """Даже если отправка сообщения падает, алерт помечается triggered."""
    db.add_alert(user_id=42, code="USD", target_price=95.0)

    send_mock = AsyncMock(side_effect=Exception("Telegram error"))
    ctx = make_context(send_mock)

    with patch("scheduler.get_fiat_rates_batch", new=AsyncMock(return_value={"USD": 96.0})):
        with patch("scheduler.get_crypto_prices_batch", new=AsyncMock(return_value={})):
            await scheduler.check_alerts(ctx)

    active = db.get_active_alerts(user_id=42)
    assert len(active) == 0  # алерт помечен даже при ошибке отправки


# ─── Trend context ────────────────────────────────────────────────────────────

def test_trend_context_empty_when_no_history():
    result = scheduler._build_trend_context("USD", 95.0)
    assert result == ""


def test_trend_context_with_one_day():
    db.upsert_rate_history("USD", 90.0, "RUB", "2026-01-01")
    result = scheduler._build_trend_context("USD", 95.0)
    assert result == ""  # нужно минимум 2 записи


def test_trend_context_shows_change():
    db.upsert_rate_history("USD", 90.0, "RUB", "2026-01-01")
    db.upsert_rate_history("USD", 92.0, "RUB", "2026-01-02")
    result = scheduler._build_trend_context("USD", 95.0)
    assert "%" in result
    assert "↑" in result or "↓" in result


def test_trend_context_highest_in_14_days():
    for i in range(14):
        db.upsert_rate_history("USD", float(80 + i), "RUB", f"2026-01-{i+1:02d}")
    # 95.0 — выше всех 14 значений
    result = scheduler._build_trend_context("USD", 95.0)
    assert "Максимум" in result


# ─── seed_rate_history ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_seed_rate_history_no_crash_on_api_failure():
    """seed_rate_history не должен падать при ошибке API."""
    db.add_alert(user_id=1, code="USD", target_price=95.0)
    ctx = make_context()

    with patch("scheduler.get_fiat_rates_batch", new=AsyncMock(side_effect=Exception("API down"))):
        with patch("scheduler.get_crypto_prices_batch", new=AsyncMock(return_value={})):
            await scheduler.seed_rate_history(ctx)  # должен завершиться без исключения


@pytest.mark.asyncio
async def test_seed_rate_history_populates_history():
    db.add_alert(user_id=1, code="USD", target_price=95.0)
    ctx = make_context()

    with patch("scheduler.get_fiat_rates_batch", new=AsyncMock(return_value={"USD": 90.0})):
        with patch("scheduler.get_crypto_prices_batch", new=AsyncMock(return_value={})):
            await scheduler.seed_rate_history(ctx)

    history = db.get_rate_history("USD")
    assert len(history) == 1
    assert history[0] == 90.0
