from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from bot.config import settings
from miniapps.backend.rate_limit import RateLimitMiddleware
from miniapps.backend.routers import battleship, dialogs, gamestats, norms, online, profile, reviews, stats, ttt

app = FastAPI(title="Спокойный рассвет — мини-приложения")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
app.add_middleware(RateLimitMiddleware)

app.include_router(reviews.router, prefix="/api/reviews",  tags=["reviews"])
app.include_router(online.router,  prefix="/api/online",   tags=["online"])
app.include_router(dialogs.router, prefix="/api/dialogs",  tags=["dialogs"])
app.include_router(stats.router,   prefix="/api/stats",    tags=["stats"])
app.include_router(profile.router, prefix="/api/profile",  tags=["profile"])
app.include_router(ttt.router,     prefix="/api/ttt",      tags=["ttt"])
app.include_router(norms.router,   prefix="/api/norms",    tags=["norms"])
app.include_router(battleship.router, prefix="/api/battleship", tags=["battleship"])
app.include_router(gamestats.router, prefix="/api/gamestats", tags=["gamestats"])

import os
os.makedirs("miniapps/backend/static/uploads/reviews", exist_ok=True)
os.makedirs("miniapps/backend/static/uploads/avatars", exist_ok=True)

app.mount("/shared",  StaticFiles(directory="miniapps/backend/static/shared"),           name="shared")
app.mount("/uploads", StaticFiles(directory="miniapps/backend/static/uploads"),          name="uploads")
app.mount("/online",  StaticFiles(directory="miniapps/backend/static/online",  html=True), name="online")
app.mount("/reviews", StaticFiles(directory="miniapps/backend/static/reviews", html=True), name="reviews")
app.mount("/dialogs", StaticFiles(directory="miniapps/backend/static/dialogs", html=True), name="dialogs")
app.mount("/profile", StaticFiles(directory="miniapps/backend/static/profile", html=True), name="profile")
app.mount("/ttt",     StaticFiles(directory="miniapps/backend/static/ttt",     html=True), name="ttt")
app.mount("/norms",   StaticFiles(directory="miniapps/backend/static/norms",   html=True), name="norms")
app.mount("/battleship", StaticFiles(directory="miniapps/backend/static/battleship", html=True), name="battleship")
app.mount("/gamestats", StaticFiles(directory="miniapps/backend/static/gamestats", html=True), name="gamestats")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.miniapp_host, port=settings.miniapp_port)

