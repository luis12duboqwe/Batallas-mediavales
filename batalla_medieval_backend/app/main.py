from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .middleware.language import LanguageMiddleware
from app.routers import (
    alliance,
    auth,
    building,
    chat,
    city,
    event,
    message,
    movement,
    notification,
    premium,
    protection,
    public_api,
    quest,
    ranking,
    report,
    season,
    troop,
    wiki,
)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Batalla Medieval Backend")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# language middleware
app.add_middleware(LanguageMiddleware)

# register routers
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
app.include_router(public_api.router, prefix="/public-api", tags=["Public API"])
