import logging
from time import perf_counter
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from eventserver import __version__
from eventserver.api import api_router
from eventserver.api.errors import http_exception_handler, validation_exception_handler
from eventserver.auth.service import require_service_auth
from eventserver.config import Settings, get_settings
from eventserver.db.session import engine
from eventserver.observability import REQUEST_COUNT, REQUEST_DURATION, configure_logging
from eventserver.providers import build_registry


def create_app(settings: Settings | None = None) -> FastAPI:
    selected = settings or get_settings()
    configure_logging()
    app = FastAPI(title="AutoQQ EventServer", version=__version__)
    if settings is not None:
        app.dependency_overrides[get_settings] = lambda: selected
    app.state.provider_registry = build_registry(selected.enabled_providers)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        started = perf_counter()
        supplied = request.headers.get("X-Request-ID", "")
        request.state.request_id = supplied[:64] if supplied else str(uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        route = getattr(request.scope.get("route"), "path", "unmatched")
        duration = perf_counter() - started
        REQUEST_COUNT.labels(request.method, route, str(response.status_code)).inc()
        REQUEST_DURATION.labels(request.method, route).observe(duration)
        logging.getLogger("eventserver.access").info(
            "request completed",
            extra={
                "request_id": request.state.request_id,
                "method": request.method,
                "route": route,
                "status": response.status_code,
                "duration_ms": round(duration * 1000, 3),
            },
        )
        return response

    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {"status": "alive", "version": __version__}

    @app.get("/ready", tags=["health"])
    def ready() -> dict[str, str]:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except Exception as exc:
            raise HTTPException(status_code=503, detail="database is unavailable") from exc
        return {"status": "ready", "version": __version__}

    @app.get("/metrics", include_in_schema=False, dependencies=[Depends(require_service_auth)])
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    app.include_router(api_router)
    return app


app = create_app()
