from datetime import date

from sqlalchemy import or_

from app.models import Documento
from app.services.document_processor import EXTRACOES_COMPLETAS

CATEGORIAS_DOCUMENTO = {
    "NORMA",
    "LEGISLACAO",
    "ENTENDIMENTO",
    "PROCEDIMENTO",
    "MANUAL",
    "MODELO_MINUTA",
    "OUTRO",
}
CATEGORIAS_CONSULTA = {
    "NORMA",
    "LEGISLACAO",
    "ENTENDIMENTO",
    "PROCEDIMENTO",
    "MANUAL",
}
TIPOS_ATO = {"COMPRA_VENDA", "DOACAO"}
SITUACOES_GOVERNANCA = {"RASCUNHO", "APROVADO", "REVOGADO", "ARQUIVADO"}
STATUS_PROCESSAMENTO = {"PROCESSANDO", "PRONTO", "ERRO"}


def condicoes_base_elegibilidade():
    hoje = date.today()
    return (
        Documento.ativo.is_(True),
        Documento.status == "PRONTO",
        Documento.situacao_extracao.in_(EXTRACOES_COMPLETAS),
        Documento.status_seguranca == "LIBERADO",
        Documento.situacao == "APROVADO",
        or_(Documento.vigencia_inicio.is_(None), Documento.vigencia_inicio <= hoje),
        or_(Documento.vigencia_fim.is_(None), Documento.vigencia_fim >= hoje),
    )


def condicoes_consulta():
    return (*condicoes_base_elegibilidade(), Documento.tipo.in_(CATEGORIAS_CONSULTA))


def condicoes_modelo_minuta(tipo_ato: str | None = None):
    condicoes = [
        *condicoes_base_elegibilidade(),
        Documento.tipo == "MODELO_MINUTA",
    ]
    if tipo_ato is not None:
        condicoes.append(Documento.tipo_ato == tipo_ato)
    return tuple(condicoes)


def documento_elegivel_consulta(documento: Documento) -> bool:
    hoje = date.today()
    return bool(
        documento.ativo
        and documento.status == "PRONTO"
        and documento.situacao_extracao in EXTRACOES_COMPLETAS
        and documento.status_seguranca == "LIBERADO"
        and documento.situacao == "APROVADO"
        and documento.tipo in CATEGORIAS_CONSULTA
        and (documento.vigencia_inicio is None or documento.vigencia_inicio <= hoje)
        and (documento.vigencia_fim is None or documento.vigencia_fim >= hoje)
    )


def modelo_minuta_elegivel(documento: Documento, tipo_ato: str) -> bool:
    hoje = date.today()
    return bool(
        documento.ativo
        and documento.status == "PRONTO"
        and documento.situacao_extracao in EXTRACOES_COMPLETAS
        and documento.status_seguranca == "LIBERADO"
        and documento.situacao == "APROVADO"
        and documento.tipo == "MODELO_MINUTA"
        and documento.tipo_ato == tipo_ato
        and (documento.vigencia_inicio is None or documento.vigencia_inicio <= hoje)
        and (documento.vigencia_fim is None or documento.vigencia_fim >= hoje)
    )
