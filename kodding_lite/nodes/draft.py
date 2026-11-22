"""draft 노드 — plan의 섹션 구조를 따라 마크다운 본문을 쓴다."""

from __future__ import annotations

from datetime import datetime, timezone

from langchain_core.messages import HumanMessage

from kodding_lite import llm, models
from kodding_lite.schemas import Plan, Ticket

NODE = "draft"


def _user_message(ticket: Ticket, plan: Plan) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m")
    return (
        f"주제: {ticket.topic}\n"
        f"콘텐츠 형식: {ticket.category}\n"
        f"제목(확정): {plan.title_candidates[0]}\n"
        f"현재 작성 시점: {now}\n"
        "목표 분량: 3,000~6,000자 (공백 포함, 코드 블록 제외)\n"
        "\n개요:\n" + plan.model_dump_json(indent=2)
    )


def run(state: dict, *, model=None) -> dict:
    ticket: Ticket = state["ticket"]
    plan: Plan = state["plan"]
    model = model or models.get_model(NODE)
    messages = [
        llm.system_message(NODE, llm.load_prompt(NODE)),
        HumanMessage(_user_message(ticket, plan)),
    ]
    with models.track_tokens(state["run_id"], NODE) as cb:
        body = llm.text_invoke(model, messages, callbacks=[cb])
    if not body.strip():
        raise ValueError("draft 노드가 빈 본문을 반환했습니다")
    return {"draft_md": body}
