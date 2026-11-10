from aiogram.fsm.state import State, StatesGroup


class AuditFlow(StatesGroup):
    photo = State()


class CalcFlow(StatesGroup):
    area = State()
    heating = State()
    payment = State()


class LeadFlow(StatesGroup):
    city = State()
    contact = State()


class PartnerRegFlow(StatesGroup):
    contact = State()


class PartnerLeadFlow(StatesGroup):
    phone = State()


class EmployeePhotoFlow(StatesGroup):
    task = State()
    photos = State()


class SerialAuditFlow(StatesGroup):
    collecting = State()
