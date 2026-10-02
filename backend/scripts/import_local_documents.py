import argparse
import hashlib
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from app.database import SessionLocal
from app.models import Documento, Usuario
from app.services.ingestion_service import processar_documento

UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads" / "documentos"
EXTENSOES_PROCESSAVEIS = {".pdf", ".docx", ".txt"}
MACROCLASSES_PRODUTIVAS = {
    "01_FONTES_JURIDICAS",
    "02_INSTRUMENTOS_OPERACIONAIS",
    "03_ESTRUTURADOS",
}


def hash_arquivo(caminho: Path) -> str:
    resumo = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        while bloco := arquivo.read(1024 * 1024):
            resumo.update(bloco)
    return resumo.hexdigest()


def categoria_inicial(caminho_relativo: Path) -> str:
    partes = {parte.casefold() for parte in caminho_relativo.parts[:-1]}
    if "01_normativas" in partes:
        return "NORMA"
    if partes & {"02_precedentes_judiciais", "03_precedentes_administrativos"}:
        return "ENTENDIMENTO"
    if "02_regras_e_parametros_de_construcao" in partes:
        return "PROCEDIMENTO"
    if "03_checklists" in partes:
        return "PROCEDIMENTO"
    if "04_manuais_e_treinamento_humano" in partes:
        return "MANUAL"
    return "OUTRO"


def nome_limitado(nome: str, limite: int = 255) -> str:
    if len(nome) <= limite:
        return nome
    caminho = Path(nome)
    return f"{caminho.stem[: limite - len(caminho.suffix)]}{caminho.suffix}"


def selecionar_responsavel(db, username: str | None) -> Usuario:
    consulta = db.query(Usuario).filter(Usuario.ativo.is_(True))
    if username:
        usuario = consulta.filter(Usuario.username == username).first()
    else:
        usuario = (
            consulta.filter(Usuario.role == "ADMIN")
            .order_by(Usuario.role.desc(), Usuario.created_at.asc())
            .first()
        )
    if usuario is None:
        raise RuntimeError(
            "Não há usuário administrativo ativo para registrar a importação."
        )
    return usuario


def preencher_hashes_existentes(db) -> None:
    documentos = db.query(Documento).filter(Documento.hash_arquivo.is_(None)).all()
    vistos = {
        valor
        for (valor,) in db.query(Documento.hash_arquivo)
        .filter(Documento.hash_arquivo.is_not(None))
        .all()
    }
    for documento in documentos:
        caminho = Path(documento.caminho_arquivo)
        if not caminho.is_file():
            continue
        resumo = hash_arquivo(caminho)
        if resumo not in vistos:
            documento.hash_arquivo = resumo
            vistos.add(resumo)
    db.commit()


def importar(
    origem: Path,
    username: str | None,
    processar: bool,
    trabalhadores: int = 1,
) -> dict[str, int]:
    origem = origem.resolve()
    if not origem.is_dir():
        raise RuntimeError("O diretório de origem não existe.")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    db = SessionLocal()
    ids_processamento = []
    contadores = {
        "encontrados": 0,
        "importados": 0,
        "duplicados": 0,
        "formatos_pendentes": 0,
        "processados": 0,
    }
    try:
        responsavel = selecionar_responsavel(db, username)
        preencher_hashes_existentes(db)
        candidatos = sorted(
            arquivo
            for arquivo in origem.rglob("*")
            if arquivo.is_file()
            and arquivo.relative_to(origem).parts[0] in MACROCLASSES_PRODUTIVAS
        )
        contadores["encontrados"] = len(candidatos)

        for fonte in candidatos:
            resumo = hash_arquivo(fonte)
            existente = (
                db.query(Documento).filter(Documento.hash_arquivo == resumo).first()
            )
            if existente:
                contadores["duplicados"] += 1
                if (
                    processar
                    and fonte.suffix.lower() in EXTENSOES_PROCESSAVEIS
                    and existente.status in {"PROCESSANDO", "ERRO"}
                ):
                    ids_processamento.append(existente.id)
                continue

            extensao = fonte.suffix.lower()
            destino = UPLOAD_DIR / f"{uuid4()}{extensao}"
            shutil.copy2(fonte, destino)
            processavel = extensao in EXTENSOES_PROCESSAVEIS
            relativo = fonte.relative_to(origem)
            documento = Documento(
                titulo=fonte.stem[:200],
                descricao="Importado do acervo documental local para revisão.",
                tipo=categoria_inicial(relativo),
                tipo_ato=None,
                situacao="RASCUNHO",
                observacoes=(
                    "Classificação inicial automática. Confira os metadados e aprove "
                    "expressamente antes do uso pela IA."
                ),
                nome_arquivo=nome_limitado(fonte.name),
                caminho_arquivo=str(destino),
                hash_arquivo=resumo,
                status_seguranca="PENDENTE",
                ativo=True,
                status="PROCESSANDO" if processavel else "ERRO",
                erro_processamento=(
                    None
                    if processavel
                    else "Formato preservado para download. Converta para PDF, DOCX ou TXT antes de processar."
                ),
                criado_por=responsavel.id,
            )
            try:
                db.add(documento)
                db.commit()
                db.refresh(documento)
            except Exception:
                db.rollback()
                destino.unlink(missing_ok=True)
                raise
            contadores["importados"] += 1
            if processavel:
                ids_processamento.append(documento.id)
            else:
                contadores["formatos_pendentes"] += 1

        if processar:
            fila = list(dict.fromkeys(ids_processamento))
            quantidade_trabalhadores = max(1, min(trabalhadores, 4))
            with ThreadPoolExecutor(max_workers=quantidade_trabalhadores) as executor:
                for _ in executor.map(processar_documento, fila):
                    contadores["processados"] += 1
                    if contadores["processados"] % 25 == 0:
                        print(
                            f"processamento={contadores['processados']}/{len(fila)}",
                            flush=True,
                        )
        return contadores
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Importa, sem mover os originais, o corpus produtivo local do Tabeleão."
    )
    parser.add_argument("origem", type=Path)
    parser.add_argument("--username")
    parser.add_argument("--processar", action="store_true")
    parser.add_argument("--trabalhadores", type=int, default=1)
    argumentos = parser.parse_args()
    resultado = importar(
        argumentos.origem,
        argumentos.username,
        argumentos.processar,
        argumentos.trabalhadores,
    )
    print("Importação documental concluída.")
    for chave, valor in resultado.items():
        print(f"{chave}={valor}")


if __name__ == "__main__":
    main()
