from fastapi import FastAPI

app = FastAPI(
    title="Cartório IA",
    description="API do assistente inteligente do tabelionato",
    version="0.1.0",
)


@app.get("/")
def root():
    return {
        "message": "Cartório IA API funcionando!"
    }


@app.get("/health")
def health():
    return {
        "status": "ok"
    }

@app.get("/api/status")
def status():
    return {
        "system": "Cartório IA",
        "backend": "online",
        "version": "0.1.0",
    }