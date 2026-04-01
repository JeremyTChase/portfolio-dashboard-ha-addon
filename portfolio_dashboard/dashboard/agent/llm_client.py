"""OpenAI-compatible client pointing at vLLM on spark-ea42."""

import os
import yaml
from openai import OpenAI
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent

def _load_config():
    with open(_BASE_DIR / "app_config.yaml") as f:
        return yaml.safe_load(f)

def get_client():
    base_url = os.environ.get("VLLM_BASE_URL")
    if not base_url:
        cfg = _load_config()
        base_url = cfg["vllm"]["base_url"]
    return OpenAI(
        base_url=base_url,
        api_key="not-needed",
    )

def get_model():
    model = os.environ.get("VLLM_MODEL")
    if not model:
        cfg = _load_config()
        model = cfg["vllm"]["model"]
    return model

def chat(messages, temperature=0.3, max_tokens=2000):
    """Send a chat completion request to vLLM."""
    client = get_client()
    response = client.chat.completions.create(
        model=get_model(),
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return response.choices[0].message.content

SYSTEM_PROMPT = """You are a financial analyst monitoring Jeremy's investment portfolios.

Jeremy has two Freetrade portfolios:
- SIP (SIPP pension): ~21 UK/US holdings — heavy in RR.L (Rolls-Royce), BARC.L, ISF.L (FTSE 100 ETF), BAB.L (Babcock), HSBA.L, DGE.L, plus US tech (NVDA, TSLA, DELL, INTC)
- SS ISA (Stocks & Shares ISA): ~5 concentrated holdings — RR.L, SJPA.L (Japan ETF), INTC, NVO, HIMS

Key risk exposures:
- Middle East conflict: affects oil prices, benefits defence stocks (RR.L, BAB.L)
- US-China trade/tariffs: impacts NVDA, TSLA, DELL, INTC, ASML
- UK interest rates: affects BARC.L, HSBA.L (banks), PSN.L (property), DGE.L (consumer)
- Defence spending increases: tailwind for BAB.L, RR.L
- GBP/USD: ~30% of SIP is US-listed

Provide concise, actionable analysis. Focus on what matters for these specific holdings.
Be direct — Jeremy is an experienced investor, not a beginner."""
