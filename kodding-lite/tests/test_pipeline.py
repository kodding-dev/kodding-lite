from datetime import date

import pytest
from tenacity import wait_none

from kodding_lite import llm
from kodding_lite.graph import build_graph
from kodding_lite.nodes import publish
from kodding_lite.schemas import Plan, Section, Ticket
from tests.fakes import Fake429, FakeChat


@pytest.fixture(autouse=True)
def _isolate(tmp_path, monkeypatch):
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path / "posts"))
    monkeypatch.setattr(llm, "RETRY_WAIT", wait_none())
    for k in ("MODEL_PLAN", "MODEL_DRAFT"):
        monkeypatch.delenv(k, raising=False)


def _plan(tags=("claude-code", "cursor")) -> Plan:
    return Plan(
        title_candidates=["Claude Code vs Cursor", "후보 2", "후보 3"],
        description="두 도구를 실무 기준으로 비교합니다.",
        sections=[Section(heading="이 글에서 얻을 것", points=["a", "b"])],
        tags=list(tags),
    )


def _ticket() -> Ticket:
    return Ticket.new(topic="Claude Code와 Cursor 비교", category="비교 리뷰")


BODY = "# 지워질 H1\n\n## 이 글에서 얻을 것\n\n본문입니다.\n\n<!-- screenshot: 설정 화면 -->\n"


def test_graph_end_to_end_writes_mdx(tmp_path):
    graph = build_graph(plan_model=FakeChat([_plan()]), draft_model=FakeChat([BODY]))
    final = graph.invoke({"run_id": "t1", "ticket": _ticket()})

    assert not final.get("error")
    assert final["slug"] == "claude-code-cursor"
    text = (tmp_path / "posts" / "claude-code-cursor.mdx").read_text(encoding="utf-8")
    assert text.startswith("---\ntitle: \"Claude Code vs Cursor\"")
    assert "draft: true" in text
    assert "지워질 H1" not in text          # 선두 H1 제거
    assert "{/* screenshot: 설정 화면 */}" in text  # HTML 주석 → MDX 주석
    assert "<!--" not in text


def test_failure_routes_to_fail_exit_without_writing(tmp_path):
    graph = build_graph(
        plan_model=FakeChat([_plan()]), draft_model=FakeChat([ValueError("boom")])
    )
    final = graph.invoke({"run_id": "t2", "ticket": _ticket()})

    assert final["failed_node"] == "draft"
    assert "boom" in final["error"]
    assert not (tmp_path / "posts").exists()


def test_empty_draft_is_a_failure():
    graph = build_graph(plan_model=FakeChat([_plan()]), draft_model=FakeChat(["   "]))
    final = graph.invoke({"run_id": "t3", "ticket": _ticket()})
    assert final["failed_node"] == "draft"


def test_retry_on_429_then_success():
    graph = build_graph(
        plan_model=FakeChat([Fake429(), _plan()]), draft_model=FakeChat([BODY])
    )
    final = graph.invoke({"run_id": "t4", "ticket": _ticket()})
    assert not final.get("error")


def test_structured_output_reasks_once_on_empty():
    model = FakeChat([None, _plan()])
    graph = build_graph(plan_model=model, draft_model=FakeChat([BODY]))
    final = graph.invoke({"run_id": "t5", "ticket": _ticket()})
    assert not final.get("error")
    assert len(model.calls) == 2  # 1회 재요청


def test_slug_collision_gets_suffix(tmp_path):
    for expected in ("claude-code-cursor", "claude-code-cursor-2"):
        graph = build_graph(plan_model=FakeChat([_plan()]), draft_model=FakeChat([BODY]))
        assert graph.invoke({"run_id": "t6", "ticket": _ticket()})["slug"] == expected


def test_korean_only_tags_fail_cleanly():
    graph = build_graph(
        plan_model=FakeChat([_plan(tags=("비교-리뷰",))]), draft_model=FakeChat([BODY])
    )
    final = graph.invoke({"run_id": "t7", "ticket": _ticket()})
    assert final["failed_node"] == "publish"


def test_frontmatter_skips_non_english_tags_and_escapes_quotes():
    fm = publish.build_frontmatter(
        title='따옴표 "포함" 제목', description="d", category="비교 리뷰",
        tags=["claude-code", "비교"], post_date=date(2026, 11, 22),
    )
    assert 'title: "따옴표 \\"포함\\" 제목"' in fm
    assert "tags: [claude-code]" in fm


def test_charter_is_injected_into_system_prompt():
    model = FakeChat([_plan()])
    build_graph(plan_model=model, draft_model=FakeChat([BODY])).invoke(
        {"run_id": "t8", "ticket": _ticket()}
    )
    system = model.calls[0][0].content
    assert "정관" in system
