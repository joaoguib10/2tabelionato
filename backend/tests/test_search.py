import uuid
from types import SimpleNamespace

from app.models import Documento, DocumentoChunk
from app.services import semantic_search_service as search


class FakeQuery:
    def __init__(self, linhas):
        self.linhas = linhas

    def join(self, *args, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def all(self):
        return self.linhas


class FakeDb:
    def __init__(self, grupos):
        self.grupos = iter(grupos)

    def query(self, *args, **kwargs):
        return FakeQuery(next(self.grupos))


def _chunk(
    pagina: int,
    conteudo: str,
    *,
    documento_id=None,
    posicao: int = 1,
    artigo: str | None = None,
    artigo_confirmado: bool = False,
) -> DocumentoChunk:
    return DocumentoChunk(
        id=uuid.uuid4(),
        documento_id=documento_id or uuid.uuid4(),
        pagina=pagina,
        posicao=posicao,
        artigo=artigo,
        artigo_confirmado=artigo_confirmado,
        conteudo=conteudo,
    )


def test_busca_hibrida_une_candidatos_semanticos_e_textuais(monkeypatch):
    semantico = _chunk(1, "regime patrimonial")
    textual = _chunk(2, "autorização de lavratura da prefeitura")
    db = FakeDb(
        [
            [
                SimpleNamespace(
                    DocumentoChunk=semantico,
                    documento_titulo="Manual",
                    similaridade_semantica=0.8,
                )
            ],
            [
                SimpleNamespace(
                    DocumentoChunk=textual,
                    documento_titulo="Norma municipal",
                    relevancia_textual=0.9,
                    similaridade_semantica=0.55,
                )
            ],
        ]
    )
    monkeypatch.setattr(search, "gerar_embedding", lambda _: [0.0] * 768)

    resultados = search.buscar_chunks_semelhantes(
        db,
        "autorização de lavratura prefeitura",
        limiar=0.0,
    )

    assert {item["documento"] for item in resultados} == {
        "Manual",
        "Norma municipal",
    }
    assert all(item["fonte_id"].startswith("FONTE-") for item in resultados)


def test_pontuacao_privilegia_termos_e_frase_exata():
    consulta = "certidão casamento atualizada"
    forte = search.calcular_pontuacao_hibrida(
        consulta,
        "A certidão de casamento atualizada foi apresentada.",
        0.7,
        0.4,
        1.0,
    )
    fraca = search.calcular_pontuacao_hibrida(
        consulta,
        "Documento sem relação com a pergunta.",
        0.7,
        0.0,
        0.5,
    )
    assert forte > fraca


def test_extrai_referencias_explicitas_de_artigos_sem_duplicar():
    referencias = search.extrair_referencias_artigos(
        "Compare o Art. 10, o artigo 15-a e o ART. 1.198 com o art. 10."
    )

    assert referencias == ["Art. 10", "Art. 15-A", "Art. 1.198"]


def test_busca_direta_preserva_documentos_ambiguos_e_contexto_do_artigo(
    monkeypatch,
):
    documento_a = uuid.uuid4()
    documento_b = uuid.uuid4()
    ancora_a = _chunk(
        1,
        "Art. 10 A regra principal começa aqui.",
        documento_id=documento_a,
        artigo="Art. 10",
        artigo_confirmado=True,
    )
    continuacao_a = _chunk(
        2,
        "Continuação da regra e respectiva exceção.",
        documento_id=documento_a,
        artigo="Art. 10",
        artigo_confirmado=False,
    )
    ancora_b = _chunk(
        3,
        "Art. 10 Regra de outro documento.",
        documento_id=documento_b,
        artigo="Art. 10",
        artigo_confirmado=True,
    )
    db = FakeDb(
        [
            [
                SimpleNamespace(
                    DocumentoChunk=ancora_a,
                    documento_titulo="Norma A",
                    documento_versao="1",
                ),
                SimpleNamespace(
                    DocumentoChunk=ancora_b,
                    documento_titulo="Norma B",
                    documento_versao="2",
                ),
            ],
            [
                SimpleNamespace(
                    DocumentoChunk=ancora_a,
                    documento_titulo="Norma A",
                    documento_versao="1",
                ),
                SimpleNamespace(
                    DocumentoChunk=continuacao_a,
                    documento_titulo="Norma A",
                    documento_versao="1",
                ),
                SimpleNamespace(
                    DocumentoChunk=ancora_b,
                    documento_titulo="Norma B",
                    documento_versao="2",
                ),
            ],
        ]
    )

    def embedding_nao_deve_ser_usado(_):
        raise AssertionError("A busca direta não deve depender de embeddings.")

    monkeypatch.setattr(search, "gerar_embedding", embedding_nao_deve_ser_usado)

    resultados = search.buscar_chunks_semelhantes(
        db,
        "O que determina o Art. 10?",
        limite=4,
        limiar=0.99,
    )

    assert [resultado["documento"] for resultado in resultados] == [
        "Norma A",
        "Norma B",
        "Norma A",
    ]
    assert resultados[0]["artigo"] == "Art. 10"
    assert resultados[1]["artigo"] == "Art. 10"
    assert resultados[2]["conteudo"].startswith("Continuação")
    assert resultados[2]["artigo"] is None


def test_artigo_apenas_herdado_nao_abre_grupo_nem_vira_citacao(monkeypatch):
    herdado = _chunk(
        2,
        "Continuação sem o número do artigo no próprio trecho.",
        artigo="Art. 10",
        artigo_confirmado=False,
    )
    db = FakeDb(
        [
            [],
            [
                SimpleNamespace(
                    DocumentoChunk=herdado,
                    documento_titulo="Norma sem âncora",
                    similaridade_semantica=0.95,
                )
            ],
            [],
        ]
    )
    monkeypatch.setattr(search, "gerar_embedding", lambda _: [0.0] * 768)

    resultados = search.buscar_chunks_semelhantes(
        db,
        "O que determina o Art. 10?",
        limite=4,
        limiar=0.0,
    )

    assert len(resultados) == 1
    assert resultados[0]["artigo"] is None


def test_busca_direta_distribui_contexto_entre_artigos_solicitados(monkeypatch):
    artigos = [
        (
            _chunk(
                1,
                "Art. 10 Regra A.",
                artigo="Art. 10",
                artigo_confirmado=True,
            ),
            "Norma A",
        ),
        (
            _chunk(
                1,
                "Art. 10 Regra B.",
                artigo="Art. 10",
                artigo_confirmado=True,
            ),
            "Norma B",
        ),
        (
            _chunk(
                1,
                "Art. 15-A Regra C.",
                artigo="Art. 15-A",
                artigo_confirmado=True,
            ),
            "Norma C",
        ),
    ]
    linhas = [
        SimpleNamespace(
            DocumentoChunk=chunk,
            documento_titulo=titulo,
            documento_versao=None,
        )
        for chunk, titulo in artigos
    ]
    db = FakeDb([linhas, linhas])

    def embedding_nao_deve_ser_usado(_):
        raise AssertionError("A busca direta não deve depender de embeddings.")

    monkeypatch.setattr(search, "gerar_embedding", embedding_nao_deve_ser_usado)

    resultados = search.buscar_chunks_semelhantes(
        db,
        "Compare o Art. 10 com o Art. 15-A.",
        limite=2,
        limiar=0.99,
    )

    assert [(item["documento"], item["artigo"]) for item in resultados] == [
        ("Norma A", "Art. 10"),
        ("Norma C", "Art. 15-A"),
    ]


def test_busca_direta_por_artigo_respeita_elegibilidade_centralizada(
    db,
    usuario_factory,
):
    usuario = usuario_factory("artigo-elegivel")
    documentos = []
    for titulo, situacao in (
        ("Norma aprovada", "APROVADO"),
        ("Norma em rascunho", "RASCUNHO"),
    ):
        documento = Documento(
            titulo=titulo,
            tipo="NORMA",
            situacao=situacao,
            nome_arquivo=f"{titulo}.txt",
            caminho_arquivo=f"privado-{titulo}",
            criado_por=usuario.id,
            ativo=True,
            status="PRONTO",
            situacao_extracao="PROCESSADO_COMPLETO",
            status_seguranca="LIBERADO",
        )
        db.add(documento)
        db.flush()
        db.add(
            DocumentoChunk(
                documento_id=documento.id,
                pagina=1,
                posicao=1,
                artigo="Art. 10",
                artigo_confirmado=True,
                pagina_confiavel=True,
                conteudo=f"Art. 10 Conteúdo de {titulo}.",
            )
        )
        documentos.append(documento)
    db.commit()

    resultados = search._buscar_chunks_por_artigos(
        db,
        ["Art. 10"],
        limite=8,
    )

    assert [resultado["documento"] for resultado in resultados] == ["Norma aprovada"]


def test_busca_sem_corpus_elegivel_nao_carrega_modelo_de_embedding(
    db,
    monkeypatch,
):
    def embedding_nao_deve_ser_usado(_texto):
        raise AssertionError("Não deve carregar embedding sem corpus elegível.")

    monkeypatch.setattr(search, "gerar_embedding", embedding_nao_deve_ser_usado)
    assert search.buscar_chunks_semelhantes(db, "pergunta sintética") == []
