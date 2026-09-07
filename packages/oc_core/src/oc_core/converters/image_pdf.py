"""Pure converters — no FastAPI/Celery."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def images_to_pdf(
    image_paths: list[Path],
    dest: Path,
    *,
    orientation: str = "auto",
) -> None:
    """Merge images into one PDF. orientation: auto | portrait."""
    if not image_paths:
        raise ValueError("no images")
    pages: list[Image.Image] = []
    try:
        for p in image_paths:
            if p.suffix.lower() not in _IMAGE_EXTS:
                raise ValueError(f"unsupported image type: {p.name}")
            img = Image.open(p)
            img.load()
            if orientation == "portrait" and img.width > img.height:
                img = img.transpose(Image.Transpose.ROTATE_90)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            elif img.mode == "L":
                img = img.convert("RGB")
            pages.append(img)
        first, rest = pages[0], pages[1:]
        first.save(dest, "PDF", save_all=True, append_images=rest, resolution=100.0)
    finally:
        for img in pages:
            img.close()
