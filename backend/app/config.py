import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR.parent / ".env")
load_dotenv(BACKEND_DIR / ".env")


SECRET_KEY = os.getenv("TABELEAO_SECRET_KEY") or os.getenv("CARTORIO_SECRET_KEY")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("Defina DATABASE_URL no arquivo .env da raiz ou no ambiente.")

# Evita que uma indisponibilidade do PostgreSQL deixe as requisições penduradas
# indefinidamente. O valor é aplicado apenas ao driver PostgreSQL em database.py.
DATABASE_CONNECT_TIMEOUT_SECONDS = int(
    os.getenv("DATABASE_CONNECT_TIMEOUT_SECONDS", "5")
)
DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "5"))
DATABASE_MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
DATABASE_POOL_RECYCLE_SECONDS = int(os.getenv("DATABASE_POOL_RECYCLE_SECONDS", "1800"))

MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
MFA_ENABLED = os.getenv("MFA_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "sim",
}
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480"))
AUTH_COOKIE_NAME = os.getenv("AUTH_COOKIE_NAME", "tabeleao_access")
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "sim",
}
AUTH_COOKIE_SAMESITE = os.getenv("AUTH_COOKIE_SAMESITE", "lax").strip().lower()
if AUTH_COOKIE_SAMESITE not in {"lax", "strict", "none"}:
    raise RuntimeError("AUTH_COOKIE_SAMESITE deve ser lax, strict ou none.")
if AUTH_COOKIE_SAMESITE == "none" and not AUTH_COOKIE_SECURE:
    raise RuntimeError("AUTH_COOKIE_SECURE deve ser true com SameSite=none.")
AUTH_COOKIE_MAX_AGE_SECONDS = ACCESS_TOKEN_EXPIRE_MINUTES * 60
RAG_CONFIDENCE_THRESHOLD = float(os.getenv("RAG_CONFIDENCE_THRESHOLD", "0.28"))
RAG_QUERY_EMBEDDING_CACHE_SIZE = int(os.getenv("RAG_QUERY_EMBEDDING_CACHE_SIZE", "256"))
OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://localhost:11434",
).rstrip("/")
OLLAMA_LOCAL_ONLY = os.getenv("OLLAMA_LOCAL_ONLY", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "sim",
}
OLLAMA_EMBED_MODEL = os.getenv(
    "OLLAMA_EMBED_MODEL",
    "nomic-embed-text-v2-moe",
)
OLLAMA_EMBED_NUM_GPU = int(os.getenv("OLLAMA_EMBED_NUM_GPU", "0"))
OLLAMA_GENERATION_MODEL = os.getenv(
    "OLLAMA_GENERATION_MODEL",
    "qwen3:8b",
)
OLLAMA_CONSULTA_MODEL = os.getenv(
    "OLLAMA_CONSULTA_MODEL",
    "qwen3:8b",
)
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "30m")
OLLAMA_CONSULTA_MAX_TOKENS = int(os.getenv("OLLAMA_CONSULTA_MAX_TOKENS", "700"))
OLLAMA_CONSULTA_CONTEXT_TOKENS = int(
    os.getenv("OLLAMA_CONSULTA_CONTEXT_TOKENS", "8192")
)
OLLAMA_VISION_MODEL = os.getenv(
    "OLLAMA_VISION_MODEL",
    "qwen3-vl:8b",
)
A2_FACT_BLOCK_CHAR_LIMIT = int(os.getenv("A2_FACT_BLOCK_CHAR_LIMIT", "8000"))
A2_FACT_MAX_BLOCKS = int(os.getenv("A2_FACT_MAX_BLOCKS", "25"))
ATA_MAX_UPLOAD_BYTES = int(
    os.getenv("ATA_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024))
)
ATA_MAX_EXTRACTED_BYTES = int(
    os.getenv("ATA_MAX_EXTRACTED_BYTES", str(4 * 1024 * 1024 * 1024))
)
ATA_MAX_ARCHIVE_ENTRIES = int(os.getenv("ATA_MAX_ARCHIVE_ENTRIES", "20000"))
ATA_MAX_COMPRESSION_RATIO = int(os.getenv("ATA_MAX_COMPRESSION_RATIO", "200"))
WHISPER_COMMAND = os.getenv("WHISPER_COMMAND", "whisper")
WHISPER_MODEL_PATH = os.getenv("WHISPER_MODEL_PATH", "")
FFMPEG_COMMAND = os.getenv("FFMPEG_COMMAND", "ffmpeg")
FFPROBE_COMMAND = os.getenv("FFPROBE_COMMAND", "ffprobe")
RAR_TOOL_COMMAND = os.getenv("RAR_TOOL_COMMAND", "7z")
OCR_PDFTOPPM_COMMAND = os.getenv("OCR_PDFTOPPM_COMMAND", "pdftoppm")
OCR_TESSERACT_COMMAND = os.getenv("OCR_TESSERACT_COMMAND", "tesseract")
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "por+eng")
OCR_MAX_PAGES_PER_DOCUMENT = int(os.getenv("OCR_MAX_PAGES_PER_DOCUMENT", "300"))
OCR_PAGE_TIMEOUT_SECONDS = int(os.getenv("OCR_PAGE_TIMEOUT_SECONDS", "90"))
OCR_DOCUMENT_TIMEOUT_SECONDS = int(os.getenv("OCR_DOCUMENT_TIMEOUT_SECONDS", "1800"))
OCR_RENDER_DPI = int(os.getenv("OCR_RENDER_DPI", "300"))
MINUTA_MODEL_CONTEXT_LIMIT = int(os.getenv("MINUTA_MODEL_CONTEXT_LIMIT", "18000"))
MINUTA_TOTAL_CONTEXT_LIMIT = int(os.getenv("MINUTA_TOTAL_CONTEXT_LIMIT", "24000"))
FRONTEND_ORIGINS = [
    origem.strip()
    for origem in os.getenv(
        "FRONTEND_ORIGINS",
        os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"),
    ).split(",")
    if origem.strip()
]
