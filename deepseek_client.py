"""
DeepSeek API client. All functions return None on any error.
Requires DEEPSEEK_API_KEY env var — if missing, all functions return None immediately.
"""
import json
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)
_API_KEY = os.getenv("DEEPSEEK_API_KEY")
_TIMEOUT = httpx.Timeout(15.0)
_BASE_URL = "https://api.deepseek.com/chat/completions"


async def _call_deepseek(system_prompt: str, user_msg: str) -> str | None:
    """Low-level call. Returns text content or None on any error."""
    if not _API_KEY:
        return None
    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg},
        ],
        "max_tokens": 200,
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                _BASE_URL,
                json=payload,
                headers={"Authorization": f"Bearer {_API_KEY}"},
            )
        if r.status_code in (401, 403):
            logger.error("DeepSeek auth error %d — check DEEPSEEK_API_KEY", r.status_code)
            return None
        if r.status_code == 429:
            logger.warning("DeepSeek rate limit hit")
            return None
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        logger.error("DeepSeek call failed: %s", exc)
        return None


def _extract_json(text: str) -> dict | None:
    """Extract JSON from LLM response (may be wrapped in markdown code blocks)."""
    cleaned = re.sub(r"```(?:json)?\s*|\s*```", "", text).strip()
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        return None


async def parse_payment_from_text(text: str) -> dict | None:
    """
    Parse a forwarded payment notification.
    Returns {"amount": float, "currency": str} or None.
    Currency validation (is_known_ticker check) done by caller (bot.py).
    """
    system = (
        "Extract the payment amount and currency from the text. "
        "Return ONLY valid JSON in this exact format: {\"amount\": 2000.0, \"currency\": \"USD\"} "
        "If you cannot find a clear amount and currency, return: {\"amount\": null, \"currency\": null}"
    )
    response = await _call_deepseek(system, text)
    if response is None:
        return None
    parsed = _extract_json(response)
    if not parsed or parsed.get("amount") is None or parsed.get("currency") is None:
        return None
    try:
        return {"amount": float(parsed["amount"]), "currency": str(parsed["currency"]).upper()}
    except (TypeError, ValueError):
        return None


async def explain_pnl(
    current_rate: float,
    rate_at_add: float,
    pnl_rub: float,
    history_14d: list[float],
) -> str | None:
    """
    One-sentence Russian explanation of P&L result.
    history_14d: list of floats, newest first (from get_rate_history).
    Returns string or None.
    """
    pct_delta = ((current_rate - rate_at_add) / rate_at_add) * 100 if rate_at_add else 0
    position_pct = None
    if history_14d and len(history_14d) >= 2:
        h_min, h_max = min(history_14d), max(history_14d)
        if h_max > h_min:
            position_pct = round((current_rate - h_min) / (h_max - h_min) * 100)
    ctx = json.dumps({
        "current_rate": current_rate,
        "rate_at_add": rate_at_add,
        "pnl_rub": pnl_rub,
        "pct_delta_vs_receipt": round(pct_delta, 1),
        "position_in_14d_range_pct": position_pct,
    })
    system = (
        "You are a currency assistant. Write ONE short sentence in Russian "
        "summarizing this P&L result. State only facts from the data. "
        "Do not give advice. Do not use markdown. Max 20 words."
    )
    return await _call_deepseek(system, ctx)


async def answer_rate_question(question: str, context: dict) -> str | None:
    """
    Answer a user question about their currency situation.
    Context contains real DB data — LLM must not invent data.
    Returns answer string (Russian) or None.
    """
    system = (
        "You are a helpful currency assistant for a Russian freelancer. "
        "Answer the user's question using ONLY the data provided in the context JSON. "
        "Do not make predictions. Do not give financial advice. "
        "State facts from the data only. Answer in Russian. Max 5 sentences."
    )
    user_msg = f"Question: {question}\n\nContext data:\n{json.dumps(context, ensure_ascii=False)}"
    return await _call_deepseek(system, user_msg)
