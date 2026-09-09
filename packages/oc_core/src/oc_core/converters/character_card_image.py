"""Pillow single-template character card poster (PNG)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def _font(size: int) -> ImageFont.ImageFont:
    # ponytail: default bitmap font — swap to bundled CJK TTF when packaging
    try:
        return ImageFont.truetype("/System/Library/Fonts/PingFang.ttc", size)
    except OSError:
        try:
            return ImageFont.truetype(
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size
            )
        except OSError:
            return ImageFont.load_default()


def _wrap(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_w: int) -> list[str]:
    lines: list[str] = []
    line = ""
    for ch in text or "":
        trial = line + ch
        if draw.textlength(trial, font=font) <= max_w:
            line = trial
        else:
            if line:
                lines.append(line)
            line = ch
    if line:
        lines.append(line)
    return lines or [""]


def render_character_card_png(payload: dict[str, Any], out_path: Path) -> Path:
    """Draw title / name / personality summary onto a fixed 1080×1440 canvas."""
    w, h = 1080, 1440
    img = Image.new("RGB", (w, h), (28, 36, 48))
    draw = ImageDraw.Draw(img)

    # Accent bar
    draw.rectangle([0, 0, w, 16], fill=(232, 168, 90))
    draw.rectangle([48, 120, w - 48, h - 120], outline=(70, 84, 104), width=2)

    title_font = _font(36)
    name_font = _font(72)
    body_font = _font(36)
    small_font = _font(28)

    name = str(payload.get("name") or "未命名角色")
    title = str(payload.get("title") or "")
    summary = str(
        payload.get("story")
        or payload.get("summary")
        or payload.get("avatarDesc")
        or ""
    )
    personality = str(payload.get("personality") or "")
    traits = payload.get("traits") or []
    if not traits:
        for key in ("ability", "weakness"):
            if payload.get(key):
                traits.append(str(payload[key])[:16])
    traits_s = " · ".join(str(t) for t in traits[:6])

    draw.text((80, 160), title or "角色卡", font=title_font, fill=(232, 168, 90))
    draw.text((80, 240), name[:32], font=name_font, fill=(245, 247, 250))

    y = 360
    for line in _wrap(draw, summary, body_font, w - 160)[:4]:
        draw.text((80, y), line, font=body_font, fill=(200, 210, 220))
        y += 48

    y += 40
    draw.text((80, y), "性格", font=title_font, fill=(232, 168, 90))
    y += 56
    for line in _wrap(draw, personality, body_font, w - 160)[:6]:
        draw.text((80, y), line, font=body_font, fill=(220, 226, 232))
        y += 48

    if traits_s:
        y += 32
        draw.text((80, y), "特质", font=title_font, fill=(232, 168, 90))
        y += 56
        for line in _wrap(draw, traits_s, small_font, w - 160)[:3]:
            draw.text((80, y), line, font=small_font, fill=(180, 190, 200))
            y += 40

    draw.text((80, h - 100), "文匠工具", font=small_font, fill=(120, 130, 140))

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, format="PNG", optimize=True)
    return out_path
