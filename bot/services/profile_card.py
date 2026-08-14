from __future__ import annotations

import io
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
CARD_SIZE = (1000, 560)

# Цветовая палитра в стиле Modern Dark Glassmorphism
BG_DARK_1 = (13, 17, 28)       # Глубокий тёмно-синий
BG_DARK_2 = (22, 28, 46)       # Индиго-сланец
ACCENT_PRIMARY = (129, 140, 248) # Неоновый фиолетовый / Индиго
ACCENT_CYAN = (56, 189, 248)    # Неоновый голубой
TEXT_MAIN = (255, 255, 255)
TEXT_MUTED = (148, 163, 184)   # Мягкий серый для описания
TEXT_ACCENT = (199, 210, 254)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        ASSETS_DIR / "fonts" / ("Inter-Bold.ttf" if bold else "Inter-Regular.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _fast_gradient_background(size: tuple[int, int]) -> Image.Image:
    """Быстрый стильный градиент с двухцветным неоновым свечением."""
    # Мгновенная генерация базового градиента через resize
    base = Image.new("RGB", (1, 2))
    base.putpixel((0, 0), BG_DARK_1)
    base.putpixel((0, 1), BG_DARK_2)
    bg = base.resize(size, Image.Resampling.BICUBIC).convert("RGBA")

    # Мягкое объемное неоновое свечение в углах
    glows = Image.new("RGBA", size, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glows)

    # Свечение 1: Фиолетовый софит за аватаром
    gdraw.ellipse([-80, -80, 420, 420], fill=ACCENT_PRIMARY + (55,))
    # Свечение 2: Бирюзовый софит в правом верхнем углу
    gdraw.ellipse([600, -120, 1100, 380], fill=ACCENT_CYAN + (35,))

    glows = glows.filter(ImageFilter.GaussianBlur(90))
    return Image.alpha_composite(bg, glows)


def _rounded_mask(size: tuple[int, int], radius: int) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size[0], size[1]], radius=radius, fill=255)
    return mask


async def render_profile_card(
    *,
    nickname: str,
    about: str,
    hobbies: str,
    avatar_bytes: bytes | None,
    stats_lines: list[str],
) -> bytes:
    """Возвращает PNG-байты современной премиальной карточки профиля."""
    # 1. Фон
    card = _fast_gradient_background(CARD_SIZE)
    overlay = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    # 2. Отрисовка аватара
    avatar_size = 160
    avatar_pos = (50, 45)

    if avatar_bytes:
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        avatar = avatar.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
    else:
        # Резервный аватар с градиентом
        avatar = Image.new("RGBA", (avatar_size, avatar_size), ACCENT_PRIMARY + (255,))
        adraw = ImageDraw.Draw(avatar)
        initial = (nickname or "?")[0].upper()
        f = _font(80, bold=True)
        bbox = adraw.textbbox((0, 0), initial, font=f)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        adraw.text(
            ((avatar_size - tw) / 2 - bbox[0], (avatar_size - th) / 2 - bbox[1]),
            initial,
            font=f,
            fill=(15, 17, 28, 255),
        )

    # Скругление аватара
    circle_mask = Image.new("L", (avatar_size, avatar_size), 0)
    ImageDraw.Draw(circle_mask).ellipse([0, 0, avatar_size, avatar_size], fill=255)

    # Неоновый ободок вокруг аватара
    ring_size = avatar_size + 12
    ring = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse(
        [0, 0, ring_size, ring_size],
        outline=ACCENT_PRIMARY + (220,),
        width=3,
    )
    card.paste(ring, (avatar_pos[0] - 6, avatar_pos[1] - 6), ring)
    card.paste(avatar, avatar_pos, circle_mask)

    # 3. Никнейм
    name_font = _font(40, bold=True)
    odraw.text((240, 48), nickname, font=name_font, fill=TEXT_MAIN)

    # 4. Статистика (в виде стильных бейджей/капсул)
    stat_font = _font(17, bold=True)
    sx, sy = 240, 115
    for stat in stats_lines:
        bbox = odraw.textbbox((0, 0), stat, font=stat_font)
        tw = bbox[2] - bbox[0]
        badge_w, badge_h = tw + 24, 34

        if sx + badge_w > 950:
            sx = 240
            sy += 42

        # Капсула статистики
        odraw.rounded_rectangle(
            [sx, sy, sx + badge_w, sy + badge_h],
            radius=17,
            fill=(255, 255, 255, 12),
            outline=ACCENT_PRIMARY + (80,),
            width=1,
        )
        odraw.text((sx + 12, sy + 7), stat, font=stat_font, fill=TEXT_ACCENT)
        sx += badge_w + 10

    # 5. Матовые стеклянные карточки для «О себе» и «Хобби»
    card_y = 220
    card_h = 290
    card_w = 435

    # Функция отрисовки секции-контейнера
    def _draw_glass_card(x: int, title: str, text: str, accent_color: tuple[int, int, int]):
        # Стекло-фон
        odraw.rounded_rectangle(
            [x, card_y, x + card_w, card_y + card_h],
            radius=20,
            fill=(255, 255, 255, 10),
            outline=(255, 255, 255, 25),
            width=1,
        )
        # Цветовой индикатор перед заголовком
        odraw.rounded_rectangle(
            [x + 20, card_y + 22, x + 25, card_y + 42],
            radius=3,
            fill=accent_color,
        )
        # Заголовок секции
        label_font = _font(20, bold=True)
        odraw.text((x + 36, card_y + 20), title, font=label_font, fill=TEXT_MAIN)

        # Текст с переносом
        body_font = _font(18)
        content_y = card_y + 62
        lines = []
        for raw_line in (text or "Не указано").split("\n"):
            lines.extend(textwrap.wrap(raw_line, width=34))

        for line in lines[:7]:  # Максимум 7 строк, чтобы не вылезало
            odraw.text((x + 20, content_y), line, font=body_font, fill=TEXT_MUTED)
            content_y += 28

    # Левая карточка: "О себе"
    _draw_glass_card(50, "О себе", about, ACCENT_PRIMARY)

    # Правая карточка: "Хобби и интересы"
    _draw_glass_card(515, "Хобби и интересы", hobbies, ACCENT_CYAN)

    # 6. Финальное объединение и скругление всей основной карточки
    final_card = Image.alpha_composite(card, overlay)
    mask = _rounded_mask(CARD_SIZE, radius=28)

    output = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    output.paste(final_card, (0, 0), mask)

    buf = io.BytesIO()
    output.convert("RGB").save(buf, format="PNG", quality=95)
    return buf.getvalue()
