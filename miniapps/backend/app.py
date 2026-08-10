from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from bot.config import settings
from miniapps.backend.routers import dialogs, online, profile, reviews, stats

app = FastAPI(title="Спокойный рассвет — мини-приложения")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://web.telegram.org", "https://webk.telegram.org"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(reviews.router, prefix="/api/reviews", tags=["reviews"])
app.include_router(online.router, prefix="/api/online", tags=["online"])
app.include_router(dialogs.router, prefix="/api/dialogs", tags=["dialogs"])
app.include_router(stats.router, prefix="/api/stats", tags=["stats"])
app.include_router(profile.router, prefix="/api/profile", tags=["profile"])

app.mount("/reviews", StaticFiles(directory="miniapps/backend/static/reviews", html=True), name="reviews")
app.mount("/online", StaticFiles(directory="miniapps/backend/static/online", html=True), name="online")
app.mount("/dialogs", StaticFiles(directory="miniapps/backend/static/dialogs", html=True), name="dialogs")
app.mount("/profile", StaticFiles(directory="miniapps/backend/static/profile", html=True), name="profile")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.miniapp_host, port=settings.miniapp_port)
