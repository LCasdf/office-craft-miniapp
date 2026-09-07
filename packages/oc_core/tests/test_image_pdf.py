from pathlib import Path

from oc_core.converters.image_pdf import images_to_pdf
from PIL import Image


def test_images_to_pdf_writes_pdf(tmp_path: Path):
    imgs = []
    for i, color in enumerate([(255, 0, 0), (0, 128, 255)]):
        p = tmp_path / f"a{i}.png"
        Image.new("RGB", (40, 60), color).save(p)
        imgs.append(p)
    dest = tmp_path / "out.pdf"
    images_to_pdf(imgs, dest, orientation="auto")
    assert dest.is_file()
    assert dest.stat().st_size > 100


def test_images_to_pdf_portrait_rotates(tmp_path: Path):
    p = tmp_path / "wide.png"
    Image.new("RGB", (80, 40), (0, 0, 0)).save(p)
    dest = tmp_path / "out.pdf"
    images_to_pdf([p], dest, orientation="portrait")
    assert dest.is_file()
