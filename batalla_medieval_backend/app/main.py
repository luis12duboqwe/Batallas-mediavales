"""Application entrypoint for Batalla Medieval API."""

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
    chat,
    city,
    conquest,
    economy,
    event,
    icon,
    message,
    movement,
    notification,
    premium,
    protection,
    public_api,
    quest,
    queue,
    ranking,
    report,
    season,
    shop,
    theme,
    troop,
    wiki,
    world,
)

# Load configuration and initialize database metadata.
settings = get_settings()
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Batalla Medieval Backend")

# Global middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(LanguageMiddleware)

# Router registration
app.include_router(auth.router, prefix="/auth", tags=["Auth"])
app.include_router(city.router, prefix="/city", tags=["City"])
app.include_router(building.router, prefix="/building", tags=["Building"])
app.include_router(troop.router, prefix="/troop", tags=["Troop"])
app.include_router(movement.router, prefix="/movement", tags=["Movement"])
app.include_router(alliance.router, prefix="/alliance", tags=["Alliance"])
app.include_router(message.router, prefix="/message", tags=["Message"])
app.include_router(ranking.router, prefix="/ranking", tags=["Ranking"])
app.include_router(report.router, prefix="/report", tags=["Report"])
app.include_router(protection.router, prefix="/protection", tags=["Protection"])
app.include_router(premium.router, prefix="/premium", tags=["Premium"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(notification.router, prefix="/notification", tags=["Notification"])
app.include_router(event.router, prefix="/event", tags=["Event"])
app.include_router(season.router, prefix="/season", tags=["Season"])
app.include_router(quest.router, prefix="/quest", tags=["Quest"])
app.include_router(wiki.router, prefix="/wiki", tags=["Wiki"])

# Additional routers
app.include_router(achievement.router, prefix="/achievement", tags=["Achievement"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(admin_bot.router, prefix="/admin-bot", tags=["Admin Bot"])
app.include_router(anticheat.router, prefix="/anticheat", tags=["Anticheat"])
app.include_router(conquest.router, prefix="/conquest", tags=["Conquest"])
app.include_router(economy.router, prefix="/economy", tags=["Economy"])
app.include_router(icon.router, prefix="/icon", tags=["Icon"])
app.include_router(public_api.router, prefix="/public-api", tags=["Public API"])
app.include_router(queue.router, prefix="/queue", tags=["Queue"])
app.include_router(shop.router, prefix="/shop", tags=["Shop"])
app.include_router(theme.router, prefix="/theme", tags=["Theme"])
app.include_router(world.router, prefix="/world", tags=["World"])


@app.get("/")
async def root():
    """Health endpoint used to verify API availability."""

    return {"message": "Welcome to Batalla Medieval API"}
