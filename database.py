"""
Модуль базы данных (SQLite).

Таблица watchlist:
  user_id  — Telegram ID пользователя
  code     — тикер (BTC, USD, ETH ...)
  kind     — тип: 'crypto' или 'fiat'
  added_at — дата добавления
"""

import os
import sqlite3
from pathlib import Path

from api_client import _COINGECKO_IDS

DB_PATH = Path(os.getenv("DB_PATH", "bot.db"))

# Единый источник правды — берём тикеры из api_client
_CRYPTO_TICKERS: set[str] = set(_COINGECKO_IDS.keys())


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Создать таблицы при первом запуске."""
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
        conn.commit()


def _detect_kind(code: str) -> str:
    return "crypto" if code in _CRYPTO_TICKERS else "fiat"


def add_to_watchlist(user_id: int, code: str) -> bool:
    """
    Добавить тикер в список.
    Возвращает True если добавлен, False если уже существует.
    """
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
    """
    Удалить тикер из списка.
    Возвращает True если удалён, False если не найден.
    """
    with _connect() as conn:
        cursor = conn.execute(
            "DELETE FROM watchlist WHERE user_id = ? AND code = ?",
            (user_id, code),
        )
        conn.commit()
    return cursor.rowcount > 0


def get_watchlist(user_id: int) -> list[tuple[str, str]]:
    """
    Вернуть список (code, kind) для пользователя, отсортированный по дате добавления.
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT code, kind FROM watchlist WHERE user_id = ? ORDER BY added_at",
            (user_id,),
        ).fetchall()
    return [(row["code"], row["kind"]) for row in rows]
