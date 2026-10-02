import json
from pathlib import Path

from app.services.evaluation_service import (
    avaliar_resposta_esperada,
    avaliar_resultado_pipeline,
)


def test_perguntas_juridicas_de_referencia_atendem_respostas_esperadas():
    caminho = Path(__file__).resolve().parents[1] / "evals" / "perguntas_juridicas.json"
    casos = json.loads(caminho.read_text(encoding="utf-8"))
    assert len(casos) >= 3

    for caso in casos:
        assert "resposta_esperada" in caso
        assert "expectativa_recusa" in caso
        assert "categoria_juridica" in caso
        assert "observacoes_revisor" in caso
        resposta_controlada = " ".join(
            [
                *caso["termos_esperados"],
                *[f"[{fonte}]" for fonte in caso["fontes_esperadas"]],
            ]
        )
        avaliacao = avaliar_resposta_esperada(
            resposta_controlada,
            caso["termos_esperados"],
            caso["termos_proibidos"],
            caso["fontes_esperadas"],
        )
        assert avaliacao["aprovada"], caso["id"]


def test_avaliacao_reprova_alucinacao_e_fonte_ausente():
    avaliacao = avaliar_resposta_esperada(
        "A validade seria de 30 dias.",
        ["90 dias"],
        ["30 dias"],
        ["FONTE-11111111-1111-1111-1111-111111111111"],
    )
    assert avaliacao["aprovada"] is False
    assert avaliacao["termos_ausentes"] == ["90 dias"]
    assert avaliacao["termos_proibidos_encontrados"] == ["30 dias"]


def test_avaliacao_ponta_a_ponta_confere_recusa_e_fonte():
    caso = {
        "termos_esperados": ["conferência"],
        "termos_proibidos": ["dispensa"],
        "expectativa_recusa": False,
        "fonte_esperada": {"titulo": "Manual sintético", "artigo": "Art. 1"},
    }
    resultado = avaliar_resultado_pipeline(
        caso,
        "A conferência é necessária.",
        "EVIDENCIA_SUFFICIENTE",
        [{"documento": "Manual sintético", "artigo": "Art. 1"}],
    )
    assert resultado["aprovada"] is True

    recusado = avaliar_resultado_pipeline(
        {**caso, "expectativa_recusa": True, "fonte_esperada": None},
        "A conferência é necessária.",
        "EVIDENCIA_SUFFICIENTE",
        [],
    )
    assert recusado["aprovada"] is False
