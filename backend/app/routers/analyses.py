import hashlib
import logging
import math
import mimetypes
import zipfile
from pathlib import Path
from uuid import UUID, uuid4

from app.auth import get_current_user
from app.dependencies import get_db
from app.models import (
    Caso,
    CasoAnalise,
    CasoConferencia,
    CasoDecisao,
    CasoDocumento,
    CasoDocumentoPagina,
    CasoFato,
    CasoMensagem,
    CasoTarefa,
    CasoVersao,
    Usuario,
    utc_now,
)
from app.permissions import require_roles
from app.schemas import (
    CASO_STATUS_VALIDOS,
    TIPOS_DOCUMENTO_CASO_VALIDOS,
    VINCULOS_ATO_VALIDOS,
    CasoAnaliseListResponse,
    CasoAnaliseLoteCreate,
    CasoAnaliseResponse,
    CasoCompraVendaResponse,
    CasoCompraVendaUpdate,
    CasoConferenciaCreate,
    CasoConferenciaListResponse,
    CasoConferenciaResponse,
    CasoCreate,
    CasoDecisaoCreate,
    CasoDecisaoListResponse,
    CasoDecisaoResponse,
    CasoDocumentoClassificacaoUpdate,
    CasoDocumentoDetalheResponse,
    CasoDocumentoListResponse,
    CasoDocumentoPaginaResponse,
    CasoDocumentoResponse,
    CasoDocumentoSegurancaUpdate,
    CasoFatoCreate,
    CasoFatoListResponse,
    CasoFatoResponse,
    CasoListResponse,
    CasoMensagemCreate,
    CasoMensagemListResponse,
    CasoMensagemResponse,
    CasoResponsavelUpdate,
    CasoResponse,
    CasoStatusUpdate,
    CasoTarefaListResponse,
    CasoTarefaResponse,
    CasoUpdate,
)
from app.services.case_chat_service import (
    aguardar_documentos_e_analisar_lote,
    processar_documento_e_responder,
    processar_mensagem_caso,
)
from app.services.case_fact_extraction_service import (
    EXTRATOR_FATOS_VERSION,
    liberar_extracao,
    ollama_configurado_localmente,
    processar_propostas_fatos,
    reservar_extracao,
)
from app.services.case_ingestion_service import (
    liberar_processamento,
    processar_documento_caso,
    reservar_processamento,
)
from app.services.case_legal_analysis_service import gerar_analise_caso
from app.services.case_task_service import (
    concluir_tarefa,
    falhar_tarefa,
    iniciar_tarefa,
)
from app.services.purchase_sale_service import (
    avaliar_limites_valor,
    dados_vazios,
    gerar_qualificacoes,
    liberar_extracao_compra_venda,
    processar_compra_venda,
    reservar_extracao_compra_venda,
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
from sqlalchemy import and_, func, or_, text
from sqlalchemy.orm import Session

router = APIRouter(
    prefix="/api/analises",
    tags=["Análises"],
)


logger = logging.getLogger(__name__)


UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads" / "analises"

UPLOAD_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


EXTENSOES_PERMITIDAS = {
    ".pdf",
    ".docx",
    ".txt",
    ".jpg",
    ".jpeg",
    ".png",
}


TAMANHO_MAXIMO = 50 * 1024 * 1024


def _caso_acessivel(
    caso: Caso,
    usuario: Usuario,
) -> bool:
    """
    ADMIN pode consultar todos os casos.

    Usuário comum pode consultar casos:
    - criados por ele; ou
    - atribuídos a ele como responsável.
    """

    if usuario.role == "ADMIN":
        return True

    return caso.criado_por == usuario.id or caso.responsavel_id == usuario.id


def _obter_caso_acessivel(
    db: Session,
    caso_id: UUID,
    usuario: Usuario,
) -> Caso:
    caso = db.get(
        Caso,
        caso_id,
    )

    if not caso or not _caso_acessivel(
        caso,
        usuario,
    ):
        raise HTTPException(
            status_code=404,
            detail="Caso não encontrado.",
        )

    return caso


def _obter_caso_gerenciavel(
    db: Session,
    caso_id: UUID,
    usuario: Usuario,
) -> Caso:
    """Restringe ações destrutivas ao criador do caso ou ao ADMIN."""

    caso = _obter_caso_acessivel(db, caso_id, usuario)
    if usuario.role != "ADMIN" and caso.criado_por != usuario.id:
        raise HTTPException(status_code=404, detail="Caso não encontrado.")
    return caso


def _obter_documento_caso(
    db: Session,
    caso: Caso,
    documento_id: UUID,
) -> CasoDocumento:
    documento = db.get(
        CasoDocumento,
        documento_id,
    )

    if documento is None or documento.caso_id != caso.id:
        raise HTTPException(
            status_code=404,
            detail=("Documento do caso " "não encontrado."),
        )

    return documento


def _nome_usuario(
    db: Session,
    usuario_id: UUID | None,
) -> str | None:
    if usuario_id is None:
        return None

    usuario = db.get(
        Usuario,
        usuario_id,
    )

    if not usuario:
        return None

    return usuario.nome


def _erro_documento_publico(
    documento: CasoDocumento,
) -> str | None:
    erro = documento.erro_processamento

    if not erro:
        return None

    if ":\\" in erro or "FileNotFoundError" in erro or "Traceback" in erro:
        return "Falha no processamento. " "Tente novamente."

    return erro[:500]


def _caminho_documento_caso(
    documento: CasoDocumento,
) -> Path | None:
    caminho = Path(documento.caminho_arquivo).resolve()

    pasta_esperada = (UPLOAD_DIR / str(documento.caso_id)).resolve()

    try:
        caminho.relative_to(pasta_esperada)

    except ValueError:
        return None

    return caminho


def _validar_conteudo_arquivo(
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

    if extensao in {".jpg", ".jpeg", ".png"}:
        with caminho.open("rb") as arquivo:
            assinatura = arquivo.read(8)
        if extensao == ".png":
            return assinatura == b"\x89PNG\r\n\x1a\n"
        return assinatura.startswith(b"\xff\xd8\xff")

    return False


def _normalizar_tipo_documento(
    valor: str | None,
) -> str | None:
    if valor is None:
        return None

    normalizado = valor.strip().upper()

    if not normalizado:
        return None

    if normalizado not in TIPOS_DOCUMENTO_CASO_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=("Tipo de documento " "do caso inválido."),
        )

    return normalizado


def _normalizar_vinculo_ato(
    valor: str | None,
) -> str | None:
    if valor is None:
        return None

    normalizado = valor.strip().upper()

    if not normalizado:
        return None

    if normalizado not in VINCULOS_ATO_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=("Vínculo do documento " "com o ato inválido."),
        )

    return normalizado


def _caso_documento_to_response(
    documento: CasoDocumento,
) -> CasoDocumentoResponse:
    return CasoDocumentoResponse(
        id=str(documento.id),
        caso_id=str(documento.caso_id),
        nome_arquivo=(documento.nome_arquivo),
        mime_type=(documento.mime_type),
        tamanho_bytes=(documento.tamanho_bytes),
        tipo_documento=(documento.tipo_documento),
        vinculo_ato=(documento.vinculo_ato),
        status=documento.status,
        status_seguranca=(documento.status_seguranca),
        alerta_seguranca=(documento.alerta_seguranca),
        seguranca_liberada_por=(
            str(documento.seguranca_liberada_por)
            if documento.seguranca_liberada_por
            else None
        ),
        seguranca_liberada_em=(documento.seguranca_liberada_em),
        erro_processamento=(_erro_documento_publico(documento)),
        total_paginas=(documento.total_paginas),
        situacao_extracao=(documento.situacao_extracao),
        diagnostico_extracao=(documento.diagnostico_extracao),
        processado_em=(documento.processado_em),
        status_extracao_fatos=(documento.status_extracao_fatos),
        erro_extracao_fatos=(documento.erro_extracao_fatos),
        diagnostico_extracao_fatos=(documento.diagnostico_extracao_fatos),
        fatos_extraidos_em=(documento.fatos_extraidos_em),
        versao_extrator_fatos=(documento.versao_extrator_fatos),
        criado_por=str(documento.criado_por),
        created_at=(documento.created_at),
        updated_at=(documento.updated_at),
    )


def _pagina_to_response(
    pagina: CasoDocumentoPagina,
) -> CasoDocumentoPaginaResponse:
    return CasoDocumentoPaginaResponse(
        id=str(pagina.id),
        caso_documento_id=str(pagina.caso_documento_id),
        pagina=pagina.pagina,
        pagina_confiavel=(pagina.pagina_confiavel),
        localizacao=(pagina.localizacao),
        conteudo=(pagina.conteudo),
        metodo_extracao=(pagina.metodo_extracao),
        situacao_extracao=(pagina.situacao_extracao),
        created_at=(pagina.created_at),
    )


def _caso_to_response(
    db: Session,
    caso: Caso,
) -> CasoResponse:
    total_documentos = (
        db.query(CasoDocumento.id).filter(CasoDocumento.caso_id == caso.id).count()
    )

    total_fatos = (
        db.query(CasoFato.id)
        .filter(
            CasoFato.caso_id == caso.id,
            CasoFato.ativo.is_(True),
        )
        .count()
    )

    total_pendentes = (
        db.query(CasoFato.id)
        .filter(
            CasoFato.caso_id == caso.id,
            CasoFato.ativo.is_(True),
            CasoFato.estado_conferencia == "PENDENTE",
        )
        .count()
    )

    total_conflitantes = (
        db.query(CasoFato.id)
        .filter(
            CasoFato.caso_id == caso.id,
            CasoFato.ativo.is_(True),
            CasoFato.estado_evidencia == "CONFLITANTE",
        )
        .count()
    )

    return CasoResponse(
        id=str(caso.id),
        titulo=caso.titulo,
        identificacao=caso.identificacao,
        tipo_ato=caso.tipo_ato,
        descricao=caso.descricao,
        status=caso.status,
        criado_por=str(caso.criado_por),
        criado_por_nome=_nome_usuario(
            db,
            caso.criado_por,
        ),
        responsavel_id=(str(caso.responsavel_id) if caso.responsavel_id else None),
        responsavel_nome=_nome_usuario(
            db,
            caso.responsavel_id,
        ),
        total_documentos=(total_documentos),
        total_fatos=total_fatos,
        total_pendentes_conferencia=(total_pendentes),
        total_conflitantes=(total_conflitantes),
        encerrado_em=(caso.encerrado_em),
        created_at=(caso.created_at),
        updated_at=(caso.updated_at),
    )


def _compra_venda_to_response(caso: Caso) -> CasoCompraVendaResponse:
    dados = dict(caso.dados_ato or dados_vazios())
    dados.pop("_diagnostico", None)
    qualificacoes, pendencias = gerar_qualificacoes(dados)
    return CasoCompraVendaResponse(
        **dados,
        status=caso.status_dados_ato,
        erro=caso.erro_dados_ato,
        atualizado_em=caso.dados_ato_atualizados_em,
        qualificacoes=qualificacoes,
        pendencias=pendencias,
        alertas_valor=avaliar_limites_valor(dados),
    )


def _validar_fontes_compra_venda(db: Session, caso: Caso, dados: dict) -> None:
    ids = set()
    for parte in dados.get("partes", []):
        ids.update(str(fonte["documento_id"]) for fonte in parte.get("fontes", []))
    imovel = dados.get("imovel", {})
    ids.update(str(fonte["documento_id"]) for fonte in imovel.get("fontes", []))
    ids.update(
        str(item["fonte"]["documento_id"])
        for item in imovel.get("averbacoes", [])
        if item.get("fonte")
    )
    ids.update(
        str(fonte["documento_id"])
        for fonte in (dados.get("negocio") or {}).get("fontes", [])
    )
    if not ids:
        return
    encontrados = {
        str(item[0])
        for item in db.query(CasoDocumento.id).filter(
            CasoDocumento.caso_id == caso.id,
            CasoDocumento.id.in_([UUID(item) for item in ids]),
        )
    }
    if encontrados != ids:
        raise HTTPException(
            status_code=422,
            detail="Uma fonte informada não pertence a este caso.",
        )


def _fato_to_response(fato: CasoFato) -> CasoFatoResponse:
    return CasoFatoResponse(
        id=str(fato.id),
        caso_id=str(fato.caso_id),
        caso_documento_id=(
            str(fato.caso_documento_id) if fato.caso_documento_id else None
        ),
        campo=fato.campo,
        categoria=fato.categoria,
        locus=fato.locus,
        valor_original=fato.valor_original,
        valor_atual=fato.valor_atual,
        proveniencia=fato.proveniencia,
        estado_evidencia=fato.estado_evidencia,
        estado_conferencia=fato.estado_conferencia,
        pagina=fato.pagina,
        localizacao=fato.localizacao,
        trecho_fonte=fato.trecho_fonte,
        metodo_extracao=fato.metodo_extracao,
        contexto=fato.contexto,
        ativo=fato.ativo,
        registrado_por=str(fato.registrado_por) if fato.registrado_por else None,
        created_at=fato.created_at,
        updated_at=fato.updated_at,
    )


def _conferencia_to_response(
    db: Session, conferencia: CasoConferencia
) -> CasoConferenciaResponse:
    return CasoConferenciaResponse(
        id=str(conferencia.id),
        caso_id=str(conferencia.caso_id),
        fato_id=str(conferencia.fato_id),
        usuario_id=str(conferencia.usuario_id) if conferencia.usuario_id else None,
        usuario_nome=_nome_usuario(db, conferencia.usuario_id),
        acao=conferencia.acao,
        valor_anterior=conferencia.valor_anterior,
        valor_novo=conferencia.valor_novo,
        observacao=conferencia.observacao,
        created_at=conferencia.created_at,
    )


def _analise_to_response(db: Session, analise: CasoAnalise) -> CasoAnaliseResponse:
    versao = db.get(CasoVersao, analise.versao_id)
    return CasoAnaliseResponse(
        id=str(analise.id),
        caso_id=str(analise.caso_id),
        versao_id=str(analise.versao_id),
        versao_numero=versao.numero if versao else 0,
        status_evidencia=analise.status_evidencia,
        resumo=analise.resumo,
        requisitos=analise.requisitos or [],
        impedimentos=analise.impedimentos or [],
        pendencias=analise.pendencias or [],
        fontes=analise.fontes_snapshot or [],
        prompt_version=analise.prompt_version,
        modelo_ia=analise.modelo_ia,
        gerado_por=str(analise.gerado_por) if analise.gerado_por else None,
        created_at=analise.created_at,
    )


def _decisao_to_response(db: Session, decisao: CasoDecisao) -> CasoDecisaoResponse:
    return CasoDecisaoResponse(
        id=str(decisao.id),
        caso_id=str(decisao.caso_id),
        analise_id=str(decisao.analise_id),
        decisao=decisao.decisao,
        texto=decisao.texto,
        fundamentacao=decisao.fundamentacao,
        escopo=decisao.escopo,
        decidido_por=str(decisao.decidido_por) if decisao.decidido_por else None,
        decidido_por_nome=_nome_usuario(db, decisao.decidido_por),
        created_at=decisao.created_at,
    )


def _obter_fato_caso(db: Session, caso: Caso, fato_id: UUID) -> CasoFato:
    fato = db.get(CasoFato, fato_id)
    if fato is None or fato.caso_id != caso.id or not fato.ativo:
        raise HTTPException(status_code=404, detail="Fato do caso não encontrado.")
    return fato


def _mensagem_to_response(mensagem: CasoMensagem) -> CasoMensagemResponse:
    return CasoMensagemResponse(
        id=str(mensagem.id),
        caso_id=str(mensagem.caso_id),
        papel=mensagem.papel,
        conteudo=mensagem.conteudo,
        usuario_id=str(mensagem.usuario_id) if mensagem.usuario_id else None,
        analise_id=str(mensagem.analise_id) if mensagem.analise_id else None,
        created_at=mensagem.created_at,
    )


def _tarefa_to_response(tarefa: CasoTarefa) -> CasoTarefaResponse:
    return CasoTarefaResponse(
        id=str(tarefa.id),
        caso_id=str(tarefa.caso_id),
        caso_documento_id=(
            str(tarefa.caso_documento_id) if tarefa.caso_documento_id else None
        ),
        tipo=tarefa.tipo,
        status=tarefa.status,
        tentativa=tarefa.tentativa,
        erro=tarefa.erro,
        iniciado_em=tarefa.iniciado_em,
        concluido_em=tarefa.concluido_em,
        created_at=tarefa.created_at,
    )


def _criar_tarefa(
    db: Session,
    caso: Caso,
    tipo: str,
    usuario_id: UUID,
    caso_documento_id: UUID | None = None,
) -> CasoTarefa:
    tarefa = CasoTarefa(
        caso_id=caso.id,
        caso_documento_id=caso_documento_id,
        tipo=tipo,
        status="PENDENTE",
        tentativa=0,
        criado_por=usuario_id,
    )
    db.add(tarefa)
    db.flush()
    return tarefa


def _caso_tem_tarefa_ativa(db: Session, caso_id: UUID) -> bool:
    return (
        db.query(CasoTarefa.id)
        .filter(
            CasoTarefa.caso_id == caso_id,
            CasoTarefa.status.in_(["PENDENTE", "PROCESSANDO"]),
        )
        .first()
        is not None
    )


def _validar_titulo_unico(
    db: Session,
    titulo: str,
    ignorar_caso_id: UUID | None = None,
) -> None:
    titulo_normalizado = titulo.strip().casefold()

    # Serialize writes for the same title in PostgreSQL, closing the race
    # between the duplicate check and the subsequent insert/update.
    if db.get_bind().dialect.name == "postgresql":
        lock_id = int.from_bytes(
            hashlib.sha256(titulo_normalizado.encode("utf-8")).digest()[:8],
            byteorder="big",
            signed=True,
        )
        db.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": lock_id},
        )

    consulta = db.query(Caso.id).filter(
        func.lower(func.trim(Caso.titulo)) == titulo_normalizado
    )
    if ignorar_caso_id is not None:
        consulta = consulta.filter(Caso.id != ignorar_caso_id)

    if consulta.first() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Já existe uma análise com esse número de processo. "
                "Abra o caso existente ou confira o número informado."
            ),
        )


# =========================================================
# CASOS
# =========================================================


@router.post(
    "/casos",
    response_model=CasoResponse,
    status_code=(status.HTTP_201_CREATED),
)
def criar_caso(
    dados: CasoCreate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    _validar_titulo_unico(db, dados.titulo)

    caso = Caso(
        titulo=dados.titulo,
        identificacao=(dados.identificacao),
        tipo_ato=dados.tipo_ato,
        descricao=dados.descricao,
        status="EM_PREPARACAO",
        criado_por=(usuario_atual.id),
        responsavel_id=(usuario_atual.id),
    )

    db.add(caso)

    try:
        db.commit()
        db.refresh(caso)

    except Exception as erro:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=("Não foi possível " "criar o caso."),
        ) from erro

    return _caso_to_response(
        db,
        caso,
    )


@router.get(
    "/casos",
    response_model=CasoListResponse,
)
def listar_casos(
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
    status_caso: str | None = Query(
        default=None,
        alias="status",
    ),
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    consulta = db.query(Caso)

    if usuario_atual.role != "ADMIN":
        consulta = consulta.filter(
            or_(
                Caso.criado_por == usuario_atual.id,
                Caso.responsavel_id == usuario_atual.id,
            )
        )

    if pesquisa and pesquisa.strip():
        termo = f"%{pesquisa.strip()}%"

        consulta = consulta.filter(
            or_(
                Caso.titulo.ilike(termo),
                Caso.identificacao.ilike(termo),
                Caso.tipo_ato.ilike(termo),
            )
        )

    if status_caso:
        status_normalizado = status_caso.strip().upper()

        if status_normalizado not in CASO_STATUS_VALIDOS:
            raise HTTPException(
                status_code=422,
                detail=("Situação do caso " "inválida."),
            )

        consulta = consulta.filter(Caso.status == status_normalizado)

    total = consulta.count()

    casos = (
        consulta.order_by(
            Caso.updated_at.desc(),
            Caso.id.desc(),
        )
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    return CasoListResponse(
        items=[
            _caso_to_response(
                db,
                caso,
            )
            for caso in casos
        ],
        total=total,
        pagina=pagina,
        por_pagina=por_pagina,
        total_paginas=(math.ceil(total / por_pagina) if total else 0),
    )


@router.get(
    "/casos/{caso_id}",
    response_model=CasoResponse,
)
def obter_caso(
    caso_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(
        db,
        caso_id,
        usuario_atual,
    )

    return _caso_to_response(
        db,
        caso,
    )


@router.patch(
    "/casos/{caso_id}",
    response_model=CasoResponse,
)
def editar_caso(
    caso_id: UUID,
    dados: CasoUpdate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(
        db,
        caso_id,
        usuario_atual,
    )

    if caso.status not in {"EM_PREPARACAO", "AGUARDANDO_CONFERENCIA"}:
        raise HTTPException(
            status_code=409,
            detail=("Retorne o caso à preparação ou conferência antes de editá-lo."),
        )

    alteracoes = dados.model_dump(exclude_unset=True)

    if "titulo" in alteracoes and alteracoes["titulo"] is None:
        raise HTTPException(
            status_code=422,
            detail=("O título do caso " "não pode ser removido."),
        )

    if "titulo" in alteracoes:
        _validar_titulo_unico(db, alteracoes["titulo"], ignorar_caso_id=caso.id)

    for (
        campo,
        valor,
    ) in alteracoes.items():
        setattr(
            caso,
            campo,
            valor,
        )

    try:
        db.commit()
        db.refresh(caso)

    except Exception as erro:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=("Não foi possível " "editar o caso."),
        ) from erro

    return _caso_to_response(
        db,
        caso,
    )


@router.get(
    "/casos/{caso_id}/compra-venda",
    response_model=CasoCompraVendaResponse,
)
def obter_dados_compra_venda(
    caso_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    if caso.tipo_ato != "COMPRA_VENDA":
        raise HTTPException(status_code=409, detail="O caso não é de Compra e Venda.")
    return _compra_venda_to_response(caso)


@router.put(
    "/casos/{caso_id}/compra-venda",
    response_model=CasoCompraVendaResponse,
)
def salvar_dados_compra_venda(
    caso_id: UUID,
    dados: CasoCompraVendaUpdate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    if caso.tipo_ato != "COMPRA_VENDA":
        raise HTTPException(status_code=409, detail="O caso não é de Compra e Venda.")
    if caso.status not in {"EM_PREPARACAO", "AGUARDANDO_CONFERENCIA"}:
        raise HTTPException(
            status_code=409,
            detail="Os dados só podem ser editados durante a preparação ou conferência.",
        )
    payload = dados.model_dump(mode="json")
    _validar_fontes_compra_venda(db, caso, payload)
    diagnostico = (caso.dados_ato or {}).get("_diagnostico")
    if isinstance(diagnostico, dict):
        payload["_diagnostico"] = diagnostico
    gerar_qualificacoes(payload)  # Também aplica a regra determinística da descrição.
    caso.dados_ato = payload
    caso.status_dados_ato = "PRONTO"
    caso.erro_dados_ato = None
    caso.dados_ato_atualizados_em = utc_now()
    caso.status = "AGUARDANDO_CONFERENCIA"
    caso.updated_at = utc_now()
    try:
        db.commit()
        db.refresh(caso)
    except Exception as erro:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Não foi possível salvar os dados de Compra e Venda.",
        ) from erro
    return _compra_venda_to_response(caso)


@router.post(
    "/casos/{caso_id}/compra-venda/extrair",
    response_model=CasoCompraVendaResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def extrair_dados_compra_venda(
    caso_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    if caso.tipo_ato != "COMPRA_VENDA":
        raise HTTPException(status_code=409, detail="O caso não é de Compra e Venda.")
    if caso.status not in {"EM_PREPARACAO", "AGUARDANDO_CONFERENCIA"}:
        raise HTTPException(
            status_code=409,
            detail="A extração só pode ocorrer durante a preparação ou conferência.",
        )
    if not ollama_configurado_localmente():
        raise HTTPException(
            status_code=503,
            detail="A análise de documentos privados exige o Ollama configurado localmente.",
        )
    elegiveis = (
        db.query(CasoDocumento.id)
        .filter(
            CasoDocumento.caso_id == caso.id,
            CasoDocumento.status == "PRONTO",
            CasoDocumento.status_seguranca == "LIBERADO",
            CasoDocumento.situacao_extracao == "PROCESSADO_COMPLETO",
        )
        .all()
    )
    if not elegiveis:
        raise HTTPException(
            status_code=409,
            detail="Adicione e processe ao menos um documento liberado antes da extração.",
        )
    possui_texto = (
        db.query(CasoDocumentoPagina.id)
        .join(CasoDocumento, CasoDocumento.id == CasoDocumentoPagina.caso_documento_id)
        .filter(
            CasoDocumento.caso_id == caso.id,
            CasoDocumento.status == "PRONTO",
            CasoDocumento.status_seguranca == "LIBERADO",
            CasoDocumentoPagina.conteudo != "",
        )
        .first()
    )
    if possui_texto is None:
        raise HTTPException(
            status_code=409, detail="Os documentos não possuem texto disponível."
        )
    if not reservar_extracao_compra_venda(caso.id):
        raise HTTPException(
            status_code=409, detail="A extração estruturada já está em andamento."
        )
    try:
        caso.status_dados_ato = "PROCESSANDO"
        caso.erro_dados_ato = None
        caso.dados_ato_atualizados_em = utc_now()
        tarefa = _criar_tarefa(
            db,
            caso,
            "ANALISE_DOCUMENTAL_A2",
            usuario_atual.id,
        )
        db.commit()
        db.refresh(caso)
    except Exception as erro:
        db.rollback()
        liberar_extracao_compra_venda(caso.id)
        raise HTTPException(
            status_code=500, detail="Não foi possível agendar a extração."
        ) from erro
    background_tasks.add_task(processar_compra_venda, caso.id, tarefa.id)
    return _compra_venda_to_response(caso)


@router.patch(
    "/casos/{caso_id}/responsavel",
    response_model=CasoResponse,
)
def atribuir_responsavel_caso(
    caso_id: UUID,
    dados: CasoResponsavelUpdate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    if caso.status == "ENCERRADO":
        raise HTTPException(
            status_code=409, detail="Um caso encerrado não pode ser reatribuído."
        )
    responsavel = None
    if dados.responsavel_id is not None:
        responsavel = db.get(Usuario, dados.responsavel_id)
        if responsavel is None or not responsavel.ativo:
            raise HTTPException(
                status_code=422, detail="Responsável não encontrado ou inativo."
            )
    caso.responsavel_id = responsavel.id if responsavel else None
    try:
        db.commit()
        db.refresh(caso)
    except Exception as erro:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Não foi possível atribuir o responsável."
        ) from erro
    return _caso_to_response(db, caso)


@router.patch(
    "/casos/{caso_id}/status",
    response_model=CasoResponse,
)
def alterar_status_caso(
    caso_id: UUID,
    dados: CasoStatusUpdate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(
        db,
        caso_id,
        usuario_atual,
    )

    status_atual = caso.status
    novo_status = dados.status

    if novo_status == "ENCERRADO" and status_atual != "ENCERRADO":
        if _caso_tem_tarefa_ativa(db, caso.id):
            raise HTTPException(
                status_code=409,
                detail="Aguarde o processamento dos documentos antes de concluir o caso.",
            )

    # A análise jurídica e a decisão permanecem reservadas a A1/TAB.
    if novo_status in {"ANALISE_DISPONIVEL", "DECISAO_REGISTRADA"}:
        if novo_status != status_atual:
            raise HTTPException(
                status_code=409,
                detail="Esta etapa depende da conferência e análise ainda não disponíveis. O caso permanece na preparação/conferência.",
            )

    if novo_status == "PRONTO_PARA_ANALISE" and novo_status != status_atual:
        documentos_invalidos = (
            db.query(CasoDocumento.id)
            .filter(
                CasoDocumento.caso_id == caso.id,
                or_(
                    CasoDocumento.status != "PRONTO",
                    CasoDocumento.status_seguranca != "LIBERADO",
                    CasoDocumento.situacao_extracao != "PROCESSADO_COMPLETO",
                ),
            )
            .first()
        )
        total_fatos = (
            db.query(CasoFato.id)
            .filter(
                CasoFato.caso_id == caso.id,
                CasoFato.ativo.is_(True),
            )
            .count()
        )
        fato_pendente = (
            db.query(CasoFato.id)
            .filter(
                CasoFato.caso_id == caso.id,
                CasoFato.ativo.is_(True),
                CasoFato.estado_conferencia == "PENDENTE",
            )
            .first()
        )
        dados_compra_venda = caso.dados_ato if caso.tipo_ato == "COMPRA_VENDA" else None
        possui_estado_estruturado = bool(
            isinstance(dados_compra_venda, dict)
            and (
                dados_compra_venda.get("partes")
                or (dados_compra_venda.get("imovel") or {}).get("matricula")
                or (dados_compra_venda.get("imovel") or {}).get("descricao_completa")
            )
        )
        estrutura_pendente = False
        if possui_estado_estruturado:
            partes_estruturadas = dados_compra_venda.get("partes") or []
            possui_limite_representacao = any(
                parte.get("modo_qualificacao") in {"PROCURACAO", "ALVARA_JUDICIAL"}
                and any(
                    (parte.get(grupo) or {}).get(campo)
                    for grupo in ("procuracao", "alvara")
                    for campo in ("valor_minimo", "valor_maximo")
                )
                for parte in partes_estruturadas
            )
            negocio = dados_compra_venda.get("negocio") or {}
            estrutura_pendente = (
                not partes_estruturadas
                or any(not parte.get("confirmado") for parte in partes_estruturadas)
                or not (dados_compra_venda.get("imovel") or {}).get("confirmado")
                or (
                    possui_limite_representacao
                    and (
                        not negocio.get("valor_escritura")
                        or not negocio.get("confirmado")
                    )
                )
            )
        if (
            documentos_invalidos
            or (not total_fatos and not possui_estado_estruturado)
            or fato_pendente
            or estrutura_pendente
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Para concluir a conferência, todos os documentos devem estar "
                    "integralmente processados e liberados, e os fatos e dados estruturados "
                    "precisam de confirmação humana. Campos ausentes podem permanecer como pendência."
                ),
            )

    transicoes_permitidas = {
        "EM_PREPARACAO": {
            "AGUARDANDO_CONFERENCIA",
            "ENCERRADO",
        },
        "AGUARDANDO_CONFERENCIA": {
            "EM_PREPARACAO",
            "PRONTO_PARA_ANALISE",
            "ENCERRADO",
        },
        "PRONTO_PARA_ANALISE": {
            "AGUARDANDO_CONFERENCIA",
            "ANALISE_DISPONIVEL",
            "ENCERRADO",
        },
        "ANALISE_DISPONIVEL": {
            "PRONTO_PARA_ANALISE",
            "DECISAO_REGISTRADA",
            "ENCERRADO",
        },
        "DECISAO_REGISTRADA": {
            "ANALISE_DISPONIVEL",
            "ENCERRADO",
        },
        "ENCERRADO": {"EM_PREPARACAO"},
    }

    if novo_status == status_atual:
        return _caso_to_response(
            db,
            caso,
        )

    permitidos = transicoes_permitidas.get(
        status_atual,
        set(),
    )

    if novo_status not in permitidos:
        raise HTTPException(
            status_code=409,
            detail=("Transição de situação " "do caso não permitida."),
        )

    caso.status = novo_status

    if novo_status == "ENCERRADO":
        caso.encerrado_em = utc_now()

    else:
        caso.encerrado_em = None

    try:
        db.commit()
        db.refresh(caso)

    except Exception as erro:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=("Não foi possível " "alterar a situação " "do caso."),
        ) from erro

    return _caso_to_response(
        db,
        caso,
    )


@router.delete(
    "/casos/{caso_id}",
    status_code=(status.HTTP_204_NO_CONTENT),
)
def excluir_caso(
    caso_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_gerenciavel(
        db,
        caso_id,
        usuario_atual,
    )

    if caso.status != "EM_PREPARACAO":
        raise HTTPException(
            status_code=409,
            detail=(
                "Somente casos em preparação "
                "podem ser excluídos. "
                "Para os demais casos, utilize "
                "o encerramento."
            ),
        )

    possui_fatos = (
        db.query(CasoFato.id).filter(CasoFato.caso_id == caso.id).first() is not None
    )

    if possui_fatos:
        raise HTTPException(
            status_code=409,
            detail=(
                "Este caso já possui fatos "
                "registrados e não pode ser "
                "excluído definitivamente."
            ),
        )

    documentos = db.query(CasoDocumento).filter(CasoDocumento.caso_id == caso.id).all()

    if any(documento.status == "PROCESSANDO" for documento in documentos):
        raise HTTPException(
            status_code=409,
            detail=(
                "Aguarde o processamento dos " "documentos antes de excluir " "o caso."
            ),
        )

    caminhos: list[Path] = []

    for documento in documentos:
        caminho = _caminho_documento_caso(documento)

        if caminho is not None:
            caminhos.append(caminho)

    pasta_caso = (UPLOAD_DIR / str(caso.id)).resolve()

    try:
        db.delete(caso)

        db.commit()

    except Exception as erro:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=("Não foi possível excluir " "o caso."),
        ) from erro

    for caminho in caminhos:
        if not caminho.exists():
            continue

        try:
            caminho.unlink()

        except OSError:
            logger.warning(
                "Arquivo %s não pôde ser " "removido após a exclusão " "do caso %s.",
                caminho,
                caso_id,
            )

    if pasta_caso.exists():
        try:
            pasta_caso.rmdir()

        except OSError:
            logger.warning(
                "A pasta do caso %s não "
                "pôde ser removida porque "
                "ainda contém arquivos.",
                caso_id,
            )

    return None


# =========================================================
# A2 — FATOS E CONFERÊNCIA HUMANA
# =========================================================


@router.get("/casos/{caso_id}/fatos", response_model=CasoFatoListResponse)
def listar_fatos_caso(
    caso_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    fatos = (
        db.query(CasoFato)
        .filter(
            CasoFato.caso_id == caso.id,
            CasoFato.ativo.is_(True),
        )
        .order_by(CasoFato.created_at.asc(), CasoFato.id.asc())
        .all()
    )
    return CasoFatoListResponse(
        items=[_fato_to_response(fato) for fato in fatos], total=len(fatos)
    )


@router.post(
    "/casos/{caso_id}/fatos",
    response_model=CasoFatoResponse,
    status_code=status.HTTP_201_CREATED,
)
def registrar_fato_caso(
    caso_id: UUID,
    dados: CasoFatoCreate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    if caso.status not in {"EM_PREPARACAO", "AGUARDANDO_CONFERENCIA"}:
        raise HTTPException(
            status_code=409,
            detail="Fatos só podem ser registrados durante a preparação ou conferência.",
        )

    documento = None
    if dados.caso_documento_id is not None:
        documento = _obter_documento_caso(db, caso, dados.caso_documento_id)
        if dados.pagina is not None:
            pagina_existe = (
                db.query(CasoDocumentoPagina.id)
                .filter(
                    CasoDocumentoPagina.caso_documento_id == documento.id,
                    CasoDocumentoPagina.pagina == dados.pagina,
                )
                .first()
            )
            if pagina_existe is None:
                raise HTTPException(
                    status_code=422,
                    detail="A página informada não pertence ao documento selecionado.",
                )

    fato = CasoFato(
        caso_id=caso.id,
        caso_documento_id=documento.id if documento else None,
        campo=dados.campo,
        categoria=dados.categoria,
        locus=dados.locus or "CORINGA",
        valor_original=dados.valor,
        valor_atual=dados.valor,
        proveniencia=dados.proveniencia,
        estado_evidencia=dados.estado_evidencia,
        estado_conferencia="PENDENTE",
        pagina=dados.pagina,
        localizacao=dados.localizacao,
        trecho_fonte=dados.trecho_fonte,
        metodo_extracao=dados.metodo_extracao,
        contexto=dados.contexto,
        ativo=True,
        registrado_por=usuario_atual.id,
    )
    db.add(fato)
    if caso.status == "EM_PREPARACAO":
        caso.status = "AGUARDANDO_CONFERENCIA"
    try:
        db.commit()
        db.refresh(fato)
    except Exception as erro:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Não foi possível registrar o fato."
        ) from erro
    return _fato_to_response(fato)


@router.get(
    "/casos/{caso_id}/fatos/{fato_id}/conferencias",
    response_model=CasoConferenciaListResponse,
)
def listar_conferencias_fato(
    caso_id: UUID,
    fato_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    fato = _obter_fato_caso(db, caso, fato_id)
    conferencias = (
        db.query(CasoConferencia)
        .filter(
            CasoConferencia.caso_id == caso.id,
            CasoConferencia.fato_id == fato.id,
        )
        .order_by(CasoConferencia.created_at.asc(), CasoConferencia.id.asc())
        .all()
    )
    return CasoConferenciaListResponse(
        items=[_conferencia_to_response(db, item) for item in conferencias],
        total=len(conferencias),
    )


@router.post(
    "/casos/{caso_id}/fatos/{fato_id}/conferencias",
    response_model=CasoFatoResponse,
)
def conferir_fato_caso(
    caso_id: UUID,
    fato_id: UUID,
    dados: CasoConferenciaCreate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    fato = _obter_fato_caso(db, caso, fato_id)
    if caso.status not in {
        "EM_PREPARACAO",
        "AGUARDANDO_CONFERENCIA",
        "PRONTO_PARA_ANALISE",
    }:
        raise HTTPException(
            status_code=409,
            detail="O estado atual do caso não permite alterar a conferência factual.",
        )
    if caso.status == "PRONTO_PARA_ANALISE" and dados.acao != "REABRIR":
        raise HTTPException(
            status_code=409,
            detail="Reabra o fato antes de alterar uma conferência já concluída.",
        )

    anterior = fato.valor_atual
    if dados.acao == "CONFIRMAR":
        if fato.estado_conferencia != "PENDENTE":
            raise HTTPException(
                status_code=409,
                detail="O fato já foi conferido. Reabra-o antes de uma nova conferência.",
            )
        fato.estado_conferencia = "CONFIRMADO"
    elif dados.acao == "CORRIGIR":
        if fato.estado_conferencia != "PENDENTE":
            raise HTTPException(
                status_code=409,
                detail="O fato já foi conferido. Reabra-o antes de corrigi-lo novamente.",
            )
        fato.valor_atual = dados.valor_novo
        fato.estado_conferencia = "CORRIGIDO"
    else:
        if fato.estado_conferencia == "PENDENTE":
            raise HTTPException(
                status_code=409, detail="O fato já está pendente de conferência."
            )
        fato.estado_conferencia = "PENDENTE"
        if caso.status == "PRONTO_PARA_ANALISE":
            caso.status = "AGUARDANDO_CONFERENCIA"

    conferencia = CasoConferencia(
        caso_id=caso.id,
        fato_id=fato.id,
        usuario_id=usuario_atual.id,
        acao=dados.acao,
        valor_anterior=anterior,
        valor_novo=fato.valor_atual,
        observacao=dados.observacao,
    )
    db.add(conferencia)
    caso.updated_at = utc_now()
    try:
        db.commit()
        db.refresh(fato)
    except Exception as erro:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Não foi possível registrar a conferência."
        ) from erro
    return _fato_to_response(fato)


# =========================================================
# A1 — ANÁLISE JURÍDICA ASSISTIVA / TAB — DECISÃO HUMANA
# =========================================================


@router.get(
    "/casos/{caso_id}/analises-juridicas",
    response_model=CasoAnaliseListResponse,
)
def listar_analises_juridicas(
    caso_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    analises = (
        db.query(CasoAnalise)
        .filter(CasoAnalise.caso_id == caso.id)
        .order_by(CasoAnalise.created_at.desc(), CasoAnalise.id.desc())
        .all()
    )
    return CasoAnaliseListResponse(
        items=[_analise_to_response(db, analise) for analise in analises],
        total=len(analises),
    )


@router.post(
    "/casos/{caso_id}/analises-juridicas",
    response_model=CasoAnaliseResponse,
    status_code=status.HTTP_201_CREATED,
)
def gerar_analise_juridica(
    caso_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    if caso.status not in {"PRONTO_PARA_ANALISE", "ANALISE_DISPONIVEL"}:
        raise HTTPException(
            status_code=409,
            detail="Conclua a conferência factual antes de solicitar a análise jurídica.",
        )
    if (
        db.query(CasoFato.id)
        .filter(
            CasoFato.caso_id == caso.id,
            CasoFato.ativo.is_(True),
            CasoFato.estado_conferencia == "PENDENTE",
        )
        .first()
    ):
        raise HTTPException(
            status_code=409, detail="Existem fatos pendentes de conferência."
        )
    tarefa = _criar_tarefa(
        db,
        caso,
        "RESUMO_A1",
        usuario_atual.id,
    )
    db.commit()
    iniciar_tarefa(tarefa.id)
    try:
        analise = gerar_analise_caso(db, caso, usuario_atual)
        concluir_tarefa(tarefa.id)
    except RuntimeError as erro:
        db.rollback()
        falhar_tarefa(tarefa.id, "A análise local não pôde ser concluída.")
        raise HTTPException(status_code=503, detail=str(erro)) from None
    except Exception as erro:
        db.rollback()
        falhar_tarefa(tarefa.id, "Não foi possível gerar a análise.")
        logger.error(
            "Falha na análise A1 do caso %s (tipo=%s).", caso.id, type(erro).__name__
        )
        raise HTTPException(
            status_code=500,
            detail="Não foi possível gerar a análise jurídica assistiva.",
        ) from erro
    return _analise_to_response(db, analise)


@router.get(
    "/casos/{caso_id}/decisoes",
    response_model=CasoDecisaoListResponse,
)
def listar_decisoes_caso(
    caso_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    decisoes = (
        db.query(CasoDecisao)
        .filter(CasoDecisao.caso_id == caso.id)
        .order_by(CasoDecisao.created_at.desc(), CasoDecisao.id.desc())
        .all()
    )
    return CasoDecisaoListResponse(
        items=[_decisao_to_response(db, decisao) for decisao in decisoes],
        total=len(decisoes),
    )


@router.post(
    "/casos/{caso_id}/decisoes",
    response_model=CasoDecisaoResponse,
    status_code=status.HTTP_201_CREATED,
)
def registrar_decisao_caso(
    caso_id: UUID,
    dados: CasoDecisaoCreate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(require_roles("ADMIN")),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    if caso.status != "ANALISE_DISPONIVEL":
        raise HTTPException(
            status_code=409, detail="O caso ainda não possui análise disponível."
        )
    analise = db.get(CasoAnalise, dados.analise_id)
    if analise is None or analise.caso_id != caso.id:
        raise HTTPException(status_code=404, detail="Análise jurídica não encontrada.")
    decisao = CasoDecisao(
        caso_id=caso.id,
        analise_id=analise.id,
        decisao=dados.decisao,
        texto=dados.texto,
        fundamentacao=dados.fundamentacao,
        escopo=dados.escopo,
        decidido_por=usuario_atual.id,
    )
    db.add(decisao)
    caso.status = "DECISAO_REGISTRADA"
    db.commit()
    db.refresh(decisao)
    return _decisao_to_response(db, decisao)


@router.get(
    "/casos/{caso_id}/mensagens",
    response_model=CasoMensagemListResponse,
)
def listar_mensagens_caso(
    caso_id: UUID,
    limite: int = Query(100, ge=1, le=200),
    antes_de: UUID | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    consulta = db.query(CasoMensagem).filter(CasoMensagem.caso_id == caso.id)
    total = consulta.count()
    tem_mais = total > limite
    if antes_de:
        cursor = (
            db.query(CasoMensagem)
            .filter(
                CasoMensagem.id == antes_de,
                CasoMensagem.caso_id == caso.id,
            )
            .first()
        )
        if cursor is None:
            raise HTTPException(
                status_code=404, detail="Mensagem do caso não encontrada."
            )
        consulta = consulta.filter(
            or_(
                CasoMensagem.created_at < cursor.created_at,
                and_(
                    CasoMensagem.created_at == cursor.created_at,
                    CasoMensagem.id < cursor.id,
                ),
            )
        )
    linhas = (
        consulta.order_by(CasoMensagem.created_at.desc(), CasoMensagem.id.desc())
        .limit(limite + 1)
        .all()
    )
    tem_mais = len(linhas) > limite
    mensagens = list(reversed(linhas[:limite]))
    return CasoMensagemListResponse(
        items=[_mensagem_to_response(item) for item in mensagens],
        total=total,
        tem_mais=tem_mais,
    )


@router.post(
    "/casos/{caso_id}/analisar-lote",
    response_model=CasoMensagemResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def analisar_lote_documentos_caso(
    caso_id: UUID,
    dados: CasoAnaliseLoteCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    if caso.status == "ENCERRADO":
        raise HTTPException(status_code=409, detail="O caso está encerrado.")
    documentos = (
        db.query(CasoDocumento)
        .filter(
            CasoDocumento.caso_id == caso.id,
            CasoDocumento.id.in_(dados.documento_ids),
        )
        .all()
    )
    if {documento.id for documento in documentos} != set(dados.documento_ids):
        raise HTTPException(
            status_code=404,
            detail="Um ou mais documentos não pertencem a este processo.",
        )
    tarefas_documentos = (
        db.query(CasoTarefa.caso_documento_id)
        .filter(
            CasoTarefa.caso_id == caso.id,
            CasoTarefa.tipo == "ANALISE_DOCUMENTO_CHAT",
            CasoTarefa.caso_documento_id.in_(dados.documento_ids),
        )
        .distinct()
        .all()
    )
    if {linha[0] for linha in tarefas_documentos} != set(dados.documento_ids):
        raise HTTPException(
            status_code=409,
            detail="A leitura de um ou mais documentos ainda não foi agendada.",
        )
    chat_ativo = (
        db.query(CasoTarefa.id)
        .filter(
            CasoTarefa.caso_id == caso.id,
            CasoTarefa.tipo.in_(["CHAT_CASO", "ANALISE_LOTE"]),
            CasoTarefa.status.in_(["PENDENTE", "PROCESSANDO"]),
        )
        .first()
    )
    if chat_ativo:
        raise HTTPException(
            status_code=409,
            detail="Já há uma análise deste processo em andamento.",
        )

    mensagem = CasoMensagem(
        caso_id=caso.id,
        papel="USUARIO",
        conteudo=dados.conteudo,
        usuario_id=usuario_atual.id,
    )
    db.add(mensagem)
    caso.updated_at = utc_now()
    tarefa = _criar_tarefa(db, caso, "ANALISE_LOTE", usuario_atual.id)
    db.commit()
    db.refresh(mensagem)
    background_tasks.add_task(
        aguardar_documentos_e_analisar_lote,
        mensagem.id,
        tarefa.id,
        dados.documento_ids,
    )
    return _mensagem_to_response(mensagem)


@router.post(
    "/casos/{caso_id}/mensagens",
    response_model=CasoMensagemResponse,
    status_code=status.HTTP_201_CREATED,
)
def registrar_mensagem_caso(
    caso_id: UUID,
    dados: CasoMensagemCreate,
    background_tasks: BackgroundTasks,
    gerar: bool = Query(False),
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    if caso.status == "ENCERRADO":
        raise HTTPException(status_code=409, detail="O caso está encerrado.")
    mensagem = CasoMensagem(
        caso_id=caso.id,
        papel="USUARIO",
        conteudo=dados.conteudo,
        usuario_id=usuario_atual.id,
    )
    db.add(mensagem)
    caso.updated_at = utc_now()
    tarefa = None
    if gerar:
        tarefa = _criar_tarefa(db, caso, "CHAT_CASO", usuario_atual.id)
    db.commit()
    db.refresh(mensagem)
    if tarefa is not None:
        background_tasks.add_task(processar_mensagem_caso, mensagem.id, tarefa.id)
    return _mensagem_to_response(mensagem)


@router.get(
    "/casos/{caso_id}/tarefas",
    response_model=CasoTarefaListResponse,
)
def listar_tarefas_caso(
    caso_id: UUID,
    tipo: str | None = Query(default=None),
    caso_documento_ids: list[UUID] | None = Query(default=None),
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    consulta_tarefas = db.query(CasoTarefa).filter(CasoTarefa.caso_id == caso.id)
    if tipo:
        consulta_tarefas = consulta_tarefas.filter(CasoTarefa.tipo == tipo.strip().upper())
    if caso_documento_ids:
        consulta_tarefas = consulta_tarefas.filter(
            CasoTarefa.caso_documento_id.in_(caso_documento_ids)
        )
    tarefas = consulta_tarefas.order_by(
        CasoTarefa.created_at.desc(), CasoTarefa.id.desc()
    ).limit(200).all()
    return CasoTarefaListResponse(
        items=[_tarefa_to_response(item) for item in tarefas], total=len(tarefas)
    )


@router.post("/casos/{caso_id}/concluir-apagar", response_model=CasoResponse)
def concluir_e_apagar_documentos_caso(
    caso_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    """Conclui o caso removendo arquivos e texto privado, preservando o registro."""
    caso = _obter_caso_gerenciavel(db, caso_id, usuario_atual)
    if caso.status == "ENCERRADO":
        return _caso_to_response(db, caso)
    if _caso_tem_tarefa_ativa(db, caso.id):
        raise HTTPException(
            status_code=409,
            detail="Aguarde o processamento dos documentos antes de apagar os arquivos do caso.",
        )
    documentos = db.query(CasoDocumento).filter(CasoDocumento.caso_id == caso.id).all()
    caminhos = [
        caminho
        for documento in documentos
        if (caminho := _caminho_documento_caso(documento)) is not None
    ]
    try:
        for documento in documentos:
            db.delete(documento)
        caso.dados_ato = None
        caso.status_dados_ato = "NAO_INICIADO"
        caso.erro_dados_ato = None
        caso.status = "ENCERRADO"
        caso.encerrado_em = utc_now()
        caso.updated_at = utc_now()
        db.commit()
    except Exception as erro:
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Não foi possível concluir a limpeza do caso."
        ) from erro
    for caminho in caminhos:
        try:
            if caminho.exists():
                caminho.unlink()
        except OSError:
            logger.warning("Arquivo temporário não removido após conclusão do caso.")
    return _caso_to_response(db, caso)


# =========================================================
# DOCUMENTOS PRIVADOS DO CASO
# =========================================================


@router.post(
    "/casos/{caso_id}/documentos",
    response_model=CasoDocumentoResponse,
    status_code=(status.HTTP_202_ACCEPTED),
)
async def enviar_documento_caso(
    caso_id: UUID,
    background_tasks: BackgroundTasks,
    tipo_documento: str | None = Form(default=None),
    vinculo_ato: str | None = Form(default=None),
    orientacao_usuario: str | None = Form(default=None),
    responder_apos_processamento: bool = Form(default=True),
    arquivo: UploadFile = File(...),
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(
        db,
        caso_id,
        usuario_atual,
    )

    if caso.status not in {"EM_PREPARACAO", "AGUARDANDO_CONFERENCIA"}:
        raise HTTPException(
            status_code=409,
            detail=(
                "Retorne o caso à preparação ou conferência antes de adicionar documentos."
            ),
        )

    tipo_documento_normalizado = _normalizar_tipo_documento(tipo_documento)

    vinculo_ato_normalizado = _normalizar_vinculo_ato(vinculo_ato)

    nome_original = Path(arquivo.filename or "").name

    if not nome_original:
        raise HTTPException(
            status_code=400,
            detail=("O arquivo enviado " "não possui nome válido."),
        )

    extensao = Path(nome_original).suffix.lower()

    if extensao not in EXTENSOES_PERMITIDAS:
        raise HTTPException(
            status_code=400,
            detail="Envie um arquivo PDF, DOCX, TXT, JPG ou PNG.",
        )

    pasta_caso = UPLOAD_DIR / str(caso.id)

    pasta_caso.mkdir(
        parents=True,
        exist_ok=True,
    )

    caminho = pasta_caso / f"{uuid4()}{extensao}"

    tamanho_total = 0

    hash_arquivo = hashlib.sha256()

    try:
        with caminho.open("wb") as destino:
            while bloco := (await arquivo.read(1024 * 1024)):
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

        if not _validar_conteudo_arquivo(
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

        existente = (
            db.query(CasoDocumento)
            .filter(
                CasoDocumento.caso_id == caso.id,
                CasoDocumento.hash_arquivo == resumo_hash,
            )
            .first()
        )

        if existente:
            raise HTTPException(
                status_code=409,
                detail=("Este arquivo já foi " "adicionado a este caso."),
            )

        mime_type = (
            arquivo.content_type
            or mimetypes.guess_type(nome_original)[0]
            or "application/octet-stream"
        )

        documento = CasoDocumento(
            caso_id=caso.id,
            nome_arquivo=(nome_original),
            caminho_arquivo=str(caminho),
            hash_arquivo=(resumo_hash),
            mime_type=mime_type,
            tamanho_bytes=(tamanho_total),
            tipo_documento=(tipo_documento_normalizado),
            vinculo_ato=(vinculo_ato_normalizado),
            status="PROCESSANDO",
            status_seguranca="PENDENTE",
            alerta_seguranca=None,
            erro_processamento=None,
            total_paginas=0,
            situacao_extracao=("PENDENTE_VERIFICACAO"),
            diagnostico_extracao=None,
            processado_em=None,
            criado_por=(usuario_atual.id),
        )

        db.add(documento)

        orientacao = (orientacao_usuario or "").strip()[:2000]
        mensagem_upload = CasoMensagem(
            caso_id=caso.id,
            papel="USUARIO",
            usuario_id=usuario_atual.id,
            conteudo=(
                f"Enviei o arquivo {nome_original}. "
                f"Tipo informado: {tipo_documento_normalizado or 'não informado'}. "
                f"Relacionado a: {vinculo_ato_normalizado or 'não informado'}. "
                + (
                    f"Orientação: {orientacao}"
                    if orientacao
                    else "Arquivo anexado ao processo."
                )
            ),
        )
        db.add(mensagem_upload)

        caso.updated_at = utc_now()

        tarefa = _criar_tarefa(
            db,
            caso,
            "EXTRACAO_DOCUMENTAL",
            usuario_atual.id,
            caso_documento_id=documento.id,
        )
        tarefa_chat = _criar_tarefa(
            db,
            caso,
            "ANALISE_DOCUMENTO_CHAT",
            usuario_atual.id,
            caso_documento_id=documento.id,
        )

        db.commit()

        db.refresh(documento)
        db.refresh(mensagem_upload)

        background_tasks.add_task(
            processar_documento_e_responder,
            documento.id,
            mensagem_upload.id,
            tarefa.id,
            tarefa_chat.id,
            responder_apos_processamento,
        )

        reservar_processamento(documento.id)

        return _caso_documento_to_response(documento)

    except HTTPException:
        db.rollback()

        if caminho.exists():
            try:
                caminho.unlink()

            except OSError:
                pass

        raise

    except Exception as erro:
        db.rollback()

        if caminho.exists():
            try:
                caminho.unlink()

            except OSError:
                pass

        raise HTTPException(
            status_code=500,
            detail=("Não foi possível adicionar " "o documento ao caso."),
        ) from erro

    finally:
        await arquivo.close()


@router.post(
    "/casos/{caso_id}/documentos/{documento_id}/reprocessar",
    response_model=CasoDocumentoResponse,
    status_code=202,
)
def reprocessar_documento_caso(
    caso_id: UUID,
    documento_id: UUID,
    background_tasks: BackgroundTasks,
    forcar_ocr: bool = Query(False),
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    documento = _obter_documento_caso(db, caso, documento_id)
    db.refresh(documento, with_for_update=True)
    if caso.status not in {"EM_PREPARACAO", "AGUARDANDO_CONFERENCIA"}:
        raise HTTPException(
            status_code=409,
            detail="Retorne o caso à preparação/conferência antes de reprocessar.",
        )
    if db.query(CasoFato).filter(CasoFato.caso_documento_id == documento.id).first():
        raise HTTPException(
            status_code=409,
            detail="O documento possui fatos vinculados e não pode ser reprocessado nesta etapa.",
        )
    caminho = _caminho_documento_caso(documento)
    if caminho is None or not caminho.is_file():
        raise HTTPException(
            status_code=404, detail="Arquivo do documento não disponível."
        )
    if not reservar_processamento(documento.id):
        raise HTTPException(
            status_code=409,
            detail="O documento já possui um processamento em andamento. Aguarde a conclusão.",
        )
    try:
        documento.status = "PROCESSANDO"
        documento.status_seguranca = "PENDENTE"
        documento.situacao_extracao = "PENDENTE_VERIFICACAO"
        documento.erro_processamento = None
        documento.alerta_seguranca = None
        documento.seguranca_liberada_por = None
        documento.seguranca_liberada_em = None
        documento.processado_em = None
        documento.status_extracao_fatos = "NAO_INICIADO"
        documento.erro_extracao_fatos = None
        documento.diagnostico_extracao_fatos = None
        documento.fatos_extraidos_em = None
        documento.versao_extrator_fatos = None
        caso.updated_at = utc_now()
        tarefa = _criar_tarefa(
            db,
            caso,
            "OCR" if forcar_ocr else "EXTRACAO_DOCUMENTAL",
            usuario_atual.id,
            caso_documento_id=documento.id,
        )
        db.commit()
        db.refresh(documento)
    except Exception as erro:
        db.rollback()
        liberar_processamento(documento_id)
        raise HTTPException(
            status_code=500, detail="Não foi possível agendar o reprocessamento."
        ) from erro
    background_tasks.add_task(
        processar_documento_caso,
        documento.id,
        forcar_ocr,
        tarefa.id,
    )
    return _caso_documento_to_response(documento)


@router.post(
    "/casos/{caso_id}/documentos/{documento_id}/propor-fatos",
    response_model=CasoDocumentoResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def propor_fatos_documento_caso(
    caso_id: UUID,
    documento_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    """Agenda propostas factuais locais, sempre sujeitas à conferência humana."""

    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    documento = _obter_documento_caso(db, caso, documento_id)
    if caso.status not in {"EM_PREPARACAO", "AGUARDANDO_CONFERENCIA"}:
        raise HTTPException(
            status_code=409,
            detail="As propostas só podem ser geradas durante a preparação ou conferência.",
        )
    if (
        documento.status != "PRONTO"
        or documento.status_seguranca != "LIBERADO"
        or documento.situacao_extracao != "PROCESSADO_COMPLETO"
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "O documento precisa estar integralmente processado e liberado "
                "antes da proposta factual."
            ),
        )
    if not documento.tipo_documento or not documento.vinculo_ato:
        raise HTTPException(
            status_code=409,
            detail="Classifique o tipo e o vínculo do documento antes de gerar propostas.",
        )
    if (
        documento.status_extracao_fatos == "PRONTO"
        and documento.versao_extrator_fatos == EXTRATOR_FATOS_VERSION
    ):
        raise HTTPException(
            status_code=409,
            detail="As propostas factuais deste documento já foram concluídas.",
        )
    if not ollama_configurado_localmente():
        raise HTTPException(
            status_code=503,
            detail="A análise de documentos privados exige o Ollama configurado localmente.",
        )
    possui_texto = (
        db.query(CasoDocumentoPagina.id)
        .filter(
            CasoDocumentoPagina.caso_documento_id == documento.id,
            CasoDocumentoPagina.conteudo != "",
        )
        .first()
    )
    if possui_texto is None:
        raise HTTPException(
            status_code=409,
            detail="O documento não possui texto disponível para proposta factual.",
        )
    if not reservar_extracao(documento.id):
        raise HTTPException(
            status_code=409,
            detail="A proposta factual deste documento já está em andamento.",
        )
    try:
        documento.status_extracao_fatos = "PROCESSANDO"
        documento.erro_extracao_fatos = None
        documento.diagnostico_extracao_fatos = None
        documento.fatos_extraidos_em = None
        tarefa = _criar_tarefa(
            db,
            caso,
            "EXTRACAO_FACTUAL_A2",
            usuario_atual.id,
            caso_documento_id=documento.id,
        )
        db.commit()
        db.refresh(documento)
    except Exception as erro:
        db.rollback()
        liberar_extracao(documento.id)
        raise HTTPException(
            status_code=500,
            detail="Não foi possível agendar a proposta factual.",
        ) from erro
    background_tasks.add_task(processar_propostas_fatos, documento.id, tarefa.id)
    return _caso_documento_to_response(documento)


@router.get(
    "/casos/{caso_id}/documentos",
    response_model=(CasoDocumentoListResponse),
)
def listar_documentos_caso(
    caso_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(
        db,
        caso_id,
        usuario_atual,
    )

    documentos = (
        db.query(CasoDocumento)
        .filter(CasoDocumento.caso_id == caso.id)
        .order_by(
            CasoDocumento.created_at.desc(),
            CasoDocumento.id.desc(),
        )
        .all()
    )

    return CasoDocumentoListResponse(
        items=[_caso_documento_to_response(documento) for documento in documentos],
        total=len(documentos),
    )


@router.patch(
    "/casos/{caso_id}/documentos/{documento_id}/seguranca",
    response_model=CasoDocumentoResponse,
)
def alterar_seguranca_documento_caso(
    caso_id: UUID,
    documento_id: UUID,
    dados: CasoDocumentoSegurancaUpdate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(db, caso_id, usuario_atual)
    documento = _obter_documento_caso(db, caso, documento_id)
    if caso.status not in {"EM_PREPARACAO", "AGUARDANDO_CONFERENCIA"}:
        raise HTTPException(
            status_code=409,
            detail="A revisão de segurança só pode ocorrer durante a preparação ou conferência.",
        )
    if dados.acao == "LIBERAR":
        if documento.status_seguranca != "REVISAO":
            raise HTTPException(
                status_code=409,
                detail="Somente um documento sinalizado para revisão pode ser liberado manualmente.",
            )
        documento.status_seguranca = "LIBERADO"
        documento.seguranca_liberada_por = usuario_atual.id
        documento.seguranca_liberada_em = utc_now()
    else:
        if documento.status_seguranca != "LIBERADO":
            raise HTTPException(
                status_code=409,
                detail="O documento não está liberado.",
            )
        possui_fatos = (
            db.query(CasoFato.id)
            .filter(
                CasoFato.caso_documento_id == documento.id,
                CasoFato.ativo.is_(True),
            )
            .first()
        )
        if possui_fatos:
            raise HTTPException(
                status_code=409,
                detail="O documento possui fatos vinculados; reabra a segurança somente após o versionamento/delta.",
            )
        documento.status_seguranca = "REVISAO"
        documento.seguranca_liberada_por = None
        documento.seguranca_liberada_em = None
    caso.updated_at = utc_now()
    try:
        db.commit()
        db.refresh(documento)
    except Exception as erro:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Não foi possível registrar a revisão de segurança.",
        ) from erro
    return _caso_documento_to_response(documento)


@router.patch(
    "/casos/{caso_id}/documentos/" "{documento_id}/classificacao",
    response_model=CasoDocumentoResponse,
)
def alterar_classificacao_documento_caso(
    caso_id: UUID,
    documento_id: UUID,
    dados: CasoDocumentoClassificacaoUpdate,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(
        db,
        caso_id,
        usuario_atual,
    )

    documento = _obter_documento_caso(
        db,
        caso,
        documento_id,
    )

    if caso.status not in {"EM_PREPARACAO", "AGUARDANDO_CONFERENCIA"}:
        raise HTTPException(
            status_code=409,
            detail=(
                "Retorne o caso à preparação ou conferência antes de alterar a classificação."
            ),
        )

    possui_fatos = (
        db.query(CasoFato.id).filter(CasoFato.caso_documento_id == documento.id).first()
        is not None
    )

    if possui_fatos:
        raise HTTPException(
            status_code=409,
            detail=(
                "Este documento já possui fatos "
                "derivados. A classificação não "
                "pode ser alterada sem revisar "
                "o estado factual do caso."
            ),
        )

    alteracoes = dados.model_dump(exclude_unset=True)

    if "tipo_documento" in alteracoes:
        documento.tipo_documento = alteracoes["tipo_documento"]

    if "vinculo_ato" in alteracoes:
        documento.vinculo_ato = alteracoes["vinculo_ato"]

    caso.updated_at = utc_now()

    try:
        db.commit()

        db.refresh(documento)

    except Exception as erro:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=("Não foi possível alterar " "a classificação do documento."),
        ) from erro

    return _caso_documento_to_response(documento)


@router.get(
    "/casos/{caso_id}/documentos/{documento_id}",
    response_model=(CasoDocumentoDetalheResponse),
)
def obter_documento_caso(
    caso_id: UUID,
    documento_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(
        db,
        caso_id,
        usuario_atual,
    )

    documento = _obter_documento_caso(
        db,
        caso,
        documento_id,
    )

    paginas = (
        db.query(CasoDocumentoPagina)
        .filter(CasoDocumentoPagina.caso_documento_id == documento.id)
        .order_by(CasoDocumentoPagina.pagina.asc())
        .all()
    )

    dados_documento = _caso_documento_to_response(documento)

    return CasoDocumentoDetalheResponse(
        **dados_documento.model_dump(),
        paginas=[_pagina_to_response(pagina) for pagina in paginas],
    )


@router.get("/casos/{caso_id}/documentos/" "{documento_id}/download")
def baixar_documento_caso(
    caso_id: UUID,
    documento_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_acessivel(
        db,
        caso_id,
        usuario_atual,
    )

    documento = _obter_documento_caso(
        db,
        caso,
        documento_id,
    )

    caminho = _caminho_documento_caso(documento)

    if caminho is None or not caminho.is_file():
        raise HTTPException(
            status_code=404,
            detail=("Arquivo do documento " "não encontrado."),
        )

    tipo, _ = mimetypes.guess_type(documento.nome_arquivo)

    return FileResponse(
        path=caminho,
        filename=(documento.nome_arquivo),
        media_type=(tipo or "application/octet-stream"),
        headers={
            "Cache-Control": ("private, no-store"),
            "X-Content-Type-Options": ("nosniff"),
        },
    )


@router.delete(
    "/casos/{caso_id}/documentos/{documento_id}",
    status_code=(status.HTTP_204_NO_CONTENT),
)
def excluir_documento_caso(
    caso_id: UUID,
    documento_id: UUID,
    db: Session = Depends(get_db),
    usuario_atual: Usuario = Depends(get_current_user),
):
    caso = _obter_caso_gerenciavel(
        db,
        caso_id,
        usuario_atual,
    )

    documento = _obter_documento_caso(
        db,
        caso,
        documento_id,
    )

    if caso.status != "EM_PREPARACAO":
        raise HTTPException(
            status_code=409,
            detail=(
                "Documentos só podem ser "
                "excluídos enquanto o caso "
                "estiver em preparação."
            ),
        )

    if documento.status == "PROCESSANDO":
        raise HTTPException(
            status_code=409,
            detail=("Aguarde o processamento do " "documento antes de excluí-lo."),
        )

    possui_fatos = (
        db.query(CasoFato.id).filter(CasoFato.caso_documento_id == documento.id).first()
        is not None
    )

    if possui_fatos:
        raise HTTPException(
            status_code=409,
            detail=(
                "Este documento já é fonte "
                "de fatos do caso e não pode "
                "ser excluído diretamente."
            ),
        )

    caminho = _caminho_documento_caso(documento)

    pasta_caso = (UPLOAD_DIR / str(caso.id)).resolve()

    try:
        db.delete(documento)

        caso.updated_at = utc_now()

        db.commit()

    except Exception as erro:
        db.rollback()

        raise HTTPException(
            status_code=500,
            detail=("Não foi possível excluir " "o documento do caso."),
        ) from erro

    if caminho is not None and caminho.exists():
        try:
            caminho.unlink()

        except OSError:
            logger.warning(
                "Arquivo físico do documento " "%s não pôde ser removido.",
                documento_id,
            )

    if pasta_caso.exists():
        try:
            pasta_caso.rmdir()

        except OSError:
            pass

    return None
