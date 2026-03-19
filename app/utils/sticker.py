from __future__ import annotations

import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RARITY_COLORS = {
    "common": (70, 70, 70),
    "rare": (30, 90, 180),
    "mythic": (180, 80, 20),
    "legendary": (190, 150, 30),
    "limited": (140, 40, 120),
}


def build_card_image(title: str, rarity: str, description: str, caption: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    bg = RARITY_COLORS.get(rarity, (60, 60, 60))
    img = Image.new("RGB", (900, 900), color=bg)
    draw = ImageDraw.Draw(img)
    title_font = ImageFont.load_default()
    body_font = ImageFont.load_default()

    draw.rectangle((30, 30, 870, 870), outline=(240, 240, 240), width=4)
    draw.text((60, 70), f"{title} [{rarity}]", fill=(255, 255, 255), font=title_font)

    y = 140
    for line in textwrap.wrap(description or "No description", width=58):
        draw.text((60, y), line, fill=(240, 240, 240), font=body_font)
        y += 22

    y = max(y + 40, 620)
    draw.text((60, y), "Quote:", fill=(255, 230, 160), font=body_font)
    y += 30
    for line in textwrap.wrap(caption or "No caption", width=58):
        draw.text((60, y), line, fill=(255, 255, 255), font=body_font)
        y += 22

    out_file = out_dir / "card_preview.png"
    img.save(out_file, format="PNG")
    return out_file
