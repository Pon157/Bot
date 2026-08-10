from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import BTN_EDIT_QUESTIONNAIRE, BTN_FAVORITE_ADMINS, BTN_PROFILE
from bot.services.profile_card import render_profile_card
from bot.states.onboarding import QuestionnaireForm
from bot.utils import emoji as e
from bot.utils.emoji import ce
from db.models import Admin, AppealMessage, FavoriteAdmin, User

router = Router(name="profile")


@router.message(F.text == BTN_PROFILE)
async def show_profile(message: Message, session: AsyncSession) -> None:
    result = await session.execute(select(User).where(User.telegram_id == message.from_user.id))
    user = result.scalar_one_or_none()
    if user is None:
        return

    # аватар пользователя
    avatar_bytes = None
    try:
        photos = await message.bot.get_user_profile_photos(message.from_user.id, limit=1)
        if photos.total_count > 0:
            file = await message.bot.get_file(photos.photos[0][-1].file_id)
            buf = await message.bot.download_file(file.file_path)
            avatar_bytes = buf.read()
    except Exception:
        pass

    dialogs_count_res = await session.execute(
        select(AppealMessage.appeal_id).where(AppealMessage.sender_id == message.from_user.id).distinct()
    )
    dialogs_count = len(dialogs_count_res.all())

    favorites_res = await session.execute(
        select(FavoriteAdmin).where(FavoriteAdmin.user_id == message.from_user.id)
    )
    favorites_count = len(favorites_res.all())

    stats_lines = [
        f"Диалогов проведено: {dialogs_count}",
        f"Избранных админов: {favorites_count}",
        f"В боте с {user.created_at.strftime('%d.%m.%Y')}",
    ]

    png = await render_profile_card(
        nickname=user.nickname or user.full_name,
        about=user.about or "—",
        hobbies=user.hobbies or "—",
        avatar_bytes=avatar_bytes,
        stats_lines=stats_lines,
    )

    await message.answer_photo(
        BufferedInputFile(png, filename="profile.png"),
        caption=f"{ce(e.EYES)} Твоя карточка профиля",
        parse_mode="HTML",
    )


@router.message(F.text == BTN_EDIT_QUESTIONNAIRE)
async def edit_questionnaire(message: Message, state: FSMContext) -> None:
    await state.set_state(QuestionnaireForm.nickname)
    await message.answer(
        f"{ce(e.PENCIL)} Обновим твою анкету. Как тебя называть?"
    )


@router.message(F.text == BTN_FAVORITE_ADMINS)
async def favorite_admins_menu(message: Message, session: AsyncSession) -> None:
    result = await session.execute(select(Admin).where(Admin.is_active.is_(True)))
    admins = result.scalars().all()

    favs_res = await session.execute(
        select(FavoriteAdmin.admin_id).where(FavoriteAdmin.user_id == message.from_user.id)
    )
    fav_ids = {row[0] for row in favs_res.all()}

    from aiogram.types import InlineKeyboardMarkup
    from bot.utils.buttons import inline_btn

    rows = []
    for admin in admins:
        is_fav = admin.telegram_id in fav_ids
        label = f"{'★' if is_fav else '☆'} {admin.nickname}"
        rows.append(
            [
                inline_btn(
                    label,
                    callback_data=f"fav:toggle:{admin.telegram_id}",
                    emo=e.STAR if is_fav else None,
                    style="success" if is_fav else "primary",
                )
            ]
        )
    markup = InlineKeyboardMarkup(inline_keyboard=rows or [[inline_btn("Пока нет администраторов", callback_data="noop")]])

    await message.answer(
        f"{ce(e.STAR)} Выбери любимых администраторов — их бот будет чаще рекомендовать при создании обращения:",
        parse_mode="HTML",
        reply_markup=markup,
    )


@router.callback_query(F.data.startswith("fav:toggle:"))
async def toggle_favorite(callback: CallbackQuery, session: AsyncSession) -> None:
    admin_id = int(callback.data.split(":")[-1])
    result = await session.execute(
        select(FavoriteAdmin).where(
            FavoriteAdmin.user_id == callback.from_user.id, FavoriteAdmin.admin_id == admin_id
        )
    )
    fav = result.scalar_one_or_none()
    if fav:
        await session.delete(fav)
        await callback.answer("Убрано из избранного")
    else:
        session.add(FavoriteAdmin(user_id=callback.from_user.id, admin_id=admin_id))
        await callback.answer("Добавлено в избранное")
    await session.commit()
    await favorite_admins_menu(callback.message, session)  # type: ignore[arg-type]
