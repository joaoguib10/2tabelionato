import logging
import re
import time
from uuid import uuid4

from app.config import FRONTEND_ORIGINS
from app.database import engine
from app.dependencies import get_db
from app.models import Usuario
from app.permissions import require_roles
from app.routers.analyses import (
    router as analyses_router,
)
from app.routers.auth import (
    router as auth_router,
)
from app.routers.consultation import (
    router as consultation_router,
)
from app.routers.documents import (
    router as documents_router,
)
from app.routers.minutes import (
    router as minutes_router,
)
from app.routers.notarial_acts import (
    router as notarial_acts_router,
)
from app.routers.reviews import (
    router as reviews_router,
)
from app.routers.users import (
    router as users_router,
)
from fastapi import (
    Depends,
    FastAPI,
)
from fastapi.exceptions import (
    RequestValidationError,
)
from fastapi.middleware.cors import (
    CORSMiddleware,
)
from fastapi.responses import (
    JSONResponse,
)
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

app = FastAPI(
    title="Tabeleão",
    description=("API do assistente inteligente " "do tabelionato"),
    version="0.1.0",
)


@app.middleware("http")
async def hardening_middleware(request, call_next):
    candidato = request.headers.get("X-Request-ID", "")
    request_id = candidato if REQUEST_ID_PATTERN.fullmatch(candidato) else uuid4().hex
    inicio = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception(
            "Falha não tratada na requisição: request_id=%s method=%s path=%s",
            request_id,
            request.method,
            request.url.path,
        )
        raise
    duracao_ms = (time.perf_counter() - inicio) * 1000
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    logger.info(
        "Requisição concluída: request_id=%s method=%s path=%s status=%s duracao_ms=%.1f",
        request_id,
        request.method,
        request.url.path,
        response.status_code,
        duracao_ms,
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request,
    exc,
):
    # Não refletir senha, código,
    # token ou conteúdo enviado
    # nos erros de validação.
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {
                    "loc": error["loc"],
                    "msg": error["msg"],
                    "type": error["type"],
                }
                for error in (exc.errors())
            ]
        },
    )


app.include_router(auth_router)

app.include_router(consultation_router)

app.include_router(users_router)

app.include_router(documents_router)

app.include_router(minutes_router)

app.include_router(reviews_router)

app.include_router(analyses_router)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(request, exc):
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Banco de dados temporariamente indisponível. Tente novamente em instantes."
        },
    )


app.include_router(notarial_acts_router)


app.add_middleware(
    CORSMiddleware,
    allow_origins=(FRONTEND_ORIGINS),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Accept", "Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Access-Token"],
)


@app.get("/")
def root():
    return {"message": ("Tabeleão API funcionando!")}


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "database": "offline"},
        )
    return {"status": "ready", "database": "online"}


@app.get("/api/status")
def status():
    return {
        "system": "Tabeleão",
        "backend": "online",
        "version": "0.1.0",
    }


@app.get("/api/database")
def database_status(
    _usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {"database": "online"}

    except Exception:
        return {"database": "offline"}


@app.get("/api/database/test")
def database_test(
    _usuario_atual: Usuario = Depends(require_roles("ADMIN")),
    db: Session = Depends(get_db),
):
    result = db.execute(text("SELECT 1"))

    return {
        "database": "online",
        "test": result.scalar(),
    }
