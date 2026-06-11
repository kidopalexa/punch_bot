from aiogram.fsm.state import State, StatesGroup


class GoalCreation(StatesGroup):
    waiting_for_name = State()
    waiting_for_count = State()


class ChallengeCreation(StatesGroup):
    waiting_for_opponent = State()
    waiting_for_goal_name = State()
    waiting_for_count = State()


class CoachDialog(StatesGroup):
    waiting_for_question = State()
