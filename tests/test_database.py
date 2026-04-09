"""
Тесты для database.py — CRUD, атомарность, FIFO.
Используют in-memory SQLite (не трогают bot.db).
"""

import sqlite3
import pytest
from unittest.mock import patch

import database as db


@pytest.fixture(autouse=True)
def in_memory_db(tmp_path, monkeypatch):
    """Переключить DB_PATH на временный файл для каждого теста."""
    test_db = tmp_path / "test.db"
    monkeypatch.setattr(db, "DB_PATH", test_db)
    db.init_db()
    yield


# ─── Alerts ───────────────────────────────────────────────────────────────────

def test_add_alert_returns_id():
    alert_id = db.add_alert(user_id=1, code="USD", target_price=95.0)
    assert isinstance(alert_id, int)
    assert alert_id > 0


def test_get_active_alerts_only_untriggered():
    db.add_alert(user_id=1, code="USD", target_price=95.0)
    db.add_alert(user_id=1, code="EUR", target_price=100.0)
    # Вручную пометить один как triggered
    alerts = db.get_active_alerts(user_id=1)
    db.mark_triggered(alerts[0]["id"])

    active = db.get_active_alerts(user_id=1)
    assert len(active) == 1
    assert active[0]["code"] == "EUR"


def test_mark_triggered_sets_flag():
    alert_id = db.add_alert(user_id=1, code="USD", target_price=95.0)
    db.mark_triggered(alert_id)

    active = db.get_active_alerts(user_id=1)
    assert len(active) == 0  # was_triggered=1 → не попадает в активные


def test_alert_does_not_double_trigger():
    """Алерт с was_triggered=1 не должен появляться в get_active_alerts."""
    alert_id = db.add_alert(user_id=1, code="USD", target_price=95.0)
    db.mark_triggered(alert_id)
    db.mark_triggered(alert_id)  # повторный вызов безопасен

    active = db.get_active_alerts(user_id=1)
    assert len(active) == 0


def test_remove_alerts_for_code():
    db.add_alert(user_id=1, code="USD", target_price=90.0)
    db.add_alert(user_id=1, code="USD", target_price=95.0)
    db.add_alert(user_id=1, code="EUR", target_price=100.0)

    removed = db.remove_alerts_for_code(user_id=1, code="USD")
    assert removed == 2

    active = db.get_active_alerts(user_id=1)
    assert len(active) == 1
    assert active[0]["code"] == "EUR"


def test_remove_alerts_does_not_affect_triggered():
    """remove_alerts_for_code не должен трогать уже сработавшие алерты."""
    alert_id = db.add_alert(user_id=1, code="USD", target_price=95.0)
    db.mark_triggered(alert_id)

    removed = db.remove_alerts_for_code(user_id=1, code="USD")
    assert removed == 0  # was_triggered=1 не удаляется


def test_alert_direction_stored():
    db.add_alert(user_id=1, code="BTC", target_price=60000.0, direction="below")
    active = db.get_active_alerts(user_id=1)
    assert active[0]["direction"] == "below"


def test_alert_code_case_normalized():
    db.add_alert(user_id=1, code="usd", target_price=95.0)
    active = db.get_active_alerts(user_id=1)
    assert active[0]["code"] == "USD"


def test_get_active_alert_codes():
    db.add_alert(user_id=1, code="USD", target_price=95.0)
    db.add_alert(user_id=2, code="BTC", target_price=60000.0)
    codes = db.get_active_alert_codes()
    code_set = {c for c, k in codes}
    assert "USD" in code_set
    assert "BTC" in code_set


# ─── Payments — атомарность ────────────────────────────────────────────────────

def test_payment_and_alert_created_atomically():
    """Если добавление алерта падает, платёж тоже откатывается."""
    with patch.object(db, "add_alert", side_effect=sqlite3.OperationalError("forced")):
        with pytest.raises(sqlite3.OperationalError):
            db.add_payment(
                user_id=1,
                amount=2000.0,
                from_cur="USD",
                rate_at_add=90.0,
                target_rate=95.0,
            )

    # Платёж не должен был сохраниться
    conn = db._connect()
    rows = conn.execute("SELECT * FROM payments").fetchall()
    assert len(rows) == 0


def test_payment_without_target_rate_no_alert():
    db.add_payment(user_id=1, amount=2000.0, from_cur="USD", rate_at_add=90.0)
    active_alerts = db.get_active_alerts(user_id=1)
    assert len(active_alerts) == 0

    conn = db._connect()
    payments = conn.execute("SELECT * FROM payments").fetchall()
    assert len(payments) == 1


def test_payment_with_target_rate_creates_alert():
    db.add_payment(user_id=1, amount=2000.0, from_cur="USD", rate_at_add=90.0, target_rate=95.0)
    active_alerts = db.get_active_alerts(user_id=1)
    assert len(active_alerts) == 1
    assert active_alerts[0]["target_price"] == 95.0


def test_payment_rate_at_add_can_be_null():
    """rate_at_add может быть None если API был недоступен."""
    payment_id = db.add_payment(user_id=1, amount=1000.0, from_cur="EUR", rate_at_add=None)
    assert payment_id > 0
    pending = db.get_oldest_pending_payment(user_id=1, from_cur="EUR")
    assert pending["rate_at_add"] is None


# ─── Payments — FIFO ──────────────────────────────────────────────────────────

def test_converted_fifo_picks_oldest_payment():
    """Из двух pending-платежей /converted должен взять старейший (по added_at)."""
    # Добавить первый платёж
    id1 = db.add_payment(user_id=1, amount=1000.0, from_cur="USD", rate_at_add=90.0)
    # Второй платёж (добавлен позже)
    id2 = db.add_payment(user_id=1, amount=2000.0, from_cur="USD", rate_at_add=91.0)

    oldest = db.get_oldest_pending_payment(user_id=1, from_cur="USD")
    assert oldest["id"] == id1
    assert oldest["amount"] == 1000.0


def test_get_oldest_pending_none_when_empty():
    result = db.get_oldest_pending_payment(user_id=1, from_cur="USD")
    assert result is None


def test_mark_payment_converted():
    payment_id = db.add_payment(user_id=1, amount=1000.0, from_cur="USD", rate_at_add=90.0)
    db.mark_payment_converted(payment_id)

    # После mark_converted — pending больше нет
    pending = db.get_oldest_pending_payment(user_id=1, from_cur="USD")
    assert pending is None


# ─── get_all_pending_payments ─────────────────────────────────────────────────

def test_get_all_pending_payments_empty():
    result = db.get_all_pending_payments(user_id=1)
    assert result == []


def test_get_all_pending_payments_multiple_currencies():
    db.add_payment(user_id=1, amount=1000.0, from_cur="USD", rate_at_add=90.0)
    db.add_payment(user_id=1, amount=500.0, from_cur="EUR", rate_at_add=100.0)

    result = db.get_all_pending_payments(user_id=1)
    assert len(result) == 2
    currencies = {row["from_cur"] for row in result}
    assert currencies == {"USD", "EUR"}


def test_get_all_pending_payments_fifo_order():
    """Старейший платёж должен быть первым."""
    id1 = db.add_payment(user_id=1, amount=1000.0, from_cur="USD", rate_at_add=90.0)
    id2 = db.add_payment(user_id=1, amount=2000.0, from_cur="USD", rate_at_add=91.0)

    result = db.get_all_pending_payments(user_id=1)
    assert result[0]["id"] == id1
    assert result[1]["id"] == id2


def test_get_all_pending_payments_excludes_converted():
    payment_id = db.add_payment(user_id=1, amount=1000.0, from_cur="USD", rate_at_add=90.0)
    db.add_payment(user_id=1, amount=500.0, from_cur="EUR", rate_at_add=100.0)
    db.mark_payment_converted(payment_id)

    result = db.get_all_pending_payments(user_id=1)
    assert len(result) == 1
    assert result[0]["from_cur"] == "EUR"


# ─── Conversions ──────────────────────────────────────────────────────────────

def test_add_conversion_returns_id():
    conv_id = db.add_conversion(
        user_id=1, amount=1000.0, from_cur="USD",
        rate=94.5, rub_received=94500.0, pnl_rub=4500.0
    )
    assert conv_id > 0


def test_add_conversion_pnl_nullable():
    conv_id = db.add_conversion(
        user_id=1, amount=1000.0, from_cur="USD",
        rate=94.5, rub_received=94500.0, pnl_rub=None
    )
    conn = db._connect()
    row = conn.execute("SELECT pnl_rub FROM conversions WHERE id = ?", (conv_id,)).fetchone()
    assert row["pnl_rub"] is None


# ─── Rate history ─────────────────────────────────────────────────────────────

def test_upsert_rate_history_insert_or_ignore():
    db.upsert_rate_history("USD", 90.0, "RUB", "2026-01-01")
    db.upsert_rate_history("USD", 99.0, "RUB", "2026-01-01")  # same date — ignored

    history = db.get_rate_history("USD")
    assert len(history) == 1
    assert history[0] == 90.0  # оригинальное значение, не перезаписано


def test_get_rate_history_returns_newest_first():
    db.upsert_rate_history("USD", 88.0, "RUB", "2026-01-01")
    db.upsert_rate_history("USD", 90.0, "RUB", "2026-01-02")
    db.upsert_rate_history("USD", 92.0, "RUB", "2026-01-03")

    history = db.get_rate_history("USD", limit=14)
    assert history[0] == 92.0  # новейший первый
    assert history[-1] == 88.0


def test_cleanup_old_rate_history():
    from datetime import date, timedelta
    today = date.today().isoformat()
    db.upsert_rate_history("USD", 88.0, "RUB", "2020-01-01")  # старая
    db.upsert_rate_history("USD", 90.0, "RUB", today)          # свежая (сегодня)

    db.cleanup_old_rate_history(days=14)

    history = db.get_rate_history("USD")
    assert len(history) == 1
    assert history[0] == 90.0
