from pathlib import Path

from alembic.script import ScriptDirectory

VERSOES = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def test_historico_de_migracoes_tem_uma_unica_cabeca():
    scripts = ScriptDirectory(str(VERSOES.parent))
    assert scripts.get_heads() == ["b12f3c4d5e6f"]
    cadeia = list(scripts.walk_revisions())
    assert len(cadeia) == len(list(VERSOES.glob("*.py")))
    assert len(scripts.get_bases()) == 1


def test_migracao_unifica_perfis_sem_colisao_semantica():
    texto = (VERSOES / "c42f8a1d7e63_unifica_perfis_administrativos.py").read_text(
        encoding="utf-8"
    )
    assert texto.index("WHERE role = 'ADMIN'") < texto.index("WHERE role = 'MASTER'")
    assert "sessao_versao = sessao_versao + 1" in texto


def test_migracao_a1_tab_e_ata_tem_historico_e_descarte_controlado():
    texto = (VERSOES / "d53a9b2e8f74_a1_tab_e_versionamento_de_casos.py").read_text(
        encoding="utf-8"
    )
    for tabela in ("caso_versoes", "caso_analises", "caso_decisoes", "ata_trabalhos"):
        assert f'"{tabela}"' in texto
    assert 'ondelete="RESTRICT"' in texto


def test_migracao_prepara_dados_estruturados_de_compra_e_venda_no_caso():
    texto = (VERSOES / "e64b1c3f9a20_dados_estruturados_compra_venda.py").read_text(
        encoding="utf-8"
    )
    assert 'op.add_column("casos"' in texto
    assert '"dados_ato"' in texto
    assert '"status_dados_ato"' in texto


def test_migracao_cria_vector_status_historico_e_indices():
    texto = (VERSOES / "a36f0d58c2b1_ingestao_login_historico_e_indices.py").read_text(
        encoding="utf-8"
    )
    assert "CREATE EXTENSION IF NOT EXISTS vector" in texto
    assert '"status"' in texto
    assert '"consultas_historico"' in texto
    assert "USING hnsw" in texto
    assert "USING gin" in texto


def test_migracao_de_governanca_preserva_antigos_como_rascunho():
    texto = (VERSOES / "f4c91a72d6e0_governanca_fontes_e_modelos.py").read_text(
        encoding="utf-8"
    )
    assert 'server_default="RASCUNHO"' in texto
    assert '"consulta_fontes"' in texto
    assert 'ondelete="SET NULL"' in texto
    assert '"tipo_ato"' in texto


def test_migracao_adiciona_seguranca_e_deduplicacao_documental():
    texto = (VERSOES / "c7d3e8a4b912_seguranca_e_deduplicacao_documental.py").read_text(
        encoding="utf-8"
    )
    assert '"status_seguranca"' in texto
    assert 'server_default="PENDENTE"' in texto
    assert '"hash_arquivo"' in texto
    assert '"uq_documentos_hash_arquivo"' in texto


def test_migracao_cria_fila_de_revisoes_e_preserva_feedback_negativo():
    texto = (VERSOES / "e91a4f3d2c10_fila_de_revisoes.py").read_text(encoding="utf-8")
    assert '"consulta_revisoes"' in texto
    assert '"uq_consulta_revisoes_consulta_id"' in texto
    assert "consultas.c.produtiva.is_(False)" in texto
    assert 'ondelete="CASCADE"' in texto


def test_migracao_registra_auditoria_minima_da_ia():
    texto = (VERSOES / "7f3c1a9b6d20_auditoria_execucao_ia.py").read_text(
        encoding="utf-8"
    )
    assert 'down_revision: Union[str, Sequence[str], None] = "e91a4f3d2c10"' in texto
    assert '"prompt_version"' in texto
    assert '"modelo_ia"' in texto
    assert '"modelo_versao"' in texto
    assert '"parametros_ia"' in texto
