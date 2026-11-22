"""CLI 엔트리.

python -m kodding_lite --topic "Claude Code와 Cursor 비교" --category "비교 리뷰" \
    [--angle "..."] [--keywords claude-code,cursor]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

from dotenv import load_dotenv

from kodding_lite import models
from kodding_lite.schemas import Category, Ticket


def make_run_id() -> str:
    return "run-" + datetime.now(timezone.utc).strftime("%m%d-%H%M%S")


def _missing_keys() -> list[str]:
    """라우팅된 모델 계열에 필요한 API 키 중 비어 있는 것."""
    import os

    needed = set()
    for node in models.ROUTING:
        name = models.model_for(node)
        if name.startswith("gemini"):
            needed.add("GOOGLE_API_KEY")
        elif name.startswith("claude"):
            needed.add("ANTHROPIC_API_KEY")
    return sorted(k for k in needed if not os.environ.get(k, "").strip())


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")  # Windows 콘솔 cp949 대응
    load_dotenv(Path.cwd() / ".env")

    parser = argparse.ArgumentParser(prog="python -m kodding_lite")
    parser.add_argument("--topic", required=True, help="글 주제")
    parser.add_argument("--category", required=True, choices=list(get_args(Category)))
    parser.add_argument("--angle", help="접근 각도 (선택)")
    parser.add_argument("--keywords", help="쉼표 구분 영문 키워드 (선택, slug 소스)")
    args = parser.parse_args(argv)

    missing = _missing_keys()
    if missing:
        print(f"API 키가 없습니다: {', '.join(missing)} — .env에 넣어주세요 (.env.example 참고)")
        return 2

    keywords = [k.strip() for k in (args.keywords or "").split(",") if k.strip()]
    ticket = Ticket.new(
        topic=args.topic, category=args.category, angle=args.angle, keywords=keywords
    )
    run_id = make_run_id()
    print(f"[{run_id}] 시작 — \"{ticket.topic}\" ({ticket.category})")

    from kodding_lite.graph import build_graph  # LLM SDK 임포트를 인자 검증 뒤로

    final = build_graph().invoke({"run_id": run_id, "ticket": ticket})

    totals = models.token_totals(run_id)
    print(f"[{run_id}] 토큰: input {totals['input_tokens']:,} / output {totals['output_tokens']:,}")
    if final.get("error"):
        print(f"[{run_id}] 실패 ({final.get('failed_node')}): {final['error']}")
        return 1
    print(f"[{run_id}] 완료: {final['mdx_path']} (draft: true — 검토 후 false로 바꿔 공개)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
