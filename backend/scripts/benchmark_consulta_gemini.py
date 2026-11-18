"""Mede a latência da Consulta Gemini com uma pergunta geral sintética.

Execute dentro de backend: python -m scripts.benchmark_consulta_gemini --concurrency 5
Não grava histórico, respostas, perguntas ou conteúdo das fontes no relatório.
"""

import argparse
import json
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter

from app.database import SessionLocal
from app.services.external_ai_service import (
    consultar_tier_externo,
    disponibilidade_externa,
)

PERGUNTA = "Quais documentos devem ser conferidos em uma compra e venda de imóvel?"


def executar(indice: int, inicio_simultaneo: threading.Barrier) -> dict:
    db = SessionLocal()
    try:
        inicio_simultaneo.wait(timeout=15)
        inicio = perf_counter()
        try:
            resultado = consultar_tier_externo(db, PERGUNTA, "ENTENDIMENTO")
            return {
                "chamada": indice,
                "segundos": round(perf_counter() - inicio, 2),
                "resultado": "com_citacao" if resultado else "sem_citacao",
            }
        except Exception as erro:
            return {
                "chamada": indice,
                "segundos": round(perf_counter() - inicio, 2),
                "resultado": "erro",
                "tipo_erro": type(erro).__name__,
            }
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, choices=range(1, 7), default=1)
    args = parser.parse_args()
    if not disponibilidade_externa():
        parser.error("Gemini indisponível neste ambiente.")

    barreira = threading.Barrier(args.concurrency)
    inicio = perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        resultados = list(
            pool.map(
                lambda indice: executar(indice, barreira),
                range(1, args.concurrency + 1),
            )
        )

    duracoes = [item["segundos"] for item in resultados]
    relatorio = {
        "simultaneas": args.concurrency,
        "duracao_total_segundos": round(perf_counter() - inicio, 2),
        "mediana_segundos": round(statistics.median(duracoes), 2),
        "maior_latencia_segundos": max(duracoes),
        "chamadas": resultados,
    }
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
