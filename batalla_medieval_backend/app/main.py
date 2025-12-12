from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import logging
import socketio

from .database import Base, engine, SessionLocal
from .middleware.language import LanguageMiddleware
from .scheduler import start_scheduler, shutdown_scheduler
from app.services import hero_service, socket_manager
from app.routers import (
    alliance,
    auth,
    building,
    chat,
    city,
    queue,
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
    world,
    market,
    hero,
    map,
    forum,
    adventure,
    tutorial,
)

logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Batalla Medieval Backend")

@app.on_event("startup")
async def startup_event():
    start_scheduler()
    db = SessionLocal()
    try:
        hero_service.seed_items(db)
    finally:
        db.close()

@app.on_event("shutdown")
async def shutdown_event():
    shutdown_scheduler()

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
app.include_router(forum.router, prefix="/forum", tags=["Forum"])
app.include_router(market.router, prefix="/market", tags=["Market"])
app.include_router(hero.router)
app.include_router(adventure.router)
app.include_router(tutorial.router, prefix="/tutorial", tags=["Tutorial"])
app.include_router(map.router)
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
app.include_router(queue.router, prefix="/queue", tags=["Queue"])
app.include_router(world.router)

# Mount Socket.IO
app = socketio.ASGIApp(socket_manager.sio, app)
