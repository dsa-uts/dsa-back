from .schemas import UserBase

GUEST = UserBase(
    id=-1,
    username="guest",
    is_admin=False,
    disabled=True,
)
