from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

from app.security import validar_senha


class TokenResponse(BaseModel):
    access_token: str
    token_type: str


class UsuarioCreate(BaseModel):
    nome: str = Field(
        min_length=2,
        max_length=150,
    )
    username: str = Field(
        min_length=3,
        max_length=100,
    )
    password: str = Field(
        min_length=5,
        max_length=72,
    )
    _validar = field_validator("password")(validar_senha)
    role: str = "USUARIO"


class UsuarioResponse(BaseModel):
    id: str
    nome: str
    username: str
    role: str
    ativo: bool


class UsuarioUpdate(BaseModel):
    nome: str | None = Field(
        default=None,
        min_length=2,
        max_length=150,
    )
    role: str | None = None


class UsuarioStatusUpdate(BaseModel):
    ativo: bool


class UsuarioPasswordUpdate(BaseModel):
    password: str = Field(
        min_length=5,
        max_length=72,
    )
    _validar = field_validator("password")(validar_senha)


class DocumentoResponse(BaseModel):
    id: str
    titulo: str
    descricao: str | None
    tipo: str
    tipo_ato: str | None
    situacao: str
    orgao_origem: str | None
    versao: str | None
    jurisdicao: str | None
    vigencia_inicio: date | None
    vigencia_fim: date | None
    observacoes: str | None
    nome_arquivo: str
    status_seguranca: str
    alerta_seguranca: str | None
    ativo: bool
    status: str
    erro_processamento: str | None
    total_paginas: int
    total_chunks: int
    situacao_extracao: str
    diagnostico_extracao: dict[str, Any] | None
    processado_em: datetime | None
    criado_por: str
    aprovado_por: str | None
    aprovado_em: datetime | None
    created_at: datetime
    updated_at: datetime


class DocumentoListResponse(BaseModel):
    items: list[DocumentoResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


class DocumentoUpdate(BaseModel):
    titulo: str | None = Field(
        default=None,
        min_length=2,
        max_length=200,
    )
    descricao: str | None = Field(
        default=None,
        max_length=4000,
    )
    tipo: str | None = None
    tipo_ato: str | None = None
    orgao_origem: str | None = Field(
        default=None,
        max_length=200,
    )
    versao: str | None = Field(
        default=None,
        max_length=100,
    )
    jurisdicao: str | None = Field(
        default=None,
        max_length=150,
    )
    vigencia_inicio: date | None = None
    vigencia_fim: date | None = None
    observacoes: str | None = Field(
        default=None,
        max_length=4000,
    )

    @model_validator(mode="after")
    def validar_vigencia(self):
        if (
            self.vigencia_inicio is not None
            and self.vigencia_fim is not None
            and self.vigencia_fim < self.vigencia_inicio
        ):
            raise ValueError("O fim da vigência não pode anteceder o início.")

        return self


class DocumentoGovernancaUpdate(BaseModel):
    situacao: str


class DocumentoSegurancaUpdate(BaseModel):
    status_seguranca: str


class MensagemConsulta(BaseModel):
    papel: str
    conteudo: str = Field(
        min_length=1,
        max_length=6000,
    )

    @field_validator("papel")
    @classmethod
    def validar_papel(
        cls,
        valor: str,
    ) -> str:
        if valor not in {
            "usuario",
            "assistente",
        }:
            raise ValueError("Papel de mensagem inválido.")

        return valor


class ConsultaRequest(BaseModel):
    consulta: str = Field(
        min_length=3,
        max_length=1000,
    )
    historico: list[MensagemConsulta] = Field(
        default_factory=list,
        max_length=10,
    )


class ConsultaResultado(BaseModel):
    fonte_id: str
    documento_id: str | None
    documento: str
    pagina: int | None
    localizacao: str | None
    posicao: int
    artigo: str | None
    capitulo: str | None = None
    secao: str | None = None
    paragrafo: str | None = None
    inciso: str | None = None
    conteudo: str
    similaridade: float


class ConsultaResponse(BaseModel):
    id: str
    consulta: str
    resposta: str
    confianca: float
    confiavel: bool
    situacao_resposta: str
    citacoes_verificadas: list[str]
    resultados: list[ConsultaResultado]


class ConsultaFeedbackRequest(BaseModel):
    produtiva: bool
    motivo: str | None = None
    comentario: str | None = Field(
        default=None,
        max_length=500,
    )

    @model_validator(mode="after")
    def validar_feedback(self):
        motivos = {
            "FONTE_INCORRETA",
            "RESPOSTA_INCOMPLETA",
            "INFORMACAO_DESATUALIZADA",
            "RESPOSTA_CONFUSA",
            "OUTRO",
        }

        if self.produtiva and (
            self.motivo is not None
            or (self.comentario is not None and self.comentario.strip())
        ):
            raise ValueError(
                "Motivo e comentário são aceitos somente " "para resposta não útil."
            )

        if self.motivo is not None and self.motivo not in motivos:
            raise ValueError("Motivo de avaliação inválido.")

        return self


class ConsultaFonteHistoricoResponse(BaseModel):
    fonte_id: str
    documento_id: str | None
    titulo_documento: str
    versao_documento: str | None
    pagina: int | None
    localizacao: str | None
    artigo: str | None
    trecho: str
    pontuacao: float
    citada: bool
    recuperada: bool


class ConsultaRevisaoHistoricoResponse(BaseModel):
    id: str
    status: str
    resposta_humana: str | None
    respondido_por_nome: str | None
    respondido_por_role: str | None
    respondida_em: datetime | None
    entendimento_documento_id: str | None


class ConsultaHistoricoResponse(BaseModel):
    id: str
    usuario_id: str
    usuario_nome: str
    usuario_username: str
    pergunta: str
    resposta: str
    confianca: float
    confiavel: bool
    situacao_resposta: str
    fonte_ids: list[str]
    fontes: list[ConsultaFonteHistoricoResponse]
    produtiva: bool | None
    feedback_motivo: str | None
    feedback_comentario: str | None
    tipo_tarefa: str = "CONSULTA"
    prompt_version: str | None = None
    modelo_ia: str | None = None
    modelo_versao: str | None = None
    parametros_ia: dict[str, Any] | None = None
    revisao: ConsultaRevisaoHistoricoResponse | None = None
    created_at: datetime


class ConsultaHistoricoListResponse(BaseModel):
    items: list[ConsultaHistoricoResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


class RevisaoStatusUpdate(BaseModel):
    status: str
    responsavel_id: UUID | None = None

    @field_validator("status")
    @classmethod
    def validar_status(
        cls,
        valor: str,
    ) -> str:
        normalizado = valor.strip().upper()

        if normalizado not in {
            "PENDENTE",
            "EM_ANALISE",
            "RESPONDIDA",
            "ENCERRADA",
        }:
            raise ValueError("Situação de revisão inválida.")

        return normalizado


class RevisaoRespostaRequest(BaseModel):
    resposta_humana: str = Field(
        min_length=3,
        max_length=20_000,
    )

    @field_validator("resposta_humana")
    @classmethod
    def normalizar_resposta_humana(
        cls,
        valor: str,
    ) -> str:
        normalizado = valor.strip()

        if len(normalizado) < 3:
            raise ValueError("A resposta humana deve possuir conteúdo válido.")

        return normalizado


class EntendimentoInternoCreate(BaseModel):
    titulo: str = Field(
        min_length=3,
        max_length=200,
    )
    texto_generalizado: str = Field(
        min_length=20,
        max_length=100_000,
    )
    origem: str = Field(
        min_length=3,
        max_length=200,
    )
    abrangencia: str = Field(
        min_length=2,
        max_length=150,
    )
    versao: str = Field(
        min_length=1,
        max_length=100,
    )
    observacao: str | None = Field(
        default=None,
        max_length=4_000,
    )

    @field_validator(
        "titulo",
        "texto_generalizado",
        "origem",
        "abrangencia",
        "versao",
    )
    @classmethod
    def remover_espacos_e_exigir_conteudo(
        cls,
        valor: str,
    ) -> str:
        normalizado = valor.strip()

        if not normalizado:
            raise ValueError("Campo obrigatório não informado.")

        return normalizado


class EntendimentoInternoUpdate(BaseModel):
    titulo: str = Field(
        min_length=3,
        max_length=200,
    )
    texto_generalizado: str = Field(
        min_length=20,
        max_length=100_000,
    )
    origem: str = Field(
        min_length=3,
        max_length=200,
    )
    abrangencia: str = Field(
        min_length=2,
        max_length=150,
    )
    versao: str = Field(
        min_length=1,
        max_length=100,
    )
    observacao: str | None = Field(
        default=None,
        max_length=4_000,
    )

    @field_validator(
        "titulo",
        "texto_generalizado",
        "origem",
        "abrangencia",
        "versao",
    )
    @classmethod
    def normalizar_campos(
        cls,
        valor: str,
    ) -> str:
        normalizado = valor.strip()

        if not normalizado:
            raise ValueError("Campo obrigatório não informado.")

        return normalizado


class EntendimentoInternoResponse(BaseModel):
    id: str
    titulo: str
    situacao: str
    status: str
    tipo: str


class EntendimentoListItemResponse(BaseModel):
    id: str
    titulo: str
    descricao: str | None
    situacao: str
    status: str
    status_seguranca: str
    ativo: bool
    origem: str | None
    abrangencia: str | None
    versao: str | None
    aprovado_em: datetime | None
    created_at: datetime
    updated_at: datetime


class EntendimentoListResponse(BaseModel):
    items: list[EntendimentoListItemResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


class EntendimentoDetalheResponse(EntendimentoListItemResponse):
    conteudo: str
    observacao: str | None


class RevisaoResponse(BaseModel):
    id: str
    consulta_id: str
    status: str
    responsavel_id: str | None
    responsavel_nome: str | None
    resposta_humana: str | None
    respondido_por: str | None
    respondido_por_nome: str | None
    respondido_por_role: str | None
    respondida_em: datetime | None
    entendimento_documento_id: str | None
    encerrada_em: datetime | None
    created_at: datetime
    updated_at: datetime
    usuario_id: str
    usuario_nome: str
    usuario_username: str
    pergunta: str
    resposta_ia: str
    situacao_resposta: str
    produtiva: bool | None
    feedback_motivo: str | None
    feedback_comentario: str | None
    fontes: list[ConsultaFonteHistoricoResponse]


class RevisaoListResponse(BaseModel):
    items: list[RevisaoResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


class ModeloMinutaResponse(BaseModel):
    id: str
    titulo: str
    tipo_ato: str
    versao: str | None
    orgao_origem: str | None
    vigencia_inicio: date | None
    updated_at: datetime


class DocumentoTemporarioAnalisado(BaseModel):
    arquivo: str
    finalidade: str
    conteudo: str
    dados_extraidos: dict[str, Any] = Field(default_factory=dict)


class MinutaAnaliseResponse(BaseModel):
    documentos: list[DocumentoTemporarioAnalisado]
    avisos: list[str]


class ModeloUtilizadoResponse(BaseModel):
    id: str
    titulo: str
    versao: str | None
    orgao_origem: str | None


class MinutaResponse(BaseModel):
    minuta: str
    avisos: list[str]
    modelo_utilizado: ModeloUtilizadoResponse


class MinutaExportRequest(BaseModel):
    minuta: str = Field(
        min_length=1,
        max_length=100_000,
    )
    titulo: str = Field(
        default="Minuta",
        min_length=1,
        max_length=150,
    )


# =========================================================
# ANÁLISE DE CASOS
# =========================================================


CASO_STATUS_VALIDOS = {
    "EM_PREPARACAO",
    "AGUARDANDO_CONFERENCIA",
    "PRONTO_PARA_ANALISE",
    "ANALISE_DISPONIVEL",
    "DECISAO_REGISTRADA",
    "ENCERRADO",
}


ESTADOS_EVIDENCIA_VALIDOS = {
    "ENCONTRADO",
    "AUSENTE",
    "INCERTO",
    "CONFLITANTE",
}


ESTADOS_CONFERENCIA_VALIDOS = {
    "PENDENTE",
    "CONFIRMADO",
    "CORRIGIDO",
}


ACOES_CONFERENCIA_VALIDAS = {
    "CONFIRMAR",
    "CORRIGIR",
    "REABRIR",
}


PROVENIENCIAS_FATO_VALIDAS = {
    "DECLARADA",
    "DOCUMENTAL",
    "OBSERVADA",
    "INFERIDA",
}


LOCUS_A2_VALIDOS = {
    "A",
    "B",
    "C",
    "D",
    "E",
    "F",
    "CORINGA",
}


TIPOS_DOCUMENTO_CASO_VALIDOS = {
    "DOCUMENTO_PESSOAL",
    "RG_CNH",
    "CERTIDAO_ESTADO_CIVIL",
    "CERTIDAO_CASAMENTO",
    "CERTIDAO_NASCIMENTO",
    "MATRICULA_IMOVEL",
    "CERTIDAO_IMOVEL",
    "PROCURACAO",
    "ALVARA_JUDICIAL",
    "CONTRATO_INSTRUMENTO",
    "CONTRATO_SOCIAL",
    "ATA",
    "ESTATUTO",
    "REGIMENTO",
    "DOCUMENTO_FISCAL",
    "COMPROVANTE",
    "CERTIDAO_DIVERSA",
    "OUTRO",
}


VINCULOS_ATO_VALIDOS = {
    "TRANSMITENTE",
    "ADQUIRENTE",
    "IMOVEL",
    "ATO",
    "OUTRO",
}


def normalizar_texto_opcional(
    valor: str | None,
) -> str | None:
    if valor is None:
        return None

    normalizado = valor.strip()

    return normalizado or None


class CasoCreate(BaseModel):
    titulo: str = Field(
        min_length=3,
        max_length=200,
    )

    identificacao: str | None = Field(
        default=None,
        max_length=100,
    )

    tipo_ato: str | None = Field(
        default="COMPRA_VENDA",
        max_length=100,
    )

    descricao: str | None = Field(
        default=None,
        max_length=10_000,
    )

    @field_validator("titulo")
    @classmethod
    def normalizar_titulo(
        cls,
        valor: str,
    ) -> str:
        normalizado = valor.strip()

        if len(normalizado) < 3:
            raise ValueError("Informe um título válido para o caso.")

        return normalizado

    @field_validator(
        "identificacao",
        "descricao",
    )
    @classmethod
    def normalizar_opcionais(
        cls,
        valor: str | None,
    ) -> str | None:
        return normalizar_texto_opcional(valor)

    @field_validator("tipo_ato")
    @classmethod
    def validar_tipo_ato(cls, valor: str | None) -> str:
        normalizado = (
            (valor or "COMPRA_VENDA")
            .strip()
            .upper()
            .replace(" E ", "_")
            .replace(" ", "_")
        )
        if normalizado != "COMPRA_VENDA":
            raise ValueError("Nesta etapa, a Análise aceita somente Compra e Venda.")
        return normalizado


class CasoUpdate(BaseModel):
    titulo: str | None = Field(
        default=None,
        min_length=3,
        max_length=200,
    )

    identificacao: str | None = Field(
        default=None,
        max_length=100,
    )

    tipo_ato: str | None = Field(
        default=None,
        max_length=100,
    )

    descricao: str | None = Field(
        default=None,
        max_length=10_000,
    )

    @field_validator("titulo")
    @classmethod
    def normalizar_titulo(
        cls,
        valor: str | None,
    ) -> str | None:
        if valor is None:
            return None

        normalizado = valor.strip()

        if len(normalizado) < 3:
            raise ValueError("Informe um título válido para o caso.")

        return normalizado

    @field_validator(
        "identificacao",
        "descricao",
    )
    @classmethod
    def normalizar_opcionais(
        cls,
        valor: str | None,
    ) -> str | None:
        return normalizar_texto_opcional(valor)

    @field_validator("tipo_ato")
    @classmethod
    def validar_tipo_ato(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        normalizado = valor.strip().upper().replace(" E ", "_").replace(" ", "_")
        if normalizado != "COMPRA_VENDA":
            raise ValueError("Nesta etapa, a Análise aceita somente Compra e Venda.")
        return normalizado

    @model_validator(mode="after")
    def exigir_alguma_alteracao(self):
        campos_informados = self.model_fields_set

        if not campos_informados:
            raise ValueError("Informe ao menos um campo para alteração.")

        return self


class CasoStatusUpdate(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validar_status(
        cls,
        valor: str,
    ) -> str:
        normalizado = valor.strip().upper()

        if normalizado not in CASO_STATUS_VALIDOS:
            raise ValueError("Situação do caso inválida.")

        return normalizado


class CasoResponsavelUpdate(BaseModel):
    responsavel_id: UUID | None


class CasoResponse(BaseModel):
    id: str
    titulo: str
    identificacao: str | None
    tipo_ato: str | None
    descricao: str | None
    status: str

    criado_por: str
    criado_por_nome: str | None

    responsavel_id: str | None
    responsavel_nome: str | None

    total_documentos: int = 0
    total_fatos: int = 0
    total_pendentes_conferencia: int = 0
    total_conflitantes: int = 0

    encerrado_em: datetime | None
    created_at: datetime
    updated_at: datetime


class FonteCampoCompraVenda(BaseModel):
    documento_id: UUID
    pagina: int | None = Field(default=None, ge=1)
    localizacao: str | None = Field(default=None, max_length=200)
    trecho: str = Field(min_length=1, max_length=2_000)


class DadosCasamentoCompraVenda(BaseModel):
    matricula: str | None = Field(default=None, max_length=200)
    data_registro: str | None = Field(default=None, max_length=50)
    regime_bens: str | None = Field(default=None, max_length=200)
    data_certidao: str | None = Field(default=None, max_length=50)
    selo_digital: str | None = Field(default=None, max_length=200)


class DadosEmpresaCompraVenda(BaseModel):
    cnpj: str | None = Field(default=None, max_length=30)
    nire: str | None = Field(default=None, max_length=50)
    endereco: str | None = Field(default=None, max_length=500)
    clausula_poderes: str | None = Field(default=None, max_length=100)
    descricao_poderes: str | None = Field(default=None, max_length=5_000)


class DadosProcuracaoCompraVenda(BaseModel):
    lavrada_em: str | None = Field(default=None, max_length=50)
    livro: str | None = Field(default=None, max_length=50)
    folhas: str | None = Field(default=None, max_length=50)
    tabelionato: str | None = Field(default=None, max_length=200)
    cidade_comarca: str | None = Field(default=None, max_length=200)
    certidao_emitida_em: str | None = Field(default=None, max_length=50)
    selo_digital: str | None = Field(default=None, max_length=200)
    poderes: str | None = Field(default=None, max_length=5_000)
    valor_minimo: str | None = Field(default=None, max_length=100)
    valor_maximo: str | None = Field(default=None, max_length=100)


class DadosAlvaraCompraVenda(BaseModel):
    numero_processo: str | None = Field(default=None, max_length=100)
    juizo: str | None = Field(default=None, max_length=300)
    data_decisao: str | None = Field(default=None, max_length=50)
    data_validade: str | None = Field(default=None, max_length=50)
    representante: str | None = Field(default=None, max_length=300)
    poderes: str | None = Field(default=None, max_length=5_000)
    valor_minimo: str | None = Field(default=None, max_length=100)
    valor_maximo: str | None = Field(default=None, max_length=100)


class DadosNegocioCompraVenda(BaseModel):
    valor_escritura: str | None = Field(default=None, max_length=100)
    forma_pagamento: str | None = Field(default=None, max_length=5_000)
    moeda: str | None = Field(default="BRL", max_length=20)
    observacoes: str | None = Field(default=None, max_length=5_000)
    fontes: list[FonteCampoCompraVenda] = Field(default_factory=list, max_length=30)
    confirmado: bool = False


class ParteCompraVenda(BaseModel):
    id: UUID
    papel: str
    natureza: str = "FISICA"
    participacao: str = "PRINCIPAL"
    principal_id: UUID | None = None
    modo_qualificacao: str = "INDIVIDUAL"
    nome_completo: str | None = Field(default=None, max_length=300)
    nacionalidade: str | None = Field(default="brasileiro(a)", max_length=100)
    capacidade: str | None = Field(default=None, max_length=150)
    estado_civil: str | None = Field(default=None, max_length=100)
    uniao_estavel: bool | None = None
    profissao: str | None = Field(default=None, max_length=200)
    cpf: str | None = Field(default=None, max_length=30)
    endereco: str | None = Field(default=None, max_length=500)
    casamento: DadosCasamentoCompraVenda = Field(
        default_factory=DadosCasamentoCompraVenda
    )
    empresa: DadosEmpresaCompraVenda = Field(default_factory=DadosEmpresaCompraVenda)
    procuracao: DadosProcuracaoCompraVenda = Field(
        default_factory=DadosProcuracaoCompraVenda
    )
    alvara: DadosAlvaraCompraVenda = Field(default_factory=DadosAlvaraCompraVenda)
    fontes: list[FonteCampoCompraVenda] = Field(default_factory=list, max_length=30)
    origem: str = "MANUAL"
    confirmado: bool = False

    @field_validator("papel")
    @classmethod
    def validar_papel(cls, valor: str) -> str:
        normalizado = valor.strip().upper()
        normalizado = {
            "VENDEDOR": "OUTORGANTE",
            "COMPRADOR": "OUTORGADO",
        }.get(normalizado, normalizado)
        if normalizado not in {"OUTORGANTE", "OUTORGADO"}:
            raise ValueError("Papel da parte inválido.")
        return normalizado

    @field_validator("natureza")
    @classmethod
    def validar_natureza(cls, valor: str) -> str:
        normalizado = valor.strip().upper()
        if normalizado not in {"FISICA", "JURIDICA"}:
            raise ValueError("Natureza da parte inválida.")
        return normalizado

    @field_validator("participacao")
    @classmethod
    def validar_participacao(cls, valor: str) -> str:
        normalizado = valor.strip().upper()
        if normalizado not in {
            "PRINCIPAL",
            "CONJUGE",
            "ANUENTE",
            "REPRESENTANTE",
            "PROCURADOR",
        }:
            raise ValueError("Participação da parte inválida.")
        return normalizado

    @field_validator("modo_qualificacao")
    @classmethod
    def validar_modo(cls, valor: str) -> str:
        normalizado = valor.strip().upper()
        validos = {
            "INDIVIDUAL",
            "UNIAO_ESTAVEL",
            "CASAL_AMBOS_ASSINAM",
            "CASAL_COM_ANUENTE",
            "CASADO_APENAS_UM",
            "EMPRESA_REPRESENTADA",
            "PROCURACAO",
            "ALVARA_JUDICIAL",
        }
        if normalizado not in validos:
            raise ValueError("Modo de qualificação inválido.")
        return normalizado


class AverbacaoCompraVenda(BaseModel):
    ordem: int = Field(ge=1)
    rotulo: str = Field(min_length=1, max_length=50)
    resumo: str = Field(min_length=1, max_length=2_000)
    fonte: FonteCampoCompraVenda | None = None


class ImovelCompraVenda(BaseModel):
    matricula: str | None = Field(default=None, max_length=200)
    logradouro: str | None = Field(default=None, max_length=300)
    numero: str | None = Field(default=None, max_length=50)
    bairro: str | None = Field(default=None, max_length=150)
    cidade: str | None = Field(default=None, max_length=150)
    descricao_completa: str | None = Field(default=None, max_length=20_000)
    descricao_utilizada: str | None = Field(default=None, max_length=20_000)
    averbacoes: list[AverbacaoCompraVenda] = Field(default_factory=list, max_length=500)
    fontes: list[FonteCampoCompraVenda] = Field(default_factory=list, max_length=100)
    origem: str = "MANUAL"
    confirmado: bool = False


class CasoCompraVendaUpdate(BaseModel):
    partes: list[ParteCompraVenda] = Field(default_factory=list, max_length=50)
    imovel: ImovelCompraVenda = Field(default_factory=ImovelCompraVenda)
    negocio: DadosNegocioCompraVenda = Field(default_factory=DadosNegocioCompraVenda)


class QualificacaoParteResponse(BaseModel):
    parte_id: str
    texto: str
    pendencias: list[str]


class CasoCompraVendaResponse(CasoCompraVendaUpdate):
    status: str
    erro: str | None
    atualizado_em: datetime | None
    qualificacoes: list[QualificacaoParteResponse]
    pendencias: list[str]
    alertas_valor: list[str]


class CasoListResponse(BaseModel):
    items: list[CasoResponse]
    total: int
    pagina: int
    por_pagina: int
    total_paginas: int


# =========================================================
# DOCUMENTOS PRIVADOS DA ANÁLISE
# =========================================================


class CasoDocumentoResponse(BaseModel):
    id: str
    caso_id: str

    nome_arquivo: str
    mime_type: str | None
    tamanho_bytes: int | None

    tipo_documento: str | None
    vinculo_ato: str | None

    status: str

    status_seguranca: str
    alerta_seguranca: str | None
    seguranca_liberada_por: str | None
    seguranca_liberada_em: datetime | None

    erro_processamento: str | None

    total_paginas: int

    situacao_extracao: str
    diagnostico_extracao: dict[str, Any] | None

    processado_em: datetime | None

    status_extracao_fatos: str
    erro_extracao_fatos: str | None
    diagnostico_extracao_fatos: dict[str, Any] | None
    fatos_extraidos_em: datetime | None
    versao_extrator_fatos: str | None

    criado_por: str

    created_at: datetime
    updated_at: datetime


class CasoDocumentoListResponse(BaseModel):
    items: list[CasoDocumentoResponse]
    total: int


class CasoDocumentoSegurancaUpdate(BaseModel):
    acao: str

    @field_validator("acao")
    @classmethod
    def validar_acao(cls, valor: str) -> str:
        normalizado = valor.strip().upper()
        if normalizado not in {"LIBERAR", "REABRIR"}:
            raise ValueError("Ação de segurança documental inválida.")
        return normalizado


class CasoDocumentoClassificacaoUpdate(BaseModel):
    tipo_documento: str | None = Field(
        default=None,
        max_length=50,
    )

    vinculo_ato: str | None = Field(
        default=None,
        max_length=30,
    )

    @field_validator("tipo_documento")
    @classmethod
    def validar_tipo_documento(
        cls,
        valor: str | None,
    ) -> str | None:
        if valor is None:
            return None

        normalizado = valor.strip().upper()

        if not normalizado:
            return None

        if normalizado not in TIPOS_DOCUMENTO_CASO_VALIDOS:
            raise ValueError("Tipo de documento do caso inválido.")

        return normalizado

    @field_validator("vinculo_ato")
    @classmethod
    def validar_vinculo_ato(
        cls,
        valor: str | None,
    ) -> str | None:
        if valor is None:
            return None

        normalizado = valor.strip().upper()

        if not normalizado:
            return None

        if normalizado not in VINCULOS_ATO_VALIDOS:
            raise ValueError("Vínculo do documento com o ato inválido.")

        return normalizado

    @model_validator(mode="after")
    def exigir_alguma_alteracao(self):
        if not self.model_fields_set:
            raise ValueError(
                "Informe ao menos um campo " "de classificação para alteração."
            )

        return self


class CasoDocumentoPaginaResponse(BaseModel):
    id: str
    caso_documento_id: str

    pagina: int
    pagina_confiavel: bool

    localizacao: str | None

    conteudo: str

    metodo_extracao: str
    situacao_extracao: str

    created_at: datetime


class CasoDocumentoPaginaListResponse(BaseModel):
    items: list[CasoDocumentoPaginaResponse]
    total: int


class CasoDocumentoDetalheResponse(CasoDocumentoResponse):
    paginas: list[CasoDocumentoPaginaResponse] = Field(default_factory=list)


# =========================================================
# A2 — ESTADO FACTUAL DO CASO
# =========================================================


class CasoFatoResponse(BaseModel):
    id: str
    caso_id: str
    caso_documento_id: str | None

    campo: str
    categoria: str | None
    locus: str | None

    valor_original: Any | None
    valor_atual: Any | None

    proveniencia: str

    estado_evidencia: str
    estado_conferencia: str

    pagina: int | None
    localizacao: str | None
    trecho_fonte: str | None
    metodo_extracao: str | None
    contexto: dict[str, Any] | None

    ativo: bool

    registrado_por: str | None

    created_at: datetime
    updated_at: datetime


class CasoFatoListResponse(BaseModel):
    items: list[CasoFatoResponse]
    total: int


class CasoFatoCreate(BaseModel):
    campo: str = Field(
        min_length=1,
        max_length=150,
    )

    categoria: str | None = Field(
        default=None,
        max_length=80,
    )

    locus: str | None = Field(
        default=None,
        max_length=30,
    )

    valor: Any | None = None

    proveniencia: str = Field(
        min_length=2,
        max_length=30,
    )

    estado_evidencia: str = "ENCONTRADO"

    caso_documento_id: UUID | None = None

    pagina: int | None = Field(
        default=None,
        ge=1,
    )

    localizacao: str | None = Field(
        default=None,
        max_length=200,
    )

    trecho_fonte: str | None = Field(
        default=None,
        max_length=20_000,
    )

    metodo_extracao: str | None = Field(
        default=None,
        max_length=30,
    )

    contexto: dict[str, Any] | None = None

    @field_validator(
        "campo",
        "proveniencia",
    )
    @classmethod
    def normalizar_obrigatorios(
        cls,
        valor: str,
    ) -> str:
        normalizado = valor.strip()

        if not normalizado:
            raise ValueError("Campo obrigatório não informado.")

        return normalizado

    @field_validator(
        "categoria",
        "locus",
        "localizacao",
        "trecho_fonte",
        "metodo_extracao",
    )
    @classmethod
    def normalizar_opcionais(
        cls,
        valor: str | None,
    ) -> str | None:
        return normalizar_texto_opcional(valor)

    @field_validator("locus")
    @classmethod
    def validar_locus(cls, valor: str | None) -> str | None:
        if valor is None:
            return None
        normalizado = valor.strip().upper()
        if normalizado not in LOCUS_A2_VALIDOS:
            raise ValueError("Locus factual inválido.")
        return normalizado

    @field_validator("proveniencia")
    @classmethod
    def validar_proveniencia(cls, valor: str) -> str:
        normalizado = valor.strip().upper()
        if normalizado not in PROVENIENCIAS_FATO_VALIDAS:
            raise ValueError("Proveniência factual inválida.")
        return normalizado

    @field_validator("estado_evidencia")
    @classmethod
    def validar_estado_evidencia(
        cls,
        valor: str,
    ) -> str:
        normalizado = valor.strip().upper()

        if normalizado not in ESTADOS_EVIDENCIA_VALIDOS:
            raise ValueError("Estado de evidência inválido.")

        return normalizado

    @model_validator(mode="after")
    def validar_origem_factual(self):
        if self.proveniencia == "DOCUMENTAL" and self.caso_documento_id is None:
            raise ValueError("Fato documental exige o documento de origem.")
        if self.pagina is not None and self.caso_documento_id is None:
            raise ValueError("A localização por página exige o documento de origem.")
        if self.proveniencia == "INFERIDA" and self.estado_evidencia == "ENCONTRADO":
            raise ValueError(
                "Informação inferida deve permanecer incerta ou conflitante até conferência adequada."
            )
        return self


class CasoConferenciaCreate(BaseModel):
    acao: str

    valor_novo: Any | None = None

    observacao: str | None = Field(
        default=None,
        max_length=10_000,
    )

    @field_validator("acao")
    @classmethod
    def validar_acao(
        cls,
        valor: str,
    ) -> str:
        normalizado = valor.strip().upper()

        if normalizado not in ACOES_CONFERENCIA_VALIDAS:
            raise ValueError("Ação de conferência inválida.")

        return normalizado

    @field_validator("observacao")
    @classmethod
    def normalizar_observacao(
        cls,
        valor: str | None,
    ) -> str | None:
        return normalizar_texto_opcional(valor)

    @model_validator(mode="after")
    def validar_correcao(self):
        if self.acao == "CORRIGIR" and "valor_novo" not in self.model_fields_set:
            raise ValueError("Informe o novo valor para corrigir o fato.")

        if self.acao == "REABRIR" and not self.observacao:
            raise ValueError("Informe o motivo para reabrir a conferência.")

        return self


class CasoConferenciaResponse(BaseModel):
    id: str
    caso_id: str
    fato_id: str

    usuario_id: str | None
    usuario_nome: str | None

    acao: str

    valor_anterior: Any | None
    valor_novo: Any | None

    observacao: str | None

    created_at: datetime


class CasoConferenciaListResponse(BaseModel):
    items: list[CasoConferenciaResponse]
    total: int


class CasoVersaoResponse(BaseModel):
    id: str
    caso_id: str
    numero: int
    motivo: str
    fatos_snapshot: list[dict[str, Any]]
    documentos_snapshot: list[dict[str, Any]]
    criado_por: str | None
    created_at: datetime


class CasoAnaliseResponse(BaseModel):
    id: str
    caso_id: str
    versao_id: str
    versao_numero: int
    status_evidencia: str
    resumo: str
    requisitos: list[Any]
    impedimentos: list[Any]
    pendencias: list[Any]
    fontes: list[dict[str, Any]]
    prompt_version: str
    modelo_ia: str | None
    gerado_por: str | None
    created_at: datetime


class CasoAnaliseListResponse(BaseModel):
    items: list[CasoAnaliseResponse]
    total: int


class CasoMensagemCreate(BaseModel):
    conteudo: str = Field(min_length=1, max_length=50_000)

    @field_validator("conteudo")
    @classmethod
    def normalizar_conteudo(cls, valor: str) -> str:
        normalizado = valor.strip()
        if not normalizado:
            raise ValueError("A mensagem não pode ficar vazia.")
        return normalizado


class CasoMensagemResponse(BaseModel):
    id: str
    caso_id: str
    papel: str
    conteudo: str
    usuario_id: str | None
    analise_id: str | None
    created_at: datetime


class CasoMensagemListResponse(BaseModel):
    items: list[CasoMensagemResponse]
    total: int
    tem_mais: bool = False


class CasoTarefaResponse(BaseModel):
    id: str
    caso_id: str
    caso_documento_id: str | None
    tipo: str
    status: str
    tentativa: int
    erro: str | None
    iniciado_em: datetime | None
    concluido_em: datetime | None
    created_at: datetime


class CasoTarefaListResponse(BaseModel):
    items: list[CasoTarefaResponse]
    total: int


class CasoDecisaoCreate(BaseModel):
    analise_id: UUID
    decisao: str
    texto: str = Field(min_length=3, max_length=50_000)
    fundamentacao: str | None = Field(default=None, max_length=50_000)
    escopo: str | None = Field(default=None, max_length=500)

    @field_validator("decisao")
    @classmethod
    def validar_decisao(cls, valor: str) -> str:
        normalizado = valor.strip().upper()
        if normalizado not in {"APROVAR", "EXIGENCIA", "RECUSAR", "OUTRA"}:
            raise ValueError("Decisão humana inválida.")
        return normalizado

    @field_validator("texto", "fundamentacao", "escopo")
    @classmethod
    def normalizar_textos(cls, valor: str | None) -> str | None:
        return normalizar_texto_opcional(valor)


class CasoDecisaoResponse(BaseModel):
    id: str
    caso_id: str
    analise_id: str
    decisao: str
    texto: str
    fundamentacao: str | None
    escopo: str | None
    decidido_por: str | None
    decidido_por_nome: str | None
    created_at: datetime


class CasoDecisaoListResponse(BaseModel):
    items: list[CasoDecisaoResponse]
    total: int


class AtaProcessoCreate(BaseModel):
    titulo: str = Field(min_length=1, max_length=200)

    @field_validator("titulo")
    @classmethod
    def normalizar_titulo(cls, valor: str) -> str:
        normalizado = valor.strip()
        if not normalizado:
            raise ValueError("Informe o nome do processo.")
        return normalizado


class CasoAnaliseLoteCreate(BaseModel):
    documento_ids: list[UUID] = Field(min_length=1, max_length=20)
    conteudo: str = Field(min_length=1, max_length=50_000)

    @field_validator("conteudo")
    @classmethod
    def normalizar_conteudo(cls, valor: str) -> str:
        normalizado = valor.strip()
        if not normalizado:
            raise ValueError("A orientação não pode ficar vazia.")
        return normalizado

    @model_validator(mode="after")
    def validar_documentos_unicos(self):
        if len(set(self.documento_ids)) != len(self.documento_ids):
            raise ValueError("A lista contém documentos repetidos.")
        return self


class AtaTrabalhoResponse(BaseModel):
    id: str
    titulo: str
    status: str
    nome_arquivo: str | None
    resultado: str | None
    diagnostico: dict[str, Any] | None
    erro_processamento: str | None
    created_at: datetime
    concluido_em: datetime | None


class AtaTrabalhoListResponse(BaseModel):
    items: list[AtaTrabalhoResponse]
    total: int
