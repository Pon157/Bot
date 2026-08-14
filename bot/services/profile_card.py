from __future__ import annotations

import io
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
CARD_SIZE = (1000, 560)

# Огненная/Warm палитра
BG_DARK_1 = (20, 15, 12)          # Глубокий тёмно-угольный
BG_DARK_2 = (35, 24, 18)          # Тёмно-каштановый
ACCENT_ORANGE = (255, 122, 0)     # Насыщенный яркий оранжевый
ACCENT_YELLOW = (255, 190, 40)    # Сочный золотисто-жёлтый
TEXT_MAIN = (255, 255, 255)
TEXT_MUTED = (215, 200, 190)       # Тёплый светлый текст описания
TEXT_ACCENT = (255, 225, 170)


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
    """Быстрый теплый градиент с оранжево-жёлтым свечением."""
    base = Image.new("RGB", (1, 2))
    base.putpixel((0, 0), BG_DARK_1)
    base.putpixel((0, 1), BG_DARK_2)
    bg = base.resize(size, Image.Resampling.BICUBIC).convert("RGBA")

    # Мягкие софиты
    glows = Image.new("RGBA", size, (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glows)

    # Оранжевое свечение за аватаром
    gdraw.ellipse([-80, -80, 420, 420], fill=ACCENT_ORANGE + (60,))
    # Жёлтое свечение в верхнем правом углу
    gdraw.ellipse([600, -120, 1100, 380], fill=ACCENT_YELLOW + (40,))

    glows = glows.filter(ImageFilter.GaussianBlur(90))
    return Image.alpha_composite(bg, glows)


async def render_profile_card(
    *,
    nickname: str,
    about: str,
    hobbies: str,
    avatar_bytes: bytes | None,
    stats_lines: list[str],
) -> bytes:
    """Возвращает PNG-байты карточки профиля в оранжево-жёлтых тонах без скругления углов."""
    # 1. Фон (прямоугольный)
    card = _fast_gradient_background(CARD_SIZE)
    overlay = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    # 2. Аватар
    avatar_size = 160
    avatar_pos = (50, 45)

    if avatar_bytes:
        avatar = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        avatar = avatar.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
    else:
        avatar = Image.new("RGBA", (avatar_size, avatar_size), ACCENT_ORANGE + (255,))
        adraw = ImageDraw.Draw(avatar)
        initial = (nickname or "?")[0].upper()
        f = _font(80, bold=True)
        bbox = adraw.textbbox((0, 0), initial, font=f)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        adraw.text(
            ((avatar_size - tw) / 2 - bbox[0], (avatar_size - th) / 2 - bbox[1]),
            initial,
            font=f,
            fill=(20, 15, 12, 255),
        )

    # Скругление самого аватара в круг
    circle_mask = Image.new("L", (avatar_size, avatar_size), 0)
    ImageDraw.Draw(circle_mask).ellipse([0, 0, avatar_size, avatar_size], fill=255)

    # Оранжевое кольцо вокруг аватара
    ring_size = avatar_size + 12
    ring = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
    ImageDraw.Draw(ring).ellipse(
        [0, 0, ring_size, ring_size],
        outline=ACCENT_ORANGE + (230,),
        width=3,
    )
    card.paste(ring, (avatar_pos[0] - 6, avatar_pos[1] - 6), ring)
    card.paste(avatar, avatar_pos, circle_mask)

    # 3. Никнейм
    name_font = _font(40, bold=True)
    odraw.text((240, 48), nickname, font=name_font, fill=TEXT_MAIN)

    # 4. Статистика (бейдж-капсулы)
    stat_font = _font(17, bold=True)
    sx, sy = 240, 115
    for stat in stats_lines:
        bbox = odraw.textbbox((0, 0), stat, font=stat_font)
        tw = bbox[2] - bbox[0]
        badge_w, badge_h = tw + 24, 34

        if sx + badge_w > 950:
            sx = 240
            sy += 42

        odraw.rounded_rectangle(
            [sx, sy, sx + badge_w, sy + badge_h],
            radius=17,
            fill=(255, 255, 255, 12),
            outline=ACCENT_YELLOW + (90,),
            width=1,
        )
        odraw.text((sx + 12, sy + 7), stat, font=stat_font, fill=TEXT_ACCENT)
        sx += badge_w + 10

    # 5. Матовые блоки «О себе» и «Хобби»
    card_y = 220
    card_h = 290
    card_w = 435

    def _draw_glass_card(
        x: int,
        title: str,
        text: str,
        accent_color: tuple[int, int, int],
        max_chars: int = 110,  # Жёсткий лимит символов
    ):
        # Отрисовка контейнера
        odraw.rounded_rectangle(
            [x, card_y, x + card_w, card_y + card_h],
            radius=18,
            fill=(255, 255, 255, 10),
            outline=(255, 255, 255, 25),
            width=1,
        )
        # Вертикальная цветная плашка слева от заголовка
        odraw.rounded_rectangle(
            [x + 20, card_y + 22, x + 25, card_y + 42],
            radius=3,
            fill=accent_color,
        )
        label_font = _font(20, bold=True)
        odraw.text((x + 36, card_y + 20), title, font=label_font, fill=TEXT_MAIN)

        # Подготовка текста и обрезом по max_chars
        clean_text = (text or "Не указано").strip()
        if len(clean_text) > max_chars:
            clean_text = clean_text[: max_chars - 3].rstrip() + "..."

        body_font = _font(18)
        content_y = card_y + 62
        lines = []
        for raw_line in clean_text.split("\n"):
            lines.extend(textwrap.wrap(raw_line, width=34))

        # Вывод максимум 6 строк
        for line in lines[:6]:
            odraw.text((x + 20, content_y), line, font=body_font, fill=TEXT_MUTED)
            content_y += 28

    # Левая карточка: "О себе" (Оранжевый акцент)
    _draw_glass_card(50, "О себе", about, ACCENT_ORANGE)

    # Правая карточка: "Хобби и интересы" (Жёлтый акцент)
    _draw_glass_card(515, "Хобби и интересы", hobbies, ACCENT_YELLOW)

    # 6. Финальное объединение БЕЗ скругления углов карточки
    final_card = Image.alpha_composite(card, overlay)

    buf = io.BytesIO()
    final_card.convert("RGB").save(buf, format="PNG", quality=95)
    return buf.getvalue()
