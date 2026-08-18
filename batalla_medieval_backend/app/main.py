from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import socketio

from .config import get_settings
from .middleware.language import LanguageMiddleware
from .services import socket_manager
from .routers import (
    admin,
    alliance,
    anticheat,
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

settings = get_settings()

app = FastAPI(title="Batalla Medieval Backend")


@app.get("/health", tags=["Health"])
def health_check():
    """Return a dependency-free liveness response for probes and CI."""
    return {"status": "ok"}


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(LanguageMiddleware)

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
# ``queue.router`` already owns the /queue prefix. Adding it again produces
# /queue/queue/* and breaks the frontend contract.
app.include_router(queue.router)
app.include_router(world.router)

# G1 administration/moderation surface. Both routers own their prefixes and
# enforce administrator authorization internally.
app.include_router(admin.router)
app.include_router(anticheat.router)

# Socket.IO is mounted around the HTTP application. The real-time transport
# authenticates every connection from its JWT before assigning a personal room.
socket_app = socketio.ASGIApp(socket_manager.sio, app)
