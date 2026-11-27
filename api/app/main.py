import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.routers import admin, auth, halving, health, topics, votes
from config.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    if settings.mail_backend == "console":
        logging.getLogger("app.mail").warning(
            "MAIL_BACKEND=console: login links are written to the logs instead of being e-mailed. Development only."
        )
    if settings.admin_password_is_default:
        logging.getLogger("app.admin").warning(
            "ADMIN_PASSWORD is the development default: anyone who knows it can open the back office. "
            "Set ADMIN_PASSWORD to your own secret (it is required with COOKIE_SECURE=true)."
        )
    app = FastAPI(title="Citizen News API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,  # session cookie
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # The contract wants {"detail": "<message en français>"}, not FastAPI's list of errors.
        fields = sorted({str(e["loc"][-1]) for e in exc.errors() if e.get("loc")})
        detail = "Requête invalide" + (f" (champ : {', '.join(fields)})" if fields else "")
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.middleware("http")
    async def admin_responses(request: Request, call_next):
        # Back-office answers are private: never cached, never indexed.
        response = await call_next(request)
        if request.url.path.startswith("/api/admin"):
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Robots-Tag"] = "noindex"
        return response

    app.include_router(health.router, prefix="/api")
    app.include_router(topics.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(votes.router, prefix="/api")
    app.include_router(halving.router, prefix="/api")
    app.include_router(admin.router, prefix="/api")
    app.include_router(admin.protected, prefix="/api")
    return app


app = create_app()
