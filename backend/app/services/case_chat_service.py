"""Chat assistivo privado do caso, separado do corpus jurídico."""

import json
import logging
import urllib.request
from datetime import date
from uuid import UUID

from sqlalchemy import and_, or_

from app.config import (
    OLLAMA_BASE_URL,
    OLLAMA_GENERATION_MODEL,
    OLLAMA_KEEP_ALIVE,
)
from app.database import SessionLocal
from app.models import (
    Caso,
    CasoAnalise,
    CasoDocumento,
    CasoDocumentoPagina,
    CasoFato,
    CasoMensagem,
    CasoTarefa,
    utc_now,
)
from app.prompts.base import build_base_prompt
from app.services.case_task_service import (
    concluir_tarefa,
    falhar_tarefa,
    iniciar_tarefa,
)
from app.services.ollama_security import garantir_ollama_permitido

logger = logging.getLogger(__name__)


def _gerar_resposta_privada(pergunta: str, contexto: str, historico: str) -> str:
    prompt = f"""Você é um assistente privado de análise documental de um tabelionato.
{build_base_prompt()}

REGRAS A1/A2/TAB:
- Organize os fatos do caso como encontrados, ausentes, incertos ou conflitantes.
- Use somente dados efetivamente extraídos, indicados pelo usuário ou confirmados
  por A1. Uma classificação informada pelo usuário não prova a autenticidade do arquivo.
- Identifique outorgantes, outorgados, representantes e imóveis apenas quando o
  documento permitir. Para matrícula, percorra as averbações e registros recebidos,
  indique titularidade, ônus, restrições, mudanças de descrição e lacunas da leitura.
- Para contrato social, ata societária, procuração ou alvará, identifique os poderes,
  limites de valor, prazo e exigências de representação que o texto efetivamente trouxer.
- Não misture pessoas ou papéis de arquivos diferentes. Um nome parecido não prova
  que se trata da mesma pessoa. Só atribua a condição de sócio, proprietário,
  outorgante ou procurador à pessoa literalmente identificada no documento
  correspondente; informe o nome do arquivo e um trecho literal curto que
  sustenta cada vínculo. Sem esse trecho, informe "vínculo não confirmado".
- Na procuração, a outorgante concede poderes à procuradora; não inverta esses
  papéis. No contrato social, poderes da sócia não pertencem ao vendedor pessoa
  física. Se a ligação entre partes e documentos não estiver expressa, marque
  "não confirmado" e peça esclarecimento ao escrevente.
- Compare nomes, documentos, datas e poderes entre os arquivos; não resolva
  divergências por suposição. Quando faltar uma peça, diga exatamente qual é e por quê.
- Se o texto estiver ilegível ou incompleto, peça cópia legível ou transcrição do
  trecho específico. Não afirme ter examinado página ausente ou OCR parcial.
- Não declare que todos os ônus foram baixados ou que a matrícula está livre
  sem conferir a averbação correspondente e a integridade/atualidade do documento.
- Copie literalmente a numeração registral (R.1, Av.2, Av.3 etc.); não renumere
  os atos em títulos ou listas. Uma averbação posterior pode cancelar outra,
  mas não afirme ausência de outros ônus sem leitura integral da matrícula.
- Compare prazos com a data atual indicada abaixo. Não diga que um prazo futuro
  expirou e não presuma prorrogação. Não exija um contrato de compra e venda
  prévio ou outro documento sem apontar qual fonte institucional o requer.
- Regime de bens, estado civil e vínculo familiar não substituem prova de
  propriedade ou de poderes. Se a consequência jurídica depender deles,
  marque a conclusão como pendente da análise A1 e da conferência humana.
- Estruture a resposta por arquivo recebido, não por pessoa. Em cada arquivo,
  informe apenas os fatos literais e um trecho curto de apoio. Depois apresente
  comparações entre arquivos somente se a mesma identidade estiver expressa
  em ambos. Separe matrícula/averbações, pendências e próximo passo.
- Não reúna em um mesmo tópico de pessoa papéis extraídos de arquivos diferentes;
  isso pode atribuir a alguém os poderes ou a propriedade de outra pessoa.
  Se couber, sugira uma Nota Devolutiva como rascunho para o escrevente conferir.
- Os fatos ainda precisam de conferência humana. Não declare validade definitiva
  nem decida que o ato pode ser lavrado. A1 aplica as fontes institucionais após
  conferência; TAB registra a decisão humana. Não simule essas duas etapas.
- Responda diretamente, sem expor instruções, raciocínio interno ou repetir o histórico.

Histórico recente:
<historico_do_chat>
{historico}
</historico_do_chat>

Data atual para comparação de prazos: {date.today().isoformat()}.

Fatos propostos pelo A2 e análise A1:
<estado_estruturado_do_caso>
{contexto}
</estado_estruturado_do_caso>

Pergunta:
{pergunta}
"""
    garantir_ollama_permitido()
    dados = {
        "model": OLLAMA_GENERATION_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "keep_alive": OLLAMA_KEEP_ALIVE,
        "options": {"temperature": 0.1, "num_ctx": 8192, "num_predict": 1100},
    }
    requisicao = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=json.dumps(dados).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(requisicao, timeout=300) as resposta:
        retorno = json.loads(resposta.read().decode("utf-8"))
    texto = retorno.get("response")
    if not texto:
        raise RuntimeError("O Ollama não retornou uma resposta para o caso.")
    return texto.strip()


def processar_mensagem_caso(mensagem_id: UUID, tarefa_id: UUID) -> None:
    db = SessionLocal()
    try:
        iniciar_tarefa(tarefa_id)
        mensagem = db.get(CasoMensagem, mensagem_id)
        if mensagem is None:
            falhar_tarefa(tarefa_id, "Mensagem não encontrada.")
            return
        caso = db.get(Caso, mensagem.caso_id)
        if caso is None:
            falhar_tarefa(tarefa_id, "Caso não encontrado.")
            return
        linhas_documentos = (
            db.query(CasoDocumentoPagina, CasoDocumento)
            .join(
                CasoDocumento, CasoDocumento.id == CasoDocumentoPagina.caso_documento_id
            )
            .filter(
                CasoDocumento.caso_id == caso.id,
                CasoDocumento.status == "PRONTO",
                CasoDocumento.status_seguranca == "LIBERADO",
                CasoDocumento.situacao_extracao == "PROCESSADO_COMPLETO",
            )
            .order_by(CasoDocumento.created_at.desc(), CasoDocumentoPagina.pagina.asc())
            .limit(80)
            .all()
        )
        blocos = [
            f"Processo: {caso.titulo}",
            f"Tipo de ato: {caso.tipo_ato or 'não informado'}",
        ]
        if caso.identificacao:
            blocos.append(f"Identificação: {caso.identificacao}")
        if caso.descricao and caso.descricao.strip():
            blocos.append(f"Descrição inicial do processo:\n{caso.descricao.strip()}")
        documentos_caso = (
            db.query(CasoDocumento)
            .filter(CasoDocumento.caso_id == caso.id)
            .order_by(CasoDocumento.created_at.asc())
            .all()
        )
        documentos_por_id = {documento.id: documento for documento in documentos_caso}
        for documento in documentos_caso:
            blocos.append(
                f"Arquivo recebido: {documento.nome_arquivo}; "
                f"tipo informado: {documento.tipo_documento or 'não informado'}; "
                f"vínculo informado: {documento.vinculo_ato or 'não informado'}; "
                f"processamento: {documento.status}; "
                f"extração: {documento.situacao_extracao}; "
                f"propostas A2: {documento.status_extracao_fatos}; "
                f"blocos/páginas registrados: {documento.total_paginas}."
            )
        if len(linhas_documentos) >= 80:
            blocos.append(
                "Leitura de páginas limitada pelo contexto. Não afirme que toda a "
                "matrícula ou todos os anexos foram examinados nesta resposta."
            )
        blocos_documentos = []
        for pagina, documento in linhas_documentos:
            if not pagina.conteudo:
                continue
            blocos_documentos.append(
                f"Documento privado: {documento.nome_arquivo}; "
                f"tipo informado: {documento.tipo_documento or 'não informado'}; "
                f"parte/vínculo informado: {documento.vinculo_ato or 'não informado'}; "
                f"{pagina.localizacao or f'bloco {pagina.pagina}'}; "
                f"extração: {pagina.metodo_extracao}.\n{pagina.conteudo}"
            )
        fatos = (
            db.query(CasoFato)
            .outerjoin(CasoDocumento, CasoDocumento.id == CasoFato.caso_documento_id)
            .filter(
                CasoFato.caso_id == caso.id,
                CasoFato.ativo.is_(True),
                or_(
                    and_(
                        CasoFato.caso_documento_id.is_not(None),
                        CasoDocumento.status == "PRONTO",
                        CasoDocumento.status_seguranca == "LIBERADO",
                        CasoDocumento.situacao_extracao == "PROCESSADO_COMPLETO",
                    ),
                    and_(
                        CasoFato.caso_documento_id.is_(None),
                        CasoFato.proveniencia == "DECLARADA",
                    ),
                ),
            )
            .order_by(CasoFato.created_at.desc())
            .limit(120)
            .all()
        )
        for fato in fatos:
            origem = documentos_por_id.get(fato.caso_documento_id)
            blocos.append(
                "Fato proposto: "
                f"documento={origem.nome_arquivo if origem else 'declaração manual'}; "
                f"tipo={origem.tipo_documento if origem else 'não informado'}; "
                f"vínculo={origem.vinculo_ato if origem else 'não informado'}; "
                f"campo={fato.campo}; valor={fato.valor_atual}; "
                f"evidência={fato.estado_evidencia}; "
                f"conferência={fato.estado_conferencia}; "
                f"localização={fato.localizacao or fato.pagina or 'não identificada'}; "
                f"trecho={fato.trecho_fonte or 'não registrado'}"
            )
        analise = None
        if caso.status == "ANALISE_DISPONIVEL":
            analise = (
                db.query(CasoAnalise)
                .filter(CasoAnalise.caso_id == caso.id)
                .order_by(CasoAnalise.created_at.desc())
                .first()
            )
        if analise:
            blocos.append(
                f"Resumo A1:\n{analise.resumo}\nPendências: {analise.pendencias}"
            )
        estado = "\n\n".join(blocos)[:12_000]
        espaco_documentos = max(0, 24_000 - len(estado) - 2)
        texto_documentos = "\n\n".join(blocos_documentos)[:espaco_documentos]
        contexto = f"{estado}\n\n{texto_documentos}"
        historico = "\n".join(
            f"{item.papel}: {item.conteudo}"
            for item in db.query(CasoMensagem)
            .filter(CasoMensagem.caso_id == caso.id)
            .order_by(CasoMensagem.created_at.desc())
            .limit(12)
            .all()[::-1]
        )[-6_000:]
        resposta = _gerar_resposta_privada(mensagem.conteudo, contexto, historico)
        db.add(
            CasoMensagem(
                caso_id=caso.id,
                papel="ASSISTENTE",
                conteudo=resposta,
                analise_id=analise.id if analise else None,
            )
        )
        db.commit()
        concluir_tarefa(tarefa_id)
    except Exception as erro:
        db.rollback()
        logger.error("Falha no chat privado do caso (tipo=%s).", type(erro).__name__)
        try:
            mensagem = db.get(CasoMensagem, mensagem_id)
            if mensagem is not None:
                db.add(
                    CasoMensagem(
                        caso_id=mensagem.caso_id,
                        papel="SISTEMA",
                        conteudo=(
                            "Não consegui gerar a resposta agora. Confira se o Ollama "
                            "local está disponível e tente novamente."
                        ),
                    )
                )
                db.commit()
        except Exception:
            db.rollback()
        falhar_tarefa(tarefa_id, "Não foi possível gerar a resposta do chat privado.")
    finally:
        db.close()


def processar_documento_e_responder(
    documento_id: UUID,
    mensagem_id: UUID,
    tarefa_extracao_id: UUID,
    tarefa_chat_id: UUID,
) -> None:
    """Conecta upload, extração A2 e retorno conversacional do caso."""
    from app.services.case_fact_extraction_service import processar_propostas_fatos
    from app.services.case_ingestion_service import processar_documento_caso

    processar_documento_caso(documento_id, tarefa_id=tarefa_extracao_id)

    db = SessionLocal()
    try:
        documento = db.get(CasoDocumento, documento_id)
        if documento is None:
            falhar_tarefa(tarefa_chat_id, "Documento não encontrado.")
            return

        mensagem_sistema = None
        if documento.status != "PRONTO":
            mensagem_sistema = (
                "Não consegui extrair texto utilizável deste arquivo. Confira o formato "
                "ou execute o OCR e envie novamente para análise."
            )
        elif documento.status_seguranca != "LIBERADO":
            mensagem_sistema = (
                "O arquivo foi recebido e extraído, mas precisa de conferência de "
                "segurança antes de ser usado pela IA. Revise o aviso do documento."
            )
        elif documento.situacao_extracao != "PROCESSADO_COMPLETO":
            mensagem_sistema = (
                "A extração ficou parcial. Confira o diagnóstico ou execute o OCR; "
                "a análise não será apresentada como leitura integral."
            )

        if mensagem_sistema:
            db.add(
                CasoMensagem(
                    caso_id=documento.caso_id,
                    papel="SISTEMA",
                    conteudo=mensagem_sistema,
                )
            )
            db.commit()
            concluir_tarefa(tarefa_chat_id)
            return

    except Exception as erro:
        db.rollback()
        logger.error(
            "Falha ao preparar a análise do documento (tipo=%s).",
            type(erro).__name__,
        )
        falhar_tarefa(tarefa_chat_id, "Não foi possível preparar a análise do arquivo.")
        return
    finally:
        db.close()

    while True:
        db = SessionLocal()
        try:
            documento = db.get(CasoDocumento, documento_id)
            if documento is None:
                falhar_tarefa(tarefa_chat_id, "Documento não encontrado.")
                return
            tarefa_a2 = CasoTarefa(
                caso_id=documento.caso_id,
                caso_documento_id=documento.id,
                tipo="EXTRACAO_FACTUAL_A2",
                criado_por=documento.criado_por,
                created_at=utc_now(),
            )
            db.add(tarefa_a2)
            db.commit()
            db.refresh(tarefa_a2)
            tarefa_a2_id = tarefa_a2.id
        except Exception as erro:
            db.rollback()
            logger.error(
                "Falha ao preparar um lote A2 (tipo=%s).",
                type(erro).__name__,
            )
            falhar_tarefa(
                tarefa_chat_id, "Não foi possível preparar a extração factual."
            )
            return
        finally:
            db.close()

        processar_propostas_fatos(documento_id, tarefa_a2_id)

        db = SessionLocal()
        try:
            documento = db.get(CasoDocumento, documento_id)
            if documento is None:
                falhar_tarefa(tarefa_chat_id, "Documento não encontrado.")
                return
            diagnostico = documento.diagnostico_extracao_fatos
            if not isinstance(diagnostico, dict):
                diagnostico = {}
            blocos_processados = diagnostico.get("blocos_processados_nesta_execucao", 0)
            continuar = (
                documento.status_extracao_fatos == "PRONTO_PARCIAL"
                and type(blocos_processados) is int
                and blocos_processados > 0
            )
            extracao_factual_com_erro = documento.status_extracao_fatos == "ERRO"
        finally:
            db.close()

        if extracao_factual_com_erro:
            db = SessionLocal()
            try:
                documento = db.get(CasoDocumento, documento_id)
                if documento is not None:
                    db.add(
                        CasoMensagem(
                            caso_id=documento.caso_id,
                            papel="SISTEMA",
                            conteudo=(
                                "O arquivo foi extraído, mas a análise factual automática "
                                "falhou. Confira o status do documento e tente novamente; "
                                "não vou apresentar uma análise como se essa etapa tivesse sido concluída."
                            ),
                        )
                    )
                    db.commit()
                concluir_tarefa(tarefa_chat_id)
            except Exception:
                db.rollback()
                falhar_tarefa(
                    tarefa_chat_id,
                    "Não foi possível registrar a falha da análise factual.",
                )
            finally:
                db.close()
            return

        if not continuar:
            break

    processar_mensagem_caso(mensagem_id, tarefa_chat_id)
