"""publish 노드 — 본문을 MDX로 변환해 출력 폴더에 쓴다.

lite 버전은 git 커밋·배포를 하지 않는다. OUTPUT_DIR(기본 ./output/posts)에
프론트매터가 붙은 .mdx 파일을 만들 뿐이다. 이 파일을 Next.js·Astro 등
MDX 블로그의 content 폴더에 두면 그대로 글이 된다.
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

from kodding_lite.schemas import Plan, Ticket

NODE = "publish"

_LEADING_H1 = re.compile(r"^\s*#\s[^\n]*\n+")
_HTML_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)


def output_dir() -> Path:
    return Path(os.environ.get("OUTPUT_DIR", "output/posts"))


def sanitize_slug(text: str) -> str:
    """영문 소문자-하이픈만 남긴다. 만들 수 없으면 ValueError."""
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    if not s:
        raise ValueError(f"영문 소문자-하이픈 slug를 만들 수 없습니다: {text!r}")
    return s


def unique_slug(slug: str) -> str:
    """같은 slug가 있으면 -2, -3… 접미사. 덮어쓰기 금지."""
    d = output_dir()
    if not (d / f"{slug}.mdx").exists():
        return slug
    n = 2
    while (d / f"{slug}-{n}.mdx").exists():
        n += 1
    return f"{slug}-{n}"


def to_mdx_body(body_md: str) -> str:
    """선두 H1 제거(제목은 프론트매터 담당) + HTML 주석을 MDX 주석으로 변환.

    `<!-- ... -->`는 MDX 문법 위반이라 빌드가 깨진다. 모델이 지침을 어겨도
    여기서 보증한다.
    """
    md = _LEADING_H1.sub("", body_md, count=1)
    return _HTML_COMMENT.sub(lambda m: "{/*" + m.group(1) + "*/}", md)


def _yaml_str(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_frontmatter(
    title: str, description: str, category: str, tags: list[str], post_date: date
) -> str:
    # 태그는 LLM 출력이라 한글이 섞일 수 있다. 영문화 불가능한 태그만 건너뛴다.
    clean = []
    for t in tags:
        try:
            clean.append(sanitize_slug(t))
        except ValueError:
            continue
    return (
        "---\n"
        f"title: {_yaml_str(title)}\n"
        f"description: {_yaml_str(description)}\n"
        f"date: {post_date.isoformat()}\n"
        f"category: {_yaml_str(category)}\n"
        f"tags: [{', '.join(clean)}]\n"
        "draft: true\n"
        "---\n"
    )


def run(state: dict) -> dict:
    plan: Plan = state["plan"]
    ticket: Ticket = state["ticket"]
    slug = unique_slug(sanitize_slug("-".join(plan.tags or ticket.keywords)))
    content = (
        build_frontmatter(
            title=plan.title_candidates[0],
            description=plan.description,
            category=ticket.category,
            tags=plan.tags,
            post_date=date.today(),
        )
        + "\n"
        + to_mdx_body(state["draft_md"]).rstrip()
        + "\n"
    )
    d = output_dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{slug}.mdx"
    path.write_text(content, encoding="utf-8")
    return {"slug": slug, "mdx_path": str(path)}
