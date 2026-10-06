import uuid
from datetime import date, datetime, timezone
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    literal_column,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.search_text import texto_metadados_documento_sql, tsvector_portugues_sql


def utc_now() -> datetime:
    """UTC sem timezone para manter compatibilidade com colunas existentes."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Usuario(Base):
    __tablename__ = "usuarios"

    senha_pendente: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    mfa_ativo: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    mfa_segredo: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    mfa_ultimo_passo: Mapped[int] = mapped_column(
        Integer,
        default=-1,
        nullable=False,
    )

    mfa_tentativas: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    recuperacao_hashes: Mapped[list] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )

    sessao_versao: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    nome: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )

    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    role: Mapped[str] = mapped_column(
        String(30),
        default="USUARIO",
        nullable=False,
    )

    ativo: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    tentativas_login: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    bloqueado_em: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class EventoSeguranca(Base):
    __tablename__ = "eventos_seguranca"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "usuarios.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    ator_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "usuarios.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    acao: Mapped[str] = mapped_column(
        String(60),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )


class Documento(Base):
    __tablename__ = "documentos"

    __table_args__ = (
        UniqueConstraint(
            "hash_arquivo",
            name="uq_documentos_hash_arquivo",
        ),
        Index(
            "ix_documentos_governanca_ia",
            "tipo",
            "tipo_ato",
            "situacao",
            "status",
            "ativo",
        ),
        Index(
            "ix_documentos_busca_textual_normalizada",
            tsvector_portugues_sql(
                texto_metadados_documento_sql(
                    literal_column("titulo"), literal_column("descricao")
                )
            ),
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    titulo: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    descricao: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    tipo: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    tipo_ato: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    situacao: Mapped[str] = mapped_column(
        String(20),
        default="RASCUNHO",
        nullable=False,
    )

    orgao_origem: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    versao: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    jurisdicao: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    vigencia_inicio: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    vigencia_fim: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    observacoes: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    nome_arquivo: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    caminho_arquivo: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    hash_arquivo: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    status_seguranca: Mapped[str] = mapped_column(
        String(20),
        default="PENDENTE",
        nullable=False,
    )

    alerta_seguranca: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    ativo: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="PROCESSANDO",
        nullable=False,
    )

    erro_processamento: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    total_paginas: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    total_chunks: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    situacao_extracao: Mapped[str] = mapped_column(
        String(30),
        default="PENDENTE_VERIFICACAO",
        nullable=False,
    )

    diagnostico_extracao: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    processado_em: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    criado_por: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id"),
        nullable=False,
    )

    aprovado_por: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "usuarios.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    aprovado_em: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class DocumentoPagina(Base):
    __tablename__ = "documento_paginas"

    metodo_extracao: Mapped[str] = mapped_column(
        String(20),
        default="NAO_VERIFICADO",
        nullable=False,
    )

    situacao_extracao: Mapped[str] = mapped_column(
        String(30),
        default="NAO_VERIFICADA",
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "documento_id",
            "pagina",
            name="uq_documento_pagina",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    documento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "documentos.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    pagina: Mapped[int] = mapped_column(
        nullable=False,
    )

    pagina_confiavel: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    localizacao: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    conteudo: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )


class DocumentoChunk(Base):
    __tablename__ = "documento_chunks"

    __table_args__ = (
        UniqueConstraint(
            "documento_id",
            "pagina",
            "posicao",
            name="uq_documento_chunk",
        ),
        Index(
            "ix_documento_chunks_busca_textual",
            func.to_tsvector(
                literal_column("'portuguese'"),
                literal_column("conteudo"),
            ),
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
        Index(
            "ix_documento_chunks_busca_textual_normalizada",
            tsvector_portugues_sql(literal_column("conteudo")),
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    documento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "documentos.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    pagina: Mapped[int] = mapped_column(
        nullable=False,
    )

    posicao: Mapped[int] = mapped_column(
        nullable=False,
    )

    artigo: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    artigo_confirmado: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    capitulo: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    secao: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    paragrafo: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    inciso: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    pagina_confiavel: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    localizacao: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    conteudo: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(768),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )


Index(
    "ix_documento_chunks_embedding_hnsw",
    DocumentoChunk.embedding,
    postgresql_using="hnsw",
    postgresql_ops={"embedding": "vector_cosine_ops"},
    postgresql_where=(DocumentoChunk.embedding.is_not(None)),
)


class ConsultaHistorico(Base):
    __tablename__ = "consultas_historico"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "usuarios.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    pergunta: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    resposta: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    confianca: Mapped[float] = mapped_column(
        Float,
        default=0.0,
        nullable=False,
    )

    confiavel: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    situacao_resposta: Mapped[str] = mapped_column(
        String(30),
        default="BASE_INSUFICIENTE",
        nullable=False,
    )

    fonte_ids: Mapped[str] = mapped_column(
        Text,
        default="[]",
        nullable=False,
    )

    produtiva: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )

    feedback_motivo: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    feedback_comentario: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    tipo_tarefa: Mapped[str] = mapped_column(
        String(30),
        default="CONSULTA",
        nullable=False,
    )

    prompt_version: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    modelo_ia: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    modelo_versao: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    parametros_ia: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )


class ConsultaFonte(Base):
    __tablename__ = "consulta_fontes"

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    consulta_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "consultas_historico.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    chunk_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "documento_chunks.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    documento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "documentos.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    fonte_id: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    titulo_documento: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    versao_documento: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    pagina: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    localizacao: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    artigo: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    trecho: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    pontuacao: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )

    citada: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    recuperada: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )


class ConsultaRevisao(Base):
    __tablename__ = "consulta_revisoes"

    __table_args__ = (
        CheckConstraint(
            "status IN " "('PENDENTE', 'EM_ANALISE', " "'RESPONDIDA', 'ENCERRADA')",
            name="ck_consulta_revisoes_status",
        ),
        UniqueConstraint(
            "consulta_id",
            name="uq_consulta_revisoes_consulta_id",
        ),
        UniqueConstraint(
            "entendimento_documento_id",
            name=("uq_consulta_revisoes_" "entendimento_documento_id"),
        ),
        Index(
            "ix_consulta_revisoes_status_created_at",
            "status",
            "created_at",
        ),
        Index(
            "ix_consulta_revisoes_responsavel_id",
            "responsavel_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    consulta_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "consultas_historico.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default="PENDENTE",
        nullable=False,
    )

    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "usuarios.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    resposta_humana: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    respondido_por: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "usuarios.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    respondida_em: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    entendimento_documento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "documentos.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    encerrada_em: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


# =========================================================
# ANÁLISE DE CASOS
# =========================================================


class Caso(Base):
    """
    Caso concreto submetido à ferramenta de Análise.

    Não integra a base jurídica reutilizável do RAG.
    """

    __tablename__ = "casos"

    __table_args__ = (
        Index(
            "ix_casos_status_updated_at",
            "status",
            "updated_at",
        ),
        Index(
            "ix_casos_criado_por_created_at",
            "criado_por",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    titulo: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )

    identificacao: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    tipo_ato: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )

    descricao: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    dados_ato: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    status_dados_ato: Mapped[str] = mapped_column(
        String(30),
        default="NAO_INICIADO",
        nullable=False,
    )

    erro_dados_ato: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    dados_ato_atualizados_em: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(40),
        default="EM_PREPARACAO",
        nullable=False,
    )

    criado_por: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id"),
        nullable=False,
    )

    responsavel_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "usuarios.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    encerrado_em: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class CasoDocumento(Base):
    """
    Documento privado pertencente a um caso concreto.

    É deliberadamente separado de Documento, DocumentoPagina
    e DocumentoChunk, utilizados pelo corpus jurídico.

    A classificação informada pelo usuário fornece contexto
    operacional ao A2, mas não constitui prova do conteúdo
    nem substitui a conferência documental.
    """

    __tablename__ = "caso_documentos"

    __table_args__ = (
        UniqueConstraint(
            "caso_id",
            "hash_arquivo",
            name="uq_caso_documentos_caso_hash",
        ),
        Index(
            "ix_caso_documentos_caso_status",
            "caso_id",
            "status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    caso_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "casos.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    nome_arquivo: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    caminho_arquivo: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    hash_arquivo: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )

    mime_type: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    tamanho_bytes: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    tipo_documento: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    vinculo_ato: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        default="PENDENTE",
        nullable=False,
    )

    status_seguranca: Mapped[str] = mapped_column(
        String(20),
        default="PENDENTE",
        nullable=False,
    )

    alerta_seguranca: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    seguranca_liberada_por: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"),
        nullable=True,
    )

    seguranca_liberada_em: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    erro_processamento: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    total_paginas: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    situacao_extracao: Mapped[str] = mapped_column(
        String(30),
        default="PENDENTE_VERIFICACAO",
        nullable=False,
    )

    diagnostico_extracao: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    processado_em: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    status_extracao_fatos: Mapped[str] = mapped_column(
        String(30),
        default="NAO_INICIADO",
        nullable=False,
    )

    erro_extracao_fatos: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    diagnostico_extracao_fatos: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    fatos_extraidos_em: Mapped[datetime | None] = mapped_column(
        DateTime,
        nullable=True,
    )

    versao_extrator_fatos: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    criado_por: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class CasoDocumentoPagina(Base):
    """
    Texto extraído de uma página ou bloco lógico de documento
    privado do caso.

    Nunca é indexado automaticamente no RAG jurídico.
    """

    __tablename__ = "caso_documento_paginas"

    __table_args__ = (
        UniqueConstraint(
            "caso_documento_id",
            "pagina",
            name="uq_caso_documento_pagina",
        ),
        Index(
            "ix_caso_documento_paginas_documento",
            "caso_documento_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    caso_documento_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "caso_documentos.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    pagina: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    pagina_confiavel: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    localizacao: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    conteudo: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )

    metodo_extracao: Mapped[str] = mapped_column(
        String(30),
        default="NAO_VERIFICADO",
        nullable=False,
    )

    situacao_extracao: Mapped[str] = mapped_column(
        String(30),
        default="NAO_VERIFICADA",
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )


class CasoFato(Base):
    """
    Unidade factual materialmente relevante do caso.

    valor_original preserva aquilo que foi inicialmente
    declarado, extraído ou inferido.

    valor_atual representa o estado corrente após eventual
    conferência humana.

    Correção não apaga o valor original.
    """

    __tablename__ = "caso_fatos"

    __table_args__ = (
        CheckConstraint(
            "estado_evidencia IN "
            "('ENCONTRADO', 'AUSENTE', "
            "'INCERTO', 'CONFLITANTE')",
            name="ck_caso_fatos_estado_evidencia",
        ),
        CheckConstraint(
            "estado_conferencia IN " "('PENDENTE', 'CONFIRMADO', 'CORRIGIDO')",
            name="ck_caso_fatos_estado_conferencia",
        ),
        Index(
            "ix_caso_fatos_caso_estado",
            "caso_id",
            "estado_evidencia",
            "estado_conferencia",
        ),
        Index(
            "ix_caso_fatos_documento",
            "caso_documento_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    caso_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "casos.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    caso_documento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "caso_documentos.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    campo: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )

    categoria: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
    )

    locus: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    valor_original: Mapped[Any | None] = mapped_column(
        JSON,
        nullable=True,
    )

    valor_atual: Mapped[Any | None] = mapped_column(
        JSON,
        nullable=True,
    )

    proveniencia: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
    )

    estado_evidencia: Mapped[str] = mapped_column(
        String(30),
        default="INCERTO",
        nullable=False,
    )

    estado_conferencia: Mapped[str] = mapped_column(
        String(20),
        default="PENDENTE",
        nullable=False,
    )

    pagina: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    localizacao: Mapped[str | None] = mapped_column(
        String(200),
        nullable=True,
    )

    trecho_fonte: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    metodo_extracao: Mapped[str | None] = mapped_column(
        String(30),
        nullable=True,
    )

    contexto: Mapped[dict | None] = mapped_column(
        JSON,
        nullable=True,
    )

    ativo: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    registrado_por: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "usuarios.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class CasoConferencia(Base):
    """
    Histórico append-only da conferência humana de fatos.
    """

    __tablename__ = "caso_conferencias"

    __table_args__ = (
        CheckConstraint(
            "acao IN " "('CONFIRMAR', 'CORRIGIR', 'REABRIR')",
            name="ck_caso_conferencias_acao",
        ),
        Index(
            "ix_caso_conferencias_fato_created_at",
            "fato_id",
            "created_at",
        ),
        Index(
            "ix_caso_conferencias_caso_created_at",
            "caso_id",
            "created_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        primary_key=True,
        default=uuid.uuid4,
    )

    caso_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "casos.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    fato_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey(
            "caso_fatos.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "usuarios.id",
            ondelete="SET NULL",
        ),
        nullable=True,
    )

    acao: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    valor_anterior: Mapped[Any | None] = mapped_column(
        JSON,
        nullable=True,
    )

    valor_novo: Mapped[Any | None] = mapped_column(
        JSON,
        nullable=True,
    )

    observacao: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utc_now,
        nullable=False,
    )


class CasoVersao(Base):
    """Snapshot mínimo do estado conferido usado por A1/TAB."""

    __tablename__ = "caso_versoes"
    __table_args__ = (
        UniqueConstraint("caso_id", "numero", name="uq_caso_versoes_numero"),
        UniqueConstraint("caso_id", "hash_estado", name="uq_caso_versoes_hash"),
        Index("ix_caso_versoes_caso_created_at", "caso_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    caso_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("casos.id", ondelete="CASCADE"), nullable=False
    )
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    hash_estado: Mapped[str] = mapped_column(String(64), nullable=False)
    motivo: Mapped[str] = mapped_column(String(200), nullable=False)
    fatos_snapshot: Mapped[list] = mapped_column(JSON, nullable=False)
    documentos_snapshot: Mapped[list] = mapped_column(JSON, nullable=False)
    criado_por: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class CasoAnalise(Base):
    """Resultado assistivo do A1; nunca representa decisão notarial."""

    __tablename__ = "caso_analises"
    __table_args__ = (
        Index("ix_caso_analises_caso_created_at", "caso_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    caso_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("casos.id", ondelete="CASCADE"), nullable=False
    )
    versao_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("caso_versoes.id", ondelete="RESTRICT"), nullable=False
    )
    status_evidencia: Mapped[str] = mapped_column(
        String(30), default="BASE_INSUFICIENTE", nullable=False
    )
    resumo: Mapped[str] = mapped_column(Text, nullable=False)
    requisitos: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    impedimentos: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    pendencias: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    fontes_snapshot: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    modelo_ia: Mapped[str | None] = mapped_column(String(150), nullable=True)
    gerado_por: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class CasoDecisao(Base):
    """Registro append-only da decisão humana TAB."""

    __tablename__ = "caso_decisoes"
    __table_args__ = (
        CheckConstraint(
            "decisao IN ('APROVAR', 'EXIGENCIA', 'RECUSAR', 'OUTRA')",
            name="ck_caso_decisoes_decisao",
        ),
        Index("ix_caso_decisoes_caso_created_at", "caso_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    caso_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("casos.id", ondelete="CASCADE"), nullable=False
    )
    analise_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("caso_analises.id", ondelete="RESTRICT"), nullable=False
    )
    decisao: Mapped[str] = mapped_column(String(20), nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    fundamentacao: Mapped[str | None] = mapped_column(Text, nullable=True)
    escopo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    decidido_por: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class CasoMensagem(Base):
    """Histórico append-only do chat temporário vinculado ao caso."""

    __tablename__ = "caso_mensagens"
    __table_args__ = (
        CheckConstraint(
            "papel IN ('USUARIO', 'ASSISTENTE', 'SISTEMA')",
            name="ck_caso_mensagens_papel",
        ),
        Index("ix_caso_mensagens_caso_created_at", "caso_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    caso_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("casos.id", ondelete="CASCADE"), nullable=False
    )
    papel: Mapped[str] = mapped_column(String(20), nullable=False)
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    usuario_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    analise_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("caso_analises.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class CasoTarefa(Base):
    """Fila persistente e idempotente das etapas assíncronas do caso."""

    __tablename__ = "caso_tarefas"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDENTE', 'PROCESSANDO', 'CONCLUIDA', 'ERRO', 'CANCELADA')",
            name="ck_caso_tarefas_status",
        ),
        Index("ix_caso_tarefas_caso_created_at", "caso_id", "created_at"),
        Index("ix_caso_tarefas_status_created_at", "status", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    caso_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("casos.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="PENDENTE", nullable=False)
    caso_documento_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("caso_documentos.id", ondelete="SET NULL"), nullable=True
    )
    tentativa: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    erro: Mapped[str | None] = mapped_column(Text, nullable=True)
    iniciado_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    criado_por: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )


class AtaTrabalho(Base):
    """Processo temporário de Ata, removido junto aos arquivos ao confirmar."""

    __tablename__ = "ata_trabalhos"
    __table_args__ = (
        CheckConstraint(
            "status IN ('ABERTO', 'PROCESSANDO', 'PRONTO', 'PRONTO_PARCIAL', 'ERRO')",
            name="ck_ata_trabalhos_status",
        ),
        Index("ix_ata_trabalhos_usuario_created_at", "usuario_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    usuario_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False
    )
    titulo: Mapped[str] = mapped_column(
        String(200), nullable=False, default="Ata Notarial", server_default="Ata Notarial"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="ABERTO", nullable=False
    )
    nome_arquivo: Mapped[str | None] = mapped_column(String(255), nullable=True)
    hash_arquivo: Mapped[str | None] = mapped_column(String(64), nullable=True)
    caminho_temporario: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resultado: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnostico: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    erro_processamento: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, nullable=False
    )
    concluido_em: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
