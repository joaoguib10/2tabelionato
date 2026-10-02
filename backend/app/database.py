from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import (
    DATABASE_CONNECT_TIMEOUT_SECONDS,
    DATABASE_MAX_OVERFLOW,
    DATABASE_POOL_RECYCLE_SECONDS,
    DATABASE_POOL_SIZE,
    DATABASE_URL,
)


class Base(DeclarativeBase):
    pass


connect_args = {}
engine_kwargs = {
    "connect_args": connect_args,
    "pool_pre_ping": True,
}
if DATABASE_URL.startswith(("postgresql", "postgres")):
    # psycopg usa ``connect_timeout``; pg8000 usa ``timeout``. Manter
    # ambos permite iniciar o mesmo backend em ambientes Windows onde a
    # biblioteca nativa do psycopg esteja bloqueada, sem alterar o driver
    # padrão da aplicação.
    timeout_param = "timeout" if "+pg8000" in DATABASE_URL else "connect_timeout"
    connect_args[timeout_param] = DATABASE_CONNECT_TIMEOUT_SECONDS
    engine_kwargs.update(
        pool_timeout=DATABASE_CONNECT_TIMEOUT_SECONDS,
        pool_size=DATABASE_POOL_SIZE,
        max_overflow=DATABASE_MAX_OVERFLOW,
        pool_recycle=DATABASE_POOL_RECYCLE_SECONDS,
    )

engine = create_engine(DATABASE_URL, **engine_kwargs)


SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)
