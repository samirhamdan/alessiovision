from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alessio_api.auth import CLIENT_HEADER
from alessio_api.routers import admin, agent, auth, dashboard, equipment
from alessio_api.settings import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="Alessio Vision", version="0.2.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", CLIENT_HEADER],
    )
    app.include_router(auth.router)
    app.include_router(dashboard.router)
    app.include_router(admin.router)
    app.include_router(equipment.router)
    app.include_router(agent.router)
    return app


app = create_app()
