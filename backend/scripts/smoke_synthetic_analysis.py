"""Triagem local e sem banco de seis tipos de documento inteiramente fictícios."""

from app.prompts.estado_factual import build_estado_factual_prompt
from app.services.case_fact_extraction_service import (
    _gerar_propostas,
    _proposta_validada,
)

AMOSTRAS = (
    (
        "RG_CNH",
        "TRANSMITENTE",
        "CARTEIRA NACIONAL DE HABILITAÇÃO\nNome: Pessoa Exemplo.\n"
        "Categoria: B.\nValidade: 31/12/2030.",
    ),
    (
        "DOCUMENTO_PESSOAL",
        "ADQUIRENTE",
        "REGISTRO GERAL FICTÍCIO\nNome: Pessoa Modelo.\n"
        "Data de nascimento: 10/05/1990.\nÓrgão emissor: Instituto Exemplo.",
    ),
    (
        "CERTIDAO_CASAMENTO",
        "TRANSMITENTE",
        "CERTIDÃO DE CASAMENTO FICTÍCIA\nPessoa Exemplo e Pessoa Consorte "
        "casaram-se em 12/06/2010.\nRegime: comunhão parcial de bens.\n"
        "Certidão emitida em 15/08/2026.",
    ),
    (
        "CONTRATO_SOCIAL",
        "ADQUIRENTE",
        "CONTRATO SOCIAL FICTÍCIO DE EMPRESA EXEMPLO LTDA.\n"
        "Cláusula 8: a administração cabe à sócia Pessoa Modelo, que pode "
        "assinar isoladamente a compra de imóveis em nome da sociedade.",
    ),
    (
        "PROCURACAO",
        "TRANSMITENTE",
        "PROCURAÇÃO FICTÍCIA\nA outorgante Pessoa Exemplo nomeia a procuradora "
        "Pessoa Representante para vender o imóvel da matrícula 123. "
        "Preço mínimo autorizado: R$ 500.000,00. Validade até 31/12/2027.",
    ),
    (
        "MATRICULA_IMOVEL",
        "IMOVEL",
        "MATRÍCULA FICTÍCIA 123\nProprietária: Pessoa Exemplo.\n"
        "R.1: aquisição por Pessoa Exemplo.\nAv.2: alienação fiduciária "
        "em favor de Banco Exemplo.\nAv.3: cancelamento da alienação fiduciária.",
    ),
)


def main() -> None:
    falhas = []
    for tipo, vinculo, texto in AMOSTRAS:
        prompt = build_estado_factual_prompt(
            texto=texto,
            tipo_documento=tipo,
            vinculo_ato=vinculo,
            localizacao="Documento sintético",
        )
        try:
            resposta = _gerar_propostas(prompt)
            validadas = [
                item
                for bruto in resposta["fatos"]
                if (item := _proposta_validada(bruto, texto)) is not None
            ]
            print(f"{tipo}: {len(validadas)} fato(s) verificável(is)")
            if not validadas:
                falhas.append(tipo)
        except Exception as erro:
            print(f"{tipo}: falha técnica ({type(erro).__name__})")
            falhas.append(tipo)
    if falhas:
        raise SystemExit(f"Triagem incompleta em {len(falhas)} tipo(s).")


if __name__ == "__main__":
    main()
