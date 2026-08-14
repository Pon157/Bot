from __future__ import annotations

import io
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
CARD_SIZE = (1000, 560)

# Мягкая "рассветная" палитра под название бота
BG_TOP = (28, 24, 48)
BG_BOTTOM = (255, 149, 114)
ACCENT = (255, 205, 130)
TEXT_MAIN = (255, 255, 255)
TEXT_SECONDARY = (235, 225, 235)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    Пытаемся использовать DejaVuSans (кириллица есть, обычно уже стоит в системе
    вместе с Pillow). Если шрифта нет — fallback на встроенный битмап-шрифт Pillow
    (тогда карточка отрисуется, но менее красиво — стоит положить .ttf в bot/assets/fonts).
    """
    candidates = [
        ASSETS_DIR / "fonts" / ("Inter-Bold.ttf" if bold else "Inter-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _gradient_background(size: tuple[int, int]) -> Image.Image:
    """
    Диагональный градиент (а не банальный вертикальный) + мягкое радиальное
    свечение в верхнем левом углу — чтобы карточка не выглядела как плоская
    закраска "цвет сверху, цвет снизу".
    """
    w, h = size
    base = Image.new("RGB", size, BG_TOP)
    px = base.load()
    diag = w + h
    for y in range(h):
        for x in range(0, w, 2):  # шаг 2px по x — картинка небольшая, а быстрее в 2 раза
            t = (x + y) / diag
            r = int(BG_TOP[0] + (BG_BOTTOM[0] - BG_TOP[0]) * t)
            g = int(BG_TOP[1] + (BG_BOTTOM[1] - BG_TOP[1]) * t)
            b = int(BG_TOP[2] + (BG_BOTTOM[2] - BG_TOP[2]) * t)
            px[x, y] = (r, g, b)
            if x + 1 < w:
                px[x + 1, y] = (r, g, b)

    # мягкое свечение — большое размытое пятно акцентного цвета в углу
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.ellipse([-260, -260, 420, 420], fill=ACCENT + (90,))
    glow = glow.filter(ImageFilter.GaussianBlur(140))
    base = Image.alpha_composite(base.convert("RGBA"), glow).convert("RGB")
    return base


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([0, 0, size[0], size[1]], radius=radius, fill=255)
    return mask


async def render_profile_card(
    *,
    nickname: str,
    about: str,
    hobbies: str,
    avatar_bytes: bytes | None,
    stats_lines: list[str],
) -> bytes:
    """Возвращает PNG-байты карточки профиля пользователя."""
    card = _gradient_background(CARD_SIZE).convert("RGB")
    card = card.filter(ImageFilter.GaussianBlur(0.5))
    draw = ImageDraw.Draw(card)

    # мягкое затемнение снизу для читаемости текста
    overlay = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    odraw.rectangle([0, 340, CARD_SIZE[0], CARD_SIZE[1]], fill=(15, 10, 25, 140))
    card = Image.alpha_composite(card.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(card)

    # аватар
    avatar_size = 220
    avatar_pos = (40, 40)
    if avatar_bytes:
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        avatar = avatar.resize((avatar_size, avatar_size))
    else:
        avatar = Image.new("RGBA", (avatar_size, avatar_size), ACCENT + (255,))
        adraw = ImageDraw.Draw(avatar)
        initial = (nickname or "?")[0].upper()
        f = _font(96, bold=True)
        bbox = adraw.textbbox((0, 0), initial, font=f)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        adraw.text(
            ((avatar_size - tw) / 2 - bbox[0], (avatar_size - th) / 2 - bbox[1]),
            initial,
            font=f,
            fill=(40, 20, 20, 255),
        )

    circle_mask = Image.new("L", (avatar_size, avatar_size), 0)
    ImageDraw.Draw(circle_mask).ellipse([0, 0, avatar_size, avatar_size], fill=255)
    # тонкая рамка-акцент вокруг аватара
    ring = Image.new("RGBA", (avatar_size + 12, avatar_size + 12), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse([0, 0, avatar_size + 12, avatar_size + 12], outline=ACCENT + (255,), width=4)
    card.paste(ring, (avatar_pos[0] - 6, avatar_pos[1] - 6), ring)
    card.paste(avatar, avatar_pos, circle_mask)

    # никнейм
    name_font = _font(46, bold=True)
    draw.text((300, 60), nickname, font=name_font, fill=TEXT_MAIN)

    # статистика (короткие плашки справа от аватара)
    stat_font = _font(24)
    stat_y = 130
    for line in stats_lines:
        draw.text((300, stat_y), f"• {line}", font=stat_font, fill=ACCENT)
        stat_y += 34

    # блок "о себе"
    body_font = _font(24)
    label_font = _font(22, bold=True)
    y = 300
    draw.text((40, y), "О себе", font=label_font, fill=ACCENT)
    y += 32
    wrapped_about = textwrap.wrap(about, width=95)[:3]
    for line in wrapped_about:
        draw.text((40, y), line, font=body_font, fill=TEXT_SECONDARY)
        y += 30

    y += 14
    draw.text((40, y), "Хобби и интересы", font=label_font, fill=ACCENT)
    y += 32
    wrapped_hobbies = textwrap.wrap(hobbies, width=95)[:3]
    for line in wrapped_hobbies:
        draw.text((40, y), line, font=body_font, fill=TEXT_SECONDARY)
        y += 30

    # скругление углов всей карточки
    mask = _rounded_mask(CARD_SIZE, radius=28)
    rounded = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    rounded.paste(card, (0, 0), mask)

    buf = io.BytesIO()
    rounded.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()

