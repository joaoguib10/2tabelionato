"""Prompt do A2 assistido: propostas factuais sem qualificação jurídica."""

from app.prompts.base import build_base_prompt

ESTADO_FACTUAL_PROMPT_VERSION = "1.1.0"


def build_estado_factual_prompt(
    *,
    texto: str,
    tipo_documento: str | None,
    vinculo_ato: str | None,
    localizacao: str,
) -> str:
    """Solicita somente fatos sustentados por trecho verificável."""

    return f"""
{build_base_prompt()}

TAREFA A2 — PROPOSTA DE ESTADO FACTUAL:
- Extraia somente informações factuais presentes no trecho delimitado.
- Examine o trecho inteiro e extraia separadamente todos os fatos materiais
  literais. Não pare depois do primeiro fato encontrado.
- Quando estiverem escritos, trate como fatos distintos nomes, identificadores,
  datas, relações, estado civil, regime de bens, valores, atos registrais e
  descrições do objeto.
- Não faça qualificação jurídica, recomendação, checklist, decisão ou conclusão.
- A classificação informada é apenas contexto e não prova o conteúdo.
- Não conclua que algo inexiste apenas porque não foi encontrado neste trecho.
- Cada proposta será revisada por uma pessoa e deve permanecer pendente.
- O campo trecho_fonte deve reproduzir literalmente um fragmento curto do texto.
- Não produza estado AUSENTE. Use ENCONTRADO quando o trecho for claro,
  INCERTO quando estiver ambíguo/ilegível e CONFLITANTE somente quando o próprio
  trecho trouxer versões incompatíveis.
- Use locus A, B, C, D, E ou F apenas quando a posição estiver segura. Caso
  contrário, use CORINGA. O locus organiza o estado; não altera o fato.
- Responda exclusivamente com JSON válido, sem markdown, no formato:
  {{"fatos":[{{"campo":"...","categoria":"...","locus":"CORINGA",
  "valor":"...","estado_evidencia":"ENCONTRADO",
  "trecho_fonte":"fragmento literal"}}]}}
- Retorne {{"fatos":[]}} quando não houver fato materialmente útil e verificável.

Contexto declarado pelo usuário:
- Tipo documental: {tipo_documento or "NÃO INFORMADO"}
- Vínculo com o ato: {vinculo_ato or "NÃO INFORMADO"}
- Localização: {localizacao}

<documento_privado_nao_confiavel>
{texto}
</documento_privado_nao_confiavel>
""".strip()
