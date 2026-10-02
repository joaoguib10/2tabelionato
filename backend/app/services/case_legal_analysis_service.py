"""A1 assistivo com snapshots; não toma nem publica decisão jurídica."""

import hashlib
import json
import re
import urllib.request
from urllib.parse import urlparse

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import OLLAMA_BASE_URL, OLLAMA_GENERATION_MODEL
from app.models import (
    Caso,
    CasoAnalise,
    CasoDocumento,
    CasoFato,
    CasoVersao,
    Usuario,
)
from app.prompts import (
    ANALISE_JURIDICA_PROMPT_VERSION,
    BASE_PROMPT_VERSION,
    build_analise_juridica_prompt,
)
from app.services.purchase_sale_service import (
    avaliar_limites_valor,
    gerar_qualificacoes,
)
from app.services.semantic_search_service import buscar_chunks_semelhantes

A1_PROMPT_AUDIT_VERSION = (
    f"a1.{ANALISE_JURIDICA_PROMPT_VERSION}+base.{BASE_PROMPT_VERSION}"
)
MAX_FATOS_CONTEXTO = 18_000
MAX_FONTES_CONTEXTO = 14_000
PADRAO_FONTE = re.compile(r"\[?(FONTE-[0-9a-fA-F-]{36})\]?")


def _ollama_local() -> bool:
    parsed = urlparse(OLLAMA_BASE_URL)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }


def _estado_atual(db: Session, caso: Caso) -> tuple[list[dict], list[dict]]:
    fatos = (
        db.query(CasoFato)
        .filter(CasoFato.caso_id == caso.id, CasoFato.ativo.is_(True))
        .order_by(CasoFato.created_at.asc(), CasoFato.id.asc())
        .all()
    )
    fatos_snapshot = [
        {
            "id": str(fato.id),
            "campo": fato.campo,
            "categoria": fato.categoria,
            "locus": fato.locus,
            "valor": fato.valor_atual,
            "proveniencia": fato.proveniencia,
            "estado_evidencia": fato.estado_evidencia,
            "estado_conferencia": fato.estado_conferencia,
            "documento_id": (
                str(fato.caso_documento_id) if fato.caso_documento_id else None
            ),
            "localizacao": fato.localizacao,
        }
        for fato in fatos
    ]
    if caso.tipo_ato == "COMPRA_VENDA" and isinstance(caso.dados_ato, dict):
        dados_estruturados = {
            chave: valor
            for chave, valor in caso.dados_ato.items()
            if chave != "_diagnostico"
        }
        qualificacoes, pendencias = gerar_qualificacoes(dados_estruturados)
        fatos_snapshot.append(
            {
                "id": f"compra-venda:{caso.id}",
                "campo": "dados estruturados da compra e venda",
                "categoria": "COMPRA_VENDA_ESTRUTURADA",
                "locus": "CORINGA",
                "valor": {
                    **dados_estruturados,
                    "qualificacoes_sugeridas": qualificacoes,
                    "pendencias_de_conferencia": pendencias,
                    "alertas_limites_valor": avaliar_limites_valor(dados_estruturados),
                },
                "proveniencia": "DOCUMENTAL_E_MANUAL",
                "estado_evidencia": "ENCONTRADO" if not pendencias else "INCERTO",
                # A1 pode prosseguir com lacunas explícitas, como autorizado para o MVP.
                # O próprio snapshot mantém as pendências; isso não equivale a decisão TAB.
                "estado_conferencia": "CONFIRMADO",
                "documento_id": None,
                "localizacao": "Estado estruturado conferível de Compra e Venda",
            }
        )
    documentos = (
        db.query(CasoDocumento)
        .filter(CasoDocumento.caso_id == caso.id)
        .order_by(CasoDocumento.created_at.asc(), CasoDocumento.id.asc())
        .all()
    )
    documentos_snapshot = [
        {
            "id": str(documento.id),
            "hash": documento.hash_arquivo,
            "nome": documento.nome_arquivo,
            "tipo": documento.tipo_documento,
            "vinculo": documento.vinculo_ato,
            "status": documento.status,
            "seguranca": documento.status_seguranca,
            "extracao": documento.situacao_extracao,
        }
        for documento in documentos
    ]
    return fatos_snapshot, documentos_snapshot


def obter_ou_criar_versao(
    db: Session,
    caso: Caso,
    usuario: Usuario,
    motivo: str = "Análise jurídica A1",
) -> CasoVersao:
    fatos, documentos = _estado_atual(db, caso)
    serializado = json.dumps(
        {"fatos": fatos, "documentos": documentos},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    hash_estado = hashlib.sha256(serializado.encode("utf-8")).hexdigest()
    existente = (
        db.query(CasoVersao)
        .filter(CasoVersao.caso_id == caso.id, CasoVersao.hash_estado == hash_estado)
        .first()
    )
    if existente:
        return existente
    numero = (
        db.query(func.max(CasoVersao.numero))
        .filter(CasoVersao.caso_id == caso.id)
        .scalar()
        or 0
    ) + 1
    versao = CasoVersao(
        caso_id=caso.id,
        numero=numero,
        hash_estado=hash_estado,
        motivo=motivo[:200],
        fatos_snapshot=fatos,
        documentos_snapshot=documentos,
        criado_por=usuario.id,
    )
    db.add(versao)
    db.flush()
    return versao


def _texto_fatos(fatos: list[dict]) -> str:
    linhas = []
    for fato in fatos:
        linhas.append(
            json.dumps(
                {
                    "campo": fato["campo"],
                    "categoria": fato["categoria"],
                    "locus": fato["locus"],
                    "valor": fato["valor"],
                    "proveniencia": fato["proveniencia"],
                    "estado_evidencia": fato["estado_evidencia"],
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(linhas)[:MAX_FATOS_CONTEXTO]


def _texto_fontes(fontes: list[dict]) -> str:
    blocos = []
    tamanho = 0
    for fonte in fontes:
        bloco = (
            f"[{fonte['fonte_id']}] {fonte['documento']}"
            f" — {fonte.get('artigo') or fonte.get('localizacao') or 'trecho'}\n"
            f"{fonte['conteudo']}"
        )
        if tamanho + len(bloco) > MAX_FONTES_CONTEXTO:
            break
        blocos.append(bloco)
        tamanho += len(bloco)
    return "\n\n".join(blocos)


def _extrair_json(texto: str) -> dict:
    inicio, fim = texto.find("{"), texto.rfind("}")
    if inicio < 0 or fim <= inicio:
        raise ValueError("Resposta A1 fora do contrato.")
    dados = json.loads(texto[inicio : fim + 1])
    if not isinstance(dados, dict):
        raise ValueError("Resposta A1 fora do contrato.")
    return dados


def _gerar_analise(prompt: str) -> dict:
    if not _ollama_local():
        raise RuntimeError("A análise de casos exige Ollama local.")
    requisicao = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=json.dumps(
            {
                "model": OLLAMA_GENERATION_MODEL,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "format": "json",
                "options": {"temperature": 0.0, "num_ctx": 12288, "num_predict": 2400},
            }
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(requisicao, timeout=300) as resposta:
        retorno = json.loads(resposta.read().decode("utf-8"))
    return _extrair_json(str(retorno.get("response") or ""))


def _sanitizar_saida(valor, ids_validos: set[str]):
    if isinstance(valor, str):
        return PADRAO_FONTE.sub(
            lambda item: f"[{item.group(1)}]" if item.group(1) in ids_validos else "",
            valor,
        ).strip()[:10_000]
    if isinstance(valor, list):
        return [_sanitizar_saida(item, ids_validos) for item in valor[:100]]
    if isinstance(valor, dict):
        return {
            str(chave)[:100]: _sanitizar_saida(conteudo, ids_validos)
            for chave, conteudo in list(valor.items())[:30]
        }
    if valor is None or isinstance(valor, (bool, int, float)):
        return valor
    return str(valor)[:1000]


def gerar_analise_caso(db: Session, caso: Caso, usuario: Usuario) -> CasoAnalise:
    if not _ollama_local():
        raise RuntimeError("A análise de casos exige Ollama local.")
    versao = obter_ou_criar_versao(db, caso, usuario)
    fatos = versao.fatos_snapshot
    consulta = " ".join(
        [caso.tipo_ato or "ato notarial"]
        + [f"{item['campo']} {item.get('valor') or ''}" for item in fatos]
    )[:4000]
    fontes = buscar_chunks_semelhantes(db, consulta, limite=10)
    if not fontes:
        analise = CasoAnalise(
            caso_id=caso.id,
            versao_id=versao.id,
            status_evidencia="BASE_INSUFICIENTE",
            resumo="Não há base institucional aprovada suficiente para analisar este caso.",
            requisitos=[],
            impedimentos=[],
            pendencias=[
                "Cadastrar ou aprovar fontes institucionais aplicáveis e tentar novamente."
            ],
            fontes_snapshot=[],
            prompt_version=A1_PROMPT_AUDIT_VERSION,
            modelo_ia=None,
            gerado_por=usuario.id,
        )
    else:
        dados = _gerar_analise(
            build_analise_juridica_prompt(
                caso.tipo_ato or "",
                _texto_fatos(fatos),
                _texto_fontes(fontes),
            )
        )
        ids_validos = {fonte["fonte_id"] for fonte in fontes}
        ids_citados = {
            str(item) for item in dados.get("fonte_ids", []) if str(item) in ids_validos
        }
        dados = _sanitizar_saida(dados, ids_validos)
        snapshots = [
            {
                "fonte_id": fonte["fonte_id"],
                "documento_id": fonte["documento_id"],
                "titulo": fonte["documento"],
                "versao": fonte.get("versao_documento"),
                "pagina": fonte.get("pagina"),
                "localizacao": fonte.get("localizacao"),
                "artigo": fonte.get("artigo"),
                "trecho": fonte["conteudo"],
                "pontuacao": fonte["similaridade"],
                "citada": fonte["fonte_id"] in ids_citados,
            }
            for fonte in fontes
        ]
        analise = CasoAnalise(
            caso_id=caso.id,
            versao_id=versao.id,
            status_evidencia=(
                "EVIDENCIA_PARCIAL" if ids_citados else "BASE_INSUFICIENTE"
            ),
            resumo=str(dados.get("resumo") or "Análise sem resumo verificável.")[
                :50_000
            ],
            requisitos=(
                dados.get("requisitos")
                if isinstance(dados.get("requisitos"), list)
                else []
            ),
            impedimentos=(
                dados.get("impedimentos")
                if isinstance(dados.get("impedimentos"), list)
                else []
            ),
            pendencias=(
                dados.get("pendencias")
                if isinstance(dados.get("pendencias"), list)
                else []
            ),
            fontes_snapshot=snapshots,
            prompt_version=A1_PROMPT_AUDIT_VERSION,
            modelo_ia=OLLAMA_GENERATION_MODEL,
            gerado_por=usuario.id,
        )
    db.add(analise)
    caso.status = "ANALISE_DISPONIVEL"
    db.commit()
    db.refresh(analise)
    return analise
