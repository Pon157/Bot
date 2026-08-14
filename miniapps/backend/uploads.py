from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

# Каталог со статикой смонтирован в app.py как /uploads -> UPLOADS_DIR
UPLOADS_DIR = Path("miniapps/backend/static/uploads")
REVIEWS_SUBDIR = "reviews"
AVATARS_SUBDIR = "avatars"

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 МБ
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}
_EXT_BY_CONTENT_TYPE = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}


async def save_upload_image(file: UploadFile, subdir: str) -> str:
    """
    Валидирует и сохраняет загруженное изображение на диск.
    Возвращает путь для сохранения в БД в виде "uploads/<subdir>/<file>.ext"
    (используется как /uploads/<subdir>/<file>.ext в статике FastAPI).

    Кидает HTTPException(400/413), если файл не картинка или больше 25 МБ.
    """
    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Разрешены только изображения (jpeg, png, webp, gif)")

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Файл слишком большой (максимум 25 МБ)")
    if not data:
        raise HTTPException(status_code=400, detail="Пустой файл")

    target_dir = UPLOADS_DIR / subdir
    target_dir.mkdir(parents=True, exist_ok=True)

    ext = _EXT_BY_CONTENT_TYPE[content_type]
    filename = f"{uuid.uuid4().hex}{ext}"
    (target_dir / filename).write_bytes(data)

    return f"uploads/{subdir}/{filename}"


def to_public_url(photo_path: str | None) -> str | None:
    if not photo_path:
        return None
    return f"/{photo_path}"
