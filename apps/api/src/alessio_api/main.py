from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from alessio_api.routers import agent, dashboard
from alessio_api.settings import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title="ALESSIO", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origins,
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(agent.router)
    app.include_router(dashboard.router)
    return app


app = create_app()
