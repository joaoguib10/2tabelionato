"""Prompts de leitura e estruturação de documentos temporários."""

from app.prompts.base import build_base_prompt

ANALISE_DOCUMENTAL_PROMPT_VERSION = "1.1.0"
ANALISE_DOCUMENTAL_TEXT_LIMIT = 12_000


def build_analise_imagem_prompt(finalidade: str) -> str:
    return (
        f"{build_base_prompt()}\n\n"
        "Transcreva e analise este documento para auxiliar uma "
        "minuta notarial. Identifique datas, nomes, CPF, estado "
        "civil, regime de bens, averbações e, se for matrícula, "
        "a descrição e os ônus/anotações. Não presuma texto "
        f"ilegível. Finalidade do arquivo: {finalidade}."
    )


def build_estruturacao_documental_prompt(
    texto: str,
    finalidade: str,
) -> str:
    return f"""
  {build_base_prompt()}

  Extraia dados do documento abaixo sem inventar informações. Responda apenas
  com JSON válido. Preserve os campos simples abaixo para compatibilidade com
  a conferência atual. Use null quando um dado não estiver legível ou não existir.
  Datas devem usar o formato AAAA-MM-DD. Retorne os campos:
  tipo_documento, pessoas (lista de objetos com nome e cpf), data_emissao,
  data_validade, estado_civil, regime_bens, data_casamento,
  data_registro_casamento, matricula, descricao_imovel, valores, tributos,
  averbacoes e observacoes.

  Retorne também o objeto "evidencias". Para cada campo relevante, use a chave
  correspondente (por exemplo, "data_emissao" ou "pessoas[0].cpf") e informe:
  status (somente ENCONTRADO, AUSENTE ou INCERTO), valor, origem, pagina,
  trecho e observacao. Use ENCONTRADO apenas quando o valor estiver legível e
  sustentado pelo trecho; AUSENTE quando o documento não apresentar o dado;
  INCERTO quando houver ambiguidade ou ilegibilidade. Não invente página:
  quando ela não puder ser determinada com segurança, use null. O trecho deve
  ser curto e fiel ao documento.

Finalidade: {finalidade}
  <documento_temporario>
  {texto[:ANALISE_DOCUMENTAL_TEXT_LIMIT]}
  </documento_temporario>
"""
