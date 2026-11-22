"""테스트용 페이크 챗 모델 — 실제 API 호출 없이 노드·그래프 로직을 검증한다."""

from __future__ import annotations

from langchain_core.messages import AIMessage


class FakeChat:
    """invoke / with_structured_output을 흉내낸다.

    outputs의 원소를 호출 순서대로 반환한다:
    - str → AIMessage(content=...) (텍스트 노드용)
    - Exception → raise
    - 그 외(Pydantic 객체, None) → 그대로 반환 (구조화 출력용)
    """

    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls: list[list] = []

    def invoke(self, messages, config=None):
        self.calls.append(list(messages))
        out = self.outputs.pop(0)
        if isinstance(out, Exception):
            raise out
        if isinstance(out, str):
            return AIMessage(content=out)
        return out

    def with_structured_output(self, schema):
        return self


class Fake429(Exception):
    status_code = 429
