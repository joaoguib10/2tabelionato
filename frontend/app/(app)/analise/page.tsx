"use client";

import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Download,
  Eye,
  FileText,
  FileUp,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  ScanText,
  ShieldAlert,
  Tag,
  Trash2,
  Upload,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { apiFetch, obterMensagemErroApi } from "../../../lib/api";
import { useAuth } from "../../../context/AuthContext";

type Caso = {
  id: string;
  titulo: string;
  identificacao: string | null;
  tipo_ato: string | null;
  descricao: string | null;
  status: string;

  criado_por: string;
  criado_por_nome: string | null;

  responsavel_id: string | null;
  responsavel_nome: string | null;

  total_documentos: number;
  total_fatos: number;
  total_pendentes_conferencia: number;
  total_conflitantes: number;

  encerrado_em: string | null;
  created_at: string;
  updated_at: string;
};

type CasoListResponse = {
  items: Caso[];
  total: number;
  pagina: number;
  por_pagina: number;
  total_paginas: number;
};

type CasoForm = {
  titulo: string;
  identificacao: string;
  tipo_ato: string;
  descricao: string;
};

type CasoDocumento = {
  id: string;
  caso_id: string;

  nome_arquivo: string;
  mime_type: string | null;
  tamanho_bytes: number | null;

  tipo_documento: string | null;
  vinculo_ato: string | null;

  status: string;

  status_seguranca: string;
  alerta_seguranca: string | null;
  seguranca_liberada_por: string | null;
  seguranca_liberada_em: string | null;

  erro_processamento: string | null;

  total_paginas: number;

  situacao_extracao: string;
  diagnostico_extracao: Record<string, unknown> | null;

  processado_em: string | null;

  status_extracao_fatos: string;
  erro_extracao_fatos: string | null;
  diagnostico_extracao_fatos: Record<string, unknown> | null;
  fatos_extraidos_em: string | null;
  versao_extrator_fatos: string | null;

  criado_por: string;

  created_at: string;
  updated_at: string;
};

type CasoDocumentoListResponse = {
  items: CasoDocumento[];
  total: number;
};

type CasoDocumentoPagina = {
  id: string;
  caso_documento_id: string;

  pagina: number;
  pagina_confiavel: boolean;

  localizacao: string | null;

  conteudo: string;

  metodo_extracao: string;
  situacao_extracao: string;

  created_at: string;
};

type CasoDocumentoDetalhe = CasoDocumento & {
  paginas: CasoDocumentoPagina[];
};

type ClassificacaoForm = {
  tipo_documento: string;
  vinculo_ato: string;
};

type DocumentoUploadSelecionado = {
  arquivo: File;
  tipo_documento: string;
  vinculo_ato: string;
};

type UsuarioResumo = {
  id: string;
  nome: string;
  username: string;
  role: string;
  ativo: boolean;
};

type CasoFato = {
  id: string;
  caso_documento_id: string | null;
  campo: string;
  categoria: string | null;
  locus: string | null;
  valor_original: unknown;
  valor_atual: unknown;
  proveniencia: string;
  estado_evidencia: string;
  estado_conferencia: string;
  pagina: number | null;
  localizacao: string | null;
  trecho_fonte: string | null;
  contexto: Record<string, unknown> | null;
};

type CasoAnaliseJuridica = {
  id: string;
  versao_numero: number;
  status_evidencia: string;
  resumo: string;
  requisitos: unknown[];
  impedimentos: unknown[];
  pendencias: unknown[];
  fontes: Array<Record<string, unknown>>;
  created_at: string;
};

type CasoDecisao = {
  id: string;
  analise_id: string;
  decisao: string;
  texto: string;
  fundamentacao: string | null;
  escopo: string | null;
  decidido_por_nome: string | null;
  created_at: string;
};

type CasoMensagem = {
  id: string;
  caso_id: string;
  papel: string;
  conteudo: string;
  usuario_id: string | null;
  analise_id: string | null;
  created_at: string;
};

type CasoTarefa = {
  id: string;
  caso_id: string;
  caso_documento_id: string | null;
  tipo: string;
  status: string;
  tentativa: number;
  erro: string | null;
  iniciado_em: string | null;
  concluido_em: string | null;
  created_at: string;
};

type FatoForm = {
  campo: string;
  categoria: string;
  locus: string;
  valor: string;
  proveniencia: string;
  estado_evidencia: string;
  caso_documento_id: string;
  pagina: string;
  localizacao: string;
  trecho_fonte: string;
};

const FORM_INICIAL: CasoForm = {
  titulo: "",
  identificacao: "",
  tipo_ato: "COMPRA_VENDA",
  descricao: "",
};

const CLASSIFICACAO_INICIAL: ClassificacaoForm = {
  tipo_documento: "",
  vinculo_ato: "",
};

const FATO_INICIAL: FatoForm = {
  campo: "",
  categoria: "",
  locus: "CORINGA",
  valor: "",
  proveniencia: "DECLARADA",
  estado_evidencia: "ENCONTRADO",
  caso_documento_id: "",
  pagina: "",
  localizacao: "",
  trecho_fonte: "",
};

const STATUS = [
  {
    id: "EM_PREPARACAO",
    label: "Em preparação",
  },
  {
    id: "AGUARDANDO_CONFERENCIA",
    label: "Aguardando conferência",
  },
  {
    id: "PRONTO_PARA_ANALISE",
    label: "Pronto para análise",
  },
  {
    id: "ANALISE_DISPONIVEL",
    label: "Análise disponível",
  },
  {
    id: "DECISAO_REGISTRADA",
    label: "Decisão registrada",
  },
  {
    id: "ENCERRADO",
    label: "Encerrado",
  },
] as const;

const TIPOS_ATO_ANALISE = [
  { id: "COMPRA_VENDA", label: "Compra e Venda" },
] as const;

const TIPOS_DOCUMENTO = [
  {
    id: "RG_CNH",
    label: "RG / CNH",
  },
  {
    id: "CERTIDAO_CASAMENTO",
    label: "Certidão de casamento",
  },
  {
    id: "CERTIDAO_NASCIMENTO",
    label: "Certidão de nascimento",
  },
  {
    id: "DOCUMENTO_PESSOAL",
    label: "Documento pessoal",
  },
  {
    id: "CERTIDAO_ESTADO_CIVIL",
    label: "Certidão de estado civil",
  },
  {
    id: "MATRICULA_IMOVEL",
    label: "Matrícula do imóvel",
  },
  {
    id: "CERTIDAO_IMOVEL",
    label: "Certidão do imóvel",
  },
  {
    id: "PROCURACAO",
    label: "Procuração",
  },
  {
    id: "ALVARA_JUDICIAL",
    label: "Alvará judicial",
  },
  {
    id: "CONTRATO_INSTRUMENTO",
    label: "Contrato / instrumento",
  },
  {
    id: "CONTRATO_SOCIAL",
    label: "Contrato social",
  },
  {
    id: "ATA",
    label: "Ata / assembleia",
  },
  {
    id: "ESTATUTO",
    label: "Estatuto",
  },
  {
    id: "REGIMENTO",
    label: "Regimento / norma interna",
  },
  {
    id: "DOCUMENTO_FISCAL",
    label: "Documento fiscal / imposto",
  },
  {
    id: "COMPROVANTE",
    label: "Comprovante",
  },
  {
    id: "CERTIDAO_DIVERSA",
    label: "Certidão diversa",
  },
  {
    id: "OUTRO",
    label: "Outro",
  },
] as const;

const VINCULOS_ATO = [
  "TRANSMITENTE",
  "ADQUIRENTE",
  "IMOVEL",
  "ATO",
  "OUTRO",
] as const;

function statusLabel(status: string) {
  return STATUS.find((item) => item.id === status)?.label || status;
}

function tipoAtoLabel(tipoAto: string | null) {
  if (tipoAto === "COMPRA_VENDA") return "Compra e Venda";
  return tipoAto || "Não informado";
}

function statusClass(status: string) {
  if (status === "EM_PREPARACAO") {
    return "border-slate-200 " + "bg-slate-100 " + "text-slate-700";
  }

  if (status === "AGUARDANDO_CONFERENCIA") {
    return "border-amber-200 " + "bg-amber-50 " + "text-amber-700";
  }

  if (status === "PRONTO_PARA_ANALISE") {
    return "border-blue-200 " + "bg-blue-50 " + "text-blue-700";
  }

  if (status === "ANALISE_DISPONIVEL") {
    return "border-indigo-200 " + "bg-indigo-50 " + "text-indigo-700";
  }

  if (status === "DECISAO_REGISTRADA") {
    return "border-emerald-200 " + "bg-emerald-50 " + "text-emerald-700";
  }

  return "border-slate-300 " + "bg-slate-100 " + "text-slate-500";
}

function documentoStatusLabel(statusDocumento: string) {
  if (statusDocumento === "PROCESSANDO") {
    return "Processando";
  }

  if (statusDocumento === "PRONTO") {
    return "Pronto";
  }

  if (statusDocumento === "ERRO") {
    return "Erro";
  }

  if (statusDocumento === "PENDENTE") {
    return "Pendente";
  }

  return statusDocumento;
}

function documentoStatusClass(statusDocumento: string) {
  if (statusDocumento === "PROCESSANDO") {
    return "border-blue-200 " + "bg-blue-50 " + "text-blue-700";
  }

  if (statusDocumento === "PRONTO") {
    return "border-emerald-200 " + "bg-emerald-50 " + "text-emerald-700";
  }

  if (statusDocumento === "ERRO") {
    return "border-red-200 " + "bg-red-50 " + "text-red-700";
  }

  return "border-slate-200 " + "bg-slate-50 " + "text-slate-600";
}

function segurancaLabel(valor: string) {
  if (valor === "LIBERADO") {
    return "Conteúdo liberado";
  }

  if (valor === "REVISAO") {
    return "Requer revisão";
  }

  if (valor === "PENDENTE") {
    return "Segurança pendente";
  }

  return valor;
}

function segurancaClass(valor: string) {
  if (valor === "LIBERADO") {
    return "border-emerald-200 " + "bg-emerald-50 " + "text-emerald-700";
  }

  if (valor === "REVISAO") {
    return "border-amber-200 " + "bg-amber-50 " + "text-amber-700";
  }

  return "border-slate-200 " + "bg-slate-50 " + "text-slate-600";
}

function extracaoLabel(valor: string) {
  if (valor === "PROCESSADO_COMPLETO") {
    return "Extração completa";
  }

  if (valor === "EXTRACAO_PARCIAL") {
    return "Extração parcial";
  }

  if (valor === "NECESSITA_OCR") {
    return "Necessita OCR";
  }

  if (valor === "SEM_TEXTO") {
    return "Sem texto";
  }

  if (valor === "ERRO_PROCESSAMENTO") {
    return "Erro de extração";
  }

  if (valor === "PENDENTE_VERIFICACAO") {
    return "Extração pendente";
  }

  return valor;
}

function extracaoFatosLabel(valor: string) {
  if (valor === "NAO_INICIADO") return "Fatos ainda não sugeridos";
  if (valor === "PROCESSANDO") return "IA local organizando fatos";
  if (valor === "PRONTO") return "Propostas concluídas";
  if (valor === "PRONTO_PARCIAL") return "Propostas parciais";
  if (valor === "ERRO") return "Erro nas propostas";
  return valor;
}

function tipoDocumentoLabel(valor: string | null) {
  if (!valor) {
    return "Não classificado";
  }

  return TIPOS_DOCUMENTO.find((item) => item.id === valor)?.label || valor;
}

function vinculoAtoLabel(valor: string | null, tipoAto: string | null) {
  if (!valor) {
    return "Não classificado";
  }

  if (valor === "IMOVEL") {
    return "Imóvel";
  }

  if (valor === "ATO") {
    return "Ato";
  }

  if (valor === "OUTRO") {
    return "Outro";
  }

  const ato = (tipoAto || "").trim().toLowerCase();

  if (valor === "TRANSMITENTE") {
    if (ato.includes("compra") || ato.includes("venda")) {
      return "Vendedor / outorgante";
    }

    if (ato.includes("doa")) {
      return "Doador";
    }

    if (ato.includes("cess")) {
      return "Cedente";
    }

    return "Transmitente";
  }

  if (valor === "ADQUIRENTE") {
    if (ato.includes("compra") || ato.includes("venda")) {
      return "Comprador / outorgado";
    }

    if (ato.includes("doa")) {
      return "Donatário";
    }

    if (ato.includes("cess")) {
      return "Cessionário";
    }

    return "Adquirente";
  }

  return valor;
}

function formatarValorFato(valor: unknown) {
  if (valor === null || valor === undefined || valor === "")
    return "Não informado";
  if (typeof valor === "string") return valor;
  try {
    return JSON.stringify(valor);
  } catch {
    return "Valor estruturado";
  }
}

function formatarData(valor: string | null) {
  if (!valor) {
    return null;
  }

  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(valor));
}

function formatarTamanho(bytes: number | null) {
  if (bytes === null || bytes < 0) {
    return "Tamanho não informado";
  }

  if (bytes < 1024) {
    return `${bytes} B`;
  }

  const kb = bytes / 1024;

  if (kb < 1024) {
    return `${kb.toFixed(1)} KB`;
  }

  const mb = kb / 1024;

  return `${mb.toFixed(1)} MB`;
}

export default function AnalisePage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "ADMIN";

  const [dados, setDados] = useState<CasoListResponse>({
    items: [],
    total: 0,
    pagina: 1,
    por_pagina: 20,
    total_paginas: 0,
  });

  const [pagina, setPagina] = useState(1);

  const [pesquisa, setPesquisa] = useState("");

  const [filtroStatus, setFiltroStatus] = useState("");

  const [carregando, setCarregando] = useState(true);

  const [erro, setErro] = useState("");

  const [sucesso, setSucesso] = useState("");

  const [mostrarFormulario, setMostrarFormulario] = useState(false);

  const [salvando, setSalvando] = useState(false);

  const [casoEditando, setCasoEditando] = useState<Caso | null>(null);

  const [casoAberto, setCasoAberto] = useState<Caso | null>(null);

  const [carregandoCaso, setCarregandoCaso] = useState(false);

  const [form, setForm] = useState<CasoForm>(FORM_INICIAL);

  const [documentos, setDocumentos] = useState<CasoDocumento[]>([]);

  const [carregandoDocumentos, setCarregandoDocumentos] = useState(false);

  const [erroDocumentos, setErroDocumentos] = useState("");

  const [sucessoDocumentos, setSucessoDocumentos] = useState("");

  const [arquivosSelecionados, setArquivosSelecionados] = useState<
    DocumentoUploadSelecionado[]
  >([]);

  const [enviandoArquivo, setEnviandoArquivo] = useState(false);

  const [documentoAberto, setDocumentoAberto] =
    useState<CasoDocumentoDetalhe | null>(null);

  const [carregandoDocumento, setCarregandoDocumento] = useState(false);

  const [baixandoDocumento, setBaixandoDocumento] = useState<string | null>(
    null,
  );

  const [documentoClassificando, setDocumentoClassificando] =
    useState<CasoDocumento | null>(null);

  const [classificacaoForm, setClassificacaoForm] = useState<ClassificacaoForm>(
    CLASSIFICACAO_INICIAL,
  );

  const [salvandoClassificacao, setSalvandoClassificacao] = useState(false);

  const [excluindoDocumento, setExcluindoDocumento] = useState<string | null>(
    null,
  );

  const [excluindoCaso, setExcluindoCaso] = useState(false);

  const [usuarios, setUsuarios] = useState<UsuarioResumo[]>([]);
  const [responsavelSelecionado, setResponsavelSelecionado] = useState("");
  const [atribuindo, setAtribuindo] = useState(false);
  const [fatos, setFatos] = useState<CasoFato[]>([]);
  const [carregandoFatos, setCarregandoFatos] = useState(false);
  const [erroFatos, setErroFatos] = useState("");
  const [mostrarFato, setMostrarFato] = useState(false);
  const [fatoForm, setFatoForm] = useState<FatoForm>(FATO_INICIAL);
  const [salvandoFato, setSalvandoFato] = useState(false);
  const [processandoFato, setProcessandoFato] = useState<string | null>(null);
  const [extraindoFatosDocumento, setExtraindoFatosDocumento] = useState<
    string | null
  >(null);
  const [revisandoSegurancaDocumento, setRevisandoSegurancaDocumento] =
    useState<string | null>(null);
  const [analisesJuridicas, setAnalisesJuridicas] = useState<
    CasoAnaliseJuridica[]
  >([]);
  const [decisoes, setDecisoes] = useState<CasoDecisao[]>([]);
  const [gerandoAnalise, setGerandoAnalise] = useState(false);
  const [salvandoDecisao, setSalvandoDecisao] = useState(false);
  const [decisaoTipo, setDecisaoTipo] = useState("APROVAR");
  const [decisaoTexto, setDecisaoTexto] = useState("");
  const [decisaoFundamentacao, setDecisaoFundamentacao] = useState("");
  const [mensagensCaso, setMensagensCaso] = useState<CasoMensagem[]>([]);
  const [temMensagensAnteriores, setTemMensagensAnteriores] = useState(false);
  const [tarefasCaso, setTarefasCaso] = useState<CasoTarefa[]>([]);
  const [mensagemCaso, setMensagemCaso] = useState("");
  const [enviandoMensagemCaso, setEnviandoMensagemCaso] = useState(false);
  const [carregandoWorkspace, setCarregandoWorkspace] = useState(false);
  const [limpandoCaso, setLimpandoCaso] = useState(false);

  const inputArquivoRef = useRef<HTMLInputElement | null>(null);

  const carregarCasos = useCallback(
    async (mostrarLoading = true) => {
      if (mostrarLoading) {
        setCarregando(true);
      }

      setErro("");

      const parametros = new URLSearchParams({
        pagina: String(pagina),
        por_pagina: "20",
      });

      if (pesquisa.trim()) {
        parametros.set("pesquisa", pesquisa.trim());
      }

      if (filtroStatus) {
        parametros.set("status", filtroStatus);
      }

      try {
        const response = await apiFetch(
          `/api/analises/casos?${parametros.toString()}`,
        );

        if (!response) {
          return;
        }

        const retorno = await response.json();

        if (!response.ok) {
          setErro(retorno.detail || "Não foi possível carregar os casos.");

          return;
        }

        setDados(retorno as CasoListResponse);
      } catch {
        setErro("Não foi possível conectar ao servidor.");
      } finally {
        if (mostrarLoading) {
          setCarregando(false);
        }
      }
    },
    [pagina, pesquisa, filtroStatus],
  );

  const carregarDocumentosCaso = useCallback(
    async (casoId: string, mostrarLoading = true) => {
      if (mostrarLoading) {
        setCarregandoDocumentos(true);
      }

      setErroDocumentos("");

      try {
        const response = await apiFetch(
          `/api/analises/casos/${casoId}/documentos`,
        );

        if (!response) {
          return;
        }

        const retorno = await response.json();

        if (!response.ok) {
          setErroDocumentos(
            retorno.detail || "Não foi possível carregar os documentos.",
          );

          return;
        }

        const lista = retorno as CasoDocumentoListResponse;

        setDocumentos(lista.items);
      } catch {
        setErroDocumentos("Não foi possível carregar os documentos do caso.");
      } finally {
        if (mostrarLoading) {
          setCarregandoDocumentos(false);
        }
      }
    },
    [],
  );

  const carregarFatosCaso = useCallback(
    async (casoId: string, mostrarLoading = true) => {
      if (mostrarLoading) setCarregandoFatos(true);
      setErroFatos("");
      try {
        const response = await apiFetch(`/api/analises/casos/${casoId}/fatos`);
        if (!response) return;
        if (!response.ok) {
          setErroFatos(
            await obterMensagemErroApi(
              response,
              "Não foi possível carregar os fatos.",
            ),
          );
          return;
        }
        const retorno = (await response.json()) as { items: CasoFato[] };
        setFatos(retorno.items);
      } catch {
        setErroFatos("Não foi possível conectar ao servidor.");
      } finally {
        if (mostrarLoading) setCarregandoFatos(false);
      }
    },
    [],
  );

  const carregarA1Tab = useCallback(async (casoId: string) => {
    try {
      const [respostaAnalises, respostaDecisoes] = await Promise.all([
        apiFetch(`/api/analises/casos/${casoId}/analises-juridicas`),
        apiFetch(`/api/analises/casos/${casoId}/decisoes`),
      ]);
      if (respostaAnalises?.ok) {
        const retorno = (await respostaAnalises.json()) as {
          items: CasoAnaliseJuridica[];
        };
        setAnalisesJuridicas(retorno.items);
      }
      if (respostaDecisoes?.ok) {
        const retorno = (await respostaDecisoes.json()) as {
          items: CasoDecisao[];
        };
        setDecisoes(retorno.items);
      }
    } catch {
      setErroFatos(
        "Não foi possível carregar a análise jurídica e as decisões.",
      );
    }
  }, []);

  const carregarWorkspaceCaso = useCallback(async (casoId: string) => {
    setCarregandoWorkspace(true);
    try {
      const [mensagensResponse, tarefasResponse] = await Promise.all([
        apiFetch(`/api/analises/casos/${casoId}/mensagens`),
        apiFetch(`/api/analises/casos/${casoId}/tarefas`),
      ]);
      if (mensagensResponse?.ok) {
        const retorno = (await mensagensResponse.json()) as {
          items: CasoMensagem[];
          total: number;
          tem_mais: boolean;
        };
        setMensagensCaso(retorno.items);
        setTemMensagensAnteriores(retorno.tem_mais);
      }
      if (tarefasResponse?.ok) {
        const retorno = (await tarefasResponse.json()) as {
          items: CasoTarefa[];
        };
        setTarefasCaso(retorno.items);
      }
    } finally {
      setCarregandoWorkspace(false);
    }
  }, []);

  async function carregarMensagensAnteriores() {
    if (!casoAberto || mensagensCaso.length === 0 || !temMensagensAnteriores) {
      return;
    }
    const parametros = new URLSearchParams({
      antes_de: mensagensCaso[0].id,
      limite: "100",
    });
    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/mensagens?${parametros.toString()}`,
      );
      if (!response?.ok) return;
      const retorno = (await response.json()) as {
        items: CasoMensagem[];
        tem_mais: boolean;
      };
      setMensagensCaso((atuais) => [...retorno.items, ...atuais]);
      setTemMensagensAnteriores(retorno.tem_mais);
    } catch {
      setErroFatos("Não foi possível carregar mensagens anteriores.");
    }
  }

  useEffect(() => {
    if (
      !casoAberto ||
      !tarefasCaso.some((item) =>
        ["PENDENTE", "PROCESSANDO"].includes(item.status),
      )
    ) {
      return;
    }
    const atraso = window.setTimeout(() => {
      void Promise.all([
        carregarWorkspaceCaso(casoAberto.id),
        carregarDocumentosCaso(casoAberto.id, false),
        carregarFatosCaso(casoAberto.id, false),
      ]);
    }, 2500);
    return () => window.clearTimeout(atraso);
  }, [
    casoAberto,
    tarefasCaso,
    carregarWorkspaceCaso,
    carregarDocumentosCaso,
    carregarFatosCaso,
  ]);

  useEffect(() => {
    if (!isAdmin) return;
    const controller = new AbortController();
    void apiFetch("/api/usuarios", { signal: controller.signal })
      .then(async (response) => {
        if (!response?.ok) return;
        const retorno = (await response.json()) as UsuarioResumo[];
        if (!controller.signal.aborted)
          setUsuarios(retorno.filter((item) => item.ativo));
      })
      .catch(() => undefined);
    return () => controller.abort();
  }, [isAdmin]);

  useEffect(() => {
    const atraso = window.setTimeout(() => {
      void carregarCasos();
    }, 250);

    return () => {
      window.clearTimeout(atraso);
    };
  }, [carregarCasos]);

  function novoCaso() {
    setCasoEditando(null);

    setForm(FORM_INICIAL);

    setErro("");
    setSucesso("");

    setMostrarFormulario(true);
  }

  function editarCaso(caso: Caso) {
    setCasoEditando(caso);

    setForm({
      titulo: caso.titulo,
      identificacao: caso.identificacao || "",
      tipo_ato: caso.tipo_ato || "",
      descricao: caso.descricao || "",
    });

    setCasoAberto(null);
    setDocumentoAberto(null);
    setDocumentoClassificando(null);

    setErro("");
    setSucesso("");

    setMostrarFormulario(true);
  }

  function fecharCaso() {
    setCasoAberto(null);
    setDocumentoAberto(null);
    setDocumentoClassificando(null);
    setDocumentos([]);
    setArquivosSelecionados([]);
    setErroDocumentos("");
    setSucessoDocumentos("");
    setFatos([]);
    setAnalisesJuridicas([]);
    setDecisoes([]);
    setMensagensCaso([]);
    setTemMensagensAnteriores(false);
    setTarefasCaso([]);
    setMensagemCaso("");
    setErroFatos("");
    setResponsavelSelecionado("");

    if (inputArquivoRef.current) {
      inputArquivoRef.current.value = "";
    }
  }

  async function salvarCaso(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();

    if (!form.titulo.trim()) {
      setErro("Informe o título do caso.");

      return;
    }

    setSalvando(true);
    setErro("");
    setSucesso("");

    try {
      const corpo = {
        titulo: form.titulo.trim(),
        identificacao: form.identificacao.trim() || null,
        tipo_ato: form.tipo_ato.trim() || null,
        descricao: form.descricao.trim() || null,
      };

      const response = casoEditando
        ? await apiFetch(`/api/analises/casos/${casoEditando.id}`, {
            method: "PATCH",
            body: JSON.stringify(corpo),
          })
        : await apiFetch("/api/analises/casos", {
            method: "POST",
            body: JSON.stringify(corpo),
          });

      if (!response) {
        return;
      }

      const retorno = await response.json();

      if (!response.ok) {
        setErro(retorno.detail || "Não foi possível salvar o caso.");

        return;
      }

      const casoSalvo = retorno as Caso;

      const eraEdicao = casoEditando !== null;

      setMostrarFormulario(false);

      setCasoEditando(null);

      setForm(FORM_INICIAL);

      setSucesso(eraEdicao ? "Caso atualizado." : "Caso criado com sucesso.");

      await carregarCasos(false);

      if (eraEdicao) {
        setCasoAberto(casoSalvo);

        await carregarDocumentosCaso(casoSalvo.id);
      }
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setSalvando(false);
    }
  }

  async function abrirCaso(casoId: string) {
    setCarregandoCaso(true);
    setErro("");
    setSucesso("");
    setErroDocumentos("");
    setSucessoDocumentos("");
    setDocumentos([]);
    setDocumentoAberto(null);
    setDocumentoClassificando(null);
    setArquivosSelecionados([]);
    setFatos([]);
    setErroFatos("");
    setMensagensCaso([]);
    setTemMensagensAnteriores(false);
    setTarefasCaso([]);
    setMensagemCaso("");

    try {
      const response = await apiFetch(`/api/analises/casos/${casoId}`);

      if (!response) {
        return;
      }

      const retorno = await response.json();

      if (!response.ok) {
        setErro(retorno.detail || "Não foi possível abrir o caso.");

        return;
      }

      setCasoAberto(retorno as Caso);

      setResponsavelSelecionado((retorno as Caso).responsavel_id || "");

      await Promise.all([
        carregarDocumentosCaso(casoId),
        carregarFatosCaso(casoId),
        carregarA1Tab(casoId),
        carregarWorkspaceCaso(casoId),
      ]);
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setCarregandoCaso(false);
    }
  }

  async function atualizarCasoAberto() {
    if (!casoAberto) {
      return;
    }

    try {
      const response = await apiFetch(`/api/analises/casos/${casoAberto.id}`);

      if (response && response.ok) {
        const retorno = await response.json();

        setCasoAberto(retorno as Caso);
      }
    } catch {
      // A atualização principal da ação já ocorreu.
    }
  }

  async function atualizarDocumentos() {
    if (!casoAberto) {
      return;
    }

    await carregarDocumentosCaso(casoAberto.id);

    await atualizarCasoAberto();

    await carregarCasos(false);
  }

  async function atribuirResponsavel() {
    if (!casoAberto || !isAdmin) return;
    setAtribuindo(true);
    setErroDocumentos("");
    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/responsavel`,
        {
          method: "PATCH",
          body: JSON.stringify({
            responsavel_id: responsavelSelecionado || null,
          }),
        },
      );
      if (!response?.ok) {
        setErroDocumentos(
          await obterMensagemErroApi(
            response,
            "Não foi possível atribuir o responsável.",
          ),
        );
        return;
      }
      const atualizado = (await response.json()) as Caso;
      setCasoAberto(atualizado);
      setSucessoDocumentos("Responsável atualizado.");
      await carregarCasos(false);
    } catch {
      setErroDocumentos("Não foi possível conectar ao servidor.");
    } finally {
      setAtribuindo(false);
    }
  }

  function abrirNovoFato() {
    setFatoForm(FATO_INICIAL);
    setErroFatos("");
    setMostrarFato(true);
  }

  async function salvarFato(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (!casoAberto) return;
    setSalvandoFato(true);
    setErroFatos("");
    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/fatos`,
        {
          method: "POST",
          body: JSON.stringify({
            campo: fatoForm.campo.trim(),
            categoria: fatoForm.categoria.trim() || null,
            locus: fatoForm.locus,
            valor: fatoForm.valor,
            proveniencia: fatoForm.proveniencia,
            estado_evidencia: fatoForm.estado_evidencia,
            caso_documento_id: fatoForm.caso_documento_id || null,
            pagina: fatoForm.pagina ? Number(fatoForm.pagina) : null,
            localizacao: fatoForm.localizacao.trim() || null,
            trecho_fonte: fatoForm.trecho_fonte.trim() || null,
          }),
        },
      );
      if (!response?.ok) {
        setErroFatos(
          await obterMensagemErroApi(
            response,
            "Não foi possível registrar o fato.",
          ),
        );
        return;
      }
      setMostrarFato(false);
      setFatoForm(FATO_INICIAL);
      await carregarFatosCaso(casoAberto.id);
      await atualizarCasoAberto();
      await carregarCasos(false);
    } catch {
      setErroFatos("Não foi possível conectar ao servidor.");
    } finally {
      setSalvandoFato(false);
    }
  }

  async function conferirFato(
    fato: CasoFato,
    acao: "CONFIRMAR" | "CORRIGIR" | "REABRIR",
  ) {
    if (!casoAberto) return;
    let valorNovo: string | undefined;
    let observacao: string | null = null;
    if (acao === "CORRIGIR") {
      const informado = window.prompt(
        "Informe o valor corrigido:",
        String(fato.valor_atual ?? ""),
      );
      if (informado === null) return;
      valorNovo = informado;
    }
    if (acao === "REABRIR") {
      observacao = window.prompt(
        "Registre resumidamente o motivo da reabertura:",
      );
      if (observacao === null || !observacao.trim()) return;
    }
    setProcessandoFato(fato.id);
    setErroFatos("");
    try {
      const corpo: Record<string, unknown> = { acao, observacao };
      if (acao === "CORRIGIR") corpo.valor_novo = valorNovo;
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/fatos/${fato.id}/conferencias`,
        { method: "POST", body: JSON.stringify(corpo) },
      );
      if (!response?.ok) {
        setErroFatos(
          await obterMensagemErroApi(
            response,
            "Não foi possível registrar a conferência.",
          ),
        );
        return;
      }
      await carregarFatosCaso(casoAberto.id);
      await atualizarCasoAberto();
      await carregarCasos(false);
    } catch {
      setErroFatos("Não foi possível conectar ao servidor.");
    } finally {
      setProcessandoFato(null);
    }
  }

  async function concluirConferencia() {
    if (!casoAberto) return;
    setErroFatos("");
    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/status`,
        {
          method: "PATCH",
          body: JSON.stringify({ status: "PRONTO_PARA_ANALISE" }),
        },
      );
      if (!response?.ok) {
        setErroFatos(
          await obterMensagemErroApi(
            response,
            "A conferência ainda não pode ser concluída.",
          ),
        );
        return;
      }
      const atualizado = (await response.json()) as Caso;
      setCasoAberto(atualizado);
      await carregarCasos(false);
    } catch {
      setErroFatos("Não foi possível conectar ao servidor.");
    }
  }

  async function gerarAnaliseJuridica() {
    if (!casoAberto) return;
    setGerandoAnalise(true);
    setErroFatos("");
    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/analises-juridicas`,
        { method: "POST" },
      );
      if (!response?.ok) {
        setErroFatos(
          await obterMensagemErroApi(
            response,
            "Não foi possível gerar a análise jurídica assistiva.",
          ),
        );
        return;
      }
      await carregarA1Tab(casoAberto.id);
      await atualizarCasoAberto();
      await carregarCasos(false);
    } catch {
      setErroFatos("Não foi possível conectar ao servidor.");
    } finally {
      setGerandoAnalise(false);
    }
  }

  async function registrarDecisaoHumana() {
    if (
      !casoAberto ||
      !isAdmin ||
      !analisesJuridicas[0] ||
      !decisaoTexto.trim()
    )
      return;
    setSalvandoDecisao(true);
    setErroFatos("");
    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/decisoes`,
        {
          method: "POST",
          body: JSON.stringify({
            analise_id: analisesJuridicas[0].id,
            decisao: decisaoTipo,
            texto: decisaoTexto.trim(),
            fundamentacao: decisaoFundamentacao.trim() || null,
            escopo: casoAberto.tipo_ato || null,
          }),
        },
      );
      if (!response?.ok) {
        setErroFatos(
          await obterMensagemErroApi(
            response,
            "Não foi possível registrar a decisão.",
          ),
        );
        return;
      }
      setDecisaoTexto("");
      setDecisaoFundamentacao("");
      await carregarA1Tab(casoAberto.id);
      await atualizarCasoAberto();
      await carregarCasos(false);
    } catch {
      setErroFatos("Não foi possível conectar ao servidor.");
    } finally {
      setSalvandoDecisao(false);
    }
  }

  async function enviarMensagemCaso() {
    if (!casoAberto) return;
    if (arquivosSelecionados.length > 0) {
      const arquivoSemClassificacao = arquivosSelecionados.find(
        (item) => !item.tipo_documento || !item.vinculo_ato,
      );
      if (arquivoSemClassificacao) {
        setErroDocumentos(
          `Classifique o tipo e o vínculo de ${arquivoSemClassificacao.arquivo.name}.`,
        );
        return;
      }
      setEnviandoMensagemCaso(true);
      try {
        await enviarDocumentos(mensagemCaso.trim());
      } finally {
        setEnviandoMensagemCaso(false);
      }
      return;
    }
    if (!mensagemCaso.trim()) return;
    setEnviandoMensagemCaso(true);
    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/mensagens?gerar=true`,
        {
          method: "POST",
          body: JSON.stringify({ conteudo: mensagemCaso.trim() }),
        },
      );
      if (!response?.ok) {
        setErroFatos(
          await obterMensagemErroApi(
            response,
            "Não foi possível registrar a mensagem.",
          ),
        );
        return;
      }
      setMensagemCaso("");
      await carregarWorkspaceCaso(casoAberto.id);
      await atualizarCasoAberto();
    } catch {
      setErroFatos("Não foi possível conectar ao servidor.");
    } finally {
      setEnviandoMensagemCaso(false);
    }
  }

  async function concluirEApagarCaso() {
    if (!casoAberto) return;
    if (
      !window.confirm(
        "Apagar os arquivos e textos extraídos deste caso? O histórico da conversa permanecerá salvo.",
      )
    )
      return;
    setLimpandoCaso(true);
    setErroDocumentos("");
    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/concluir-apagar`,
        { method: "POST" },
      );
      if (!response?.ok) {
        setErroDocumentos(
          await obterMensagemErroApi(
            response,
            "Não foi possível concluir a limpeza.",
          ),
        );
        return;
      }
      fecharCaso();
      setSucesso("Caso concluído. Os documentos privados foram removidos.");
      await carregarCasos(false);
    } catch {
      setErroDocumentos("Não foi possível conectar ao servidor.");
    } finally {
      setLimpandoCaso(false);
    }
  }

  async function reabrirCaso() {
    if (!casoAberto) return;
    setLimpandoCaso(true);
    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/status`,
        {
          method: "PATCH",
          body: JSON.stringify({ status: "EM_PREPARACAO" }),
        },
      );
      if (!response?.ok) {
        setErroDocumentos(
          await obterMensagemErroApi(
            response,
            "Não foi possível reabrir o caso.",
          ),
        );
        return;
      }
      setCasoAberto((await response.json()) as Caso);
      await Promise.all([
        carregarWorkspaceCaso(casoAberto.id),
        carregarCasos(false),
      ]);
      setSucesso("Caso reaberto. O histórico da conversa foi preservado.");
    } catch {
      setErroDocumentos("Não foi possível conectar ao servidor.");
    } finally {
      setLimpandoCaso(false);
    }
  }

  async function concluirCaso() {
    if (!casoAberto) return;
    if (
      !window.confirm(
        "Concluir este caso mantendo os documentos e todo o histórico? Você poderá reabri-lo depois.",
      )
    )
      return;
    setLimpandoCaso(true);
    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/status`,
        {
          method: "PATCH",
          body: JSON.stringify({ status: "ENCERRADO" }),
        },
      );
      if (!response?.ok) {
        setErroDocumentos(
          await obterMensagemErroApi(
            response,
            "Não foi possível concluir o caso.",
          ),
        );
        return;
      }
      setCasoAberto((await response.json()) as Caso);
      await carregarCasos(false);
      setSucesso(
        "Caso concluído. Os documentos e a conversa foram preservados.",
      );
    } catch {
      setErroDocumentos("Não foi possível conectar ao servidor.");
    } finally {
      setLimpandoCaso(false);
    }
  }

  function alterarTipoDocumentoUpload(indice: number, valor: string) {
    setArquivosSelecionados((atuais) =>
      atuais.map((item, posicao) =>
        posicao === indice
          ? {
              ...item,
              tipo_documento: valor,
              vinculo_ato:
                (valor === "MATRICULA_IMOVEL" || valor === "CERTIDAO_IMOVEL") &&
                !item.vinculo_ato
                  ? "IMOVEL"
                  : item.vinculo_ato,
            }
          : item,
      ),
    );
  }

  function alterarVinculoDocumentoUpload(indice: number, valor: string) {
    setArquivosSelecionados((atuais) =>
      atuais.map((item, posicao) =>
        posicao === indice ? { ...item, vinculo_ato: valor } : item,
      ),
    );
  }

  async function aguardarProcessamentoLote(
    casoId: string,
    documentoIds: string[],
  ): Promise<{ ok: boolean; erro?: string }> {
    const estadosTerminais = new Set(["CONCLUIDA", "ERRO", "CANCELADA"]);
    while (true) {
      const parametros = new URLSearchParams({
        tipo: "ANALISE_DOCUMENTO_CHAT",
      });
      documentoIds.forEach((id) => parametros.append("caso_documento_ids", id));
      const response = await apiFetch(
        `/api/analises/casos/${casoId}/tarefas?${parametros.toString()}`,
      );
      if (!response?.ok) {
        return {
          ok: false,
          erro: await obterMensagemErroApi(
            response,
            "Não foi possível acompanhar o processamento dos documentos.",
          ),
        };
      }

      const retorno = (await response.json()) as { items: CasoTarefa[] };
      const tarefas = retorno.items.filter(
        (item) =>
          item.tipo === "ANALISE_DOCUMENTO_CHAT" &&
          documentoIds.includes(item.caso_documento_id || ""),
      );
      const falha = tarefas.find((item) =>
        ["ERRO", "CANCELADA"].includes(item.status),
      );
      if (falha) {
        return {
          ok: false,
          erro:
            falha.erro ||
            "Um dos documentos não concluiu o processamento; a análise conjunta não foi gerada.",
        };
      }

      const concluidas = tarefas.filter(
        (item) => item.status === "CONCLUIDA",
      ).length;
      setSucessoDocumentos(
        `Leitura dos documentos do lote: ${concluidas} de ${documentoIds.length} concluído(s). A análise conjunta será gerada ao final.`,
      );
      if (
        tarefas.length === documentoIds.length &&
        tarefas.every((item) => estadosTerminais.has(item.status))
      ) {
        return { ok: true };
      }

      await new Promise<void>((resolver) => window.setTimeout(resolver, 2500));
    }
  }

  async function enviarDocumentos(orientacaoUsuario = "") {
    if (!casoAberto || arquivosSelecionados.length === 0) {
      setErroDocumentos("Selecione ao menos um arquivo para enviar.");
      return;
    }
    if (
      arquivosSelecionados.some(
        (item) => !item.tipo_documento || !item.vinculo_ato,
      )
    ) {
      setErroDocumentos("Informe o tipo e o vínculo de cada documento.");
      return;
    }

    if (casoAberto.status === "ENCERRADO") {
      setErroDocumentos(
        "Não é possível adicionar documentos a um caso encerrado.",
      );

      return;
    }

    setEnviandoArquivo(true);
    setErroDocumentos("");
    setSucessoDocumentos("");
    const lote = [...arquivosSelecionados];
    const documentoIdsLote: string[] = [];
    let enviados = 0;
    let erroProcessamentoLote = "";
    try {
      for (const item of lote) {
        const formData = new FormData();
        formData.append("arquivo", item.arquivo);
        formData.append("tipo_documento", item.tipo_documento);
        formData.append("vinculo_ato", item.vinculo_ato);
        formData.append("responder_apos_processamento", "false");
        if (orientacaoUsuario) {
          formData.append("orientacao_usuario", orientacaoUsuario);
        }
        const response = await apiFetch(
          `/api/analises/casos/${casoAberto.id}/documentos`,
          { method: "POST", body: formData },
        );
        if (!response) {
          setErroDocumentos(
            `O envio de ${item.arquivo.name} foi interrompido.`,
          );
          break;
        }
        const retorno = await response.json();
        if (!response.ok) {
          const detalhe =
            retorno.detail || "não foi possível enviar o documento.";
          setErroDocumentos(`${item.arquivo.name}: ${detalhe}`);
          break;
        }
        documentoIdsLote.push((retorno as CasoDocumento).id);
        enviados += 1;
        setSucessoDocumentos(
          `Leitura do documento ${enviados} de ${lote.length} em andamento.`,
        );
        await carregarDocumentosCaso(casoAberto.id, false);
        const processamento = await aguardarProcessamentoLote(casoAberto.id, [
          documentoIdsLote[documentoIdsLote.length - 1],
        ]);
        if (!processamento.ok) {
          erroProcessamentoLote ||= `${item.arquivo.name}: ${processamento.erro || "o processamento não foi concluído."}`;
        }
      }

      setArquivosSelecionados(lote.slice(enviados));
      if (enviados === lote.length) {
        setMensagemCaso("");
      }

      if (enviados === lote.length && inputArquivoRef.current) {
        inputArquivoRef.current.value = "";
      }

      if (enviados > 0) {
        if (erroProcessamentoLote) {
          setErroDocumentos(erroProcessamentoLote);
          setSucessoDocumentos(
            `${enviados} documento(s) foram recebidos; não gerei uma análise conjunta porque o processamento do lote foi interrompido.`,
          );
        } else {
          setSucessoDocumentos(
            enviados === lote.length && lote.length > 1
              ? `${enviados} documentos recebidos. Vou analisar o conjunto.`
              : enviados === lote.length
                ? "Documento recebido. Vou analisar o processo com o material disponível."
                : `${enviados} documento(s) enviado(s) para processamento.`,
          );
        }
        await carregarDocumentosCaso(casoAberto.id, false);
        await carregarWorkspaceCaso(casoAberto.id);
        await atualizarCasoAberto();
        await carregarCasos(false);

        if (
          enviados === lote.length &&
          enviados > 0 &&
          !erroProcessamentoLote
        ) {
          const processamento = await aguardarProcessamentoLote(
            casoAberto.id,
            documentoIdsLote,
          );
          await Promise.all([
            carregarWorkspaceCaso(casoAberto.id),
            carregarDocumentosCaso(casoAberto.id, false),
            carregarFatosCaso(casoAberto.id, false),
          ]);
          if (!processamento.ok) {
            setErroDocumentos(
              processamento.erro || "Falha no processamento do lote.",
            );
          } else {
            const documentosResponse = await apiFetch(
              `/api/analises/casos/${casoAberto.id}/documentos`,
            );
            if (!documentosResponse?.ok) {
              setErroDocumentos(
                await obterMensagemErroApi(
                  documentosResponse,
                  "Não foi possível conferir se todos os documentos ficaram prontos.",
                ),
              );
            } else {
              const retornoDocumentos =
                (await documentosResponse.json()) as CasoDocumentoListResponse;
              const documentosNaoProntos = retornoDocumentos.items.filter(
                (documento) =>
                  documento.status !== "PRONTO" ||
                  documento.status_seguranca !== "LIBERADO" ||
                  documento.situacao_extracao !== "PROCESSADO_COMPLETO",
              );
              if (documentosNaoProntos.length > 0) {
                const nomes = documentosNaoProntos
                  .map((documento) => documento.nome_arquivo)
                  .join(", ");
                setErroDocumentos(
                  `A análise conjunta aguarda documentos prontos, liberados e com extração completa: ${nomes}. Revise a segurança ou reprocese os arquivos indicados.`,
                );
              } else {
                const instrucoes = [
                  "Analise os documentos deste processo em conjunto. Comece identificando as partes e, quando houver empresa ou representação, a pessoa que o documento indica e os poderes que estão escritos. Confira também a matrícula e as averbações relevantes. Separe o que foi encontrado, o que diverge e o que ainda falta; cite arquivo e página quando disponíveis.",
                  "Depois dos achados, peça apenas o próximo documento ou informação que esteja faltando. Se a matrícula ainda não foi enviada, solicite-a. Se a matrícula já foi conferida mas faltarem dados, pergunte a forma de pagamento, o valor e as datas. Compare essas datas com o estado civil documentado. Não conclua validade definitiva nem invente exigências.",
                  orientacaoUsuario.trim()
                    ? `O escrevente também pediu esta conferência: ${orientacaoUsuario.trim()}`
                    : "",
                ]
                  .filter(Boolean)
                  .join("\n\n");
                const respostaAnalise = await apiFetch(
                  `/api/analises/casos/${casoAberto.id}/mensagens?gerar=true`,
                  {
                    method: "POST",
                    body: JSON.stringify({ conteudo: instrucoes }),
                  },
                );
                if (!respostaAnalise?.ok) {
                  setErroDocumentos(
                    await obterMensagemErroApi(
                      respostaAnalise,
                      "Os documentos foram lidos, mas não foi possível solicitar a análise conjunta.",
                    ),
                  );
                } else {
                  setSucessoDocumentos(
                    "Leitura concluída. A IA está preparando uma única análise conjunta do processo com referências aos arquivos e às páginas.",
                  );
                  await Promise.all([
                    carregarWorkspaceCaso(casoAberto.id),
                    carregarDocumentosCaso(casoAberto.id, false),
                    carregarFatosCaso(casoAberto.id, false),
                  ]);
                }
              }
            }
          }
        }
      }
    } catch (erro) {
      setErroDocumentos(
        erro instanceof Error
          ? erro.message
          : "Não foi possível conectar ao servidor durante o envio.",
      );
    } finally {
      setEnviandoArquivo(false);
    }
  }

  function abrirClassificacao(documento: CasoDocumento) {
    setDocumentoClassificando(documento);

    setClassificacaoForm({
      tipo_documento: documento.tipo_documento || "",
      vinculo_ato: documento.vinculo_ato || "",
    });

    setErroDocumentos("");
  }

  function alterarTipoClassificacao(valor: string) {
    setClassificacaoForm((atual) => ({
      ...atual,
      tipo_documento: valor,
      vinculo_ato:
        (valor === "MATRICULA_IMOVEL" || valor === "CERTIDAO_IMOVEL") &&
        !atual.vinculo_ato
          ? "IMOVEL"
          : atual.vinculo_ato,
    }));
  }

  async function salvarClassificacao() {
    if (!casoAberto || !documentoClassificando) {
      return;
    }

    if (!classificacaoForm.tipo_documento) {
      setErroDocumentos("Informe o tipo do documento.");

      return;
    }

    if (!classificacaoForm.vinculo_ato) {
      setErroDocumentos(
        "Informe a quem ou a que o documento está relacionado.",
      );

      return;
    }

    setSalvandoClassificacao(true);

    setErroDocumentos("");
    setSucessoDocumentos("");

    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/documentos/${documentoClassificando.id}/classificacao`,
        {
          method: "PATCH",
          body: JSON.stringify({
            tipo_documento: classificacaoForm.tipo_documento,
            vinculo_ato: classificacaoForm.vinculo_ato,
          }),
        },
      );

      if (!response) {
        return;
      }

      const retorno = await response.json();

      if (!response.ok) {
        setErroDocumentos(
          retorno.detail || "Não foi possível alterar a classificação.",
        );

        return;
      }

      setDocumentoClassificando(null);

      setClassificacaoForm(CLASSIFICACAO_INICIAL);

      setSucessoDocumentos("Classificação do documento atualizada.");

      await carregarDocumentosCaso(casoAberto.id, false);

      await atualizarCasoAberto();

      await carregarCasos(false);
    } catch {
      setErroDocumentos(
        "Não foi possível alterar a classificação do documento.",
      );
    } finally {
      setSalvandoClassificacao(false);
    }
  }

  async function abrirDocumento(documento: CasoDocumento) {
    if (!casoAberto) {
      return;
    }

    setCarregandoDocumento(true);

    setErroDocumentos("");

    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/documentos/${documento.id}`,
      );

      if (!response) {
        return;
      }

      const retorno = await response.json();

      if (!response.ok) {
        setErroDocumentos(
          retorno.detail || "Não foi possível abrir o documento.",
        );

        return;
      }

      setDocumentoAberto(retorno as CasoDocumentoDetalhe);
    } catch {
      setErroDocumentos("Não foi possível carregar o conteúdo extraído.");
    } finally {
      setCarregandoDocumento(false);
    }
  }

  async function baixarDocumento(documento: CasoDocumento) {
    if (!casoAberto) {
      return;
    }

    setBaixandoDocumento(documento.id);

    setErroDocumentos("");

    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/documentos/${documento.id}/download`,
      );

      if (!response) {
        return;
      }

      if (!response.ok) {
        let mensagem = "Não foi possível baixar o documento.";

        try {
          const retorno = await response.json();

          mensagem = retorno.detail || mensagem;
        } catch {
          // Resposta sem JSON.
        }

        setErroDocumentos(mensagem);

        return;
      }

      const blob = await response.blob();

      const url = URL.createObjectURL(blob);

      const link = document.createElement("a");

      link.href = url;
      link.download = documento.nome_arquivo;

      document.body.appendChild(link);

      link.click();

      link.remove();

      URL.revokeObjectURL(url);
    } catch {
      setErroDocumentos("Não foi possível baixar o documento.");
    } finally {
      setBaixandoDocumento(null);
    }
  }

  async function reprocessarDocumento(
    documento: CasoDocumento,
    forcarOcr = false,
  ) {
    if (!casoAberto) return;
    if (
      !window.confirm(
        "Reprocessar este documento? Se houver uma tarefa em andamento, o servidor impedirá a duplicação.",
      )
    )
      return;
    setErroDocumentos("");
    setSucessoDocumentos("");
    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/documentos/${documento.id}/reprocessar${forcarOcr ? "?forcar_ocr=true" : ""}`,
        { method: "POST" },
      );
      if (!response?.ok) {
        setErroDocumentos(
          await obterMensagemErroApi(
            response,
            "Não foi possível reprocessar o documento.",
          ),
        );
        return;
      }
      setDocumentoAberto(null);
      setSucessoDocumentos(
        "Reprocessamento solicitado. Atualize a lista para acompanhar a conclusão.",
      );
      await carregarDocumentosCaso(casoAberto.id, false);
      await atualizarCasoAberto();
    } catch {
      setErroDocumentos("Não foi possível conectar ao servidor.");
    }
  }

  async function proporFatosDocumento(documento: CasoDocumento) {
    if (!casoAberto) return;
    setExtraindoFatosDocumento(documento.id);
    setErroDocumentos("");
    setSucessoDocumentos("");
    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/documentos/${documento.id}/propor-fatos`,
        { method: "POST" },
      );
      if (!response?.ok) {
        setErroDocumentos(
          await obterMensagemErroApi(
            response,
            "Não foi possível iniciar as propostas factuais.",
          ),
        );
        return;
      }
      const atualizado = (await response.json()) as CasoDocumento;
      setDocumentos((atuais) =>
        atuais.map((item) => (item.id === atualizado.id ? atualizado : item)),
      );
      setSucessoDocumentos(
        "A IA local iniciou a organização factual. Todas as propostas continuarão pendentes até a conferência humana.",
      );
    } catch {
      setErroDocumentos("Não foi possível conectar ao servidor.");
    } finally {
      setExtraindoFatosDocumento(null);
    }
  }

  async function liberarSegurancaDocumento(documento: CasoDocumento) {
    if (!casoAberto) return;
    const confirmou = window.confirm(
      "Confirma que você leu o conteúdo extraído, identificou o alerta e deseja liberar este documento para a proposta factual local?",
    );
    if (!confirmou) return;
    setRevisandoSegurancaDocumento(documento.id);
    setErroDocumentos("");
    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/documentos/${documento.id}/seguranca`,
        { method: "PATCH", body: JSON.stringify({ acao: "LIBERAR" }) },
      );
      if (!response?.ok) {
        setErroDocumentos(
          await obterMensagemErroApi(
            response,
            "Não foi possível liberar o documento.",
          ),
        );
        return;
      }
      const atualizado = (await response.json()) as CasoDocumento;
      setDocumentos((atuais) =>
        atuais.map((item) => (item.id === atualizado.id ? atualizado : item)),
      );
      setSucessoDocumentos(
        "Revisão de segurança registrada. O documento está liberado para propostas factuais locais.",
      );
    } catch {
      setErroDocumentos("Não foi possível conectar ao servidor.");
    } finally {
      setRevisandoSegurancaDocumento(null);
    }
  }

  async function excluirDocumento(documento: CasoDocumento) {
    if (!casoAberto) {
      return;
    }

    const confirmou = window.confirm(
      `Excluir o documento "${documento.nome_arquivo}"?\n\n` +
        "O arquivo original e o conteúdo extraído serão removidos deste caso. " +
        "Esta ação não pode ser desfeita.",
    );

    if (!confirmou) {
      return;
    }

    setExcluindoDocumento(documento.id);

    setErroDocumentos("");
    setSucessoDocumentos("");

    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoAberto.id}/documentos/${documento.id}`,
        {
          method: "DELETE",
        },
      );

      if (!response) {
        return;
      }

      if (!response.ok) {
        let mensagem = "Não foi possível excluir o documento.";

        try {
          const retorno = await response.json();

          mensagem = retorno.detail || mensagem;
        } catch {
          // Resposta sem JSON.
        }

        setErroDocumentos(mensagem);

        return;
      }

      if (documentoAberto?.id === documento.id) {
        setDocumentoAberto(null);
      }

      if (documentoClassificando?.id === documento.id) {
        setDocumentoClassificando(null);
      }

      setSucessoDocumentos("Documento excluído do caso.");

      await carregarDocumentosCaso(casoAberto.id, false);

      await atualizarCasoAberto();

      await carregarCasos(false);
    } catch {
      setErroDocumentos("Não foi possível excluir o documento.");
    } finally {
      setExcluindoDocumento(null);
    }
  }

  async function excluirCaso() {
    if (!casoAberto) {
      return;
    }

    const confirmou = window.confirm(
      `Excluir definitivamente o caso "${casoAberto.titulo}"?\n\n` +
        "Os documentos privados e arquivos associados também serão removidos. " +
        "A exclusão só será permitida se o caso ainda estiver em preparação " +
        "e não possuir fatos registrados.\n\n" +
        "Esta ação não pode ser desfeita.",
    );

    if (!confirmou) {
      return;
    }

    setExcluindoCaso(true);
    setErroDocumentos("");
    setSucessoDocumentos("");

    const casoId = casoAberto.id;

    try {
      const response = await apiFetch(`/api/analises/casos/${casoId}`, {
        method: "DELETE",
      });

      if (!response) {
        return;
      }

      if (!response.ok) {
        let mensagem = "Não foi possível excluir o caso.";

        try {
          const retorno = await response.json();

          mensagem = retorno.detail || mensagem;
        } catch {
          // Resposta sem JSON.
        }

        setErroDocumentos(mensagem);

        return;
      }

      fecharCaso();

      setSucesso("Caso excluído com sucesso.");

      if (dados.items.length === 1 && pagina > 1) {
        setPagina((atual) => atual - 1);
      } else {
        await carregarCasos(false);
      }
    } catch {
      setErroDocumentos("Não foi possível excluir o caso.");
    } finally {
      setExcluindoCaso(false);
    }
  }

  function alterarPesquisa(valor: string) {
    setPesquisa(valor);
    setPagina(1);
  }

  function alterarStatus(valor: string) {
    setFiltroStatus(valor);
    setPagina(1);
  }

  return (
    <div className="min-h-full bg-slate-100 p-6 text-slate-900 lg:p-8">
      <div className="mx-auto max-w-7xl">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">Análise</h1>
          </div>

          <button
            type="button"
            onClick={novoCaso}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white transition hover:bg-slate-700"
          >
            <Plus size={17} />
            Nova análise
          </button>
        </div>

        {erro && (
          <div className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {erro}
          </div>
        )}

        {sucesso && (
          <div className="mt-6 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
            {sucesso}
          </div>
        )}

        <section className="mt-8 rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="flex flex-col gap-3 border-b border-slate-200 p-4 md:flex-row md:items-center">
            <label className="relative flex-1">
              <Search
                size={17}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />

              <input
                value={pesquisa}
                onChange={(evento) => alterarPesquisa(evento.target.value)}
                placeholder="Pesquisar análises"
                className="w-full rounded-lg border border-slate-300 bg-white py-2.5 pl-10 pr-3 text-sm text-slate-900 outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
              />
            </label>

            <select
              value={filtroStatus}
              onChange={(evento) => alterarStatus(evento.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none transition focus:border-slate-500 focus:ring-2 focus:ring-slate-200 md:w-64"
            >
              <option value="">Todos os status</option>

              {STATUS.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
                </option>
              ))}
            </select>

            <button
              type="button"
              onClick={() => void carregarCasos()}
              disabled={carregando}
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
            >
              <RefreshCw
                size={16}
                className={carregando ? "animate-spin" : ""}
              />
              Atualizar
            </button>
          </div>

          {carregando ? (
            <div className="flex min-h-56 items-center justify-center">
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <LoaderCircle size={18} className="animate-spin" />
                Carregando casos...
              </div>
            </div>
          ) : dados.items.length === 0 ? (
            <div className="px-6 py-16 text-center">
              <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-slate-500">
                <ClipboardCheck size={22} />
              </div>

              <p className="mt-4 text-sm font-medium text-slate-800">
                Nenhum caso encontrado
              </p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100">
              {dados.items.map((caso) => (
                <article
                  key={caso.id}
                  className="p-5 transition hover:bg-slate-50/60"
                >
                  <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h2 className="text-base font-semibold text-slate-900">
                          {caso.titulo}
                        </h2>

                        <span
                          className={`rounded-full border px-2.5 py-1 text-xs font-medium ${statusClass(
                            caso.status,
                          )}`}
                        >
                          {statusLabel(caso.status)}
                        </span>
                      </div>

                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                        {caso.identificacao && (
                          <span>Identificação: {caso.identificacao}</span>
                        )}

                        {caso.tipo_ato && (
                          <span>Tipo: {tipoAtoLabel(caso.tipo_ato)}</span>
                        )}

                        <span>
                          Responsável:{" "}
                          {caso.responsavel_nome || "não informado"}
                        </span>

                        <span>
                          Atualizado em {formatarData(caso.updated_at)}
                        </span>
                      </div>

                      {caso.descricao && (
                        <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
                          {caso.descricao}
                        </p>
                      )}

                      <div className="mt-4 flex flex-wrap gap-2">
                        <Indicador
                          icone={<FileText size={14} />}
                          texto={`${caso.total_documentos} documento(s)`}
                        />

                        <Indicador
                          icone={<ClipboardCheck size={14} />}
                          texto={`${caso.total_fatos} fato(s)`}
                        />

                        <Indicador
                          icone={<ClipboardCheck size={14} />}
                          texto={`${caso.total_pendentes_conferencia} pendente(s) de conferência`}
                          destaque={caso.total_pendentes_conferencia > 0}
                        />

                        {caso.total_conflitantes > 0 && (
                          <Indicador
                            icone={<AlertTriangle size={14} />}
                            texto={`${caso.total_conflitantes} conflito(s)`}
                            alerta
                          />
                        )}
                      </div>
                    </div>

                    <div className="flex shrink-0 items-center gap-2">
                      <button
                        type="button"
                        onClick={() => editarCaso(caso)}
                        disabled={caso.status === "ENCERRADO"}
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <Pencil size={15} />
                        Editar
                      </button>

                      <button
                        type="button"
                        onClick={() => void abrirCaso(caso.id)}
                        disabled={carregandoCaso}
                        className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
                      >
                        Abrir
                        <ChevronRight size={16} />
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}

          <div className="flex flex-col gap-3 border-t border-slate-200 px-5 py-4 text-sm text-slate-600 sm:flex-row sm:items-center sm:justify-between">
            <span>{dados.total} caso(s)</span>

            <div className="flex items-center gap-3">
              <button
                type="button"
                disabled={pagina <= 1}
                onClick={() => setPagina((atual) => atual - 1)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Anterior
              </button>

              <span>
                Página {pagina} de {Math.max(dados.total_paginas, 1)}
              </span>

              <button
                type="button"
                disabled={
                  dados.total_paginas === 0 || pagina >= dados.total_paginas
                }
                onClick={() => setPagina((atual) => atual + 1)}
                className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-700 disabled:cursor-not-allowed disabled:opacity-40"
              >
                Próxima
              </button>
            </div>
          </div>
        </section>
      </div>

      {mostrarFormulario && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
          <div className="w-full max-w-2xl rounded-2xl bg-white shadow-xl">
            <div className="flex items-start justify-between border-b border-slate-200 px-6 py-5">
              <div className="grid gap-4 md:grid-cols-2">
                <h2 className="text-lg font-semibold text-slate-900">
                  {casoEditando ? "Editar caso" : "Nova análise"}
                </h2>
              </div>

              <button
                type="button"
                onClick={() => setMostrarFormulario(false)}
                className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100"
                aria-label="Fechar"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={salvarCaso} className="space-y-5 p-6">
              <div>
                <label className="text-sm font-medium text-slate-800">
                  Título
                </label>

                <input
                  value={form.titulo}
                  onChange={(evento) =>
                    setForm({
                      ...form,
                      titulo: evento.target.value,
                    })
                  }
                  required
                  minLength={3}
                  maxLength={200}
                  placeholder="Ex.: Compra e venda - imóvel Rua X"
                  className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                />
              </div>

              <p className="text-sm text-slate-600">
                Descreva o caso. Depois, na conversa, anexe cada documento e
                indique a quem ele pertence. Os arquivos do caso não entram na
                Consulta.
              </p>

              <div className="grid gap-4 md:grid-cols-2">
                <div>
                  <label className="text-sm font-medium text-slate-800">
                    Identificação
                  </label>

                  <input
                    value={form.identificacao}
                    onChange={(evento) =>
                      setForm({
                        ...form,
                        identificacao: evento.target.value,
                      })
                    }
                    maxLength={100}
                    placeholder="Protocolo, referência ou número interno"
                    className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                  />
                </div>

                <div>
                  <label className="text-sm font-medium text-slate-800">
                    Tipo de análise
                  </label>

                  <select
                    value={form.tipo_ato}
                    onChange={(evento) =>
                      setForm({
                        ...form,
                        tipo_ato: evento.target.value,
                      })
                    }
                    className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                  >
                    {TIPOS_ATO_ANALISE.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-slate-800">
                  Descrição
                </label>

                <textarea
                  value={form.descricao}
                  onChange={(evento) =>
                    setForm({
                      ...form,
                      descricao: evento.target.value,
                    })
                  }
                  maxLength={10000}
                  rows={5}
                  placeholder="Contexto inicial ou observações úteis para identificar o caso."
                  className="mt-2 w-full resize-y rounded-lg border border-slate-300 px-3 py-3 text-sm leading-6 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                />
              </div>

              {erro && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {erro}
                </div>
              )}

              <div className="flex justify-end gap-3 border-t border-slate-200 pt-5">
                <button
                  type="button"
                  onClick={() => setMostrarFormulario(false)}
                  className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
                >
                  Cancelar
                </button>

                <button
                  type="submit"
                  disabled={salvando}
                  className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
                >
                  {salvando && (
                    <LoaderCircle size={16} className="animate-spin" />
                  )}

                  {casoEditando ? "Salvar alterações" : "Criar análise"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {casoAberto && (
        <div className="fixed inset-0 z-50 bg-slate-50">
          <div className="h-screen w-full overflow-y-auto bg-slate-50">
            <div className="sticky top-0 z-10 flex items-start justify-between border-b border-slate-200 bg-white px-6 py-5">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-xl font-semibold text-slate-900">
                    {casoAberto.titulo}
                  </h2>

                  <span
                    className={`rounded-full border px-2.5 py-1 text-xs font-medium ${statusClass(
                      casoAberto.status,
                    )}`}
                  >
                    {statusLabel(casoAberto.status)}
                  </span>
                </div>
              </div>

              <button
                type="button"
                onClick={fecharCaso}
                className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100"
                aria-label="Fechar"
              >
                <X size={20} />
              </button>
            </div>

            <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 p-6">
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-slate-600">
                <span>{tipoAtoLabel(casoAberto.tipo_ato)}</span>
                {casoAberto.identificacao && (
                  <span>· {casoAberto.identificacao}</span>
                )}
                <span>
                  · Responsável:{" "}
                  {casoAberto.responsavel_nome || "não atribuído"}
                </span>
              </div>

              <details className="order-2 rounded-xl border border-slate-200 bg-white p-4">
                <summary className="cursor-pointer text-sm font-semibold text-slate-800">
                  Mais informações do processo
                </summary>
                <div className="mt-5 space-y-6">
                  {isAdmin && casoAberto.status !== "ENCERRADO" && (
                    <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                      <label className="text-xs font-medium uppercase tracking-wide text-slate-600">
                        Atribuir responsável
                      </label>
                      <div className="mt-2 flex flex-col gap-2 sm:flex-row">
                        <select
                          value={responsavelSelecionado}
                          onChange={(evento) =>
                            setResponsavelSelecionado(evento.target.value)
                          }
                          className="min-w-0 flex-1 rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-800"
                        >
                          <option value="">Sem responsável atribuído</option>
                          {usuarios.map((item) => (
                            <option key={item.id} value={item.id}>
                              {item.nome} · {item.username}
                            </option>
                          ))}
                        </select>
                        <button
                          type="button"
                          onClick={() => void atribuirResponsavel()}
                          disabled={atribuindo}
                          className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
                        >
                          {atribuindo ? "Salvando..." : "Atribuir"}
                        </button>
                      </div>
                    </div>
                  )}

                  {casoAberto.descricao && (
                    <div>
                      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                        Descrição
                      </p>

                      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">
                        {casoAberto.descricao}
                      </p>
                    </div>
                  )}

                  <div>
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                      <ResumoCard
                        titulo="Documentos"
                        valor={casoAberto.total_documentos}
                      />

                      <ResumoCard
                        titulo="Fatos"
                        valor={casoAberto.total_fatos}
                      />

                      <ResumoCard
                        titulo="A conferir"
                        valor={casoAberto.total_pendentes_conferencia}
                      />

                      <ResumoCard
                        titulo="Conflitos"
                        valor={casoAberto.total_conflitantes}
                        alerta={casoAberto.total_conflitantes > 0}
                      />
                    </div>
                  </div>

                  <section className="rounded-xl border border-slate-200 bg-white">
                    <div className="flex flex-col gap-3 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900">
                          Informações extraídas dos documentos
                        </h3>
                      </div>
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => void carregarFatosCaso(casoAberto.id)}
                          disabled={carregandoFatos}
                          className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 disabled:opacity-50"
                        >
                          Atualizar
                        </button>
                        {["EM_PREPARACAO", "AGUARDANDO_CONFERENCIA"].includes(
                          casoAberto.status,
                        ) && (
                          <button
                            type="button"
                            onClick={abrirNovoFato}
                            className="rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white"
                          >
                            Registrar fato
                          </button>
                        )}
                      </div>
                    </div>

                    {erroFatos && (
                      <div className="m-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                        {erroFatos}
                      </div>
                    )}

                    {carregandoFatos ? (
                      <div className="p-8 text-center text-sm text-slate-600">
                        Carregando fatos...
                      </div>
                    ) : fatos.length === 0 ? (
                      <div className="p-8 text-center text-sm text-slate-600">
                        Nenhum fato registrado. A ausência de registro não
                        significa inexistência de fatos.
                      </div>
                    ) : (
                      <div className="divide-y divide-slate-200">
                        {fatos.map((fato) => (
                          <article key={fato.id} className="p-5">
                            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2">
                                  <h4 className="font-medium text-slate-900">
                                    {fato.campo}
                                  </h4>
                                  {fato.contexto?.origem_registro ===
                                    "PROPOSTA_IA" && (
                                    <span className="rounded-full bg-indigo-50 px-2 py-1 text-xs text-indigo-700">
                                      Sugestão da IA
                                    </span>
                                  )}
                                  <span className="rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-700">
                                    {fato.locus || "CORINGA"}
                                  </span>
                                  <span className="rounded-full bg-blue-50 px-2 py-1 text-xs text-blue-800">
                                    {fato.estado_evidencia}
                                  </span>
                                  <span
                                    className={`rounded-full px-2 py-1 text-xs ${fato.estado_conferencia === "PENDENTE" ? "bg-amber-50 text-amber-800" : "bg-emerald-50 text-emerald-800"}`}
                                  >
                                    {fato.estado_conferencia}
                                  </span>
                                </div>
                                <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-800">
                                  {formatarValorFato(fato.valor_atual)}
                                </p>
                                <p className="mt-2 text-xs text-slate-600">
                                  Origem: {fato.proveniencia}
                                  {fato.categoria ? ` · ${fato.categoria}` : ""}
                                  {fato.localizacao
                                    ? ` · ${fato.localizacao}`
                                    : ""}
                                </p>
                                {fato.valor_original !== fato.valor_atual && (
                                  <p className="mt-1 text-xs text-slate-600">
                                    Valor inicialmente registrado:{" "}
                                    {formatarValorFato(fato.valor_original)}
                                  </p>
                                )}
                                {fato.trecho_fonte && (
                                  <blockquote className="mt-3 border-l-2 border-slate-300 pl-3 text-xs leading-5 text-slate-700">
                                    {fato.trecho_fonte}
                                  </blockquote>
                                )}
                              </div>
                              {casoAberto.status !== "ENCERRADO" && (
                                <div className="flex shrink-0 flex-wrap gap-2">
                                  {fato.estado_conferencia === "PENDENTE" ? (
                                    <>
                                      <button
                                        type="button"
                                        disabled={processandoFato === fato.id}
                                        onClick={() =>
                                          void conferirFato(fato, "CONFIRMAR")
                                        }
                                        className="rounded-lg border border-emerald-300 px-3 py-2 text-xs font-medium text-emerald-800 disabled:opacity-50"
                                      >
                                        Confirmar
                                      </button>
                                      <button
                                        type="button"
                                        disabled={processandoFato === fato.id}
                                        onClick={() =>
                                          void conferirFato(fato, "CORRIGIR")
                                        }
                                        className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium text-slate-800 disabled:opacity-50"
                                      >
                                        Corrigir
                                      </button>
                                    </>
                                  ) : (
                                    <button
                                      type="button"
                                      disabled={processandoFato === fato.id}
                                      onClick={() =>
                                        void conferirFato(fato, "REABRIR")
                                      }
                                      className="rounded-lg border border-amber-300 px-3 py-2 text-xs font-medium text-amber-800 disabled:opacity-50"
                                    >
                                      Reabrir
                                    </button>
                                  )}
                                </div>
                              )}
                            </div>
                          </article>
                        ))}
                      </div>
                    )}

                    {casoAberto.status === "AGUARDANDO_CONFERENCIA" && (
                      <div className="flex justify-end border-t border-slate-200 p-5">
                        <button
                          type="button"
                          onClick={() => void concluirConferencia()}
                          className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white"
                        >
                          Concluir conferência
                        </button>
                      </div>
                    )}
                  </section>

                  <section className="rounded-xl border border-slate-200 bg-white">
                    <div className="flex flex-col gap-3 border-b border-slate-200 p-5 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <h3 className="text-sm font-semibold text-slate-900">
                          Análise jurídica assistiva
                        </h3>
                        <p className="mt-1 text-sm text-slate-600">
                          Resultado assistivo sujeito à decisão humana.
                        </p>
                      </div>
                      {["PRONTO_PARA_ANALISE", "ANALISE_DISPONIVEL"].includes(
                        casoAberto.status,
                      ) && (
                        <button
                          type="button"
                          onClick={() => void gerarAnaliseJuridica()}
                          disabled={gerandoAnalise}
                          className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
                        >
                          {gerandoAnalise
                            ? "Analisando..."
                            : analisesJuridicas.length
                              ? "Gerar nova análise"
                              : "Gerar análise"}
                        </button>
                      )}
                    </div>

                    {analisesJuridicas.length === 0 ? (
                      <p className="p-5 text-sm text-slate-600">
                        Nenhuma análise jurídica foi gerada para o estado
                        factual atual.
                      </p>
                    ) : (
                      <div className="space-y-4 p-5">
                        {analisesJuridicas.slice(0, 3).map((analise) => (
                          <article
                            key={analise.id}
                            className="rounded-lg border border-slate-200 p-4"
                          >
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className="text-sm font-semibold text-slate-900">
                                Versão factual {analise.versao_numero}
                              </p>
                              <span className="rounded-full bg-amber-50 px-2 py-1 text-xs text-amber-800">
                                {analise.status_evidencia.replaceAll("_", " ")}
                              </span>
                            </div>
                            <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-800">
                              {analise.resumo}
                            </p>
                            {(
                              [
                                "Requisitos",
                                "Impedimentos",
                                "Pendências",
                              ] as const
                            ).map((titulo, indice) => {
                              const itens = [
                                analise.requisitos,
                                analise.impedimentos,
                                analise.pendencias,
                              ][indice];
                              return itens.length ? (
                                <div key={titulo} className="mt-4">
                                  <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                                    {titulo}
                                  </h4>
                                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-700">
                                    {itens.map((item, posicao) => (
                                      <li key={posicao}>
                                        {formatarValorFato(item)}
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              ) : null;
                            })}
                            <details className="mt-4 rounded-lg bg-slate-50 p-3">
                              <summary className="cursor-pointer text-sm font-medium text-slate-700">
                                Fontes preservadas ({analise.fontes.length})
                              </summary>
                              <div className="mt-3 space-y-3">
                                {analise.fontes.map((fonte, posicao) => (
                                  <blockquote
                                    key={posicao}
                                    className="border-l-2 border-slate-300 pl-3 text-xs leading-5 text-slate-700"
                                  >
                                    <strong>
                                      {String(fonte.titulo || "Fonte")}
                                    </strong>
                                    {fonte.artigo
                                      ? ` · ${String(fonte.artigo)}`
                                      : ""}
                                    <br />
                                    {String(fonte.trecho || "")}
                                  </blockquote>
                                ))}
                              </div>
                            </details>
                          </article>
                        ))}
                      </div>
                    )}

                    {isAdmin &&
                      casoAberto.status === "ANALISE_DISPONIVEL" &&
                      analisesJuridicas[0] && (
                        <div className="border-t border-slate-200 bg-slate-50 p-5">
                          <h4 className="text-sm font-semibold text-slate-900">
                            Decisão do responsável
                          </h4>
                          <div className="mt-4 grid gap-3">
                            <select
                              value={decisaoTipo}
                              onChange={(evento) =>
                                setDecisaoTipo(evento.target.value)
                              }
                              className="rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-800"
                            >
                              <option value="APROVAR">Aprovar</option>
                              <option value="EXIGENCIA">
                                Formular exigência
                              </option>
                              <option value="RECUSAR">Recusar</option>
                              <option value="OUTRA">Outra decisão</option>
                            </select>
                            <textarea
                              value={decisaoTexto}
                              onChange={(evento) =>
                                setDecisaoTexto(evento.target.value)
                              }
                              placeholder="Registre a decisão humana"
                              rows={4}
                              className="rounded-lg border border-slate-300 bg-white p-3 text-sm text-slate-900"
                            />
                            <textarea
                              value={decisaoFundamentacao}
                              onChange={(evento) =>
                                setDecisaoFundamentacao(evento.target.value)
                              }
                              placeholder="Fundamentação ou observações (opcional)"
                              rows={3}
                              className="rounded-lg border border-slate-300 bg-white p-3 text-sm text-slate-900"
                            />
                            <button
                              type="button"
                              onClick={() => void registrarDecisaoHumana()}
                              disabled={salvandoDecisao || !decisaoTexto.trim()}
                              className="justify-self-end rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
                            >
                              {salvandoDecisao
                                ? "Registrando..."
                                : "Registrar decisão"}
                            </button>
                          </div>
                        </div>
                      )}

                    {decisoes.length > 0 && (
                      <div className="border-t border-slate-200 p-5">
                        <h4 className="text-sm font-semibold text-slate-900">
                          Decisões registradas
                        </h4>
                        <div className="mt-3 space-y-3">
                          {decisoes.map((decisao) => (
                            <article
                              key={decisao.id}
                              className="rounded-lg border border-slate-200 p-4 text-sm text-slate-800"
                            >
                              <p className="font-semibold">
                                {decisao.decisao} ·{" "}
                                {decisao.decidido_por_nome ||
                                  "Responsável não disponível"}
                              </p>
                              <p className="mt-2 whitespace-pre-wrap leading-6">
                                {decisao.texto}
                              </p>
                              {decisao.fundamentacao && (
                                <p className="mt-2 whitespace-pre-wrap text-slate-600">
                                  {decisao.fundamentacao}
                                </p>
                              )}
                            </article>
                          ))}
                        </div>
                      </div>
                    )}
                  </section>

                  <section className="rounded-xl border border-slate-200 bg-white">
                    <div className="flex flex-col gap-4 border-b border-slate-200 p-5 md:flex-row md:items-center md:justify-between">
                      <div>
                        <div className="flex items-center gap-2">
                          <FileText size={19} className="text-slate-600" />

                          <h3 className="text-sm font-semibold text-slate-900">
                            Documentos do caso
                          </h3>
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => void atualizarDocumentos()}
                        disabled={carregandoDocumentos}
                        className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
                      >
                        <RefreshCw
                          size={15}
                          className={carregandoDocumentos ? "animate-spin" : ""}
                        />
                        Atualizar
                      </button>
                    </div>

                    {casoAberto.status !== "ENCERRADO" && (
                      <p className="border-b border-slate-200 bg-slate-50 px-5 py-3 text-xs text-slate-600">
                        Envie novos arquivos pela conversa para manter cada
                        documento vinculado à orientação dada.
                      </p>
                    )}

                    {erroDocumentos && (
                      <div className="m-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                        {erroDocumentos}
                      </div>
                    )}

                    {sucessoDocumentos && (
                      <div className="m-5 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">
                        {sucessoDocumentos}
                      </div>
                    )}

                    {carregandoDocumentos ? (
                      <div className="flex min-h-40 items-center justify-center">
                        <div className="flex items-center gap-2 text-sm text-slate-500">
                          <LoaderCircle size={17} className="animate-spin" />
                          Carregando documentos...
                        </div>
                      </div>
                    ) : documentos.length === 0 ? (
                      <div className="px-6 py-12 text-center">
                        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-slate-100 text-slate-500">
                          <FileUp size={20} />
                        </div>

                        <p className="mt-3 text-sm font-medium text-slate-800">
                          Nenhum documento adicionado
                        </p>

                        <p className="mt-1 text-sm text-slate-500">
                          Adicione os documentos apresentados para este caso.
                        </p>
                      </div>
                    ) : (
                      <div className="divide-y divide-slate-100">
                        {documentos.map((documento) => (
                          <article key={documento.id} className="p-5">
                            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                              <div className="min-w-0 flex-1">
                                <div className="flex items-start gap-3">
                                  <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-slate-100 text-slate-600">
                                    <FileText size={18} />
                                  </div>

                                  <div className="min-w-0">
                                    <p className="break-words text-sm font-semibold text-slate-900">
                                      {documento.nome_arquivo}
                                    </p>

                                    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-500">
                                      <span>
                                        {formatarTamanho(
                                          documento.tamanho_bytes,
                                        )}
                                      </span>

                                      <span>
                                        {documento.total_paginas}{" "}
                                        página(s)/bloco(s)
                                      </span>

                                      <span>
                                        Enviado em{" "}
                                        {formatarData(documento.created_at)}
                                      </span>
                                    </div>
                                  </div>
                                </div>

                                <div className="mt-3 flex flex-wrap gap-2">
                                  <span
                                    className={
                                      documento.tipo_documento
                                        ? "rounded-full border border-violet-200 bg-violet-50 px-2.5 py-1 text-xs font-medium text-violet-700"
                                        : "rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700"
                                    }
                                  >
                                    <Tag size={12} className="mr-1 inline" />

                                    {tipoDocumentoLabel(
                                      documento.tipo_documento,
                                    )}
                                  </span>

                                  <span
                                    className={
                                      documento.vinculo_ato
                                        ? "rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700"
                                        : "rounded-full border border-amber-200 bg-amber-50 px-2.5 py-1 text-xs font-medium text-amber-700"
                                    }
                                  >
                                    {vinculoAtoLabel(
                                      documento.vinculo_ato,
                                      casoAberto.tipo_ato,
                                    )}
                                  </span>
                                </div>

                                <div className="mt-2 flex flex-wrap gap-2">
                                  <span
                                    className={`rounded-full border px-2.5 py-1 text-xs font-medium ${documentoStatusClass(
                                      documento.status,
                                    )}`}
                                  >
                                    {documento.status === "PROCESSANDO" && (
                                      <LoaderCircle
                                        size={12}
                                        className="mr-1 inline animate-spin"
                                      />
                                    )}

                                    {documentoStatusLabel(documento.status)}
                                  </span>

                                  <span
                                    className={`rounded-full border px-2.5 py-1 text-xs font-medium ${segurancaClass(
                                      documento.status_seguranca,
                                    )}`}
                                  >
                                    {segurancaLabel(documento.status_seguranca)}
                                  </span>

                                  <span className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-600">
                                    {extracaoLabel(documento.situacao_extracao)}
                                  </span>

                                  <span className="rounded-full border border-indigo-200 bg-indigo-50 px-2.5 py-1 text-xs font-medium text-indigo-700">
                                    {documento.status_extracao_fatos ===
                                      "PROCESSANDO" && (
                                      <LoaderCircle
                                        size={12}
                                        className="mr-1 inline animate-spin"
                                      />
                                    )}
                                    {extracaoFatosLabel(
                                      documento.status_extracao_fatos,
                                    )}
                                  </span>
                                </div>

                                {documento.alerta_seguranca && (
                                  <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2.5 text-xs leading-5 text-amber-800">
                                    <ShieldAlert
                                      size={15}
                                      className="mt-0.5 shrink-0"
                                    />

                                    <span>{documento.alerta_seguranca}</span>
                                  </div>
                                )}

                                {documento.erro_processamento && (
                                  <div className="mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-xs leading-5 text-red-700">
                                    <AlertTriangle
                                      size={15}
                                      className="mt-0.5 shrink-0"
                                    />

                                    <span>{documento.erro_processamento}</span>
                                  </div>
                                )}

                                {documento.erro_extracao_fatos && (
                                  <div className="mt-3 flex items-start gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-xs leading-5 text-red-700">
                                    <AlertTriangle
                                      size={15}
                                      className="mt-0.5 shrink-0"
                                    />
                                    <span>{documento.erro_extracao_fatos}</span>
                                  </div>
                                )}
                              </div>

                              <div className="flex shrink-0 flex-wrap gap-2">
                                <button
                                  type="button"
                                  onClick={() => abrirClassificacao(documento)}
                                  disabled={casoAberto.status === "ENCERRADO"}
                                  className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                                >
                                  <Tag size={15} />

                                  {documento.tipo_documento &&
                                  documento.vinculo_ato
                                    ? "Classificação"
                                    : "Classificar"}
                                </button>

                                <button
                                  type="button"
                                  disabled={
                                    carregandoDocumento ||
                                    documento.status === "PROCESSANDO"
                                  }
                                  onClick={() => void abrirDocumento(documento)}
                                  className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                                >
                                  <Eye size={15} />
                                  Ver conteúdo
                                </button>

                                <button
                                  type="button"
                                  disabled={baixandoDocumento === documento.id}
                                  onClick={() =>
                                    void baixarDocumento(documento)
                                  }
                                  className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
                                >
                                  {baixandoDocumento === documento.id ? (
                                    <LoaderCircle
                                      size={15}
                                      className="animate-spin"
                                    />
                                  ) : (
                                    <Download size={15} />
                                  )}
                                  Baixar
                                </button>

                                {documento.status_seguranca === "REVISAO" &&
                                  [
                                    "EM_PREPARACAO",
                                    "AGUARDANDO_CONFERENCIA",
                                  ].includes(casoAberto.status) && (
                                    <button
                                      type="button"
                                      onClick={() =>
                                        void liberarSegurancaDocumento(
                                          documento,
                                        )
                                      }
                                      disabled={
                                        revisandoSegurancaDocumento ===
                                        documento.id
                                      }
                                      className="inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm font-medium text-amber-800 hover:bg-amber-50 disabled:opacity-50"
                                    >
                                      {revisandoSegurancaDocumento ===
                                      documento.id ? (
                                        <LoaderCircle
                                          size={15}
                                          className="animate-spin"
                                        />
                                      ) : (
                                        <ShieldAlert size={15} />
                                      )}
                                      Liberar após revisão
                                    </button>
                                  )}

                                {[
                                  "EM_PREPARACAO",
                                  "AGUARDANDO_CONFERENCIA",
                                ].includes(casoAberto.status) && (
                                  <button
                                    type="button"
                                    onClick={() =>
                                      void proporFatosDocumento(documento)
                                    }
                                    disabled={
                                      documento.status !== "PRONTO" ||
                                      documento.status_seguranca !==
                                        "LIBERADO" ||
                                      documento.situacao_extracao !==
                                        "PROCESSADO_COMPLETO" ||
                                      !documento.tipo_documento ||
                                      !documento.vinculo_ato ||
                                      documento.status_extracao_fatos ===
                                        "PRONTO" ||
                                      documento.status_extracao_fatos ===
                                        "PROCESSANDO" ||
                                      extraindoFatosDocumento === documento.id
                                    }
                                    className="inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-white px-3 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-50 disabled:cursor-not-allowed disabled:opacity-40"
                                    title="Cria propostas pendentes com o Ollama local; não confirma fatos nem produz análise jurídica."
                                  >
                                    {documento.status_extracao_fatos ===
                                      "PROCESSANDO" ||
                                    extraindoFatosDocumento === documento.id ? (
                                      <LoaderCircle
                                        size={15}
                                        className="animate-spin"
                                      />
                                    ) : (
                                      <ClipboardCheck size={15} />
                                    )}
                                    {documento.status_extracao_fatos ===
                                    "PRONTO"
                                      ? "Sugestões concluídas"
                                      : documento.status_extracao_fatos ===
                                          "PRONTO_PARCIAL"
                                        ? "Continuar sugestões"
                                        : "Sugerir fatos"}
                                  </button>
                                )}

                                {[
                                  "EM_PREPARACAO",
                                  "AGUARDANDO_CONFERENCIA",
                                ].includes(casoAberto.status) && (
                                  <button
                                    type="button"
                                    onClick={() =>
                                      void reprocessarDocumento(documento)
                                    }
                                    className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
                                  >
                                    <RefreshCw size={15} /> Reprocessar
                                  </button>
                                )}

                                {[
                                  "EM_PREPARACAO",
                                  "AGUARDANDO_CONFERENCIA",
                                ].includes(casoAberto.status) &&
                                  /\.pdf$/i.test(documento.nome_arquivo) && (
                                    <button
                                      type="button"
                                      onClick={() => {
                                        if (
                                          window.confirm(
                                            "Executar OCR em todas as páginas deste PDF? Os dados extraídos precisarão ser conferidos novamente.",
                                          )
                                        ) {
                                          void reprocessarDocumento(
                                            documento,
                                            true,
                                          );
                                        }
                                      }}
                                      className="inline-flex items-center gap-2 rounded-lg border border-indigo-200 bg-white px-3 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-50"
                                    >
                                      <ScanText size={15} /> Executar OCR
                                    </button>
                                  )}

                                {(isAdmin ||
                                  casoAberto.criado_por === user?.id) &&
                                  casoAberto.status === "EM_PREPARACAO" && (
                                    <button
                                      type="button"
                                      onClick={() =>
                                        void excluirDocumento(documento)
                                      }
                                      disabled={
                                        documento.status === "PROCESSANDO" ||
                                        excluindoDocumento === documento.id
                                      }
                                      className="inline-flex items-center gap-2 rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-40"
                                    >
                                      {excluindoDocumento === documento.id ? (
                                        <LoaderCircle
                                          size={15}
                                          className="animate-spin"
                                        />
                                      ) : (
                                        <Trash2 size={15} />
                                      )}
                                      Excluir
                                    </button>
                                  )}
                              </div>
                            </div>
                          </article>
                        ))}
                      </div>
                    )}
                  </section>
                </div>
              </details>

              <section className="order-1 rounded-xl border border-slate-200 bg-white">
                <div className="border-b border-slate-200 p-5">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <h3 className="text-sm font-semibold text-slate-900">
                        Conversa do processo
                      </h3>
                      <p className="mt-1 text-xs text-slate-600">
                        Envie vários documentos de uma vez e indique a quem cada
                        um pertence. A análise e as próximas perguntas ficam
                        nesta conversa.
                      </p>
                      <p className="mt-1 text-xs text-amber-800">
                        A triagem da IA exige conferência dos documentos
                        originais e não decide a lavratura.
                      </p>
                    </div>
                  </div>
                </div>
                {documentos.length > 0 && (
                  <div className="border-b border-slate-200 bg-slate-50 px-5 py-3">
                    <p className="mb-2 text-xs font-semibold text-slate-700">
                      Documentos deste caso
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {documentos.map((documento) => (
                        <button
                          key={documento.id}
                          type="button"
                          onClick={() => void abrirDocumento(documento)}
                          className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-left text-xs text-slate-700 hover:border-slate-400"
                        >
                          <span className="font-medium">
                            {documento.nome_arquivo}
                          </span>
                          <span className="ml-2 text-slate-500">
                            {tipoDocumentoLabel(documento.tipo_documento)} ·{" "}
                            {vinculoAtoLabel(
                              documento.vinculo_ato,
                              casoAberto.tipo_ato,
                            )}{" "}
                            · {documentoStatusLabel(documento.status)}
                          </span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
                {tarefasCaso.some((tarefa) =>
                  ["PENDENTE", "PROCESSANDO"].includes(tarefa.status),
                ) && (
                  <div
                    role="status"
                    className="flex items-center gap-2 border-b border-slate-200 bg-slate-50 px-5 py-3 text-xs text-slate-600"
                  >
                    <LoaderCircle size={14} className="animate-spin" />
                    Estou analisando os documentos. A resposta aparecerá nesta
                    conversa.
                  </div>
                )}
                <div className="max-h-[min(60vh,48rem)] min-h-64 space-y-3 overflow-y-auto p-5">
                  {temMensagensAnteriores && (
                    <button
                      type="button"
                      onClick={() => void carregarMensagensAnteriores()}
                      className="mb-2 rounded-lg border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-50"
                    >
                      Carregar mensagens anteriores
                    </button>
                  )}
                  {carregandoWorkspace ? (
                    <p className="text-sm text-slate-500">
                      Carregando histórico do caso...
                    </p>
                  ) : mensagensCaso.length === 0 ? (
                    <p className="rounded-lg bg-slate-50 px-4 py-5 text-sm leading-6 text-slate-600">
                      Esta conversa ainda está vazia. Envie um documento com o
                      tipo e a parte relacionada, ou faça uma pergunta sobre o
                      processo. A descrição inicial do caso também será
                      considerada pela IA.
                    </p>
                  ) : (
                    mensagensCaso.map((mensagem) => (
                      <div
                        key={mensagem.id}
                        className={`rounded-lg px-3 py-2 text-sm ${
                          mensagem.papel === "USUARIO"
                            ? "ml-8 bg-slate-900 text-white"
                            : "mr-8 bg-slate-100 text-slate-800"
                        }`}
                      >
                        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide opacity-70">
                          {mensagem.papel === "USUARIO"
                            ? "Usuário"
                            : mensagem.papel}
                        </p>
                        <p className="whitespace-pre-wrap leading-5">
                          {mensagem.conteudo}
                        </p>
                      </div>
                    ))
                  )}
                </div>
                {casoAberto.status !== "ENCERRADO" && (
                  <div className="space-y-3 border-t border-slate-200 p-5">
                    {erroDocumentos && (
                      <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                        {erroDocumentos}
                      </p>
                    )}
                    <input
                      ref={inputArquivoRef}
                      type="file"
                      multiple
                      accept=".pdf,.docx,.txt,.jpg,.jpeg,.png"
                      onChange={(evento) => {
                        const novosArquivos = Array.from(
                          evento.target.files || [],
                        ).map((arquivo) => ({
                          arquivo,
                          tipo_documento: "",
                          vinculo_ato: "",
                        }));
                        setArquivosSelecionados((atuais) => [
                          ...atuais,
                          ...novosArquivos,
                        ]);
                        evento.target.value = "";
                      }}
                      className="sr-only"
                      aria-label="Anexar documento ao caso"
                    />
                    {arquivosSelecionados.length > 0 && (
                      <div className="max-h-80 space-y-3 overflow-y-auto rounded-lg border border-slate-200 p-3">
                        {arquivosSelecionados.map((item, indice) => (
                          <div
                            key={`${item.arquivo.name}-${item.arquivo.lastModified}-${indice}`}
                            className="space-y-2 rounded-md bg-slate-50 p-3"
                          >
                            <div className="flex items-start justify-between gap-3">
                              <p className="min-w-0 break-all text-xs font-medium text-slate-700">
                                {item.arquivo.name} ·{" "}
                                {formatarTamanho(item.arquivo.size)}
                              </p>
                              <button
                                type="button"
                                onClick={() =>
                                  setArquivosSelecionados((atuais) =>
                                    atuais.filter(
                                      (_, posicao) => posicao !== indice,
                                    ),
                                  )
                                }
                                className="shrink-0 text-xs text-red-700 hover:underline"
                                aria-label={`Remover ${item.arquivo.name}`}
                              >
                                Remover
                              </button>
                            </div>
                            <div className="grid gap-2 md:grid-cols-2">
                              <select
                                value={item.tipo_documento}
                                onChange={(evento) =>
                                  alterarTipoDocumentoUpload(
                                    indice,
                                    evento.target.value,
                                  )
                                }
                                aria-label={`Tipo de ${item.arquivo.name}`}
                                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700"
                              >
                                <option value="">Tipo do documento...</option>
                                {TIPOS_DOCUMENTO.map((tipo) => (
                                  <option key={tipo.id} value={tipo.id}>
                                    {tipo.label}
                                  </option>
                                ))}
                              </select>
                              <select
                                value={item.vinculo_ato}
                                onChange={(evento) =>
                                  alterarVinculoDocumentoUpload(
                                    indice,
                                    evento.target.value,
                                  )
                                }
                                aria-label={`Vínculo de ${item.arquivo.name}`}
                                className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-700"
                              >
                                <option value="">Relacionado a...</option>
                                {VINCULOS_ATO.map((vinculo) => (
                                  <option key={vinculo} value={vinculo}>
                                    {vinculoAtoLabel(
                                      vinculo,
                                      casoAberto.tipo_ato,
                                    )}
                                  </option>
                                ))}
                              </select>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="flex items-end gap-2">
                      <button
                        type="button"
                        onClick={() => inputArquivoRef.current?.click()}
                        disabled={enviandoMensagemCaso || enviandoArquivo}
                        className="inline-flex shrink-0 items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-50"
                      >
                        <FileUp size={17} />
                        Anexar
                      </button>
                      <textarea
                        value={mensagemCaso}
                        onChange={(evento) =>
                          setMensagemCaso(evento.target.value)
                        }
                        onKeyDown={(evento) => {
                          if (evento.key === "Enter" && !evento.shiftKey) {
                            evento.preventDefault();
                            void enviarMensagemCaso();
                          }
                        }}
                        rows={3}
                        placeholder={
                          arquivosSelecionados.length > 0
                            ? "O que você quer conferir? (opcional)"
                            : "Faça uma pergunta ou envie um complemento sobre o caso"
                        }
                        className="min-w-0 flex-1 resize-y rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
                      />
                      <button
                        type="button"
                        onClick={() => void enviarMensagemCaso()}
                        disabled={
                          enviandoMensagemCaso ||
                          (arquivosSelecionados.length > 0
                            ? arquivosSelecionados.some(
                                (item) =>
                                  !item.tipo_documento || !item.vinculo_ato,
                              )
                            : !mensagemCaso.trim())
                        }
                        className="inline-flex items-center gap-2 self-end rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
                      >
                        {enviandoMensagemCaso || enviandoArquivo ? (
                          <LoaderCircle size={16} className="animate-spin" />
                        ) : (
                          <Upload size={16} />
                        )}
                        {arquivosSelecionados.length > 0
                          ? `Analisar ${arquivosSelecionados.length} documento${arquivosSelecionados.length === 1 ? "" : "s"}`
                          : "Enviar"}
                      </button>
                    </div>
                    <p className="text-xs text-slate-500">
                      Você pode anexar vários arquivos. Para cada um, informe o
                      tipo e se pertence ao vendedor, ao comprador ou ao imóvel.
                      PDF, DOCX, TXT, JPG, JPEG ou PNG até 50 MB cada.
                    </p>
                  </div>
                )}
              </section>

              <div className="order-3 flex flex-col gap-4 border-t border-slate-200 pt-5 sm:flex-row sm:items-center sm:justify-between">
                <div className="text-xs text-slate-500">
                  Criado em {formatarData(casoAberto.created_at)}
                  {" · "}
                  Atualizado em {formatarData(casoAberto.updated_at)}
                </div>

                <div className="flex flex-wrap justify-end gap-2">
                  {(isAdmin || casoAberto.criado_por === user?.id) &&
                    casoAberto.status === "EM_PREPARACAO" && (
                      <button
                        type="button"
                        onClick={() => void excluirCaso()}
                        disabled={excluindoCaso}
                        className="inline-flex items-center gap-2 rounded-lg border border-red-200 bg-white px-3 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50 disabled:opacity-50"
                      >
                        {excluindoCaso ? (
                          <LoaderCircle size={15} className="animate-spin" />
                        ) : (
                          <Trash2 size={15} />
                        )}
                        Excluir caso
                      </button>
                    )}

                  {casoAberto.status !== "ENCERRADO" && (
                    <button
                      type="button"
                      onClick={() => editarCaso(casoAberto)}
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                    >
                      <Pencil size={15} />
                      Editar caso
                    </button>
                  )}

                  {casoAberto.status === "ENCERRADO" && (
                    <button
                      type="button"
                      onClick={() => void reabrirCaso()}
                      disabled={limpandoCaso}
                      className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
                    >
                      {limpandoCaso && (
                        <LoaderCircle size={15} className="animate-spin" />
                      )}
                      Reabrir caso
                    </button>
                  )}
                  {casoAberto.status !== "ENCERRADO" && (
                    <button
                      type="button"
                      onClick={() => void concluirCaso()}
                      disabled={limpandoCaso}
                      className="inline-flex items-center gap-2 rounded-lg border border-emerald-300 bg-white px-3 py-2 text-sm font-medium text-emerald-800 transition hover:bg-emerald-50 disabled:opacity-50"
                    >
                      {limpandoCaso && (
                        <LoaderCircle size={15} className="animate-spin" />
                      )}
                      Concluir caso
                    </button>
                  )}
                  {casoAberto.status !== "ENCERRADO" &&
                    (isAdmin || casoAberto.criado_por === user?.id) && (
                      <button
                        type="button"
                        onClick={() => void concluirEApagarCaso()}
                        disabled={limpandoCaso}
                        className="inline-flex items-center gap-2 rounded-lg border border-amber-300 bg-white px-3 py-2 text-sm font-medium text-amber-800 transition hover:bg-amber-50 disabled:opacity-50"
                      >
                        {limpandoCaso ? (
                          <LoaderCircle size={15} className="animate-spin" />
                        ) : (
                          <Trash2 size={15} />
                        )}
                        Concluir e apagar arquivos
                      </button>
                    )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {mostrarFato && casoAberto && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/60 p-4">
          <div className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white shadow-2xl">
            <div className="flex items-start justify-between border-b border-slate-200 px-6 py-5">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">
                  Registrar fato
                </h2>
              </div>
              <button
                type="button"
                onClick={() => setMostrarFato(false)}
                aria-label="Fechar"
                className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"
              >
                <X size={20} />
              </button>
            </div>
            <form onSubmit={salvarFato} className="space-y-5 p-6">
              <div>
                <label className="text-sm font-medium text-slate-800">
                  Campo
                  <input
                    required
                    maxLength={150}
                    value={fatoForm.campo}
                    onChange={(e) =>
                      setFatoForm({ ...fatoForm, campo: e.target.value })
                    }
                    placeholder="Ex.: estado civil"
                    className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal"
                  />
                </label>
                <label className="text-sm font-medium text-slate-800">
                  Condição da evidência
                  <select
                    value={fatoForm.estado_evidencia}
                    onChange={(e) =>
                      setFatoForm({
                        ...fatoForm,
                        estado_evidencia: e.target.value,
                      })
                    }
                    className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 font-normal"
                  >
                    <option value="ENCONTRADO">Encontrado</option>
                    <option value="AUSENTE">Ausência informacional</option>
                    <option value="INCERTO">Incerto</option>
                    <option value="CONFLITANTE">Conflitante</option>
                  </select>
                </label>
              </div>
              <label className="block text-sm font-medium text-slate-800">
                Valor ou descrição
                <textarea
                  rows={3}
                  value={fatoForm.valor}
                  onChange={(e) =>
                    setFatoForm({ ...fatoForm, valor: e.target.value })
                  }
                  className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal"
                />
              </label>
              <div className="grid gap-4 md:grid-cols-2">
                <label className="text-sm font-medium text-slate-800">
                  Proveniência
                  <select
                    value={fatoForm.proveniencia}
                    onChange={(e) =>
                      setFatoForm({
                        ...fatoForm,
                        proveniencia: e.target.value,
                        estado_evidencia:
                          e.target.value === "INFERIDA"
                            ? "INCERTO"
                            : fatoForm.estado_evidencia,
                        caso_documento_id:
                          e.target.value === "DOCUMENTAL"
                            ? fatoForm.caso_documento_id
                            : "",
                        pagina:
                          e.target.value === "DOCUMENTAL"
                            ? fatoForm.pagina
                            : "",
                      })
                    }
                    className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 font-normal"
                  >
                    <option value="DECLARADA">Declarada</option>
                    <option value="DOCUMENTAL">Documental</option>
                    <option value="OBSERVADA">Observada</option>
                    <option value="INFERIDA">Inferida</option>
                  </select>
                </label>
                {fatoForm.proveniencia === "DOCUMENTAL" && (
                  <label className="text-sm font-medium text-slate-800">
                    Documento de origem
                    <select
                      required
                      value={fatoForm.caso_documento_id}
                      onChange={(e) =>
                        setFatoForm({
                          ...fatoForm,
                          caso_documento_id: e.target.value,
                        })
                      }
                      className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 font-normal"
                    >
                      <option value="">Selecione...</option>
                      {documentos.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.nome_arquivo}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
                {fatoForm.proveniencia === "DOCUMENTAL" && (
                  <label className="text-sm font-medium text-slate-800">
                    Página ou bloco
                    <input
                      type="number"
                      min={1}
                      value={fatoForm.pagina}
                      onChange={(e) =>
                        setFatoForm({ ...fatoForm, pagina: e.target.value })
                      }
                      className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal"
                    />
                  </label>
                )}
                <label className="text-sm font-medium text-slate-800">
                  Localização
                  <input
                    maxLength={200}
                    value={fatoForm.localizacao}
                    onChange={(e) =>
                      setFatoForm({ ...fatoForm, localizacao: e.target.value })
                    }
                    placeholder="Ex.: parágrafo ou seção"
                    className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal"
                  />
                </label>
              </div>
              <label className="block text-sm font-medium text-slate-800">
                Trecho de origem
                <textarea
                  rows={3}
                  maxLength={20000}
                  value={fatoForm.trecho_fonte}
                  onChange={(e) =>
                    setFatoForm({ ...fatoForm, trecho_fonte: e.target.value })
                  }
                  className="mt-2 w-full rounded-lg border border-slate-300 px-3 py-2.5 font-normal"
                />
              </label>
              {erroFatos && (
                <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
                  {erroFatos}
                </div>
              )}
              <div className="flex justify-end gap-3 border-t border-slate-200 pt-5">
                <button
                  type="button"
                  onClick={() => setMostrarFato(false)}
                  className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={salvandoFato}
                  className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
                >
                  {salvandoFato ? "Salvando..." : "Registrar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {documentoAberto && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/60 p-4">
          <div className="max-h-[92vh] w-full max-w-5xl overflow-y-auto rounded-2xl bg-white shadow-2xl">
            <div className="sticky top-0 z-10 flex items-start justify-between border-b border-slate-200 bg-white px-6 py-5">
              <div className="min-w-0 pr-4">
                <div className="flex items-center gap-2">
                  <FileText size={19} className="shrink-0 text-slate-600" />

                  <h2 className="break-words text-lg font-semibold text-slate-900">
                    {documentoAberto.nome_arquivo}
                  </h2>
                </div>
              </div>

              <button
                type="button"
                onClick={() => setDocumentoAberto(null)}
                className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100"
                aria-label="Fechar documento"
              >
                <X size={20} />
              </button>
            </div>

            <div className="space-y-5 p-6">
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                <Info
                  label="Tipo documental"
                  valor={tipoDocumentoLabel(documentoAberto.tipo_documento)}
                />

                <Info
                  label="Relacionado a"
                  valor={vinculoAtoLabel(
                    documentoAberto.vinculo_ato,
                    casoAberto?.tipo_ato || null,
                  )}
                />

                <Info
                  label="Processamento"
                  valor={documentoStatusLabel(documentoAberto.status)}
                />

                <Info
                  label="Extração"
                  valor={extracaoLabel(documentoAberto.situacao_extracao)}
                />

                <Info
                  label="Segurança"
                  valor={segurancaLabel(documentoAberto.status_seguranca)}
                />

                <Info
                  label="Páginas/blocos"
                  valor={String(documentoAberto.total_paginas)}
                />

                <Info
                  label="Organização factual"
                  valor={extracaoFatosLabel(
                    documentoAberto.status_extracao_fatos,
                  )}
                />
              </div>

              {documentoAberto.alerta_seguranca && (
                <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm leading-6 text-amber-800">
                  <ShieldAlert size={18} className="mt-0.5 shrink-0" />

                  <div>
                    <p className="font-medium">Revisão de segurança</p>

                    <p className="mt-1">{documentoAberto.alerta_seguranca}</p>
                  </div>
                </div>
              )}

              <div className="flex items-start gap-3 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm leading-6 text-blue-800">
                <CheckCircle2 size={18} className="mt-0.5 shrink-0" />

                <p>
                  O texto abaixo é uma extração automática para auxiliar a
                  organização do caso. A classificação informada pelo usuário
                  também é apenas contexto operacional. Informações relevantes
                  devem ser conferidas no documento original.
                </p>
              </div>

              {documentoAberto.paginas.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-300 bg-slate-50 px-5 py-10 text-center">
                  <p className="text-sm font-medium text-slate-700">
                    Nenhum texto extraído
                  </p>

                  <p className="mt-1 text-sm text-slate-500">
                    Confira a situação de extração do documento.
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {documentoAberto.paginas.map((paginaDocumento) => (
                    <section
                      key={paginaDocumento.id}
                      className="overflow-hidden rounded-xl border border-slate-200"
                    >
                      <div className="flex flex-col gap-2 border-b border-slate-200 bg-slate-50 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                        <div>
                          <p className="text-sm font-semibold text-slate-800">
                            {paginaDocumento.localizacao ||
                              `Página ${paginaDocumento.pagina}`}
                          </p>

                          {!paginaDocumento.pagina_confiavel && (
                            <p className="mt-0.5 text-xs text-slate-500">
                              Localização lógica; o formato original não possui
                              paginação física confiável.
                            </p>
                          )}
                        </div>

                        <div className="flex flex-wrap gap-2">
                          <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600">
                            {paginaDocumento.metodo_extracao}
                          </span>

                          <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600">
                            {paginaDocumento.situacao_extracao}
                          </span>
                        </div>
                      </div>

                      <div className="grid gap-4 p-4 lg:grid-cols-[minmax(0,1fr)_minmax(280px,0.65fr)]">
                        <div>
                          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                            Texto extraído
                          </p>
                          {paginaDocumento.conteudo ? (
                            <pre className="max-h-[34rem] overflow-y-auto whitespace-pre-wrap break-words rounded-lg bg-slate-50 p-3 font-sans text-sm leading-7 text-slate-700">
                              {paginaDocumento.conteudo}
                            </pre>
                          ) : (
                            <p className="text-sm italic text-slate-500">
                              Nenhum texto foi extraído desta página/bloco.
                            </p>
                          )}
                        </div>

                        <div>
                          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
                            Fatos vinculados
                          </p>
                          {fatos.filter(
                            (fato) =>
                              fato.caso_documento_id === documentoAberto.id &&
                              fato.pagina === paginaDocumento.pagina,
                          ).length === 0 ? (
                            <div className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500">
                              Nenhum fato foi proposto ou registrado para esta
                              localização.
                            </div>
                          ) : (
                            <div className="space-y-3">
                              {fatos
                                .filter(
                                  (fato) =>
                                    fato.caso_documento_id ===
                                      documentoAberto.id &&
                                    fato.pagina === paginaDocumento.pagina,
                                )
                                .map((fato) => (
                                  <article
                                    key={fato.id}
                                    className="rounded-lg border border-slate-200 p-3"
                                  >
                                    <div className="flex flex-wrap items-center gap-2">
                                      <p className="text-sm font-semibold text-slate-900">
                                        {fato.campo}
                                      </p>
                                      {fato.contexto?.origem_registro ===
                                        "PROPOSTA_IA" && (
                                        <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-[11px] font-medium text-indigo-700">
                                          Sugestão da IA
                                        </span>
                                      )}
                                      <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[11px] text-amber-800">
                                        {fato.estado_conferencia}
                                      </span>
                                    </div>
                                    <p className="mt-2 text-sm text-slate-800">
                                      {formatarValorFato(fato.valor_atual)}
                                    </p>
                                    {fato.trecho_fonte && (
                                      <blockquote className="mt-2 border-l-2 border-indigo-200 pl-2 text-xs leading-5 text-slate-600">
                                        {fato.trecho_fonte}
                                      </blockquote>
                                    )}
                                    {fato.estado_conferencia === "PENDENTE" &&
                                      casoAberto?.status !== "ENCERRADO" && (
                                        <div className="mt-3 flex gap-2">
                                          <button
                                            type="button"
                                            onClick={() =>
                                              void conferirFato(
                                                fato,
                                                "CONFIRMAR",
                                              )
                                            }
                                            disabled={
                                              processandoFato === fato.id
                                            }
                                            className="rounded-md border border-emerald-300 px-2.5 py-1.5 text-xs font-medium text-emerald-800 disabled:opacity-50"
                                          >
                                            Confirmar
                                          </button>
                                          <button
                                            type="button"
                                            onClick={() =>
                                              void conferirFato(
                                                fato,
                                                "CORRIGIR",
                                              )
                                            }
                                            disabled={
                                              processandoFato === fato.id
                                            }
                                            className="rounded-md border border-slate-300 px-2.5 py-1.5 text-xs font-medium text-slate-800 disabled:opacity-50"
                                          >
                                            Corrigir
                                          </button>
                                        </div>
                                      )}
                                  </article>
                                ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </section>
                  ))}
                </div>
              )}

              <div className="flex flex-col gap-3 border-t border-slate-200 pt-5 sm:flex-row sm:items-center sm:justify-between">
                <p className="text-xs text-slate-500">
                  Processado em{" "}
                  {formatarData(documentoAberto.processado_em) ||
                    "ainda não concluído"}
                </p>

                <button
                  type="button"
                  onClick={() => void baixarDocumento(documentoAberto)}
                  disabled={baixandoDocumento === documentoAberto.id}
                  className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
                >
                  {baixandoDocumento === documentoAberto.id ? (
                    <LoaderCircle size={16} className="animate-spin" />
                  ) : (
                    <Download size={16} />
                  )}
                  Baixar original
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {documentoClassificando && (
        <div className="fixed inset-0 z-[70] flex items-center justify-center bg-slate-950/60 p-4">
          <div className="w-full max-w-xl rounded-2xl bg-white shadow-2xl">
            <div className="flex items-start justify-between border-b border-slate-200 px-6 py-5">
              <div>
                <div className="flex items-center gap-2">
                  <Tag size={18} className="text-slate-600" />

                  <h2 className="text-lg font-semibold text-slate-900">
                    Classificar documento
                  </h2>
                </div>

                <p className="mt-2 break-words text-sm text-slate-500">
                  {documentoClassificando.nome_arquivo}
                </p>
              </div>

              <button
                type="button"
                onClick={() => setDocumentoClassificando(null)}
                className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100"
                aria-label="Fechar classificação"
              >
                <X size={20} />
              </button>
            </div>

            <div className="space-y-5 p-6">
              <div>
                <label className="text-sm font-medium text-slate-800">
                  Tipo do documento
                </label>

                <select
                  value={classificacaoForm.tipo_documento}
                  onChange={(evento) =>
                    alterarTipoClassificacao(evento.target.value)
                  }
                  className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                >
                  <option value="">Selecione...</option>

                  {TIPOS_DOCUMENTO.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-sm font-medium text-slate-800">
                  Relacionado a
                </label>

                <select
                  value={classificacaoForm.vinculo_ato}
                  onChange={(evento) =>
                    setClassificacaoForm((atual) => ({
                      ...atual,
                      vinculo_ato: evento.target.value,
                    }))
                  }
                  className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-700 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                >
                  <option value="">Selecione...</option>

                  {VINCULOS_ATO.map((item) => (
                    <option key={item} value={item}>
                      {vinculoAtoLabel(item, casoAberto?.tipo_ato || null)}
                    </option>
                  ))}
                </select>
              </div>

              <div className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm leading-6 text-blue-800">
                Esta classificação auxilia a organização do caso. Ela não
                confirma, por si só, que o documento efetivamente pertence à
                parte selecionada.
              </div>

              <div className="flex justify-end gap-3 border-t border-slate-200 pt-5">
                <button
                  type="button"
                  onClick={() => setDocumentoClassificando(null)}
                  className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50"
                >
                  Cancelar
                </button>

                <button
                  type="button"
                  onClick={() => void salvarClassificacao()}
                  disabled={
                    salvandoClassificacao ||
                    !classificacaoForm.tipo_documento ||
                    !classificacaoForm.vinculo_ato
                  }
                  className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
                >
                  {salvandoClassificacao && (
                    <LoaderCircle size={16} className="animate-spin" />
                  )}
                  Salvar classificação
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function Indicador({
  icone,
  texto,
  destaque = false,
  alerta = false,
}: {
  icone: React.ReactNode;
  texto: string;
  destaque?: boolean;
  alerta?: boolean;
}) {
  let classe = "border-slate-200 bg-slate-50 text-slate-600";

  if (destaque) {
    classe = "border-amber-200 bg-amber-50 text-amber-700";
  }

  if (alerta) {
    classe = "border-red-200 bg-red-50 text-red-700";
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${classe}`}
    >
      {icone}
      {texto}
    </span>
  );
}

function Info({ label, valor }: { label: string; valor: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </p>

      <p className="mt-1 break-words text-sm font-medium text-slate-800">
        {valor}
      </p>
    </div>
  );
}

function ResumoCard({
  titulo,
  valor,
  alerta = false,
}: {
  titulo: string;
  valor: number;
  alerta?: boolean;
}) {
  return (
    <div
      className={
        alerta
          ? "rounded-lg border border-red-200 bg-red-50 p-4"
          : "rounded-lg border border-slate-200 bg-slate-50 p-4"
      }
    >
      <p
        className={
          alerta
            ? "text-xs font-medium text-red-600"
            : "text-xs font-medium text-slate-500"
        }
      >
        {titulo}
      </p>

      <p
        className={
          alerta
            ? "mt-1 text-xl font-semibold text-red-700"
            : "mt-1 text-xl font-semibold text-slate-900"
        }
      >
        {valor}
      </p>
    </div>
  );
}
