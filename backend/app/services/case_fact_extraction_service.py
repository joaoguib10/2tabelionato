"""Extração assistida de fatos de documentos privados do caso.

O serviço cria somente propostas pendentes. Ele não confirma fatos, não faz
qualificação jurídica e não grava conteúdo no corpus institucional/RAG.
"""

import hashlib
import json
import logging
import re
import urllib.request
from threading import Lock
from urllib.parse import urlparse
from uuid import UUID

from app.config import (
    A2_FACT_BLOCK_CHAR_LIMIT,
    A2_FACT_MAX_BLOCKS,
    OLLAMA_BASE_URL,
    OLLAMA_GENERATION_MODEL,
)
from app.database import SessionLocal
from app.models import Caso, CasoDocumento, CasoDocumentoPagina, CasoFato, utc_now
from app.prompts import (
    BASE_PROMPT_VERSION,
    ESTADO_FACTUAL_PROMPT_VERSION,
    build_estado_factual_prompt,
)
from app.services.case_task_service import (
    concluir_tarefa,
    falhar_tarefa,
    iniciar_tarefa,
)

logger = logging.getLogger(__name__)
EXTRATOR_FATOS_VERSION = (
    f"a2.{ESTADO_FACTUAL_PROMPT_VERSION}+base.{BASE_PROMPT_VERSION}"
)
ESTADOS_EVIDENCIA_AUTOMATICOS = {"ENCONTRADO", "INCERTO", "CONFLITANTE"}
LOCI_VALIDOS = {"A", "B", "C", "D", "E", "F", "CORINGA"}
_reserva_lock = Lock()
_extracoes_ativas: set = set()


def ollama_configurado_localmente() -> bool:
    """Dados privados só podem seguir para uma instância loopback do Ollama."""

    parsed = urlparse(OLLAMA_BASE_URL)
    return parsed.scheme in {"http", "https"} and parsed.hostname in {
        "localhost",
        "127.0.0.1",
        "::1",
    }


def reservar_extracao(caso_documento_id) -> bool:
    with _reserva_lock:
        if caso_documento_id in _extracoes_ativas:
            return False
        _extracoes_ativas.add(caso_documento_id)
        return True


def liberar_extracao(caso_documento_id) -> None:
    with _reserva_lock:
        _extracoes_ativas.discard(caso_documento_id)


def _normalizar_trecho(texto: str) -> str:
    return " ".join(texto.split()).casefold()


def _blocos(texto: str, limite: int):
    texto = texto.strip()
    inicio = 0
    while inicio < len(texto):
        fim = min(inicio + limite, len(texto))
        if fim < len(texto):
            corte = texto.rfind("\n", inicio, fim)
            if corte <= inicio + limite // 2:
                corte = texto.rfind(" ", inicio, fim)
            if corte > inicio:
                fim = corte
        bloco = texto[inicio:fim].strip()
        if bloco:
            yield bloco
        inicio = max(fim, inicio + 1)


def _extrair_json(texto: str) -> dict:
    resposta = texto.strip()
    if resposta.startswith("```"):
        resposta = re.sub(r"^```(?:json)?\s*", "", resposta, flags=re.I)
        resposta = re.sub(r"\s*```$", "", resposta)
    inicio = resposta.find("{")
    fim = resposta.rfind("}")
    if inicio < 0 or fim <= inicio:
        raise ValueError("Resposta sem objeto JSON.")
    resultado = json.loads(resposta[inicio : fim + 1])
    if not isinstance(resultado, dict) or not isinstance(resultado.get("fatos"), list):
        raise ValueError("Resposta factual fora do contrato.")
    return resultado


def _gerar_propostas(prompt: str) -> dict:
    dados = {
        "model": OLLAMA_GENERATION_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0.0, "num_ctx": 12288, "num_predict": 1800},
    }
    requisicao = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=json.dumps(dados).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(requisicao, timeout=300) as resposta:
        resultado = json.loads(resposta.read().decode("utf-8"))
    texto = resultado.get("response")
    if not texto:
        raise RuntimeError("O modelo local não retornou uma resposta.")
    return _extrair_json(texto)


def _proposta_validada(item, texto_bloco: str) -> dict | None:
    if not isinstance(item, dict):
        return None
    campo = str(item.get("campo") or "").strip()[:150]
    trecho = str(item.get("trecho_fonte") or "").strip()[:2000]
    if not campo or not trecho:
        return None
    # Uma fonte inventada nunca é promovida a proposta conferível.
    if _normalizar_trecho(trecho) not in _normalizar_trecho(texto_bloco):
        return None
    estado = str(item.get("estado_evidencia") or "INCERTO").strip().upper()
    if estado not in ESTADOS_EVIDENCIA_AUTOMATICOS:
        return None
    locus = str(item.get("locus") or "CORINGA").strip().upper()
    if locus not in LOCI_VALIDOS:
        locus = "CORINGA"
    categoria = str(item.get("categoria") or "").strip()[:80] or None
    valor = item.get("valor")
    try:
        if len(json.dumps(valor, ensure_ascii=False)) > 5000:
            return None
    except (TypeError, ValueError):
        return None
    return {
        "campo": campo,
        "categoria": categoria,
        "locus": locus,
        "valor": valor,
        "estado_evidencia": estado,
        "trecho_fonte": trecho,
    }


def processar_propostas_fatos(caso_documento_id, tarefa_id: UUID | None = None) -> None:
    """Executa em segundo plano e mantém falhas técnicas fora da resposta pública."""

    db = SessionLocal()
    try:
        iniciar_tarefa(tarefa_id)
        documento = db.get(CasoDocumento, caso_documento_id)
        if documento is None:
            falhar_tarefa(tarefa_id, "Documento não encontrado.")
            return
        if not ollama_configurado_localmente():
            raise RuntimeError("Ollama não local recusado para documento privado.")

        paginas = (
            db.query(CasoDocumentoPagina)
            .filter(CasoDocumentoPagina.caso_documento_id == documento.id)
            .order_by(CasoDocumentoPagina.pagina.asc())
            .all()
        )
        blocos = []
        for pagina in paginas:
            for numero_bloco, texto in enumerate(
                _blocos(pagina.conteudo or "", max(A2_FACT_BLOCK_CHAR_LIMIT, 1000)),
                start=1,
            ):
                blocos.append((pagina, numero_bloco, texto))

        total_blocos = len(blocos)
        diagnostico_anterior = documento.diagnostico_extracao_fatos or {}
        hashes_processados = set()
        if documento.versao_extrator_fatos == EXTRATOR_FATOS_VERSION:
            hashes_processados.update(
                diagnostico_anterior.get("hashes_blocos_processados") or []
            )
        blocos_pendentes = [
            (pagina, numero_bloco, texto)
            for pagina, numero_bloco, texto in blocos
            if hashlib.sha256(texto.encode("utf-8")).hexdigest()
            not in hashes_processados
        ]
        blocos_processados_nesta_execucao = 0
        criados = 0
        descartados = 0
        existentes = set()
        for fato in db.query(CasoFato).filter(
            CasoFato.caso_documento_id == documento.id,
            CasoFato.ativo.is_(True),
        ):
            contexto = fato.contexto or {}
            chave = contexto.get("chave_proposta")
            if chave:
                existentes.add(chave)

        for pagina, numero_bloco, texto in blocos_pendentes[
            : max(A2_FACT_MAX_BLOCKS, 1)
        ]:
            hash_bloco = hashlib.sha256(texto.encode("utf-8")).hexdigest()
            prompt = build_estado_factual_prompt(
                texto=texto,
                tipo_documento=documento.tipo_documento,
                vinculo_ato=documento.vinculo_ato,
                localizacao=pagina.localizacao or f"Bloco {pagina.pagina}",
            )
            resposta = _gerar_propostas(prompt)
            for item in resposta["fatos"][:50]:
                proposta = _proposta_validada(item, texto)
                if proposta is None:
                    descartados += 1
                    continue
                chave = hashlib.sha256(
                    f"{hash_bloco}|{proposta['campo'].casefold()}|{proposta['locus']}".encode(
                        "utf-8"
                    )
                ).hexdigest()
                if chave in existentes:
                    continue
                contexto = {
                    "origem_registro": "PROPOSTA_IA",
                    "chave_proposta": chave,
                    "hash_bloco": hash_bloco,
                    "numero_bloco": numero_bloco,
                    "prompt_version": EXTRATOR_FATOS_VERSION,
                    "modelo": OLLAMA_GENERATION_MODEL,
                }
                db.add(
                    CasoFato(
                        caso_id=documento.caso_id,
                        caso_documento_id=documento.id,
                        campo=proposta["campo"],
                        categoria=proposta["categoria"],
                        locus=proposta["locus"],
                        valor_original=proposta["valor"],
                        valor_atual=proposta["valor"],
                        proveniencia="DOCUMENTAL",
                        estado_evidencia=proposta["estado_evidencia"],
                        estado_conferencia="PENDENTE",
                        pagina=pagina.pagina,
                        localizacao=pagina.localizacao,
                        trecho_fonte=proposta["trecho_fonte"],
                        metodo_extracao="OLLAMA_LOCAL",
                        contexto=contexto,
                        ativo=True,
                        registrado_por=None,
                    )
                )
                existentes.add(chave)
                criados += 1
            blocos_processados_nesta_execucao += 1
            hashes_processados.add(hash_bloco)
            db.flush()

        total_processado = len(hashes_processados)
        parcial = total_processado < total_blocos
        documento.status_extracao_fatos = "PRONTO_PARCIAL" if parcial else "PRONTO"
        documento.erro_extracao_fatos = None
        documento.diagnostico_extracao_fatos = {
            "total_blocos": total_blocos,
            "blocos_processados": total_processado,
            "blocos_processados_nesta_execucao": blocos_processados_nesta_execucao,
            "propostas_criadas": criados,
            "propostas_descartadas_sem_evidencia_verificavel": descartados,
            "limite_blocos": A2_FACT_MAX_BLOCKS,
            "hashes_blocos_processados": sorted(hashes_processados),
        }
        documento.fatos_extraidos_em = utc_now()
        documento.versao_extrator_fatos = EXTRATOR_FATOS_VERSION
        caso = db.get(Caso, documento.caso_id)
        if caso is not None and caso.status == "EM_PREPARACAO" and criados:
            caso.status = "AGUARDANDO_CONFERENCIA"
        db.commit()
        concluir_tarefa(tarefa_id)
    except Exception as erro:
        db.rollback()
        logger.error(
            "Falha na proposta factual do documento de caso %s (tipo=%s).",
            caso_documento_id,
            type(erro).__name__,
        )
        documento = db.get(CasoDocumento, caso_documento_id)
        if documento is not None:
            documento.status_extracao_fatos = "ERRO"
            documento.erro_extracao_fatos = (
                "Não foi possível gerar propostas factuais com a IA local. "
                "Verifique o Ollama e tente novamente."
            )
            documento.fatos_extraidos_em = utc_now()
            documento.versao_extrator_fatos = EXTRATOR_FATOS_VERSION
            db.commit()
        falhar_tarefa(tarefa_id, "Não foi possível gerar propostas factuais.")
    finally:
        db.close()
        liberar_extracao(caso_documento_id)
