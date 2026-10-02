"""Extração A2 especializada para Compra e Venda, sempre sujeita à conferência."""

from app.prompts.base import build_base_prompt

COMPRA_VENDA_PROMPT_VERSION = "1.3.0"


def build_compra_venda_prompt(
    *, texto: str, tipo_documento: str | None, vinculo_ato: str | None, localizacao: str
) -> str:
    return f"""
{build_base_prompt()}

TAREFA A2 — EXTRAÇÃO ESTRUTURADA DE COMPRA E VENDA:
- Extraia apenas dados escritos literalmente no trecho.
- A classificação declarada é contexto, não prova.
- Não decida a validade, capacidade, propriedade, anuência ou aptidão do ato.
- Não preencha profissão ou endereço por suposição.
- Cada pessoa deve ser separada. Diferencie principal, cônjuge, anuente,
  representante ou procurador somente quando o texto permitir.
- Use OUTORGANTE para quem transmite e OUTORGADO para quem adquire. Não use
  vendedor/comprador como papel estrutural.
- O vínculo declarado TRANSMITENTE sugere OUTORGANTE e ADQUIRENTE sugere
  OUTORGADO, mas continua sendo contexto sujeito à conferência.
- Na frase "X, representado(a) por Y", X é a parte PRINCIPAL e Y é o
  REPRESENTANTE ou PROCURADOR. Em Y, principal_nome deve ser X. Os dados do
  alvará ou da procuração pertencem a X, não a Y. Nunca inverta essa relação.
- Para pessoa física, procure nome, CPF, nacionalidade, capacidade expressa,
  estado civil, união estável, profissão e endereço.
- Para casamento, procure matrícula da certidão, data do registro/celebração,
  regime de bens, data de emissão e selo digital. Registre averbação de divórcio,
  separação ou óbito como fato, sem concluir o estado civil quando houver dúvida.
- Para empresa, procure razão social, CNPJ, NIRE, endereço, representante,
  cláusula e trecho literal dos poderes de representação.
- Para atas, estatutos e regimentos, identifique a instituição, a reunião ou
  assembleia, a data, os participantes, a deliberação e o trecho literal que
  confere poderes de representação. Não presuma poderes apenas pela função
  informada; exija a deliberação ou regra documental correspondente.
- Para procuração, procure data, livro, folhas, tabelionato, cidade/comarca,
  emissão da certidão, selo, poderes expressos e limites mínimo/máximo de valor.
- Para alvará judicial, procure processo, juízo, decisão, validade, representante,
  poderes e limites mínimo/máximo de valor. Não conclua que o alvará é suficiente.
- Extraia o valor e a forma de pagamento da escritura/negócio somente quando
  estiverem literais.
- Para matrícula, preserve todos os R./Av. materialmente relevantes na ordem.
  Extraia a última descrição completa/especialidade objetiva e, separadamente,
  logradouro, número, bairro e cidade quando escritos.
- Todo item precisa conter trecho_fonte curto e literal. Não invente.
- Responda somente JSON válido:
{{
  "partes": [{{
    "papel":"OUTORGANTE|OUTORGADO|null", "participacao":"PRINCIPAL|CONJUGE|ANUENTE|REPRESENTANTE|PROCURADOR",
    "principal_nome":"...|null", "natureza":"FISICA|JURIDICA", "nome_completo":"...|null",
    "nacionalidade":"...|null", "capacidade":"...|null", "estado_civil":"...|null",
    "uniao_estavel":true|false|null, "profissao":"...|null", "cpf":"...|null", "endereco":"...|null",
    "casamento":{{"matricula":null,"data_registro":null,"regime_bens":null,"data_certidao":null,"selo_digital":null}},
    "empresa":{{"cnpj":null,"nire":null,"endereco":null,"clausula_poderes":null,"descricao_poderes":null}},
    "modo_qualificacao":"INDIVIDUAL|UNIAO_ESTAVEL|CASAL_AMBOS_ASSINAM|CASAL_COM_ANUENTE|CASADO_APENAS_UM|EMPRESA_REPRESENTADA|PROCURACAO|ALVARA_JUDICIAL",
    "procuracao":{{"lavrada_em":null,"livro":null,"folhas":null,"tabelionato":null,"cidade_comarca":null,"certidao_emitida_em":null,"selo_digital":null,"poderes":null,"valor_minimo":null,"valor_maximo":null}},
    "alvara":{{"numero_processo":null,"juizo":null,"data_decisao":null,"data_validade":null,"representante":null,"poderes":null,"valor_minimo":null,"valor_maximo":null}},
    "trecho_fonte":"fragmento literal"
  }}],
  "imovel": {{"matricula":null,"logradouro":null,"numero":null,"bairro":null,"cidade":null,
    "descricao_completa":null,"trecho_fonte":null,
    "averbacoes":[{{"rotulo":"Av.1","resumo":"...","trecho_fonte":"fragmento literal"}}]}},
  "negocio":{{"valor_escritura":null,"forma_pagamento":null,"moeda":"BRL","observacoes":null,"trecho_fonte":null}}
}}

Contexto declarado:
- Tipo: {tipo_documento or "NÃO INFORMADO"}
- Relação com o ato: {vinculo_ato or "NÃO INFORMADO"}
- Localização: {localizacao}

<documento_privado_nao_confiavel>
{texto}
</documento_privado_nao_confiavel>
""".strip()
