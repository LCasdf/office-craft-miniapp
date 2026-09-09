"""Text → character portrait image (mock now; real image API later)."""

from __future__ import annotations

import hashlib
import io
from typing import Any

from PIL import Image, ImageDraw, ImageFont


def _font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _palette(seed: str) -> tuple[tuple[int, int, int], ...]:
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()
    colors = []
    for i in range(0, 12, 2):
        colors.append(
            (
                40 + int(h[i : i + 2], 16) % 180,
                40 + int(h[i + 2 : i + 4], 16) % 160,
                50 + int(h[i + 4 : i + 6], 16) % 180,
            )
        )
    return tuple(colors)  # type: ignore[return-value]


def _keyword_mood(prompt: str) -> str:
    p = prompt or ""
    if any(k in p for k in ("山", "林", "草", "药", "隐")):
        return "forest"
    if any(k in p for k in ("海", "雨", "江", "湖", "夜")):
        return "night"
    if any(k in p for k in ("火", "战", "剑", "魔")):
        return "ember"
    if any(k in p for k in ("仙", "云", "天", "清")):
        return "cloud"
    return "plain"


def generate_character_portrait_png(
    prompt: str,
    *,
    name: str = "",
    title: str = "",
    size: tuple[int, int] = (768, 1024),
) -> bytes:
    """
    Mock 文生图：按文字描述生成风格化角色立绘（非真实大模型）。
    真模型：换 build_image_client 即可，契约仍返回 PNG bytes。
    """
    w, h = size
    seed = f"{name}|{title}|{prompt}"
    pal = _palette(seed)
    mood = _keyword_mood(prompt)
    bg = {
        "forest": (28, 48, 36),
        "night": (18, 24, 48),
        "ember": (48, 22, 18),
        "cloud": (60, 78, 98),
        "plain": (32, 36, 48),
    }[mood]

    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)

    # atmosphere gradients / orbs
    for i, c in enumerate(pal[:4]):
        cx = int(w * (0.2 + 0.2 * i))
        cy = int(h * (0.15 + 0.08 * (i % 3)))
        r = 80 + (i * 40)
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*c, 55))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        draw = ImageDraw.Draw(img)

    # ground
    draw.ellipse([int(w * 0.1), int(h * 0.72), int(w * 0.9), int(h * 1.05)], fill=pal[1])

    # body silhouette
    body_c = pal[2]
    head_r = int(w * 0.14)
    hx, hy = w // 2, int(h * 0.32)
    draw.ellipse([hx - head_r, hy - head_r, hx + head_r, hy + head_r], fill=body_c)

    # shoulders / torso
    shoulder_w = int(w * 0.42)
    draw.polygon(
        [
            (hx - shoulder_w, int(h * 0.78)),
            (hx + shoulder_w, int(h * 0.78)),
            (hx + int(shoulder_w * 0.55), int(h * 0.42)),
            (hx - int(shoulder_w * 0.55), int(h * 0.42)),
        ],
        fill=body_c,
    )

    # face hint
    face = tuple(min(255, x + 50) for x in body_c)
    fr = int(head_r * 0.55)
    draw.ellipse([hx - fr, hy - fr + 8, hx + fr, hy + fr + 8], fill=face)
    eye_y = hy - 4
    draw.ellipse([hx - 22, eye_y - 6, hx - 8, eye_y + 6], fill=(30, 30, 35))
    draw.ellipse([hx + 8, eye_y - 6, hx + 22, eye_y + 6], fill=(30, 30, 35))

    # hair / hood accent from mood
    accent = pal[0]
    if mood in ("forest", "cloud"):
        draw.arc(
            [hx - head_r - 8, hy - head_r - 20, hx + head_r + 8, hy + 10],
            start=200,
            end=340,
            fill=accent,
            width=18,
        )
    else:
        draw.chord(
            [hx - head_r - 4, hy - head_r - 16, hx + head_r + 4, hy],
            start=180,
            end=0,
            fill=accent,
        )

    # decorative ring
    draw.ellipse(
        [hx - head_r - 28, hy - head_r - 28, hx + head_r + 28, hy + head_r + 28],
        outline=pal[3],
        width=3,
    )

    # vignette-ish border
    draw.rectangle([18, 18, w - 18, h - 18], outline=pal[3], width=2)

    # title block
    name_s = (name or "未命名角色")[:12]
    title_s = (title or "")[:16]
    prompt_s = (prompt or "").replace("\n", " ")[:28]
    draw.rectangle([40, h - 160, w - 40, h - 40], fill=(12, 14, 18))
    draw.text((56, h - 140), name_s, font=_font(42), fill=(245, 240, 230))
    if title_s:
        draw.text((56, h - 90), title_s, font=_font(26), fill=pal[3])
    draw.text((56, h - 58), prompt_s, font=_font(20), fill=(160, 160, 170))

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def build_image_prompt(fields: dict[str, Any]) -> str:
    """Compose image prompt from editor fields."""
    parts = [
        fields.get("name") or "",
        fields.get("title") or "",
        fields.get("avatarDesc") or "",
        fields.get("personality") or "",
        fields.get("prompt") or fields.get("premise") or "",
    ]
    text = "，".join(str(p).strip() for p in parts if str(p).strip())
    return text[:800] or "一位神秘旅人"


class MockImageClient:
    def imagine_character(self, *, prompt: str, name: str = "", title: str = "") -> bytes:
        return generate_character_portrait_png(prompt, name=name, title=title)


def build_image_client(provider: str = "mock") -> MockImageClient:
    # ponytail: real文生图 API 接到此 — OpenAI/通义等，仍返回 PNG bytes
    return MockImageClient()
