from aiogram.fsm.state import State, StatesGroup


class GoalCreation(StatesGroup):
    waiting_for_name = State()
    waiting_for_count = State()