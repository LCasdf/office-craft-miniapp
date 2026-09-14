"""PPT outline schema — pages with title + bullets."""

from __future__ import annotations

from typing import Any

PAGE_COUNT_MIN = 5
PAGE_COUNT_MAX = 15
TEMPLATE_BASIC = "tpl_basic_01"
ALLOWED_TEMPLATES = frozenset({TEMPLATE_BASIC})


class OutlineSchemaError(ValueError):
    """Invalid outline / pages."""


def validate_page_count(n: int) -> int:
    try:
        n = int(n)
    except (TypeError, ValueError) as e:
        raise OutlineSchemaError("pageCount invalid") from e
    if n < PAGE_COUNT_MIN or n > PAGE_COUNT_MAX:
        raise OutlineSchemaError(f"pageCount must be {PAGE_COUNT_MIN}-{PAGE_COUNT_MAX}")
    return n


def validate_template_id(template_id: str) -> str:
    tid = (template_id or "").strip()
    if tid not in ALLOWED_TEMPLATES:
        raise OutlineSchemaError("unsupported templateId")
    return tid


def normalize_pages(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise OutlineSchemaError("pages required")
    n = len(raw)
    if n < PAGE_COUNT_MIN or n > PAGE_COUNT_MAX:
        raise OutlineSchemaError(f"pages length must be {PAGE_COUNT_MIN}-{PAGE_COUNT_MAX}")
    pages: list[dict[str, Any]] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            raise OutlineSchemaError(f"page {i} invalid")
        title = str(item.get("title") or "").strip()[:80] or f"第{i + 1}页"
        bullets_raw = item.get("bullets") or []
        if isinstance(bullets_raw, str):
            bullets_raw = [bullets_raw]
        if not isinstance(bullets_raw, list):
            raise OutlineSchemaError(f"page {i} bullets invalid")
        bullets = [str(b).strip()[:120] for b in bullets_raw if str(b).strip()][:8]
        if not bullets:
            bullets = ["（待补充要点）"]
        pages.append({"title": title, "bullets": bullets})
    return pages


def mock_outline_pages(topic: str, page_count: int) -> list[dict[str, Any]]:
    """Deterministic mock outline for AI_PROVIDER=mock."""
    topic = (topic or "未命名主题").strip()[:80] or "未命名主题"
    n = validate_page_count(page_count)
    sections = [
        ("封面", [topic, "Office Craft 自动大纲"]),
        ("目录", ["背景", "目标", "方案", "节奏", "总结"][: max(3, min(5, n - 2))]),
        ("背景与动机", [f"围绕「{topic}」的现状", "痛点与机会"]),
        ("目标", ["短期可交付", "中期可扩展", "成功指标"]),
        ("方案概览", ["核心路径", "关键能力", "风险预案"]),
        ("关键步骤", ["准备", "执行", "验收"]),
        ("资源与节奏", ["人力", "时间盒", "里程碑"]),
        ("风险与应对", ["依赖风险", "质量风险", "回退方案"]),
        ("案例 / 演示", ["场景 A", "场景 B"]),
        ("数据与度量", ["过程指标", "结果指标"]),
        ("下一步行动", ["本周", "下周", "负责人"]),
        ("Q&A 预备", ["常见问题", "答疑口径"]),
        ("附录", ["参考资料", "术语表"]),
        ("总结", ["一句话回顾", "行动呼吁"]),
        ("致谢 / 结束", ["感谢聆听", "联系方式"]),
    ]
    # Always start with cover + toc-ish, then fill to n
    picked = [sections[0], sections[1]]
    for s in sections[2:]:
        if len(picked) >= n:
            break
        picked.append(s)
    while len(picked) < n:
        i = len(picked) + 1
        picked.append((f"扩展页 {i}", [f"{topic} — 要点 {i}", "待编辑"]))
    return [{"title": t, "bullets": list(b)} for t, b in picked[:n]]
