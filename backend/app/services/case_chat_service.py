"""Chat assistivo privado do caso, separado do corpus jurídico."""

import json
import logging
import re
import unicodedata
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

_PALAVRAS_VAZIAS = {
    "a",
    "ao",
    "aos",
    "as",
    "com",
    "como",
    "da",
    "das",
    "de",
    "do",
    "dos",
    "e",
    "em",
    "entre",
    "esta",
    "este",
    "eu",
    "foi",
    "for",
    "ha",
    "me",
    "na",
    "nas",
    "no",
    "nos",
    "o",
    "os",
    "ou",
    "para",
    "pela",
    "pelas",
    "pelo",
    "pelos",
    "por",
    "que",
    "se",
    "sobre",
    "um",
    "uma",
    "umas",
    "uns",
    "voce",
    "qual",
    "quais",
    "quem",
    "quando",
    "onde",
}
_EXPANSAO_REPRESENTACAO = {
    "represent",
    "representante",
    "representacao",
    "administr",
    "administrador",
    "administracao",
    "gestor",
    "gerente",
    "socio",
    "sociedade",
    "empresa",
    "poder",
    "procurador",
    "procuracao",
    "mandato",
    "assinatura",
    "assinar",
    "isoladamente",
    "conjuntamente",
    "nome",
    "empresarial",
    "limitada",
}


def _normalizar_termos(texto: str) -> list[str]:
    normalizado = unicodedata.normalize("NFKD", texto.casefold())
    sem_acentos = "".join(
        caractere
        for caractere in normalizado
        if not unicodedata.combining(caractere)
    )
    return re.findall(r"[a-z0-9]+", sem_acentos)


def _termos_da_pergunta(pergunta: str) -> tuple[set[str], bool]:
    termos = {
        termo
        for termo in _normalizar_termos(pergunta)
        if len(termo) >= 3 and termo not in _PALAVRAS_VAZIAS
    }
    representacao = any(
        termo.startswith(("represent", "administr", "procur", "assin"))
        or termo in {"poder", "poderes", "socio", "sociedade", "empresa"}
        for termo in termos
    )
    if representacao:
        termos.update(_EXPANSAO_REPRESENTACAO)
    return termos, representacao


def _pontuar_texto(texto: str, termos: set[str]) -> int:
    tokens = _normalizar_termos(texto)
    pontuacao = 0
    for termo in termos:
        ocorrencias = sum(
            1 for token in tokens
            if token == termo
            or (len(termo) >= 5 and token.startswith(termo))
            or (len(token) >= 5 and termo.startswith(token))
        )
        if ocorrencias:
            pontuacao += min(ocorrencias, 3) * (2 if len(termo) >= 6 else 1)
    return pontuacao


def _trecho_relevante(texto: str, termos: set[str], limite: int = 1000) -> str:
    texto = texto.strip()
    if len(texto) <= limite:
        return texto
    passo = limite // 2
    inicios = list(range(0, len(texto) - limite + 1, passo))
    if not inicios or inicios[-1] != len(texto) - limite:
        inicios.append(len(texto) - limite)
    janelas = [
        (inicio, _pontuar_texto(texto[inicio : inicio + limite], termos))
        for inicio in inicios
    ]
    if not janelas or max(pontuacao for _, pontuacao in janelas) == 0:
        return texto[:limite]
    inicio = max(janelas, key=lambda item: (item[1], -item[0]))[0]
    fim = min(len(texto), inicio + limite)
    return texto[inicio:fim].strip()


def _selecionar_paginas_contexto(linhas, pergunta: str) -> list[str]:
    """Busca evidência em todas as páginas e monta contexto equilibrado por arquivo."""
    termos, representacao = _termos_da_pergunta(pergunta)
    candidatos = []
    paginas_por_documento: dict[
        UUID, list[tuple[int, int, str, CasoDocumento]]
    ] = {}
    for pagina, documento in linhas:
        if not pagina.conteudo or not pagina.conteudo.strip():
            continue
        pontuacao = _pontuar_texto(pagina.conteudo, termos)
        if representacao:
            classificacao = " ".join(
                [documento.tipo_documento or "", documento.nome_arquivo]
            ).casefold()
            if any(
                palavra in classificacao
                for palavra in ("social", "societ", "contrato")
            ):
                pontuacao += 4
        item = (pontuacao, pagina.pagina, pagina.conteudo, documento)
        paginas_por_documento.setdefault(documento.id, []).append(item)
        candidatos.append(item)

    # Primeiro reserva uma página com evidência para cada arquivo, evitando que
    # um documento longo esconda os demais; depois completa pelas melhores notas.
    selecionados = []
    ids_selecionados: set[tuple[UUID, int]] = set()
    for paginas in paginas_por_documento.values():
        melhor = max(paginas, key=lambda item: (item[0], -item[1]))
        selecionados.append(melhor)
        ids_selecionados.add((melhor[3].id, melhor[1]))
    candidatos.sort(key=lambda item: (item[0], -item[1]), reverse=True)
    for item in candidatos:
        chave = (item[3].id, item[1])
        if chave in ids_selecionados:
            continue
        if len(selecionados) >= 18:
            break
        selecionados.append(item)
        ids_selecionados.add(chave)
    selecionados.sort(key=lambda item: item[0], reverse=True)

    blocos = []
    tamanho = 0
    for pontuacao, numero_pagina, conteudo, documento in selecionados:
        trecho = _trecho_relevante(conteudo, termos)
        localizacao = (
            f"Página {numero_pagina}"
            if documento.nome_arquivo.lower().endswith(".pdf")
            else f"Bloco {numero_pagina}"
        )
        bloco = (
            f"Arquivo: {documento.nome_arquivo}; "
            f"tipo: {documento.tipo_documento or 'não informado'}; "
            f"{localizacao}; "
            f"relevância da pergunta: {pontuacao}.\n{trecho}"
        )
        if tamanho + len(bloco) > 10_000:
            continue
        blocos.append(bloco)
        tamanho += len(bloco)
    return blocos


def _selecionar_fatos_contexto(fatos, documentos_por_id, pergunta: str) -> list[str]:
    termos, _ = _termos_da_pergunta(pergunta)
    candidatos = []
    for fato in fatos:
        origem = documentos_por_id.get(fato.caso_documento_id)
        texto_fato = " ".join(
            [
                str(fato.campo or ""),
                str(fato.valor_atual or ""),
                str(fato.trecho_fonte or ""),
                str(fato.localizacao or ""),
            ]
        )
        candidatos.append(
            (_pontuar_texto(texto_fato, termos), fato.created_at, fato, origem)
        )
    candidatos.sort(key=lambda item: (item[0], item[1]), reverse=True)
    selecionados = []
    documentos_incluidos: set[UUID] = set()
    ids = set()
    for pontuacao, _, fato, origem in candidatos:
        if origem is None or origem.id in documentos_incluidos:
            continue
        selecionados.append((pontuacao, fato, origem))
        documentos_incluidos.add(origem.id)
        ids.add(fato.id)
    for candidato in candidatos:
        if len(selecionados) >= 80:
            break
        pontuacao, _, fato, origem = candidato
        if fato.id in ids:
            continue
        selecionados.append((pontuacao, fato, origem))
        ids.add(fato.id)

    blocos = []
    tamanho = 0
    for _, fato, origem in selecionados:
        bloco = (
            "Fato proposto: "
            f"documento={origem.nome_arquivo if origem else 'declaração manual'}; "
            f"campo={fato.campo}; valor={fato.valor_atual}; "
            f"evidência={fato.estado_evidencia}; "
            f"conferência={fato.estado_conferencia}; "
            f"localização={fato.localizacao or fato.pagina or 'não identificada'}; "
            f"trecho={fato.trecho_fonte or 'não registrado'}"
        )
        if tamanho + len(bloco) > 4_000:
            continue
        blocos.append(bloco)
        tamanho += len(bloco)
    return blocos


def _gerar_resposta_privada(pergunta: str, contexto: str, historico: str) -> str:
    prompt = f"""Você é um assistente privado de análise documental de um tabelionato.
{build_base_prompt()}

REGRAS A1/A2/TAB:
- Organize os fatos do caso como encontrados, ausentes, incertos ou conflitantes.
- Use somente dados efetivamente extraídos, indicados pelo usuário ou confirmados
  por A1. Uma classificação informada pelo usuário não prova a autenticidade do arquivo.
- Use o tipo e o vínculo informados pelo escrevente como mapa do papel esperado
  daquele arquivo no processo, sem tratá-los como prova de autenticidade. Se o
  conteúdo identificar a mesma pessoa ou entidade, explique como o documento se
  relaciona ao papel indicado; não diga que ele é alheio à negociação só porque
  não menciona o ato específico.
- Identifique outorgantes, outorgados, representantes e imóveis apenas quando o
  documento permitir. Para matrícula, percorra as averbações e registros recebidos,
  indique titularidade, ônus, restrições, mudanças de descrição e lacunas da leitura.
- Para contrato social ou alteração contratual, procure também as cláusulas de
  administração, uso do nome empresarial e representação. Identifique nominalmente
  o administrador ou sócio administrador quando indicado, transcreva o trecho que
  atribui poderes e explique se a atuação é isolada, conjunta ou limitada.
- Não exija que o contrato use literalmente a palavra "representante": uma cláusula
  expressa que atribua ao administrador poderes para agir ou assinar em nome da
  sociedade sustenta essa função nos limites escritos. Não confunda sócio com
  administrador quando o texto não lhes der os mesmos poderes.
- Diferencie o representante indicado no documento da pessoa que efetivamente
  assinará o ato. Se só houver um contrato social, informe quem ele designa e peça
  alteração contratual ou certidão atualizada apenas para confirmar que os poderes
  continuam vigentes; não deixe de identificar o nome e a cláusula já localizados.
- Para procuração ou alvará, identifique os poderes, limites de valor, prazo e
  exigências de representação que o texto efetivamente trouxer.
- Se o documento identificar expressamente uma pessoa como representante ou
  administrador de uma empresa e lhe atribuir poderes específicos, relate esse
  vínculo e esses poderes com base no trecho, mesmo que a palavra representante
  não apareça literalmente. Não negue um poder que esteja escrito; se a identidade da
  pessoa que assinará não estiver vinculada ao representante identificado, marque
  somente essa correspondência como pendente.
- Para pessoa física registrada como proprietária, relate a titularidade que consta
  na matrícula. Não converta a falta de procuração ou alvará em falta de poderes
  para alienar quando o titular comparecer em nome próprio; eventual necessidade
  de participação de cônjuge ou outro requisito jurídico deve ser apontada como
  ponto de conferência, sem afirmar que é impeditivo se os documentos não bastarem.
- Não peça prova de que o proprietário autorizou a própria alienação se ele puder
  comparecer em nome próprio. Se não estiver confirmado quem comparecerá, formule
  isso como conferência de identidade/comparecimento, não como falta de autorização.
- Para empresa indicada como adquirente, se o contrato social identificar a empresa
  e atribuir poderes de representação a administrador ou representante, relate que o documento sustenta a capacidade
  da empresa nos limites literais descritos. Se faltar algo, especifique se é a
  identidade do signatário, a extensão dos poderes ou outra peça; não atribua ao
  representante a obrigação de representar o alienante.
- Não misture pessoas ou papéis de arquivos diferentes. Um nome parecido não prova
  que se trata da mesma pessoa. Só atribua a condição de sócio, administrador,
  proprietário, outorgante ou procurador à pessoa literalmente identificada no documento
  correspondente; informe o nome do arquivo e um trecho literal curto que
  sustenta cada vínculo. Sem esse trecho, informe "vínculo não confirmado".
- Na procuração, a outorgante concede poderes à procuradora; não inverta esses
  papéis. No contrato social, poderes da sócia não pertencem ao vendedor pessoa
  física. Se a ligação entre partes e documentos não estiver expressa, marque
  "não confirmado" e peça esclarecimento ao escrevente.
- Compare nomes, documentos, datas e poderes entre os arquivos; não resolva
  divergências por suposição. Quando faltar uma peça, diga exatamente qual é e por quê.
- A busca local percorre todas as páginas e blocos processados dos arquivos liberados;
  o contexto traz os trechos mais relevantes e fatos propostos, não a transcrição
  integral. Fundamente a resposta nos trechos exibidos, cite arquivo e página e
  informe se algum arquivo estiver pendente, parcial ou bloqueado.
- Quando o escrevente pedir uma análise geral do processo, comece com uma síntese
  do conjunto: objeto do ato, situação aparente da titularidade e representação,
  compatibilidades ou divergências entre os documentos e pendências relevantes.
  Em seguida, detalhe o que cada arquivo trata e quais fatos literais ele sustenta;
  não reduza a resposta a uma lista isolada de documentos nem trate cada arquivo
  como se pertencesse a um processo diferente.
- Se o texto estiver ilegível ou incompleto, peça cópia legível ou transcrição do
  trecho específico. Não afirme ter examinado página ausente ou OCR parcial.
- Não declare que todos os ônus foram baixados ou que a matrícula está livre
  sem conferir a averbação correspondente e a integridade/atualidade do documento.
- Copie literalmente a numeração registral (R.1, Av.2, Av.3 etc.); não renumere
  os atos em títulos ou listas. Uma averbação posterior pode cancelar outra,
  mas não afirme ausência de outros ônus sem leitura integral da matrícula.
- Relacione cronologicamente os atos registrais: quando uma averbação posterior
  disser expressamente que cancela ou baixa um ônus anterior, informe que aquele
  ônus foi cancelado/baixado conforme o texto; não o descreva como ainda vigente
  ou de situação indeterminada. Não generalize esse cancelamento a outros atos.
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
- Antes de listar pendências, compare-as com todos os documentos disponíveis e
  remova qualquer pendência que já esteja expressamente resolvida por outro arquivo
  ou por averbação posterior. Não contradiga um fato explícito do contexto.
- Toda pendência deve indicar qual requisito ou fato está ausente e por que isso
  impede ou limita a conclusão. Não invente exigências, vínculos ou autorizações;
  se a relevância jurídica depender de norma externa ao contexto, identifique-a
  como ponto para conferência, não como impedimento comprovado.
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
            .order_by(CasoDocumento.created_at.asc(), CasoDocumentoPagina.pagina.asc())
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
            .all()
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
        estado = "\n\n".join(blocos)[:6_000]
        texto_fatos = "\n\n".join(
            _selecionar_fatos_contexto(fatos, documentos_por_id, mensagem.conteudo)
        )
        texto_documentos = "\n\n".join(
            _selecionar_paginas_contexto(linhas_documentos, mensagem.conteudo)
        )
        contexto = (
            f"{estado}\n\n{texto_fatos}\n\n"
            f"Evidências localizadas nos arquivos:\n{texto_documentos}"
        )[:20_000]
        historico = "\n".join(
            f"{item.papel}: {item.conteudo}"
            for item in db.query(CasoMensagem)
            .filter(CasoMensagem.caso_id == caso.id)
            .order_by(CasoMensagem.created_at.desc())
            .limit(8)
            .all()[::-1]
        )[-2_000:]
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
    responder_apos_processamento: bool = True,
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

    if not responder_apos_processamento:
        concluir_tarefa(tarefa_chat_id)
        return

    processar_mensagem_caso(mensagem_id, tarefa_chat_id)
