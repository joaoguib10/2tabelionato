import json
from pathlib import Path

from app.services.evaluation_service import avaliar_resposta_esperada
from app.services.ollama_service import gerar_resposta


def main() -> None:
    caminho = Path(__file__).resolve().parents[1] / "evals" / "perguntas_juridicas.json"
    casos = json.loads(caminho.read_text(encoding="utf-8"))
    aprovados = 0

    for caso in casos:
        resposta = gerar_resposta(caso["pergunta"], caso["contexto"])
        avaliacao = avaliar_resposta_esperada(
            resposta,
            caso["termos_esperados"],
            caso.get("termos_proibidos"),
            caso.get("fontes_esperadas"),
        )
        aprovados += int(avaliacao["aprovada"])
        estado = "OK" if avaliacao["aprovada"] else "FALHOU"
        print(f"{estado}: {caso['id']} - {avaliacao}")

    print(f"Resultado: {aprovados}/{len(casos)} casos aprovados")
    if aprovados != len(casos):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
