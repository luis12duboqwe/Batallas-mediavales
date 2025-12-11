from pydantic import BaseModel


class PremiumPurchase(BaseModel):
    feature: str


class GrantRubies(BaseModel):
    user_id: int
    amount: int


class MapBookmarkBase(BaseModel):
    name: str
    x: int
    y: int


class MapBookmarkRead(MapBookmarkBase):
    id: int

    class Config:
        orm_mode = True


class PremiumUseAction(BaseModel):
    action: str
    city_id: int | None = None
    queue_id: int | None = None
    new_value: str | None = None
    bookmark: MapBookmarkBase | None = None


class PremiumStatusRead(BaseModel):
    rubies_balance: int
    second_build_queue: bool
    second_troop_queue: bool
    rename_city_unlocked: bool
    rename_player_unlocked: bool
    extra_themes: bool
    profile_banner: bool
    instant_building_cancel: bool
    increased_message_storage: bool
    map_bookmarks: bool
    selected_theme: str | None
    selected_banner: str | None
    bookmarks: list[MapBookmarkRead] = []

    class Config:
        orm_mode = True
