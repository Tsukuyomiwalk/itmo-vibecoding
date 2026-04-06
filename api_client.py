"""
Клиент для внешних API.

Источники данных:
  - Курсы фиатных валют: https://open.er-api.com/v6/latest/  (бесплатно, без ключа)
  - Криптовалюты:        https://api.coingecko.com/api/v3/    (бесплатно, без ключа)
"""

import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# Простой in-memory кэш: ключ → (значение, timestamp)
_CACHE: dict[str, tuple[object, float]] = {}
_CACHE_TTL = 60  # секунд


def _cache_get(key: str) -> object | None:
    entry = _CACHE.get(key)
    if entry and (time.monotonic() - entry[1]) < _CACHE_TTL:
        return entry[0]
    return None


def _cache_set(key: str, value: object) -> None:
    _CACHE[key] = (value, time.monotonic())


# Маппинг популярных тикеров → CoinGecko ID
_COINGECKO_IDS: dict[str, str] = {
    "BTC":   "bitcoin",
    "ETH":   "ethereum",
    "SOL":   "solana",
    "BNB":   "binancecoin",
    "XRP":   "ripple",
    "ADA":   "cardano",
    "DOGE":  "dogecoin",
    "AVAX":  "avalanche-2",
    "DOT":   "polkadot",
    "MATIC": "matic-network",
    "LTC":   "litecoin",
    "LINK":  "chainlink",
    "UNI":   "uniswap",
    "ATOM":  "cosmos",
    "TON":   "the-open-network",
    "NEAR":  "near",
    "APT":   "aptos",
    "SUI":   "sui",
    "OP":    "optimism",
    "ARB":   "arbitrum",
    "PEPE":  "pepe",
    "SHIB":  "shiba-inu",
    "TRX":   "tron",
    "XLM":   "stellar",
    "ALGO":  "algorand",
}

_TIMEOUT = httpx.Timeout(10.0)

# Популярные фиатные коды — для валидации в /watch
KNOWN_FIAT_CODES: set[str] = {
    "USD", "EUR", "GBP", "JPY", "CNY", "CHF", "CAD", "AUD", "NZD",
    "HKD", "SGD", "SEK", "NOK", "DKK", "PLN", "CZK", "HUF", "TRY",
    "BRL", "INR", "KRW", "ZAR", "MXN", "AED", "SAR", "THB", "IDR",
    "RUB", "UAH", "KZT", "BYN", "GEL", "AMD", "AZN", "UZS",
}


def is_known_ticker(code: str) -> bool:
    """Проверить, известен ли тикер (крипта или фиатная валюта)."""
    return code.upper() in _COINGECKO_IDS or code.upper() in KNOWN_FIAT_CODES


def _resolve_coingecko_id(symbol: str) -> str:
    """Вернуть CoinGecko ID для тикера (или сам символ в нижнем регистре как фолбэк)."""
    return _COINGECKO_IDS.get(symbol.upper(), symbol.lower())


async def get_exchange_rate(currency_code: str) -> Optional[float]:
    """
    Вернуть курс валюты в рублях.
    Например, get_exchange_rate("USD") → 90.5
    """
    cache_key = f"rate:{currency_code.upper()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    url = "https://open.er-api.com/v6/latest/RUB"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        rates = data.get("rates", {})
        # rates[USD] = кол-во USD за 1 RUB → нам нужно обратное
        rate_per_rub = rates.get(currency_code.upper())
        if rate_per_rub and rate_per_rub > 0:
            result = 1.0 / rate_per_rub
            _cache_set(cache_key, result)
            return result
        return None
    except Exception as exc:
        logger.error("Ошибка получения курса %s: %s", currency_code, exc)
        return None


async def get_crypto_price(symbol: str) -> Optional[tuple[float, float]]:
    """
    Вернуть (цена в USD, изменение за 24ч в %).
    Например, get_crypto_price("BTC") → (65000.0, 2.5)
    """
    cache_key = f"crypto:{symbol.upper()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached  # type: ignore[return-value]

    coin_id = _resolve_coingecko_id(symbol)
    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": coin_id,
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        coin_data = data.get(coin_id)
        if not coin_data:
            return None

        price = coin_data.get("usd", 0.0)
        change = coin_data.get("usd_24h_change", 0.0)
        result = (price, change)
        _cache_set(cache_key, result)
        return result
    except Exception as exc:
        logger.error("Ошибка получения цены крипты %s: %s", symbol, exc)
        return None


async def get_crypto_prices_batch(symbols: list[str]) -> dict[str, tuple[float, float]]:
    """
    Получить цены нескольких криптовалют за один запрос.
    Возвращает dict: {SYMBOL: (price, change_24h)} для найденных монет.
    """
    if not symbols:
        return {}

    id_to_symbol: dict[str, str] = {}
    for sym in symbols:
        coin_id = _resolve_coingecko_id(sym)
        id_to_symbol[coin_id] = sym

    url = "https://api.coingecko.com/api/v3/simple/price"
    params = {
        "ids": ",".join(id_to_symbol.keys()),
        "vs_currencies": "usd",
        "include_24hr_change": "true",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()

        result: dict[str, tuple[float, float]] = {}
        for coin_id, sym in id_to_symbol.items():
            coin_data = data.get(coin_id)
            if coin_data:
                price = coin_data.get("usd", 0.0)
                change = coin_data.get("usd_24h_change", 0.0)
                result[sym] = (price, change)
        return result
    except Exception as exc:
        logger.error("Ошибка batch-запроса крипты: %s", exc)
        return {}


async def convert_currency(amount: float, from_cur: str, to_cur: str) -> Optional[float]:
    """
    Конвертировать сумму из одной фиатной валюты в другую.
    Например, convert_currency(100, "USD", "EUR") → 92.3
    """
    # Кэшируем курс (не результат, т.к. сумма меняется), чтобы переиспользовать rate
    cache_key = f"convert:{from_cur.upper()}:{to_cur.upper()}"
    cached_rate = _cache_get(cache_key)
    if cached_rate is not None:
        return amount * cached_rate  # type: ignore[operator]

    url = f"https://open.er-api.com/v6/latest/{from_cur.upper()}"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()

        rate = data.get("rates", {}).get(to_cur.upper())
        if rate is None:
            return None
        _cache_set(cache_key, rate)
        return amount * rate
    except Exception as exc:
        logger.error("Ошибка конвертации %s→%s: %s", from_cur, to_cur, exc)
        return None
