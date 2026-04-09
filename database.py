"""
Модуль базы данных (SQLite).

Таблицы:
  watchlist    — список наблюдения пользователя
  user_settings — настройки пользователя (язык)
  alerts       — пороговые алерты (/alert)
  payments     — входящие платежи (/payment)
  conversions  — логи конвертаций (/converted)
  rate_history — дневные курсы для контекста тренда в алертах
"""

import os
import sqlite3
from pathlib import Path
from typing import Optional

from api_client import _COINGECKO_IDS

DB_PATH = Path(os.getenv("DB_PATH", "bot.db"))

# Единый источник правды — берём тикеры из api_client
_CRYPTO_TICKERS: set[str] = set(_COINGECKO_IDS.keys())


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Создать таблицы и индексы при первом запуске."""
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS watchlist (
                user_id  INTEGER NOT NULL,
                code     TEXT    NOT NULL,
                kind     TEXT    NOT NULL DEFAULT 'fiat',
                added_at TEXT    NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (user_id, code)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id  INTEGER PRIMARY KEY,
                language TEXT NOT NULL DEFAULT 'ru',
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alerts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id         INTEGER NOT NULL,
                code            TEXT    NOT NULL,
                kind            TEXT    NOT NULL,
                target_price    REAL    NOT NULL,
                direction       TEXT    NOT NULL DEFAULT 'above',
                was_triggered   INTEGER NOT NULL DEFAULT 0,
                last_checked_at TEXT,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                amount      REAL    NOT NULL,
                from_cur    TEXT    NOT NULL,
                rate_at_add REAL,
                target_rate REAL,
                status      TEXT    NOT NULL DEFAULT 'pending',
                added_at    TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS conversions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL,
                amount       REAL    NOT NULL,
                from_cur     TEXT    NOT NULL,
                rate         REAL    NOT NULL,
                rub_received REAL    NOT NULL,
                pnl_rub      REAL,
                payment_id   INTEGER,
                converted_at TEXT    NOT NULL DEFAULT (datetime('now'))
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rate_history (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                code          TEXT NOT NULL,
                rate          REAL NOT NULL,
                currency      TEXT NOT NULL DEFAULT 'RUB',
                recorded_date TEXT NOT NULL,
                UNIQUE(code, recorded_date)
            )
        """)
        # Индексы для горячих путей
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_alerts_active "
            "ON alerts(was_triggered, user_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_rate_history "
            "ON rate_history(code, recorded_date)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_payments_pending "
            "ON payments(user_id, from_cur, status)"
        )
        conn.commit()


def _detect_kind(code: str) -> str:
    return "crypto" if code in _CRYPTO_TICKERS else "fiat"


# ─── Watchlist ────────────────────────────────────────────────────────────────

def add_to_watchlist(user_id: int, code: str) -> bool:
    """Добавить тикер в список. True если добавлен, False если уже существует."""
    kind = _detect_kind(code)
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO watchlist (user_id, code, kind) VALUES (?, ?, ?)",
                (user_id, code, kind),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def remove_from_watchlist(user_id: int, code: str) -> bool:
    """Удалить тикер из списка. True если удалён, False если не найден."""
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND code = ?",
            (user_id, code),
        )
        conn.commit()
    return cursor.rowcount > 0


def get_watchlist(user_id: int) -> list[tuple[str, str]]:
    """Вернуть список (code, kind) для пользователя, отсортированный по дате добавления."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT code, kind FROM watchlist WHERE user_id = ? ORDER BY added_at",
            (user_id,),
        ).fetchall()
    return [(row["code"], row["kind"]) for row in rows]


# ─── User settings ────────────────────────────────────────────────────────────

def get_user_language(user_id: int) -> str | None:
    """Вернуть язык пользователя (ru/en), если ранее был сохранен."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT language FROM user_settings WHERE user_id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    return row["language"]


def set_user_language(user_id: int, language: str) -> None:
    """Сохранить язык пользователя (upsert)."""
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO user_settings (user_id, language, updated_at)
            VALUES (?, ?, datetime('now'))
            ON CONFLICT(user_id)
            DO UPDATE SET language = excluded.language, updated_at = datetime('now')
            """,
            (user_id, language),
        )
        conn.commit()


# ─── Alerts ───────────────────────────────────────────────────────────────────

def add_alert(
    user_id: int,
    code: str,
    target_price: float,
    direction: str = "above",
    conn: Optional[sqlite3.Connection] = None,
) -> int:
    """
    Добавить алерт. Возвращает id новой записи.
    Принимает опциональный conn для использования внутри транзакции.
    """
    kind = _detect_kind(code.upper())
    _conn = conn or _connect()
    try:
        cursor = _conn.execute(
            """
            INSERT INTO alerts (user_id, code, kind, target_price, direction)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, code.upper(), kind, target_price, direction),
        )
        if conn is None:
            _conn.commit()
        return cursor.lastrowid
    finally:
        if conn is None:
            _conn.close()


def get_active_alerts(user_id: Optional[int] = None) -> list[sqlite3.Row]:
    """
    Вернуть все активные (was_triggered=0) алерты.
    Если user_id указан — только для этого пользователя.
    """
    with _connect() as conn:
        if user_id is not None:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE was_triggered = 0 AND user_id = ? ORDER BY created_at",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE was_triggered = 0 ORDER BY created_at",
            ).fetchall()
    return rows


def mark_triggered(alert_id: int) -> None:
    """Пометить алерт как сработавший (идемпотентно)."""
    with _connect() as conn:
        conn.execute(
            "UPDATE alerts SET was_triggered = 1, last_checked_at = datetime('now') WHERE id = ?",
            (alert_id,),
        )
        conn.commit()


def remove_alerts_for_code(user_id: int, code: str) -> int:
    """Удалить все активные алерты пользователя для данного кода. Возвращает число удалённых."""
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM alerts WHERE user_id = ? AND code = ? AND was_triggered = 0",
            (user_id, code.upper()),
        )
        conn.commit()
    return cursor.rowcount


def cleanup_old_alerts(days: int = 7) -> None:
    """Удалить сработавшие алерты старше N дней."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM alerts WHERE was_triggered = 1 AND created_at < datetime('now', ?)",
            (f"-{days} days",),
        )
        conn.commit()


# ─── Payments ─────────────────────────────────────────────────────────────────

def add_payment(
    user_id: int,
    amount: float,
    from_cur: str,
    rate_at_add: Optional[float],
    target_rate: Optional[float] = None,
) -> int:
    """
    Атомарно добавить платёж и, если указан target_rate, создать алерт.
    Возвращает payment_id.

    /payment flow:
      rate_at_add = get_exchange_rate(code)   ← BEFORE this function (async API)
      BEGIN TRANSACTION
        INSERT payments
        INSERT alerts (only if target_rate provided)
      COMMIT
      └── ROLLBACK on any error (both rows or neither)
    """
    with _connect() as conn:
        try:
            conn.execute("BEGIN")
            cursor = conn.execute(
                """
                INSERT INTO payments (user_id, amount, from_cur, rate_at_add, target_rate)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, amount, from_cur.upper(), rate_at_add, target_rate),
            )
            payment_id = cursor.lastrowid
            if target_rate is not None:
                add_alert(user_id, from_cur, target_rate, direction="above", conn=conn)
            conn.execute("COMMIT")
            return payment_id
        except Exception:
            conn.execute("ROLLBACK")
            raise


def get_oldest_pending_payment(user_id: int, from_cur: str) -> Optional[sqlite3.Row]:
    """FIFO: вернуть старейший pending-платёж пользователя для данной валюты."""
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT * FROM payments
            WHERE user_id = ? AND from_cur = ? AND status = 'pending'
            ORDER BY added_at ASC
            LIMIT 1
            """,
            (user_id, from_cur.upper()),
        ).fetchone()
    return row


def get_all_pending_payments(user_id: int) -> list[sqlite3.Row]:
    """Вернуть все pending-платежи пользователя (все валюты), FIFO."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM payments WHERE user_id = ? AND status = 'pending' ORDER BY added_at ASC",
            (user_id,),
        ).fetchall()
    return rows


def mark_payment_converted(payment_id: int) -> None:
    """Пометить платёж как конвертированный."""
    with _connect() as conn:
        conn.execute(
            "UPDATE payments SET status = 'converted' WHERE id = ?",
            (payment_id,),
        )
        conn.commit()


# ─── Conversions ──────────────────────────────────────────────────────────────

def add_conversion(
    user_id: int,
    amount: float,
    from_cur: str,
    rate: float,
    rub_received: float,
    pnl_rub: Optional[float] = None,
    payment_id: Optional[int] = None,
) -> int:
    """Записать конвертацию. Возвращает conversion_id."""
    with _connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO conversions
              (user_id, amount, from_cur, rate, rub_received, pnl_rub, payment_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, amount, from_cur.upper(), rate, rub_received, pnl_rub, payment_id),
        )
        conn.commit()
    return cursor.lastrowid


# ─── Rate history ─────────────────────────────────────────────────────────────

def upsert_rate_history(code: str, rate: float, currency: str, date_str: str) -> None:
    """
    Записать (или пропустить, если дата уже есть) дневной курс.
    date_str: YYYY-MM-DD (UTC)
    currency: 'RUB' для фиата, 'USD' для крипты
    """
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO rate_history (code, rate, currency, recorded_date)
            VALUES (?, ?, ?, ?)
            """,
            (code.upper(), rate, currency, date_str),
        )
        conn.commit()


def get_rate_history(code: str, limit: int = 14) -> list[float]:
    """Вернуть последние N дневных курсов для кода (новые первыми)."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT rate FROM rate_history
            WHERE code = ?
            ORDER BY recorded_date DESC
            LIMIT ?
            """,
            (code.upper(), limit),
        ).fetchall()
    return [row["rate"] for row in rows]


def cleanup_old_rate_history(days: int = 14) -> None:
    """Удалить записи rate_history старше N дней."""
    with _connect() as conn:
        conn.execute(
            "DELETE FROM rate_history WHERE recorded_date < date('now', ?)",
            (f"-{days} days",),
        )
        conn.commit()


def get_active_alert_codes() -> list[tuple[str, str]]:
    """Вернуть список (code, kind) из активных алертов — для seed_rate_history."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT DISTINCT code, kind FROM alerts WHERE was_triggered = 0",
        ).fetchall()
    return [(row["code"], row["kind"]) for row in rows]
