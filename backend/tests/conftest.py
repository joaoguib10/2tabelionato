import os

import pytest

os.environ["OCR_ENABLED"] = "false"  # Suíte determinística; testes OCR injetam o motor.
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

os.environ["TABELEAO_SECRET_KEY"] = "segredo-exclusivo-da-suite-de-testes"
os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["MFA_ENABLED"] = "true"

from app.auth import create_access_token
from app.database import Base
from app.dependencies import get_db
from app.models import Usuario
from app.security import hash_password
from main import app


@pytest.fixture(autouse=True)
def isolar_arquivos_e_ingestao(tmp_path, monkeypatch, testing_session_factory):
    from app.routers import analyses, documents, reviews
    from app.services import (
        case_fact_extraction_service,
        case_ingestion_service,
        ingestion_service,
        purchase_sale_service,
    )

    for modulo in (analyses, documents, reviews):
        destino = tmp_path / modulo.__name__.rsplit(".", 1)[-1]
        destino.mkdir()
        monkeypatch.setattr(modulo, "UPLOAD_DIR", destino)
    for modulo in (
        case_fact_extraction_service,
        case_ingestion_service,
        ingestion_service,
        purchase_sale_service,
    ):
        monkeypatch.setattr(modulo, "SessionLocal", testing_session_factory)
    monkeypatch.setattr(case_ingestion_service, "_processamentos", set())
    monkeypatch.setattr(case_fact_extraction_service, "_extracoes_ativas", set())
    monkeypatch.setattr(purchase_sale_service, "_extracoes_ativas", set())


@pytest.fixture()
def testing_session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db(testing_session_factory):
    session = testing_session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(testing_session_factory):
    def override_db():
        session = testing_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def usuario_factory(db):
    def criar(
        username: str,
        role: str = "USUARIO",
        pin: str = "1234",
    ) -> Usuario:
        usuario = Usuario(
            nome=username.title(),
            username=username,
            password_hash=hash_password(pin),
            role=role,
            ativo=True,
            senha_pendente=False,
            mfa_ativo=True,
        )
        db.add(usuario)
        db.commit()
        db.refresh(usuario)
        return usuario

    return criar


@pytest.fixture()
def auth_headers():
    def criar(usuario: Usuario) -> dict[str, str]:
        token = create_access_token(
            {
                "sub": str(usuario.id),
                "role": usuario.role,
                "purpose": "access",
                "ver": usuario.sessao_versao,
            }
        )
        return {"Authorization": f"Bearer {token}"}

    return criar
