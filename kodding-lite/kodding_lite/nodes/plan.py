"""plan 노드 — 티켓을 받아 제목·요약·섹션 구조·태그를 설계한다 (구조화 출력)."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from kodding_lite import llm, models
from kodding_lite.schemas import Plan, Ticket

NODE = "plan"


def _user_message(ticket: Ticket) -> str:
    return (
        f"주제: {ticket.topic}\n"
        f"콘텐츠 형식: {ticket.category}\n"
        + (f"접근 각도: {ticket.angle}\n" if ticket.angle else "")
        + (f"키워드: {', '.join(ticket.keywords)}\n" if ticket.keywords else "")
    )


def run(state: dict, *, model=None) -> dict:
    ticket: Ticket = state["ticket"]
    model = model or models.get_model(NODE)
    messages = [
        llm.system_message(NODE, llm.load_prompt(NODE)),
        HumanMessage(_user_message(ticket)),
    ]
    with models.track_tokens(state["run_id"], NODE) as cb:
        plan = llm.structured_invoke(model, Plan, messages, callbacks=[cb])
    return {"plan": plan}
