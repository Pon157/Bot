from aiogram.fsm.state import State, StatesGroup


class QuestionnaireForm(StatesGroup):
    """Мини-анкета при первом входе (и при редактировании через 'Изменить анкету')."""

    nickname = State()
    about = State()
    hobbies = State()
    confirm = State()


class AgreementForm(StatesGroup):
    waiting_accept = State()
