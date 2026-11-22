"""LLM 호출 공통 유틸 — 정관 주입, 프롬프트 로드, 재시도, 구조화 출력.

- 정관(charter)은 파일에서 읽어 모든 노드의 시스템 프롬프트에 주입한다 (복붙 금지).
- Claude로 라우팅된 노드는 정관을 프롬프트 캐시 블록으로 분리한다.
- API 오류(429/5xx)는 지수 백오프 3회.
- 구조화 출력 파싱 실패 시 1회 재요청.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError
from tenacity import Retrying, retry_if_exception, stop_after_attempt, wait_exponential

from kodding_lite import models

_REPO_ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

# 테스트에서 wait_none()으로 바꿔 재시도 지연을 없앨 수 있게 모듈 변수로 둔다
RETRY_WAIT = wait_exponential(multiplier=1, min=1, max=20)
RETRY_ATTEMPTS = 3


def load_charter() -> str:
    """정관 전문. 기본은 charter.md, 없으면 charter.example.md. CHARTER_PATH로 지정 가능."""
    override = os.environ.get("CHARTER_PATH")
    if override:
        return Path(override).read_text(encoding="utf-8")
    for name in ("charter.md", "charter.example.md"):
        path = _REPO_ROOT / name
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError("charter.md 또는 charter.example.md가 필요합니다")


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def system_message(node: str, instructions: str) -> SystemMessage:
    """정관 + 노드 지침으로 시스템 메시지를 만든다."""
    charter = load_charter()
    if models.model_for(node).startswith("claude"):
        return SystemMessage(
            content=[
                {"type": "text", "text": charter, "cache_control": {"type": "ephemeral"}},
                {"type": "text", "text": instructions},
            ]
        )
    return SystemMessage(content=charter + "\n\n---\n\n" + instructions)


def _is_retryable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if status is None:
        code = getattr(exc, "code", None)
        status = code if isinstance(code, int) else None
    return isinstance(status, int) and (status == 429 or 500 <= status < 600)


def invoke_with_retry(runnable: Any, messages: list[BaseMessage], *, callbacks=None):
    config = {"callbacks": callbacks} if callbacks else None
    for attempt in Retrying(
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        wait=RETRY_WAIT,
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    ):
        with attempt:
            return runnable.invoke(messages, config=config)
    raise AssertionError("unreachable")  # pragma: no cover


def text_invoke(model: Any, messages: list[BaseMessage], *, callbacks=None) -> str:
    """텍스트 출력 호출. Claude의 블록 리스트 응답도 문자열로 정규화한다."""
    message = invoke_with_retry(model, messages, callbacks=callbacks)
    content = message.content
    if isinstance(content, list):
        content = "".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return content.strip()


def structured_invoke(
    model: Any, schema: type[BaseModel], messages: list[BaseMessage], *, callbacks=None
) -> BaseModel:
    """with_structured_output 호출. 파싱/검증 실패 시 1회 재요청."""
    chain = model.with_structured_output(schema)
    try:
        result = invoke_with_retry(chain, messages, callbacks=callbacks)
        error = None if result is not None else "빈 출력"
    except (ValidationError, OutputParserException) as exc:
        result, error = None, str(exc)
    if result is not None:
        return result

    retry_messages = messages + [
        HumanMessage(
            f"직전 출력이 {schema.__name__} 스키마와 맞지 않았습니다 ({error}). "
            "요구된 JSON 스키마에 정확히 맞는 완전한 객체를 다시 출력하세요."
        )
    ]
    result = invoke_with_retry(chain, retry_messages, callbacks=callbacks)
    if result is None:
        raise ValueError(f"{schema.__name__} 구조화 출력이 재요청에도 실패했습니다")
    return result
