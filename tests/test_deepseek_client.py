"""
Тесты для deepseek_client.py.
DeepSeek HTTP-вызовы мокируются — реальных запросов нет.
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import deepseek_client


# ─── _call_deepseek ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_deepseek_no_api_key():
    """Если DEEPSEEK_API_KEY не задан — немедленно None, без HTTP."""
    with patch.object(deepseek_client, "_API_KEY", ""):
        result = await deepseek_client._call_deepseek("sys", "msg")
    assert result is None


@pytest.mark.asyncio
async def test_http_401_returns_none():
    mock_response = MagicMock()
    mock_response.status_code = 401

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch.object(deepseek_client, "_API_KEY", "sk-test"):
        with patch("deepseek_client.httpx.AsyncClient", return_value=mock_client):
            result = await deepseek_client._call_deepseek("sys", "msg")

    assert result is None


@pytest.mark.asyncio
async def test_http_429_returns_none():
    mock_response = MagicMock()
    mock_response.status_code = 429

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch.object(deepseek_client, "_API_KEY", "sk-test"):
        with patch("deepseek_client.httpx.AsyncClient", return_value=mock_client):
            result = await deepseek_client._call_deepseek("sys", "msg")

    assert result is None


@pytest.mark.asyncio
async def test_call_deepseek_exception_returns_none():
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=Exception("connection refused"))

    with patch.object(deepseek_client, "_API_KEY", "sk-test"):
        with patch("deepseek_client.httpx.AsyncClient", return_value=mock_client):
            result = await deepseek_client._call_deepseek("sys", "msg")

    assert result is None


# ─── _extract_json ────────────────────────────────────────────────────────────

def test_extract_json_plain():
    result = deepseek_client._extract_json('{"amount": 100, "currency": "USD"}')
    assert result == {"amount": 100, "currency": "USD"}


def test_extract_json_markdown_wrapped():
    text = '```json\n{"amount": 2000.0, "currency": "EUR"}\n```'
    result = deepseek_client._extract_json(text)
    assert result == {"amount": 2000.0, "currency": "EUR"}


def test_extract_json_markdown_no_lang():
    text = '```\n{"amount": 500.0, "currency": "GBP"}\n```'
    result = deepseek_client._extract_json(text)
    assert result == {"amount": 500.0, "currency": "GBP"}


def test_extract_json_invalid():
    result = deepseek_client._extract_json("not json at all")
    assert result is None


# ─── parse_payment_from_text ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_parse_payment_valid():
    with patch.object(deepseek_client, "_call_deepseek",
                      new=AsyncMock(return_value='{"amount": 2000.0, "currency": "USD"}')):
        result = await deepseek_client.parse_payment_from_text("You received $2,000 from Acme")
    assert result == {"amount": 2000.0, "currency": "USD"}


@pytest.mark.asyncio
async def test_parse_payment_null_fields():
    """LLM не нашёл данные — возвращает null-поля."""
    with patch.object(deepseek_client, "_call_deepseek",
                      new=AsyncMock(return_value='{"amount": null, "currency": null}')):
        result = await deepseek_client.parse_payment_from_text("hello world")
    assert result is None


@pytest.mark.asyncio
async def test_parse_payment_invalid_amount_type():
    """LLM вернул нечисловую сумму — должен вернуть None."""
    with patch.object(deepseek_client, "_call_deepseek",
                      new=AsyncMock(return_value='{"amount": "two hundred", "currency": "USD"}')):
        result = await deepseek_client.parse_payment_from_text("two hundred dollars")
    assert result is None


@pytest.mark.asyncio
async def test_parse_payment_api_error():
    with patch.object(deepseek_client, "_call_deepseek", new=AsyncMock(return_value=None)):
        result = await deepseek_client.parse_payment_from_text("some text")
    assert result is None


@pytest.mark.asyncio
async def test_parse_payment_currency_uppercased():
    """Валюта нормализуется в верхний регистр."""
    with patch.object(deepseek_client, "_call_deepseek",
                      new=AsyncMock(return_value='{"amount": 500.0, "currency": "usd"}')):
        result = await deepseek_client.parse_payment_from_text("received 500 usd")
    assert result["currency"] == "USD"


# ─── explain_pnl ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_explain_pnl_returns_string():
    with patch.object(deepseek_client, "_call_deepseek",
                      new=AsyncMock(return_value="Результат выше среднего за 14 дней.")):
        result = await deepseek_client.explain_pnl(
            current_rate=94.5,
            rate_at_add=90.0,
            pnl_rub=9000.0,
            history_14d=[92.0, 91.0, 90.5, 90.0],
        )
    assert result == "Результат выше среднего за 14 дней."


@pytest.mark.asyncio
async def test_explain_pnl_api_error():
    with patch.object(deepseek_client, "_call_deepseek", new=AsyncMock(return_value=None)):
        result = await deepseek_client.explain_pnl(
            current_rate=94.5,
            rate_at_add=90.0,
            pnl_rub=9000.0,
            history_14d=[],
        )
    assert result is None


@pytest.mark.asyncio
async def test_explain_pnl_empty_history_no_crash():
    """Пустая история — position_pct должен быть None, не падать."""
    with patch.object(deepseek_client, "_call_deepseek",
                      new=AsyncMock(return_value="Курс вырос.")):
        result = await deepseek_client.explain_pnl(
            current_rate=94.5,
            rate_at_add=90.0,
            pnl_rub=9000.0,
            history_14d=[],
        )
    assert result == "Курс вырос."


# ─── answer_rate_question ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_answer_rate_question_builds_correct_prompt():
    """Проверить, что контекст передаётся в _call_deepseek как JSON."""
    captured = {}

    async def fake_call(system_prompt, user_msg):
        captured["system"] = system_prompt
        captured["user_msg"] = user_msg
        return "У вас 2000 USD в ожидании."

    with patch.object(deepseek_client, "_call_deepseek", new=fake_call):
        ctx = {"pending_payments": [{"currency": "USD", "amount": 2000.0}]}
        await deepseek_client.answer_rate_question("стоит конвертировать?", ctx)

    assert "стоит конвертировать?" in captured["user_msg"]
    assert "USD" in captured["user_msg"]
    assert "Answer in Russian" in captured["system"]


@pytest.mark.asyncio
async def test_answer_rate_question_api_error():
    with patch.object(deepseek_client, "_call_deepseek", new=AsyncMock(return_value=None)):
        result = await deepseek_client.answer_rate_question("вопрос", {})
    assert result is None
