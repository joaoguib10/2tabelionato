"""Processamento temporário e local de exportações do WhatsApp."""

import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from app.config import (
    ATA_MAX_ARCHIVE_ENTRIES,
    ATA_MAX_COMPRESSION_RATIO,
    ATA_MAX_EXTRACTED_BYTES,
    FFMPEG_COMMAND,
    FFPROBE_COMMAND,
    RAR_TOOL_COMMAND,
    WHISPER_COMMAND,
    WHISPER_MODEL_PATH,
)
from app.database import SessionLocal
from app.models import AtaTrabalho, utc_now

EXTENSOES_AUDIO = {".aac", ".flac", ".m4a", ".mp3", ".oga", ".ogg", ".opus", ".wav"}
PADROES_MENSAGEM = (
    re.compile(r"^\[(?P<data>[^\]]+)\]\s*(?P<autor>[^:]+):\s*(?P<texto>.*)$"),
    re.compile(
        r"^(?P<data>\d{1,2}/\d{1,2}/\d{2,4},?\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s+[AP]M)?)\s+-\s+(?P<autor>[^:]+):\s*(?P<texto>.*)$",
        re.I,
    ),
)


class AtaProcessamentoErro(Exception):
    pass


def _nome_seguro(nome: str) -> PurePosixPath:
    normalizado = nome.replace("\\", "/")
    caminho = PurePosixPath(normalizado)
    if (
        caminho.is_absolute()
        or ".." in caminho.parts
        or any(":" in parte for parte in caminho.parts)
    ):
        raise AtaProcessamentoErro("O arquivo compactado contém caminho inválido.")
    return caminho


def _validar_limites(entradas: list[tuple[str, int, int]]) -> None:
    if len(entradas) > ATA_MAX_ARCHIVE_ENTRIES:
        raise AtaProcessamentoErro("O arquivo compactado possui entradas demais.")
    total = 0
    for nome, tamanho, comprimido in entradas:
        _nome_seguro(nome)
        if tamanho < 0 or comprimido < 0:
            raise AtaProcessamentoErro(
                "O arquivo compactado possui metadados inválidos."
            )
        total += tamanho
        if total > ATA_MAX_EXTRACTED_BYTES:
            raise AtaProcessamentoErro(
                "O conteúdo descompactado excede o limite configurado."
            )
        if tamanho and tamanho / max(1, comprimido) > ATA_MAX_COMPRESSION_RATIO:
            raise AtaProcessamentoErro(
                "O arquivo compactado possui taxa de compressão insegura."
            )


def _copiar_fluxo(origem, destino: Path) -> None:
    destino.parent.mkdir(parents=True, exist_ok=True)
    with destino.open("wb") as saida:
        shutil.copyfileobj(origem, saida, length=1024 * 1024)


def _extrair_zip(arquivo: Path, destino: Path) -> list[Path]:
    extraidos = []
    with zipfile.ZipFile(arquivo) as pacote:
        infos = [info for info in pacote.infolist() if not info.is_dir()]
        _validar_limites([(i.filename, i.file_size, i.compress_size) for i in infos])
        for info in infos:
            relativo = _nome_seguro(info.filename)
            extensao = relativo.suffix.lower()
            if extensao != ".txt" and extensao not in EXTENSOES_AUDIO:
                continue
            alvo = destino.joinpath(*relativo.parts)
            with pacote.open(info) as origem:
                _copiar_fluxo(origem, alvo)
            extraidos.append(alvo)
    return extraidos


def _extrair_rar(arquivo: Path, destino: Path) -> list[Path]:
    try:
        import rarfile
    except ImportError as erro:
        raise AtaProcessamentoErro(
            "Instale o suporte local a RAR antes de processar este arquivo."
        ) from erro
    rarfile.SEVENZIP_TOOL = RAR_TOOL_COMMAND
    try:
        rarfile.tool_setup(
            unrar=False,
            unar=False,
            bsdtar=False,
            sevenzip=True,
            sevenzip2=False,
            force=True,
        )
    except rarfile.RarCannotExec as erro:
        raise AtaProcessamentoErro(
            "Configure uma ferramenta local compatível para processar arquivos RAR."
        ) from erro
    extraidos = []
    try:
        with rarfile.RarFile(arquivo) as pacote:
            infos = [info for info in pacote.infolist() if not info.isdir()]
            _validar_limites(
                [(i.filename, i.file_size, i.compress_size) for i in infos]
            )
            for info in infos:
                relativo = _nome_seguro(info.filename)
                extensao = relativo.suffix.lower()
                if extensao != ".txt" and extensao not in EXTENSOES_AUDIO:
                    continue
                alvo = destino.joinpath(*relativo.parts)
                with pacote.open(info) as origem:
                    _copiar_fluxo(origem, alvo)
                extraidos.append(alvo)
    except AtaProcessamentoErro:
        raise
    except Exception as erro:
        raise AtaProcessamentoErro(
            "Não foi possível abrir o arquivo RAR localmente."
        ) from erro
    return extraidos


def _ler_texto(caminho: Path) -> str:
    dados = caminho.read_bytes()
    for codificacao in ("utf-8-sig", "utf-8", "utf-16", "latin-1"):
        try:
            return dados.decode(codificacao)
        except UnicodeDecodeError:
            continue
    raise AtaProcessamentoErro("Não foi possível interpretar o arquivo de conversa.")


def _mensagens(texto: str) -> list[dict[str, str]]:
    mensagens: list[dict[str, str]] = []
    for linha_original in texto.replace("\u200e", "").splitlines():
        linha = linha_original.strip()
        if not linha:
            continue
        encontrada = None
        for padrao in PADROES_MENSAGEM:
            encontrada = padrao.match(linha)
            if encontrada:
                break
        if encontrada:
            mensagens.append(
                {
                    "data": encontrada.group("data").strip(),
                    "autor": encontrada.group("autor").strip(),
                    "texto": encontrada.group("texto").strip(),
                }
            )
        elif mensagens:
            mensagens[-1]["texto"] = f"{mensagens[-1]['texto']} {linha}".strip()
    if not mensagens:
        raise AtaProcessamentoErro(
            "Nenhuma mensagem reconhecível foi encontrada na exportação."
        )
    return mensagens


def _duracao_audio(caminho: Path) -> str:
    ffprobe = shutil.which(FFPROBE_COMMAND)
    if not ffprobe:
        return "duração não identificada"
    try:
        retorno = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(caminho),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        segundos = int(round(float(json.loads(retorno.stdout)["format"]["duration"])))
        return f"{segundos // 60:02d}:{segundos % 60:02d}s"
    except (
        OSError,
        subprocess.SubprocessError,
        KeyError,
        ValueError,
        json.JSONDecodeError,
    ):
        return "duração não identificada"


def _transcrever_audio(caminho: Path) -> str | None:
    comando = shutil.which(WHISPER_COMMAND)
    ffmpeg = shutil.which(FFMPEG_COMMAND)
    modelo = Path(WHISPER_MODEL_PATH) if WHISPER_MODEL_PATH else None
    if not comando or not ffmpeg or not modelo or not modelo.exists():
        return None
    ambiente = os.environ.copy()
    ambiente["PATH"] = str(Path(ffmpeg).parent) + os.pathsep + ambiente.get("PATH", "")
    with tempfile.TemporaryDirectory(prefix="tabeleao-whisper-") as pasta:
        try:
            subprocess.run(
                [
                    comando,
                    str(caminho),
                    "--model",
                    modelo.stem,
                    "--model_dir",
                    str(modelo.parent),
                    "--language",
                    "Portuguese",
                    "--output_format",
                    "txt",
                    "--output_dir",
                    pasta,
                    "--fp16",
                    "False",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1800,
                env=ambiente,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            saida = Path(pasta) / f"{caminho.stem}.txt"
            return (
                " ".join(saida.read_text(encoding="utf-8").split())
                if saida.is_file()
                else None
            )
        except (OSError, subprocess.SubprocessError, UnicodeDecodeError):
            return None


def _formatar(mensagens: list[dict[str, str]], audios: list[Path]) -> tuple[str, int]:
    por_nome = {audio.name.casefold(): audio for audio in audios}
    pendentes = 0
    saida = []
    for mensagem in mensagens:
        texto = " ".join(mensagem["texto"].split())
        audio = next(
            (arquivo for nome, arquivo in por_nome.items() if nome in texto.casefold()),
            None,
        )
        if audio:
            transcricao = _transcrever_audio(audio)
            if transcricao:
                texto = f"(Áudio de {_duracao_audio(audio)}): {transcricao}"
            else:
                texto = (
                    f"(Áudio de {_duracao_audio(audio)}): transcrição local pendente"
                )
                pendentes += 1
        # Referências a imagens, vídeos, PDFs e stickers permanecem exatamente
        # onde aparecem na exportação. Os binários não são processados nesta fase.
        saida.append(f"[{mensagem['data']}] {mensagem['autor']}: {texto}")
    return " ".join(saida), pendentes


def processar_ata(trabalho_id) -> None:
    db = SessionLocal()
    try:
        trabalho = db.get(AtaTrabalho, trabalho_id)
        if trabalho is None:
            return
        arquivo = Path(trabalho.caminho_temporario)
        pasta = arquivo.parent / "extraido"
        if pasta.exists():
            shutil.rmtree(pasta)
        pasta.mkdir(parents=True, exist_ok=True)
        extraidos = (
            _extrair_zip(arquivo, pasta)
            if arquivo.suffix.lower() == ".zip"
            else _extrair_rar(arquivo, pasta)
        )
        textos = [item for item in extraidos if item.suffix.lower() == ".txt"]
        if not textos:
            raise AtaProcessamentoErro(
                "A exportação não contém arquivo TXT da conversa."
            )
        conversa = max(textos, key=lambda item: item.stat().st_size)
        mensagens = _mensagens(_ler_texto(conversa))
        audios = [item for item in extraidos if item.suffix.lower() in EXTENSOES_AUDIO]
        resultado, pendentes = _formatar(mensagens, audios)
        trabalho.resultado = resultado
        trabalho.status = "PRONTO_PARCIAL" if pendentes else "PRONTO"
        trabalho.diagnostico = {
            "mensagens": len(mensagens),
            "audios": len(audios),
            "transcricoes_pendentes": pendentes,
            "referencias_anexos_preservadas": True,
        }
        trabalho.erro_processamento = None
        trabalho.concluido_em = utc_now()
        db.commit()
    except AtaProcessamentoErro as erro:
        db.rollback()
        trabalho = db.get(AtaTrabalho, trabalho_id)
        if trabalho:
            trabalho.status = "ERRO"
            trabalho.erro_processamento = str(erro)[:500]
            trabalho.concluido_em = utc_now()
            db.commit()
    except Exception:
        db.rollback()
        trabalho = db.get(AtaTrabalho, trabalho_id)
        if trabalho:
            trabalho.status = "ERRO"
            trabalho.erro_processamento = (
                "Falha local durante o processamento da exportação."
            )
            trabalho.concluido_em = utc_now()
            db.commit()
    finally:
        db.close()
