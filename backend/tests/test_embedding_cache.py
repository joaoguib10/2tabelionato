import json

from app.services import embedding_service


class RespostaEmbedding:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(
            {"embeddings": [[0.1] * embedding_service.DIMENSAO_EMBEDDING]}
        ).encode("utf-8")


def test_embedding_de_consulta_repetida_usa_cache_por_hash(monkeypatch):
    chamadas = []

    def responder(requisicao, timeout):
        chamadas.append((requisicao, timeout))
        return RespostaEmbedding()

    embedding_service.limpar_cache_embeddings_consulta()
    monkeypatch.setattr(embedding_service.urllib.request, "urlopen", responder)
    primeiro = embedding_service.gerar_embedding("pergunta sintética única")
    segundo = embedding_service.gerar_embedding("pergunta sintética única")

    assert primeiro == segundo
    assert len(chamadas) == 1
    payload = json.loads(chamadas[0][0].data.decode("utf-8"))
    assert payload["options"] == {"num_gpu": embedding_service.OLLAMA_EMBED_NUM_GPU}
    assert "pergunta sintética única" not in next(
        iter(embedding_service._cache_consultas)
    )
    embedding_service.limpar_cache_embeddings_consulta()
