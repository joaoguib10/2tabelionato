from app.models import Documento
from app.services.document_eligibility import (
    documento_elegivel_consulta,
    modelo_minuta_elegivel,
)


def criar_documento(db, usuario, indice=1, **alteracoes):
    dados = {
        "titulo": f"Documento {indice:02d}",
        "tipo": "NORMA",
        "tipo_ato": None,
        "situacao": "APROVADO",
        "nome_arquivo": f"documento-{indice:02d}.txt",
        "caminho_arquivo": f"caminho-privado-{indice}",
        "criado_por": usuario.id,
        "ativo": True,
        "status": "PRONTO",
        "situacao_extracao": "PROCESSADO_COMPLETO",
        "status_seguranca": "LIBERADO",
    }
    dados.update(alteracoes)
    documento = Documento(**dados)
    db.add(documento)
    db.flush()
    return documento


def test_elegibilidade_separa_consulta_e_modelos(db, usuario_factory):
    usuario = usuario_factory("governanca")
    norma = criar_documento(db, usuario)
    modelo = criar_documento(
        db,
        usuario,
        2,
        tipo="MODELO_MINUTA",
        tipo_ato="COMPRA_VENDA",
    )
    assert documento_elegivel_consulta(norma) is True
    assert modelo_minuta_elegivel(norma, "COMPRA_VENDA") is False
    assert documento_elegivel_consulta(modelo) is False
    assert modelo_minuta_elegivel(modelo, "COMPRA_VENDA") is True

    for situacao in ("RASCUNHO", "REVOGADO", "ARQUIVADO"):
        norma.situacao = situacao
        assert documento_elegivel_consulta(norma) is False
    norma.situacao = "APROVADO"
    norma.status = "PROCESSANDO"
    assert documento_elegivel_consulta(norma) is False


def test_documentos_tem_filtros_paginacao_e_nao_expoem_caminho(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    usuario = usuario_factory("listador")
    for indice in range(25):
        criar_documento(db, usuario, indice)
    criar_documento(db, usuario, 30, tipo="ENTENDIMENTO", situacao="RASCUNHO")
    db.commit()

    primeira = client.get(
        "/api/documentos?pagina=1&por_pagina=20&categoria=NORMA",
        headers=auth_headers(usuario),
    ).json()
    segunda = client.get(
        "/api/documentos?pagina=2&por_pagina=20&categoria=NORMA",
        headers=auth_headers(usuario),
    ).json()
    assert primeira["total"] == 25
    assert len(primeira["items"]) == 20
    assert len(segunda["items"]) == 5
    assert "caminho_arquivo" not in primeira["items"][0]

    rascunhos = client.get(
        "/api/documentos?grupo=RASCUNHOS",
        headers=auth_headers(usuario),
    ).json()
    assert rascunhos["total"] == 0  # Entendimento não publicado é privado do ADMIN.


def test_publicacao_exige_administrador_e_processamento_pronto(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    comum = usuario_factory("comum-governanca")
    admin = usuario_factory("admin-governanca", role="ADMIN")
    documento = criar_documento(
        db,
        comum,
        situacao="RASCUNHO",
        status="PROCESSANDO",
    )
    db.commit()
    url = f"/api/documentos/{documento.id}/governanca"
    assert (
        client.patch(
            url,
            headers=auth_headers(comum),
            json={"situacao": "APROVADO"},
        ).status_code
        == 403
    )
    assert (
        client.patch(
            url,
            headers=auth_headers(admin),
            json={"situacao": "APROVADO"},
        ).status_code
        == 409
    )
    documento.status = "PRONTO"
    db.commit()
    aprovado = client.patch(
        url,
        headers=auth_headers(admin),
        json={"situacao": "APROVADO"},
    )
    assert aprovado.status_code == 200
    assert aprovado.json()["situacao"] == "APROVADO"


def test_publicacao_exige_revisao_de_seguranca(
    client,
    db,
    usuario_factory,
    auth_headers,
):
    admin = usuario_factory("admin-seguranca", role="ADMIN")
    documento = criar_documento(
        db,
        admin,
        situacao="RASCUNHO",
        status_seguranca="REVISAO",
    )
    db.commit()
    url = f"/api/documentos/{documento.id}/governanca"
    bloqueado = client.patch(
        url,
        headers=auth_headers(admin),
        json={"situacao": "APROVADO"},
    )
    assert bloqueado.status_code == 409

    liberado = client.patch(
        f"/api/documentos/{documento.id}/seguranca",
        headers=auth_headers(admin),
        json={"status_seguranca": "LIBERADO"},
    )
    assert liberado.status_code == 200
    aprovado = client.patch(
        url,
        headers=auth_headers(admin),
        json={"situacao": "APROVADO"},
    )
    assert aprovado.status_code == 200
