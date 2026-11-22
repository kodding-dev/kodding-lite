"""단계 간 통신 스키마.

에이전트끼리 자유 텍스트를 주고받지 않고, 모든 단계 산출물을 Pydantic 모델로 고정한다.
LLM 구조화 출력은 `with_structured_output(스키마)`로 이 모델들을 그대로 쓴다.
Field description은 LLM에게 전달되는 스키마 힌트이므로 구체적으로 쓴다.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["비교 리뷰", "워크플로우", "비용 분석"]


class Ticket(BaseModel):
    """파이프라인 입력. 사람이 CLI로 넣거나, 상위 기획 에이전트가 만든다."""

    id: str
    topic: str
    category: Category
    angle: str | None = None
    keywords: list[str] = []
    created_at: datetime

    @classmethod
    def new(
        cls,
        topic: str,
        category: Category,
        angle: str | None = None,
        keywords: list[str] | None = None,
    ) -> "Ticket":
        return cls(
            id=uuid.uuid4().hex[:12],
            topic=topic,
            category=category,
            angle=angle,
            keywords=keywords or [],
            created_at=datetime.now(timezone.utc),
        )


class Section(BaseModel):
    heading: str = Field(description="섹션 제목 (H2)")
    points: list[str] = Field(description="이 섹션에서 다룰 핵심 포인트 2~4개")


class Plan(BaseModel):
    """기획 단계 산출물 — 제목·요약·섹션 구조·태그."""

    title_candidates: list[str] = Field(
        min_length=3, description="제목 후보 3개 이상. 첫 번째가 최종 제목"
    )
    description: str = Field(description="검색·OG용 1~2문장 요약")
    sections: list[Section] = Field(description="H2 섹션 4~6개")
    tags: list[str] = Field(description="영문 소문자-하이픈 태그 2~5개 (예: claude-code)")
