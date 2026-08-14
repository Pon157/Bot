from aiogram.fsm.state import State, StatesGroup


class CreateAppealForm(StatesGroup):
    choosing_mode = State()
    choosing_admin_by_nickname = State()
    typing_message = State()  # первое сообщение обращения (текст/медиа с подписью)


class DialogState(StatesGroup):
    """Пока пользователь находится в активном диалоге — все его сообщения пересылаются в топик."""

    in_dialog = State()

