import json
import os
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory

from app.config import DATABASE_URL
from app.models import Documento, DocumentoPagina, Usuario
from app.routers.consultation import _garantir_citacoes, _montar_contexto
from app.security import hash_password
from app.services.chunk_service import gerar_chunks_documento
from app.services.document_processor import extrair_documento
from app.services.embedding_service import gerar_embeddings_documento
from app.services.evaluation_service import avaliar_resultado_pipeline
from app.services.ollama_service import gerar_resposta
from app.services.semantic_search_service import buscar_chunks_semelhantes
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def main() -> None:
    url_avaliacao = os.getenv("EVAL_DATABASE_URL")
    if not url_avaliacao:
        raise SystemExit(
            "Defina EVAL_DATABASE_URL apontando para um banco exclusivo de avaliação."
        )
    if url_avaliacao == DATABASE_URL:
        raise SystemExit("EVAL_DATABASE_URL não pode ser igual ao banco operacional.")

    caminho = Path(__file__).resolve().parents[1] / "evals" / "casos_ponta_a_ponta.json"
    casos = json.loads(caminho.read_text(encoding="utf-8"))
    engine = create_engine(url_avaliacao, pool_pre_ping=True)
    aprovados = 0

    with TemporaryDirectory(prefix="tabeleao-eval-") as diretorio:
        for caso in casos:
            with engine.connect() as conexao:
                transacao = conexao.begin()
                db = Session(bind=conexao)
                try:
                    usuario = Usuario(
                        nome="Avaliador fictício",
                        username=f"avaliacao-{uuid.uuid4().hex}",
                        password_hash=hash_password("0000"),
                        role="ADMIN",
                        ativo=True,
                    )
                    db.add(usuario)
                    db.flush()

                    for indice, definicao in enumerate(
                        caso.get("documentos", []), start=1
                    ):
                        arquivo = (
                            Path(diretorio) / f"{indice}-{definicao['nome_arquivo']}"
                        )
                        arquivo.write_text(definicao["conteudo"], encoding="utf-8")
                        documento = Documento(
                            titulo=definicao["titulo"],
                            tipo=definicao["categoria"],
                            situacao="APROVADO",
                            nome_arquivo=definicao["nome_arquivo"],
                            caminho_arquivo=str(arquivo),
                            criado_por=usuario.id,
                            ativo=True,
                            status="PROCESSANDO",
                            status_seguranca="LIBERADO",
                        )
                        db.add(documento)
                        db.flush()
                        extracao = extrair_documento(str(arquivo))
                        documento.situacao_extracao = extracao.situacao
                        documento.diagnostico_extracao = extracao.resumo()
                        for parte in extracao.partes:
                            db.add(
                                DocumentoPagina(
                                    documento_id=documento.id,
                                    pagina=parte.numero,
                                    pagina_confiavel=False,
                                    localizacao="Documento sintético sem paginação física",
                                    conteudo=parte.conteudo,
                                    metodo_extracao=parte.metodo,
                                    situacao_extracao=parte.situacao,
                                )
                            )
                        db.flush()
                        gerar_chunks_documento(db, documento.id, commit=False)
                        gerar_embeddings_documento(db, documento.id, commit=False)
                        documento.status = "PRONTO"
                    db.flush()

                    resultados = buscar_chunks_semelhantes(
                        db, caso["pergunta"], limite=8
                    )
                    if resultados:
                        resposta_modelo = gerar_resposta(
                            caso["pergunta"], _montar_contexto(resultados)
                        )
                        resposta, citacoes, situacao = _garantir_citacoes(
                            resposta_modelo, resultados
                        )
                        fontes = [
                            item for item in resultados if item["fonte_id"] in citacoes
                        ]
                    else:
                        resposta = "Não há base documental suficiente para responder."
                        situacao = "BASE_INSUFICIENTE"
                        fontes = []
                    avaliacao = avaliar_resultado_pipeline(
                        caso, resposta, situacao, fontes
                    )
                    aprovados += int(avaliacao["aprovada"])
                    estado = "OK" if avaliacao["aprovada"] else "FALHOU"
                    print(f"{estado}: {caso['id']} - {avaliacao}")
                finally:
                    db.close()
                    transacao.rollback()

    print(f"Resultado: {aprovados}/{len(casos)} casos aprovados")
    if aprovados != len(casos):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
