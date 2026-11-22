"""LangGraph 그래프 — 기획 → 초안 → 발행.

    [plan] → [draft] → [publish] → END
       │        │          │
       └────────┴──────────┴──(예외)──→ [fail_exit] → END

모든 노드를 _guard로 감싸 예외를 state["error"]/["failed_node"]로 바꾸고,
조건부 엣지가 fail_exit로 라우팅한다. 어떤 노드가 실패해도 그래프가
예외로 죽지 않고, 어디서 왜 실패했는지가 최종 state에 남는다.
"""

from __future__ import annotations

import logging
from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph

from kodding_lite.nodes import draft, plan, publish
from kodding_lite.schemas import Plan, Ticket

logger = logging.getLogger(__name__)


class PipelineState(TypedDict, total=False):
    run_id: str
    ticket: Ticket
    plan: Plan | None
    draft_md: str | None
    slug: str | None
    mdx_path: str | None
    error: str | None
    failed_node: str | None


def _guard(node_name: str, fn: Callable[[PipelineState], dict]) -> Callable:
    def wrapped(state: PipelineState) -> dict:
        try:
            return fn(state)
        except Exception as exc:
            logger.exception("%s 노드 실패", node_name)
            return {"error": str(exc) or type(exc).__name__, "failed_node": node_name}

    wrapped.__name__ = node_name
    return wrapped


def _route(next_node: str) -> Callable[[PipelineState], str]:
    return lambda state: "fail_exit" if state.get("error") else next_node


def _fail_exit(state: PipelineState) -> dict:
    logger.error("파이프라인 실패 (%s): %s", state.get("failed_node"), state.get("error"))
    return {}


def build_graph(*, plan_model=None, draft_model=None):
    """모델을 주입하면 테스트에서 실제 API 없이 그래프 전체를 돌릴 수 있다."""
    g = StateGraph(PipelineState)
    g.add_node("plan", _guard("plan", lambda s: plan.run(s, model=plan_model)))
    g.add_node("draft", _guard("draft", lambda s: draft.run(s, model=draft_model)))
    g.add_node("publish", _guard("publish", publish.run))
    g.add_node("fail_exit", _fail_exit)

    g.add_edge(START, "plan")
    g.add_conditional_edges("plan", _route("draft"), {"draft": "draft", "fail_exit": "fail_exit"})
    g.add_conditional_edges(
        "draft", _route("publish"), {"publish": "publish", "fail_exit": "fail_exit"}
    )
    g.add_conditional_edges("publish", _route(END), {END: END, "fail_exit": "fail_exit"})
    g.add_edge("fail_exit", END)
    return g.compile()
