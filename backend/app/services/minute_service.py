import base64
import json
import urllib.request
from datetime import date, datetime, timedelta
from io import BytesIO

from pypdf import PdfReader

from app.config import (
    OLLAMA_BASE_URL,
    OLLAMA_GENERATION_MODEL,
    OLLAMA_VISION_MODEL,
)
from app.prompts import (
    build_analise_imagem_prompt,
    build_estruturacao_documental_prompt,
    build_minuta_prompt,
)


def extrair_texto_pdf(conteudo: bytes) -> str:
    leitor = PdfReader(BytesIO(conteudo))
    return "\n\n".join(
        texto.strip()
        for pagina in leitor.pages
        if (texto := pagina.extract_text()) and texto.strip()
    )


def analisar_imagem(conteudo: bytes, finalidade: str) -> str:
    dados = {
        "model": OLLAMA_VISION_MODEL,
        "stream": False,
        "messages": [
            {
                "role": "user",
                "content": build_analise_imagem_prompt(finalidade),
                "images": [base64.b64encode(conteudo).decode("ascii")],
            }
        ],
        "options": {"temperature": 0.0},
    }
    requisicao = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/chat",
        data=json.dumps(dados).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(requisicao, timeout=300) as resposta:
        resultado = json.loads(resposta.read().decode("utf-8"))

    texto = resultado.get("message", {}).get("content")
    if not texto:
        raise RuntimeError("O modelo visual não retornou uma análise.")
    return texto.strip()


def analisar_arquivo(
    nome: str,
    conteudo: bytes,
    finalidade: str,
) -> str:
    nome_normalizado = nome.lower()
    if nome_normalizado.endswith(".pdf"):
        return extrair_texto_pdf(conteudo)
    if nome_normalizado.endswith((".jpg", ".jpeg", ".png")):
        return analisar_imagem(conteudo, finalidade)
    raise ValueError("Formato não suportado. Envie PDF, JPG, JPEG ou PNG.")


def estruturar_analise(texto: str, finalidade: str) -> dict:
    if not texto.strip():
        return {}
    prompt = build_estruturacao_documental_prompt(texto, finalidade)
    dados_requisicao = {
        "model": OLLAMA_GENERATION_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "format": "json",
        "options": {"temperature": 0.0, "num_ctx": 4096},
    }
    requisicao = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=json.dumps(dados_requisicao).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(requisicao, timeout=300) as resposta:
        resultado = json.loads(resposta.read().decode("utf-8"))
    conteudo = resultado.get("response", "").strip()
    try:
        estruturado = json.loads(conteudo)
        if not isinstance(estruturado, dict):
            return {}
        return completar_dados_certidao(estruturado, finalidade)
    except json.JSONDecodeError:
        return {}


def _data_iso(valor) -> str | None:
    if not isinstance(valor, str) or not valor.strip():
        return None
    texto = valor.strip()
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, formato).date().isoformat()
        except ValueError:
            continue
    return None


def completar_dados_certidao(dados: dict, finalidade: str) -> dict:
    """Normaliza pessoas e calcula a validade interna sem inventar datas."""
    resultado = dict(dados)
    pessoas = resultado.get("pessoas")
    if not isinstance(pessoas, list):
        nomes = resultado.get("nomes")
        cpfs = resultado.get("cpfs")
        nomes = nomes if isinstance(nomes, list) else ([nomes] if nomes else [])
        cpfs = cpfs if isinstance(cpfs, list) else ([cpfs] if cpfs else [])
        pessoas = [
            {
                "nome": nomes[indice] if indice < len(nomes) else None,
                "cpf": cpfs[indice] if indice < len(cpfs) else None,
            }
            for indice in range(max(len(nomes), len(cpfs)))
        ]
    resultado["pessoas"] = [pessoa for pessoa in pessoas if isinstance(pessoa, dict)]

    emissao = _data_iso(resultado.get("data_emissao"))
    if emissao:
        resultado["data_emissao"] = emissao
    validade = _data_iso(resultado.get("data_validade"))
    if validade:
        resultado["data_validade"] = validade
    elif emissao and "vendedor/doador" in finalidade.casefold():
        resultado["data_validade"] = (
            datetime.strptime(emissao, "%Y-%m-%d").date() + timedelta(days=90)
        ).isoformat()

    for campo in ("data_casamento", "data_registro_casamento"):
        valor = _data_iso(resultado.get(campo))
        if valor:
            resultado[campo] = valor
    return resultado


def gerar_minuta(
    tipo_ato: str,
    dados: dict,
    documentos_analisados: list[dict],
    modelo_texto: str,
) -> str:
    prompt = build_minuta_prompt(
        tipo_ato=tipo_ato,
        dados=dados,
        documentos_analisados=documentos_analisados,
        modelo_texto=modelo_texto,
        data_analise=date.today().isoformat(),
    )
    dados_requisicao = {
        "model": OLLAMA_GENERATION_MODEL,
        "prompt": prompt,
        "stream": False,
        "think": False,
        "options": {"temperature": 0.1, "num_ctx": 8192},
    }
    requisicao = urllib.request.Request(
        f"{OLLAMA_BASE_URL}/api/generate",
        data=json.dumps(dados_requisicao).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(requisicao, timeout=300) as resposta:
        resultado = json.loads(resposta.read().decode("utf-8"))

    texto = resultado.get("response")
    if not texto:
        raise RuntimeError("O modelo de linguagem não retornou a minuta.")
    return texto.strip()
