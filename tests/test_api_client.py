"""
Тесты для api_client.py — get_fiat_rates_batch(), верификация URL.
HTTP-запросы мокируются через respx или unittest.mock.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

import api_client


# ─── URL verification ─────────────────────────────────────────────────────────

def test_exchange_rate_uses_correct_api():
    """get_exchange_rate() должен обращаться к exchangerate-api.com, не к open.er-api.com."""
    import inspect
    source = inspect.getsource(api_client.get_exchange_rate)
    assert "open.exchangerate-api.com" in source
    assert "open.er-api.com" not in source


def test_convert_currency_uses_correct_api():
    """convert_currency() должен обращаться к exchangerate-api.com."""
    import inspect
    source = inspect.getsource(api_client.convert_currency)
    assert "open.exchangerate-api.com" in source
    assert "open.er-api.com" not in source


def test_get_fiat_rates_batch_uses_correct_api():
    """get_fiat_rates_batch() должен обращаться к exchangerate-api.com."""
    import inspect
    source = inspect.getsource(api_client.get_fiat_rates_batch)
    assert "open.exchangerate-api.com" in source


# ─── get_fiat_rates_batch ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_fiat_rates_batch_empty_input():
    result = await api_client.get_fiat_rates_batch([])
    assert result == {}


@pytest.mark.asyncio
async def test_get_fiat_rates_batch_returns_rates():
    """Один HTTP-запрос возвращает курсы для нескольких кодов."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "result": "success",
        "rates": {
            "USD": 0.011,  # 1 RUB = 0.011 USD → 1 USD ≈ 90.9 RUB
            "EUR": 0.010,  # 1 RUB = 0.010 EUR → 1 EUR = 100 RUB
        }
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("api_client.httpx.AsyncClient", return_value=mock_client):
        result = await api_client.get_fiat_rates_batch(["USD", "EUR"])

    assert "USD" in result
    assert "EUR" in result
    assert abs(result["USD"] - 90.9) < 1.0
    assert abs(result["EUR"] - 100.0) < 1.0


@pytest.mark.asyncio
async def test_get_fiat_rates_batch_returns_empty_on_api_error():
    """При ошибке API возвращает пустой dict, не бросает исключение."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(side_effect=Exception("connection refused"))

    with patch("api_client.httpx.AsyncClient", return_value=mock_client):
        result = await api_client.get_fiat_rates_batch(["USD", "EUR"])

    assert result == {}


@pytest.mark.asyncio
async def test_get_fiat_rates_batch_single_request_for_multiple_codes():
    """Независимо от числа кодов — ровно один HTTP GET запрос."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "rates": {"USD": 0.011, "EUR": 0.010, "GBP": 0.0085}
    }

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("api_client.httpx.AsyncClient", return_value=mock_client):
        await api_client.get_fiat_rates_batch(["USD", "EUR", "GBP"])

    assert mock_client.get.call_count == 1  # ровно один запрос


# ─── is_known_ticker ──────────────────────────────────────────────────────────

def test_is_known_ticker_fiat():
    assert api_client.is_known_ticker("USD") is True
    assert api_client.is_known_ticker("EUR") is True
    assert api_client.is_known_ticker("usd") is True  # case-insensitive


def test_is_known_ticker_crypto():
    assert api_client.is_known_ticker("BTC") is True
    assert api_client.is_known_ticker("ETH") is True
    assert api_client.is_known_ticker("btc") is True


def test_is_known_ticker_unknown():
    assert api_client.is_known_ticker("FAKECOIN") is False
    assert api_client.is_known_ticker("XYZ") is False
