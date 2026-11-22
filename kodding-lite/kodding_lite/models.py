"""모델 라우팅 단일 정의 + 클라이언트 팩토리 + 토큰 집계.

다른 곳에서 모델명을 하드코딩하지 않는다. 노드는 get_model(노드명)만 쓴다.
env `MODEL_<노드대문자>`로 노드별 모델을 바꿀 수 있다.
  예) MODEL_DRAFT=claude-sonnet-4-6  → 초안만 Claude로
"""

from __future__ import annotations

import os
from collections import defaultdict
from contextlib import contextmanager
from typing import Iterator

from langchain_core.callbacks import UsageMetadataCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel

ROUTING = {
    "plan": "gemini-2.5-flash",   # 구조 설계 — 저비용으로 충분
    "draft": "gemini-2.5-flash",  # 대량 생성 — 저비용
}

TEMPERATURES = {
    "plan": 0.3,
    "draft": 0.7,
}

_CLAUDE_MAX_TOKENS = 8192

# run_id → node → {"input_tokens", "output_tokens"}
_TOKEN_LOG: dict[str, dict[str, dict[str, int]]] = defaultdict(
    lambda: defaultdict(lambda: {"input_tokens": 0, "output_tokens": 0})
)


def model_for(node: str) -> str:
    if node not in ROUTING:
        raise KeyError(f"알 수 없는 노드: {node!r} (가능: {sorted(ROUTING)})")
    return os.environ.get(f"MODEL_{node.upper()}", ROUTING[node])


def get_model(node: str) -> BaseChatModel:
    name = model_for(node)
    temperature = TEMPERATURES[node]
    if name.startswith("gemini"):
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=name, temperature=temperature)
    if name.startswith("claude"):
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(
            model=name, temperature=temperature, max_tokens=_CLAUDE_MAX_TOKENS
        )
    raise ValueError(f"지원하지 않는 모델 계열: {name!r}")


@contextmanager
def track_tokens(run_id: str, node: str) -> Iterator[UsageMetadataCallbackHandler]:
    """LLM 호출의 토큰 사용량을 메모리에 집계하는 콜백 컨텍스트."""
    handler = UsageMetadataCallbackHandler()
    try:
        yield handler
    finally:
        for usage in (handler.usage_metadata or {}).values():
            bucket = _TOKEN_LOG[run_id][node]
            bucket["input_tokens"] += int(usage.get("input_tokens", 0))
            bucket["output_tokens"] += int(usage.get("output_tokens", 0))


def token_totals(run_id: str) -> dict[str, int]:
    totals = {"input_tokens": 0, "output_tokens": 0}
    for bucket in _TOKEN_LOG.get(run_id, {}).values():
        totals["input_tokens"] += bucket["input_tokens"]
        totals["output_tokens"] += bucket["output_tokens"]
    return totals
