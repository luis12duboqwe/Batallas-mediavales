from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .config import get_settings
from .database import Base, engine
from .middleware import LanguageMiddleware
from .routers import (
    achievement,
    admin,
    admin_bot,
    alliance,
    anticheat,
    auth,
    building,
    city,
    conquest,
    event,
    message,
    movement,
    notification,
    premium,
    protection,
    queue,
    ranking,
    report,
    season,
    shop,
    theme,
    troop,
    quest,
    world,
    wiki,
)

Base.metadata.create_all(bind=engine)

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LanguageMiddleware)

app.include_router(auth.router)
app.include_router(city.router)
app.include_router(building.router)
app.include_router(troop.router)
app.include_router(movement.router)
app.include_router(queue.router)
app.include_router(report.router)
app.include_router(notification.router)
app.include_router(protection.router)
app.include_router(alliance.router)
app.include_router(message.router)
app.include_router(conquest.router)
app.include_router(ranking.router)
app.include_router(theme.router)
app.include_router(admin.router)
app.include_router(season.router)
app.include_router(achievement.router)
app.include_router(shop.router)
app.include_router(admin_bot.router)
app.include_router(anticheat.router)
app.include_router(event.router)
app.include_router(quest.router)
app.include_router(premium.router)
app.include_router(world.router)
app.include_router(wiki.router)


@app.get("/")
async def root():
    return {"message": "Welcome to Batalla Medieval API"}
