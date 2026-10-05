"""Prompt do A2 assistido: propostas factuais sem qualificação jurídica."""

from app.prompts.base import build_base_prompt

ESTADO_FACTUAL_PROMPT_VERSION = "1.3.0"


def build_estado_factual_prompt(
    *,
    texto: str,
    tipo_documento: str | None,
    vinculo_ato: str | None,
    localizacao: str,
) -> str:
    """Solicita somente fatos sustentados por trecho verificável."""

    tipo_normalizado = (tipo_documento or "").casefold()
    foco_societario = ""
    foco_matricula = ""
    foco_civil = ""
    foco_identificacao = ""
    foco_representacao = ""
    if any(
        termo in tipo_normalizado for termo in ("social", "societ", "alter", "estat")
    ):
        foco_societario = """
- Como o documento pode ser societário, procure e extraia, se estiverem neste
  trecho: nomes dos administradores/sócios administradores, cláusula de
  administração e representação, poderes para agir ou assinar pela sociedade,
  atuação isolada ou conjunta, limitações, prazo e necessidade de deliberação.
  Registre cada pessoa, poder e condição em fatos separados, com a cláusula
  literal como trecho_fonte. A função pode estar expressa sem a palavra
  "representante" (por exemplo, administrador autorizado a usar o nome
  empresarial); não atribua esses poderes aos demais sócios sem apoio textual.
""".strip()

    if "matricula" in tipo_normalizado or "certidao_imovel" in tipo_normalizado:
        foco_matricula = """
- Como o documento pode ser uma matrícula ou certidão imobiliária, percorra cada
  registro e averbação visível na ordem original (R., Av. e seus números). Extraia
  separadamente titular atual, transmissões/aquisições, herança ou meação, ônus,
  restrições, indisponibilidades, penhoras, cancelamentos e descrição do imóvel.
  Preserve a numeração literal e associe cada fato ao trecho exato; não conclua que
  o imóvel está livre nem que uma anotação posterior cancela outra sem texto expresso.
""".strip()

    if "certidao" in tipo_normalizado or "estado_civil" in tipo_normalizado:
        foco_civil = """
- Como o documento pode ser certidão civil, extraia nome completo, CPF se constar,
  filiação, estado civil demonstrado, data do registro/celebração, regime de bens,
  emissão e cada averbação de divórcio, separação ou óbito com sua data. Não trate
  certidão de nascimento como prova de estado civil atual quando o trecho não o disser.
""".strip()

    if any(termo in tipo_normalizado for termo in ("rg", "cnh", "pessoal")):
        foco_identificacao = """
- Como o documento pode ser de identificação, procure nome completo, CPF, número
  e órgão emissor, filiação e data de nascimento quando legíveis. Não invente
  campos ausentes nem combine dados de pessoas diferentes.
""".strip()

    if any(
        termo in tipo_normalizado
        for termo in ("procuracao", "alvara", "ata", "estatuto", "contrato_instrumento")
    ):
        foco_representacao = """
- Como o documento pode conferir poderes de representação, extraia outorgante,
  representante, pessoa/entidade representada, poderes literais, objeto, limites,
  valor mínimo, prazo, condições e assinaturas/deliberações indicadas.
""".strip()

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
{foco_societario}
{foco_matricula}
{foco_civil}
{foco_identificacao}
{foco_representacao}
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
