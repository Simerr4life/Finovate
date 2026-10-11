#!/usr/bin/env python3
"""Render Finovate demo title cards to PNG (1920x1080)."""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "source" / "cards"
OUT.mkdir(parents=True, exist_ok=True)

W, H = 1920, 1080
NAVY = (17, 43, 43)
GREEN = (47, 125, 98)
GREEN2 = (63, 149, 116)
CREAM = (245, 246, 242)
GOLD = (210, 164, 77)
INK = (23, 35, 34)
MUTED = (104, 117, 115)
WHITE = (255, 255, 255)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def logo_tile(size: int = 220) -> Image.Image:
    """Paint a simple brand mark matching Finovate green gradient + F-ish mark."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad = int(size * 0.06)
    # Rounded square with vertical-ish green gradient
    for y in range(pad, size - pad):
        t = (y - pad) / max(1, size - 2 * pad)
        r = int(GREEN2[0] + (20 - GREEN2[0]) * t * 0.35)
        g = int(GREEN2[1] + (98 - GREEN2[1]) * t * 0.55)
        b = int(GREEN2[2] + (68 - GREEN2[2]) * t * 0.45)
        draw.line([(pad, y), (size - pad - 1, y)], fill=(r, g, b, 255))
    # Soft corner mask
    mask = Image.new("L", (size, size), 0)
    md = ImageDraw.Draw(mask)
    radius = int(size * 0.22)
    md.rounded_rectangle([pad, pad, size - pad, size - pad], radius=radius, fill=255)
    base = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    base.paste(img, (0, 0), mask)
    # White "F" mark
    d = ImageDraw.Draw(base)
    font = load_font(int(size * 0.55), bold=True)
    text = "F"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((size - tw) / 2 - bbox[0], (size - th) / 2 - bbox[1] - size * 0.03), text, font=font, fill=WHITE)
    return base


def atmosphere(base_rgb=CREAM) -> Image.Image:
    img = Image.new("RGB", (W, H), base_rgb)
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # Soft green wash top-left / gold wash bottom-right
    for i in range(40):
        alpha = int(18 * (1 - i / 40))
        draw.ellipse([-400 + i * 8, -350 + i * 6, 900 - i * 4, 700 - i * 3], fill=(*GREEN, alpha))
    for i in range(35):
        alpha = int(14 * (1 - i / 35))
        draw.ellipse([1100 + i * 5, 500 + i * 4, 2300 - i * 2, 1400 - i * 2], fill=(*GOLD, alpha))
    # Subtle grid dots
    for x in range(60, W, 48):
        for y in range(60, H, 48):
            draw.ellipse([x, y, x + 2, y + 2], fill=(17, 43, 43, 18))
    blurred = overlay.filter(ImageFilter.GaussianBlur(28))
    return Image.alpha_composite(img.convert("RGBA"), blurred).convert("RGB")


def centered_text(draw, text, y, font, fill, max_width=None):
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (W - tw) / 2 - bbox[0]
    draw.text((x, y), text, font=font, fill=fill)
    return bbox[3] - bbox[1]


def wrap_lines(text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    probe = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    for word in words:
        trial = f"{cur} {word}".strip()
        if probe.textbbox((0, 0), trial, font=font)[2] <= max_width:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def save_card(name: str, title: str, subtitle: str = "", eyebrow: str = "", dark: bool = False):
    img = atmosphere(NAVY if dark else CREAM)
    draw = ImageDraw.Draw(img)
    mark = logo_tile(160 if not dark else 180)
    img.paste(mark, ((W - mark.width) // 2, 170 if subtitle else 210), mark)

    ey_font = load_font(28, bold=True)
    title_font = load_font(72 if len(title) < 28 else 58, bold=True)
    sub_font = load_font(34)
    brand_font = load_font(42, bold=True)

    y = 390
    if eyebrow:
        color = GOLD if dark else GREEN
        centered_text(draw, eyebrow.upper(), y, ey_font, color)
        y += 56
    title_color = WHITE if dark else NAVY
    title_lines: list[str] = []
    for chunk in title.split("\n"):
        title_lines.extend(wrap_lines(chunk, title_font, 1500) or [""])
    for line in title_lines:
        centered_text(draw, line, y, title_font, title_color)
        y += 82
    if subtitle:
        y += 12
        sub_color = (196, 210, 204) if dark else MUTED
        for line in wrap_lines(subtitle, sub_font, 1400):
            centered_text(draw, line, y, sub_font, sub_color)
            y += 48

    # Brand wordmark
    brand_y = H - 120
    brand_color = (220, 235, 228) if dark else GREEN
    centered_text(draw, "finovate", brand_y, brand_font, brand_color)

    path = OUT / f"{name}.png"
    img.save(path, "PNG")
    print(f"wrote {path}")


def main():
    save_card(
        "01_intro",
        "See your money clearly.\nPlan it on purpose.",
        "Personal finance clarity — budgets, goals, and simulated investing.",
        "Product demo",
        dark=True,
    )
    save_card(
        "02_first_impressions",
        "First impressions",
        "A calm financial home built around the numbers you enter.",
        "01 · Interface",
    )
    save_card(
        "03_core_walkthrough",
        "Core walkthrough",
        "Track spending, plan budgets, and watch savings progress.",
        "02 · Features",
    )
    save_card(
        "04_differentiators",
        "What sets Finovate apart",
        "Explainable savings plans and clearly labeled simulated investing.",
        "03 · Differentiators",
    )
    save_card(
        "05_journey",
        "A complete user journey",
        "From recorded cash flow to goals, insights, and next steps.",
        "04 · Journey",
    )
    save_card(
        "06_closing",
        "Clarity over complexity.",
        "Track. Budget. Save. Preview investments — all on your own data.",
        "Thank you",
        dark=True,
    )


if __name__ == "__main__":
    main()
