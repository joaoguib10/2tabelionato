"""Expressões PostgreSQL compartilhadas pelos índices de busca textual."""

from sqlalchemy import func, literal_column

CARACTERES_COM_ACENTO = "áàâãéêíóôõúüçÁÀÂÃÉÊÍÓÔÕÚÜÇ"
CARACTERES_SEM_ACENTO = "aaaaeeiooouucAAAAEEIOOOUUC"


def normalizar_texto_busca_sql(expressao):
    return func.translate(
        expressao,
        literal_column(f"'{CARACTERES_COM_ACENTO}'"),
        literal_column(f"'{CARACTERES_SEM_ACENTO}'"),
    )


def texto_metadados_documento_sql(titulo, descricao):
    return (
        func.coalesce(titulo, literal_column("''"))
        .op("||")(literal_column("' '"))
        .op("||")(func.coalesce(descricao, literal_column("''")))
    )


def tsvector_portugues_sql(expressao):
    return func.to_tsvector(
        literal_column("'portuguese'"), normalizar_texto_busca_sql(expressao)
    )
