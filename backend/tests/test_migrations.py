from pathlib import Path

from alembic.script import ScriptDirectory

VERSOES = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def test_historico_de_migracoes_tem_uma_unica_cabeca():
    scripts = ScriptDirectory(str(VERSOES.parent))
    assert scripts.get_heads() == ["f17a69c0b482"]
    cadeia = list(scripts.walk_revisions())
    assert len(cadeia) == len(list(VERSOES.glob("*.py")))
    assert len(scripts.get_bases()) == 1


def test_migracao_de_ata_cria_processos_sem_apagar_trabalhos_existentes():
    texto = (VERSOES / "c9e2f71a4b63_processos_temporarios_ata.py").read_text(
        encoding="utf-8"
    )
    assert 'down_revision: Union[str, Sequence[str], None] = "b12f3c4d5e6f"' in texto
    assert 'sa.Column("titulo"' in texto
    assert "'ABERTO'" in texto
    assert "UPDATE ata_trabalhos" in texto
    assert "DELETE FROM ata_trabalhos" not in texto


def test_migracao_preserva_compatibilidade_com_titulo_ata_legado():
    texto = (
        VERSOES / "d1a6c83f9b24_titulo_ata_com_padrao_compativel.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: Union[str, Sequence[str], None] = "c9e2f71a4b63"' in texto
    assert 'server_default="Ata Notarial"' in texto


def test_migracao_indexa_metadados_para_busca_textual_em_portugues():
    texto = (
        VERSOES / "e2c4f97a18b3_indice_busca_textual_de_entendimentos.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: Union[str, Sequence[str], None] = "d1a6c83f9b24"' in texto
    assert "USING gin" in texto
    assert "to_tsvector" in texto
    assert "DROP INDEX IF EXISTS ix_documentos_busca_textual" in texto


def test_migracao_adiciona_indices_textuais_sem_acento():
    texto = (VERSOES / "f17a69c0b482_indice_textual_sem_acentos.py").read_text(
        encoding="utf-8"
    )
    assert 'down_revision: Union[str, Sequence[str], None] = "e2c4f97a18b3"' in texto
    assert "ix_documentos_busca_textual_normalizada" in texto
    assert "ix_documento_chunks_busca_textual_normalizada" in texto
    assert "translate(" in texto
    assert "DROP INDEX IF EXISTS ix_documentos_busca_textual" in texto


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
