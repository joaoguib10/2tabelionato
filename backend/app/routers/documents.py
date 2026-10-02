import hashlib
import logging
import math
import mimetypes
import zipfile
from datetime import date, timedelta
from pathlib import Path
from uuid import UUID, uuid4

from app.auth import get_current_user
from app.dependencies import get_db
from app.models import (
    ConsultaRevisao,
    Documento,
    DocumentoPagina,
    Usuario,
    utc_now,
)
from app.permissions import require_roles
from app.schemas import (
    DocumentoGovernancaUpdate,
    DocumentoListResponse,
    DocumentoResponse,
    DocumentoSegurancaUpdate,
    DocumentoUpdate,
    EntendimentoDetalheResponse,
    EntendimentoInternoCreate,
    EntendimentoInternoUpdate,
    EntendimentoListItemResponse,
    EntendimentoListResponse,
)
from app.services.document_eligibility import (
    CATEGORIAS_DOCUMENTO,
    SITUACOES_GOVERNANCA,
    TIPOS_ATO,
)
from app.services.document_security import (
    STATUS_SEGURANCA,
)
from app.services.ingestion_service import (
    processar_documento,
)
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/api/documentos",
    tags=["Documentos"],
)

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "documentos"

UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

EXTENSOES_PERMITIDAS = {
    ".pdf",
    ".docx",
    ".txt",
}

TAMANHO_MAXIMO = 50 * 1024 * 1024

GRUPOS = {
    "NORMAS_LEGISLACAO": {
        "NORMA",
        "LEGISLACAO",
    },
    "ENTENDIMENTOS": {
        "ENTENDIMENTO",
    },
    "PROCEDIMENTOS_MANUAIS": {
        "PROCEDIMENTO",
        "MANUAL",
    },
    "MODELOS_MINUTA": {
        "MODELO_MINUTA",
    },
}


def validar_conteudo_arquivo(
    caminho: Path,
    extensao: str,
) -> bool:
    if extensao == ".pdf":
        with caminho.open("rb") as arquivo:
            return arquivo.read(5) == b"%PDF-"

    if extensao == ".docx":
        try:
            with zipfile.ZipFile(
                caminho,
                "r",
            ) as arquivo_zip:
                return "word/document.xml" in arquivo_zip.namelist()
        except zipfile.BadZipFile:
            return False

    if extensao == ".txt":
        try:
            caminho.read_text(
                encoding="utf-8",
            )
            return True
        except UnicodeDecodeError:
            return False

    return False


def _texto_opcional(
    valor: str | None,
) -> str | None:
    if not valor:
        return None

    normalizado = valor.strip()

    return normalizado or None


def _erro_publico(
    documento: Documento,
) -> str | None:
    erro = documento.erro_processamento

    if not erro:
        return None

    if ":\\" in erro or "FileNotFoundError" in erro or "Traceback" in erro:
        return "Falha no processamento. " "Tente reprocessar o documento."

    return erro[:500]


def _caminho_armazenado(
    documento: Documento,
) -> Path | None:
    caminho = Path(documento.caminho_arquivo).resolve()

    try:
        caminho.relative_to(UPLOAD_DIR.resolve())
    except ValueError:
        return None

    return caminho


def _validar_classificacao(
    tipo: str,
    tipo_ato: str | None,
) -> None:
    if tipo not in CATEGORIAS_DOCUMENTO:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_ENTITY),
            detail=("Categoria documental inválida."),
        )

    if tipo == "MODELO_MINUTA" and tipo_ato not in TIPOS_ATO:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_ENTITY),
            detail=("Informe o tipo de ato " "do modelo de minuta."),
        )

    if tipo != "MODELO_MINUTA" and tipo_ato is not None:
        raise HTTPException(
            status_code=(status.HTTP_422_UNPROCESSABLE_ENTITY),
            detail=("Tipo de ato é permitido somente " "para modelo de minuta."),
        )


def _originado_de_revisao(
    db: Session,
    documento_id: UUID,
) -> bool:
    return (
        db.query(ConsultaRevisao.id)
        .filter(ConsultaRevisao.entendimento_documento_id == documento_id)
        .first()
        is not None
    )


def documento_to_response(
    documento: Documento,
) -> DocumentoResponse:
    return DocumentoResponse(
        id=str(documento.id),
        titulo=documento.titulo,
        descricao=documento.descricao,
        tipo=documento.tipo,
        tipo_ato=documento.tipo_ato,
        situacao=documento.situacao,
        orgao_origem=documento.orgao_origem,
        versao=documento.versao,
        jurisdicao=documento.jurisdicao,
        vigencia_inicio=documento.vigencia_inicio,
        vigencia_fim=documento.vigencia_fim,
        observacoes=documento.observacoes,
        nome_arquivo=documento.nome_arquivo,
        status_seguranca=documento.status_seguranca,
        alerta_seguranca=documento.alerta_seguranca,
        ativo=documento.ativo,
        status=documento.status,
        erro_processamento=_erro_publico(documento),
        total_paginas=documento.total_paginas,
        total_chunks=documento.total_chunks,
        situacao_extracao=(documento.situacao_extracao),
        diagnostico_extracao=(documento.diagnostico_extracao),
        processado_em=documento.processado_em,
        criado_por=str(documento.criado_por),
        aprovado_por=(str(documento.aprovado_por) if documento.aprovado_por else None),
        aprovado_em=documento.aprovado_em,
        created_at=documento.created_at,
        updated_at=documento.updated_at,
    )


def entendimento_to_response(
    documento: Documento,
) -> EntendimentoListItemResponse:
    return EntendimentoListItemResponse(
        id=str(documento.id),
        titulo=documento.titulo,
        descricao=documento.descricao,
        situacao=documento.situacao,
        status=documento.status,
        status_seguranca=(documento.status_seguranca),
        ativo=documento.ativo,
        origem=documento.orgao_origem,
        abrangencia=documento.jurisdicao,
        versao=documento.versao,
        aprovado_em=documento.aprovado_em,
        created_at=documento.created_at,
        updated_at=documento.updated_at,
    )


def _entendimento_visivel_para_usuario(
    documento: Documento,
    usuario: Usuario,
) -> bool:
    if documento.tipo != "ENTENDIMENTO":
        return False

    if usuario.role == "ADMIN":
        return True

    return (
        documento.situacao == "APROVADO"
        and documento.ativo
        and documento.status == "PRONTO"
        and documento.status_seguranca == "LIBERADO"
    )


def _condicoes_entendimento_publicado():
    return (
        Documento.situacao == "APROVADO",
        Documento.ativo.is_(True),
        Documento.status == "PRONTO",
        Documento.status_seguranca == "LIBERADO",
    )


def _validar_visibilidade_documento(documento: Documento, usuario: Usuario) -> None:
    if documento.tipo == "ENTENDIMENTO" and not _entendimento_visivel_para_usuario(
        documento, usuario
    ):
        raise HTTPException(status_code=404, detail="Documento não encontrado.")


def _ler_conteudo_entendimento(
    db: Session,
    documento: Documento,
) -> str:
    caminho = _caminho_armazenado(documento)

    if caminho is not None and caminho.is_file() and caminho.suffix.lower() == ".txt":
        try:
            return caminho.read_text(encoding="utf-8").strip()
        except UnicodeDecodeError:
            pass

    paginas = (
        db.query(DocumentoPagina)
        .filter(DocumentoPagina.documento_id == documento.id)
        .order_by(DocumentoPagina.pagina.asc())
        .all()
    )

    return "\n\n".join(
        pagina.conteudo.strip()
        for pagina in paginas
        if pagina.conteudo and pagina.conteudo.strip()
    )


# =========================================================
# NOVOS ENTENDIMENTOS
# =========================================================


@router.get(
    "/entendimentos",
    response_model=EntendimentoListResponse,
)
def listar_entendimentos(
    pagina: int = Query(
        1,
        ge=1,
    ),
    por_pagina: int = Query(
        20,
        ge=1,
        le=100,
    ),
    pesquisa: str | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    consulta = db.query(Documento).filter(Documento.tipo == "ENTENDIMENTO")

    if usuario_atual.role != "ADMIN":
        consulta = consulta.filter(
            *_condicoes_entendimento_publicado(),
        )

    if pesquisa and pesquisa.strip():
        termo = f"%{pesquisa.strip()}%"

        consulta = consulta.filter(
            or_(
                Documento.titulo.ilike(termo),
                Documento.descricao.ilike(termo),
                Documento.orgao_origem.ilike(termo),
            )
        )

    total = consulta.count()

    documentos = (
        consulta.order_by(
            Documento.updated_at.desc(),
            Documento.id.desc(),
        )
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    return EntendimentoListResponse(
        items=[entendimento_to_response(documento) for documento in documentos],
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        total_paginas=(math.ceil(total / por_pagina) if total else 0),
    )


@router.post(
    "/entendimentos",
    response_model=EntendimentoListItemResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def criar_entendimento(
    dados: EntendimentoInternoCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    conteudo = dados.texto_generalizado.strip()

    conteudo_bytes = conteudo.encode("utf-8")

    resumo_hash = hashlib.sha256(conteudo_bytes).hexdigest()

    existente = (
        db.query(Documento).filter(Documento.hash_arquivo == resumo_hash).first()
    )

    if existente:
        raise HTTPException(
            status_code=(status.HTTP_409_CONFLICT),
            detail=("Já existe um documento " "com este mesmo conteúdo."),
        )

    identificador = uuid4()

    nome_arquivo = f"entendimento-" f"{identificador}.txt"

    caminho = UPLOAD_DIR / nome_arquivo

    try:
        caminho.write_bytes(conteudo_bytes)

        documento = Documento(
            titulo=dados.titulo.strip(),
            descricao=("Entendimento interno " "do tabelião."),
            tipo="ENTENDIMENTO",
            tipo_ato=None,
            situacao="RASCUNHO",
            orgao_origem=(dados.origem.strip()),
            versao=(dados.versao.strip()),
            jurisdicao=(dados.abrangencia.strip()),
            observacoes=(_texto_opcional(dados.observacao)),
            nome_arquivo=nome_arquivo,
            caminho_arquivo=str(caminho),
            hash_arquivo=resumo_hash,
            status_seguranca="PENDENTE",
            alerta_seguranca=None,
            ativo=True,
            status="PROCESSANDO",
            criado_por=(usuario_atual.id),
        )

        db.add(documento)

        db.commit()

        db.refresh(documento)

        background_tasks.add_task(
            processar_documento,
            documento.id,
        )

        return entendimento_to_response(documento)

    except HTTPException:
        if caminho.exists():
            caminho.unlink()

        db.rollback()
        raise

    except Exception as erro:
        if caminho.exists():
            caminho.unlink()

        db.rollback()

        raise HTTPException(
            status_code=(status.HTTP_500_INTERNAL_SERVER_ERROR),
            detail=("Não foi possível criar " "o entendimento."),
        ) from erro


@router.get(
    "/entendimentos/{documento_id}",
    response_model=EntendimentoDetalheResponse,
)
def obter_entendimento(
    documento_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    documento = db.get(
        Documento,
        documento_id,
    )

    if not documento or documento.tipo != "ENTENDIMENTO":
        raise HTTPException(
            status_code=404,
            detail=("Entendimento não encontrado."),
        )

    if not _entendimento_visivel_para_usuario(
        documento,
        usuario_atual,
    ):
        raise HTTPException(
            status_code=404,
            detail=("Entendimento não encontrado."),
        )

    conteudo = _ler_conteudo_entendimento(
        db,
        documento,
    )

    return EntendimentoDetalheResponse(
        **entendimento_to_response(documento).model_dump(),
        conteudo=conteudo,
        observacao=documento.observacoes,
    )


@router.patch(
    "/entendimentos/{documento_id}",
    response_model=EntendimentoListItemResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def editar_entendimento(
    documento_id: UUID,
    dados: EntendimentoInternoUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    documento = db.get(
        Documento,
        documento_id,
    )

    if not documento or documento.tipo != "ENTENDIMENTO":
        raise HTTPException(
            status_code=404,
            detail=("Entendimento não encontrado."),
        )

    if documento.status == "PROCESSANDO":
        raise HTTPException(
            status_code=409,
            detail=("Aguarde o processamento atual " "antes de editar o entendimento."),
        )

    caminho = _caminho_armazenado(documento)

    if caminho is None or not caminho.is_file():
        raise HTTPException(
            status_code=409,
            detail=("O arquivo associado ao " "entendimento não foi encontrado."),
        )

    if caminho.suffix.lower() != ".txt":
        raise HTTPException(
            status_code=409,
            detail=(
                "Somente entendimentos em formato "
                "TXT podem ter o conteúdo editado "
                "diretamente nesta área."
            ),
        )

    conteudo = dados.texto_generalizado.strip()

    conteudo_bytes = conteudo.encode("utf-8")

    novo_hash = hashlib.sha256(conteudo_bytes).hexdigest()

    duplicado = (
        db.query(Documento)
        .filter(
            Documento.hash_arquivo == novo_hash,
            Documento.id != documento.id,
        )
        .first()
    )

    if duplicado:
        raise HTTPException(
            status_code=409,
            detail=("Já existe outro documento " "com este mesmo conteúdo."),
        )

    try:
        conteudo_anterior = caminho.read_bytes()
    except OSError as erro:
        raise HTTPException(
            status_code=409,
            detail=("Não foi possível acessar " "o arquivo atual do entendimento."),
        ) from erro

    try:
        caminho.write_bytes(conteudo_bytes)

        documento.titulo = dados.titulo.strip()

        documento.orgao_origem = dados.origem.strip()

        documento.jurisdicao = dados.abrangencia.strip()

        documento.versao = dados.versao.strip()

        documento.observacoes = _texto_opcional(dados.observacao)

        documento.hash_arquivo = novo_hash

        # Toda edição invalida a publicação
        # anterior imediatamente.
        documento.situacao = "RASCUNHO"

        documento.ativo = True

        documento.aprovado_por = None
        documento.aprovado_em = None

        # O documento deixa de ser elegível
        # para o RAG até terminar o novo
        # processamento e ser aprovado outra vez.
        documento.status = "PROCESSANDO"

        documento.erro_processamento = None

        documento.status_seguranca = "PENDENTE"

        documento.alerta_seguranca = None

        documento.situacao_extracao = "PENDENTE_VERIFICACAO"

        documento.diagnostico_extracao = None

        documento.total_paginas = 0
        documento.total_chunks = 0
        documento.processado_em = None

        db.commit()

        db.refresh(documento)

    except Exception as erro:
        db.rollback()

        try:
            caminho.write_bytes(conteudo_anterior)
        except OSError:
            logger.exception(
                "Não foi possível restaurar "
                "o arquivo do entendimento %s "
                "após falha na edição.",
                documento_id,
            )

        raise HTTPException(
            status_code=500,
            detail=("Não foi possível editar " "o entendimento."),
        ) from erro

    background_tasks.add_task(
        processar_documento,
        documento.id,
    )

    return entendimento_to_response(documento)


# =========================================================
# DOCUMENTOS
# =========================================================


@router.get(
    "",
    response_model=DocumentoListResponse,
)
def listar_documentos(
    pagina: int = Query(
        1,
        ge=1,
    ),
    por_pagina: int = Query(
        20,
        ge=1,
        le=100,
    ),
    pesquisa: str | None = None,
    categoria: str | None = None,
    situacao: str | None = None,
    status_processamento: str | None = None,
    situacao_extracao: str | None = None,
    tipo_ato: str | None = None,
    grupo: str | None = None,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    consulta = db.query(Documento)

    if usuario_atual.role != "ADMIN":
        consulta = consulta.filter(
            or_(
                Documento.tipo != "ENTENDIMENTO",
                and_(*_condicoes_entendimento_publicado()),
            )
        )

    if pesquisa and pesquisa.strip():
        termo = f"%{pesquisa.strip()}%"

        consulta = consulta.filter(
            or_(
                Documento.titulo.ilike(termo),
                Documento.nome_arquivo.ilike(termo),
            )
        )

    if categoria:
        consulta = consulta.filter(Documento.tipo == categoria)

    if situacao:
        consulta = consulta.filter(Documento.situacao == situacao)

    if status_processamento:
        consulta = consulta.filter(Documento.status == status_processamento)

    if situacao_extracao:
        consulta = consulta.filter(Documento.situacao_extracao == situacao_extracao)

    if tipo_ato:
        consulta = consulta.filter(Documento.tipo_ato == tipo_ato)

    if grupo in GRUPOS:
        consulta = consulta.filter(Documento.tipo.in_(GRUPOS[grupo]))

    elif grupo == "RASCUNHOS":
        consulta = consulta.filter(Documento.situacao == "RASCUNHO")

    elif grupo == "INATIVOS":
        consulta = consulta.filter(
            Documento.situacao.in_(
                {
                    "REVOGADO",
                    "ARQUIVADO",
                }
            )
        )

    total = consulta.count()

    documentos = (
        consulta.order_by(
            Documento.updated_at.desc(),
            Documento.id.desc(),
        )
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    return DocumentoListResponse(
        items=[documento_to_response(item) for item in documentos],
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        total_paginas=(math.ceil(total / por_pagina) if total else 0),
    )


@router.get(
    "/{documento_id}",
    response_model=DocumentoResponse,
)
def obter_documento(
    documento_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    documento = db.get(
        Documento,
        documento_id,
    )

    if not documento:
        raise HTTPException(
            status_code=404,
            detail=("Documento não encontrado."),
        )

    _validar_visibilidade_documento(documento, usuario_atual)

    return documento_to_response(documento)


@router.post(
    "",
    response_model=DocumentoResponse,
    status_code=202,
)
async def criar_documento(
    background_tasks: BackgroundTasks,
    titulo: str = Form(...),
    descricao: str | None = Form(None),
    tipo: str = Form(...),
    tipo_ato: str | None = Form(None),
    orgao_origem: str | None = Form(None),
    versao: str | None = Form(None),
    jurisdicao: str | None = Form(None),
    vigencia_inicio: date | None = Form(None),
    vigencia_fim: date | None = Form(None),
    observacoes: str | None = Form(None),
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    categoria = tipo.strip().upper()

    ato = _texto_opcional(tipo_ato)

    if ato:
        ato = ato.upper()

    _validar_classificacao(
        categoria,
        ato,
    )

    if vigencia_inicio and vigencia_fim and vigencia_fim < vigencia_inicio:
        raise HTTPException(
            status_code=422,
            detail=("Período de vigência inválido."),
        )

    if not titulo.strip():
        raise HTTPException(
            status_code=400,
            detail=("O título do documento " "é obrigatório."),
        )

    nome_original = Path(arquivo.filename or "").name

    extensao = Path(nome_original).suffix.lower()

    if extensao not in EXTENSOES_PERMITIDAS:
        raise HTTPException(
            status_code=400,
            detail=("Envie um arquivo PDF, " "DOCX ou TXT."),
        )

    caminho = UPLOAD_DIR / f"{uuid4()}{extensao}"

    tamanho_total = 0

    hash_arquivo = hashlib.sha256()

    try:
        with caminho.open("wb") as destino:
            while bloco := await arquivo.read(1024 * 1024):
                tamanho_total += len(bloco)

                if tamanho_total > TAMANHO_MAXIMO:
                    raise HTTPException(
                        status_code=413,
                        detail=("O arquivo excede " "50 MB."),
                    )

                hash_arquivo.update(bloco)

                destino.write(bloco)

        if tamanho_total == 0:
            raise HTTPException(
                status_code=400,
                detail=("O arquivo enviado " "está vazio."),
            )

        if not validar_conteudo_arquivo(
            caminho,
            extensao,
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "O conteúdo do arquivo " "não corresponde ao " "formato informado."
                ),
            )

        resumo_hash = hash_arquivo.hexdigest()

        if db.query(Documento).filter(Documento.hash_arquivo == resumo_hash).first():
            raise HTTPException(
                status_code=409,
                detail=("Este arquivo já " "está cadastrado."),
            )

        documento = Documento(
            titulo=titulo.strip(),
            descricao=_texto_opcional(descricao),
            tipo=categoria,
            tipo_ato=ato,
            situacao="RASCUNHO",
            orgao_origem=_texto_opcional(orgao_origem),
            versao=_texto_opcional(versao),
            jurisdicao=_texto_opcional(jurisdicao),
            vigencia_inicio=(vigencia_inicio),
            vigencia_fim=(vigencia_fim),
            observacoes=_texto_opcional(observacoes),
            nome_arquivo=nome_original,
            caminho_arquivo=str(caminho),
            hash_arquivo=resumo_hash,
            status_seguranca="PENDENTE",
            ativo=True,
            status="PROCESSANDO",
            criado_por=(usuario_atual.id),
        )

        db.add(documento)

        db.commit()

        db.refresh(documento)

        background_tasks.add_task(
            processar_documento,
            documento.id,
        )

        return documento_to_response(documento)

    except HTTPException:
        if caminho.exists():
            caminho.unlink()

        db.rollback()
        raise

    except Exception as erro:
        if caminho.exists():
            caminho.unlink()

        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=("Não foi possível cadastrar " "o documento."),
        ) from erro


@router.patch(
    "/{documento_id}",
    response_model=DocumentoResponse,
)
def editar_documento(
    documento_id: UUID,
    dados: DocumentoUpdate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    documento = db.get(
        Documento,
        documento_id,
    )

    if not documento:
        raise HTTPException(
            status_code=404,
            detail=("Documento não encontrado."),
        )

    alteracoes = dados.model_dump(exclude_unset=True)

    if "titulo" in alteracoes and not str(alteracoes["titulo"] or "").strip():
        raise HTTPException(
            status_code=422,
            detail=("O título do documento " "é obrigatório."),
        )

    categoria = str(
        alteracoes.get(
            "tipo",
            documento.tipo,
        )
    ).upper()

    ato = alteracoes.get(
        "tipo_ato",
        documento.tipo_ato,
    )

    ato = (
        ato.upper()
        if isinstance(
            ato,
            str,
        )
        and ato
        else None
    )

    entendimento_de_revisao = _originado_de_revisao(
        db,
        documento.id,
    )

    if entendimento_de_revisao and categoria != "ENTENDIMENTO":
        raise HTTPException(
            status_code=(status.HTTP_409_CONFLICT),
            detail=(
                "Um entendimento originado "
                "de revisão deve permanecer "
                "classificado como entendimento."
            ),
        )

    if categoria != "MODELO_MINUTA":
        ato = None
        alteracoes["tipo_ato"] = None

    _validar_classificacao(
        categoria,
        ato,
    )

    inicio = alteracoes.get(
        "vigencia_inicio",
        documento.vigencia_inicio,
    )

    fim = alteracoes.get(
        "vigencia_fim",
        documento.vigencia_fim,
    )

    if inicio and fim and fim < inicio:
        raise HTTPException(
            status_code=422,
            detail=("Período de vigência inválido."),
        )

    for campo, valor in alteracoes.items():
        if isinstance(
            valor,
            str,
        ):
            valor = _texto_opcional(valor)

        setattr(
            documento,
            campo,
            valor,
        )

    documento.tipo = categoria
    documento.tipo_ato = ato

    if documento.situacao == "APROVADO" and alteracoes:
        documento.situacao = "RASCUNHO"
        documento.aprovado_por = None
        documento.aprovado_em = None

    db.commit()

    db.refresh(documento)

    return documento_to_response(documento)


@router.patch(
    "/{documento_id}/governanca",
    response_model=DocumentoResponse,
)
def alterar_governanca(
    documento_id: UUID,
    dados: DocumentoGovernancaUpdate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    documento = db.get(
        Documento,
        documento_id,
    )

    if not documento:
        raise HTTPException(
            status_code=404,
            detail=("Documento não encontrado."),
        )

    situacao = dados.situacao.upper()

    if situacao not in SITUACOES_GOVERNANCA:
        raise HTTPException(
            status_code=422,
            detail=("Situação documental inválida."),
        )

    if situacao == "APROVADO":
        entendimento_de_revisao = _originado_de_revisao(
            db,
            documento.id,
        )

        if entendimento_de_revisao and documento.tipo != "ENTENDIMENTO":
            raise HTTPException(
                status_code=(status.HTTP_409_CONFLICT),
                detail=(
                    "O documento originado "
                    "de revisão possui "
                    "classificação inválida "
                    "e não pode ser aprovado."
                ),
            )

        if documento.tipo == "ENTENDIMENTO":
            if usuario_atual.role != "ADMIN":
                raise HTTPException(
                    status_code=403,
                    detail=("Somente o perfil ADMIN " "pode aprovar entendimentos."),
                )

        _validar_classificacao(
            documento.tipo,
            documento.tipo_ato,
        )

        if documento.status != "PRONTO":
            raise HTTPException(
                status_code=409,
                detail=("Apenas documentos " "processados podem ser " "aprovados."),
            )

        if documento.status_seguranca != "LIBERADO":
            raise HTTPException(
                status_code=409,
                detail=(
                    "Conclua a revisão de " "segurança antes de " "aprovar o documento."
                ),
            )

        documento.ativo = True
        documento.aprovado_por = usuario_atual.id
        documento.aprovado_em = utc_now()

    elif situacao in {
        "REVOGADO",
        "ARQUIVADO",
    }:
        documento.ativo = False
        documento.aprovado_por = None
        documento.aprovado_em = None

    else:
        documento.ativo = True
        documento.aprovado_por = None
        documento.aprovado_em = None

    documento.situacao = situacao

    db.commit()

    db.refresh(documento)

    return documento_to_response(documento)


@router.patch(
    "/{documento_id}/seguranca",
    response_model=DocumentoResponse,
)
def alterar_seguranca(
    documento_id: UUID,
    dados: DocumentoSegurancaUpdate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    documento = db.get(
        Documento,
        documento_id,
    )

    if not documento:
        raise HTTPException(
            status_code=404,
            detail=("Documento não encontrado."),
        )

    novo_status = dados.status_seguranca.upper()

    if novo_status not in (STATUS_SEGURANCA - {"REVISAO"}):
        raise HTTPException(
            status_code=422,
            detail=("Situação de segurança inválida."),
        )

    documento.status_seguranca = novo_status

    if novo_status == "PENDENTE" and documento.situacao == "APROVADO":
        documento.situacao = "RASCUNHO"
        documento.aprovado_por = None
        documento.aprovado_em = None

    db.commit()

    db.refresh(documento)

    return documento_to_response(documento)


@router.post(
    "/{documento_id}/processar",
    response_model=DocumentoResponse,
    status_code=202,
)
def reprocessar_documento(
    documento_id: UUID,
    background_tasks: BackgroundTasks,
    forcar_ocr: bool = Query(False),
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    documento = db.get(
        Documento,
        documento_id,
    )

    if not documento:
        raise HTTPException(
            status_code=404,
            detail=("Documento não encontrado."),
        )

    if (
        documento.status == "PROCESSANDO"
        and documento.updated_at > utc_now() - timedelta(minutes=10)
    ):
        raise HTTPException(
            status_code=409,
            detail=("O documento ainda está " "sendo processado."),
        )

    documento.status = "PROCESSANDO"
    documento.status_seguranca = "PENDENTE"
    documento.alerta_seguranca = None
    documento.erro_processamento = None

    db.commit()

    db.refresh(documento)

    background_tasks.add_task(
        processar_documento,
        documento.id,
        forcar_ocr,
    )

    return documento_to_response(documento)


@router.get("/{documento_id}/download")
def baixar_documento(
    documento_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    documento = db.get(
        Documento,
        documento_id,
    )

    if not documento:
        raise HTTPException(
            status_code=404,
            detail=("Documento não encontrado."),
        )

    _validar_visibilidade_documento(documento, usuario_atual)

    caminho = _caminho_armazenado(documento)

    if caminho is None or not caminho.is_file():
        raise HTTPException(
            status_code=404,
            detail=("Arquivo do documento " "não encontrado."),
        )

    tipo, _ = mimetypes.guess_type(documento.nome_arquivo)

    return FileResponse(
        caminho,
        filename=(documento.nome_arquivo),
        media_type=(tipo or "application/octet-stream"),
        headers={
            "Cache-Control": ("private, no-store"),
            "X-Content-Type-Options": ("nosniff"),
        },
    )


@router.delete(
    "/{documento_id}",
    status_code=204,
)
def excluir_documento(
    documento_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    documento = db.get(
        Documento,
        documento_id,
    )

    if not documento:
        raise HTTPException(
            status_code=404,
            detail=("Documento não encontrado."),
        )

    caminho = _caminho_armazenado(documento)

    db.delete(documento)

    db.commit()

    if caminho and caminho.exists():
        try:
            caminho.unlink()

        except OSError:
            logger.warning(
                "Arquivo do documento %s " "não pôde ser removido.",
                documento_id,
            )

    return None
