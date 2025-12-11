from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import models
from .config import get_settings
from .database import Base, engine
from .migrations import run_migrations
from .routers import admin, alliance, auth, building, city, message, movement, report, troop

Base.metadata.create_all(bind=engine)
run_migrations(engine)

settings = get_settings()

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(city.router)
app.include_router(building.router)
app.include_router(troop.router)
app.include_router(movement.router)
app.include_router(report.router)
app.include_router(alliance.router)
app.include_router(message.router)
app.include_router(admin.router)


@app.get("/")
async def root():
    return {"message": "Welcome to Batalla Medieval API"}
