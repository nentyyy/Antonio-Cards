from aiogram.fsm.state import State, StatesGroup


class AddCardState(StatesGroup):
    waiting_payload = State()


class EditCardState(StatesGroup):
    waiting_payload = State()


class SetCooldownState(StatesGroup):
    waiting_payload = State()


class SetDropState(StatesGroup):
    waiting_payload = State()


class SetPriceState(StatesGroup):
    waiting_payload = State()


class BroadcastState(StatesGroup):
    waiting_text = State()
