"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  Archive,
  CheckCircle2,
  Download,
  Pencil,
  RefreshCw,
  ScanText,
  Search,
  ShieldCheck,
  Trash2,
  Upload,
  XCircle,
} from "lucide-react";

import { useAuth } from "../../../context/AuthContext";
import { apiFetch } from "../../../lib/api";

type Documento = {
  id: string;
  titulo: string;
  descricao: string | null;
  tipo: string;
  tipo_ato: string | null;
  situacao: "RASCUNHO" | "APROVADO" | "REVOGADO" | "ARQUIVADO";
  orgao_origem: string | null;
  versao: string | null;
  jurisdicao: string | null;
  vigencia_inicio: string | null;
  vigencia_fim: string | null;
  observacoes: string | null;
  nome_arquivo: string;
  status_seguranca: "PENDENTE" | "LIBERADO" | "REVISAO";
  alerta_seguranca: string | null;
  ativo: boolean;
  status: "PROCESSANDO" | "PRONTO" | "ERRO";
  erro_processamento: string | null;
  total_paginas: number;
  total_chunks: number;
  situacao_extracao: string;
  diagnostico_extracao: {
    partes_originais: number;
    partes_com_texto: number;
    partes_necessitam_ocr: number;
    partes_vazias: number;
    partes_com_erro: number;
    partes_com_ocr?: number;
    partes_pendentes: number[];
    caracteres_extraidos: number;
    avisos: string[];
  } | null;
  updated_at: string;
};

type PaginaDocumentos = {
  items: Documento[];
  total: number;
  pagina: number;
  por_pagina: number;
  total_paginas: number;
};

const categorias = [
  ["NORMA", "Norma"],
  ["LEGISLACAO", "Legislação"],
  ["ENTENDIMENTO", "Entendimento"],
  ["PROCEDIMENTO", "Procedimento"],
  ["MANUAL", "Manual"],
  ["MODELO_MINUTA", "Modelo de minuta"],
  ["OUTRO", "Outro"],
] as const;

const categoriasUsuario = categorias.filter(
  ([id]) => id !== "ENTENDIMENTO" && id !== "MODELO_MINUTA",
);

const abas = [
  ["", "Todos"],
  ["NORMAS_LEGISLACAO", "Normas e legislação"],
  ["ENTENDIMENTOS", "Entendimentos"],
  ["PROCEDIMENTOS_MANUAIS", "Procedimentos e manuais"],
  ["MODELOS_MINUTA", "Modelos de minuta"],
  ["RASCUNHOS", "Rascunhos"],
  ["INATIVOS", "Revogados ou arquivados"],
] as const;

const categoriaLabel = (valor: string) =>
  categorias.find(([id]) => id === valor)?.[1] || valor;

const extracoes: Record<string, string> = {
  PENDENTE_VERIFICACAO: "Verificação pendente",
  PROCESSADO_COMPLETO: "Extração textual completa",
  EXTRACAO_PARCIAL: "Extração parcial",
  NECESSITA_OCR: "Necessita OCR",
  SEM_TEXTO: "Sem texto",
  ERRO_PROCESSAMENTO: "Falha na extração",
};

function DiagnosticoExtracao({ documento }: { documento: Documento }) {
  const resumo = documento.diagnostico_extracao;

  const completo = documento.situacao_extracao === "PROCESSADO_COMPLETO";

  const unidade = documento.nome_arquivo.toLowerCase().endsWith(".pdf")
    ? "páginas"
    : "blocos lógicos";

  return (
    <div className="mt-2 max-w-xs text-xs text-slate-700">
      <p
        className={`font-medium ${
          completo ? "text-emerald-700" : "text-amber-800"
        }`}
      >
        {extracoes[documento.situacao_extracao] || "Verificação pendente"}
      </p>

      {resumo ? (
        <>
          <p className="mt-1">
            {resumo.partes_com_texto} de {resumo.partes_originais} {unidade} com
            texto · {documento.total_chunks} trechos
          </p>

          <details className="mt-2">
            <summary className="cursor-pointer">Detalhes da extração</summary>

            <p className="mt-1">
              {resumo.partes_necessitam_ocr} precisam de OCR ·{" "}
              {resumo.partes_vazias} vazias · {resumo.partes_com_erro} com falha
            </p>

            <p>
              {resumo.caracteres_extraidos.toLocaleString("pt-BR")} caracteres
              extraídos
            </p>

            {!!resumo.partes_com_ocr && (
              <p>
                {resumo.partes_com_ocr} páginas reconhecidas por OCR local.
                Confira nomes, números e tabelas no original.
              </p>
            )}

            {resumo.partes_pendentes?.length > 0 && (
              <p>Posições pendentes: {resumo.partes_pendentes.join(", ")}</p>
            )}

            {resumo.avisos.map((aviso) => (
              <p key={aviso} className="mt-1">
                {aviso}
              </p>
            ))}
          </details>
        </>
      ) : (
        <p className="mt-1">
          {documento.total_paginas} partes armazenadas ·{" "}
          {documento.total_chunks} trechos. Total original ainda não verificado.
        </p>
      )}

      {!completo && (
        <p className="mt-1">
          Não utilizado pela IA até concluir a verificação da extração.
        </p>
      )}
    </div>
  );
}

export default function DocumentosPage() {
  const { user } = useAuth();

  const podeAdministrar = user?.role === "ADMIN";

  const podeCadastrar = podeAdministrar;

  const categoriasCadastro = podeAdministrar ? categorias : categoriasUsuario;

  const [dados, setDados] = useState<PaginaDocumentos>({
    items: [],
    total: 0,
    pagina: 1,
    por_pagina: 20,
    total_paginas: 0,
  });

  const [pagina, setPagina] = useState(1);

  const [grupo, setGrupo] = useState("");

  const [pesquisa, setPesquisa] = useState("");

  const [categoria, setCategoria] = useState("");

  const [situacao, setSituacao] = useState("");

  const [processamento, setProcessamento] = useState("");

  const [extracao, setExtracao] = useState("");

  const [filtroAto, setFiltroAto] = useState("");

  const [loading, setLoading] = useState(true);

  const [erro, setErro] = useState("");

  const [modal, setModal] = useState(false);

  const [editando, setEditando] = useState<Documento | null>(null);

  const [salvando, setSalvando] = useState(false);

  const [excluindoId, setExcluindoId] = useState<string | null>(null);

  const [arquivo, setArquivo] = useState<File | null>(null);

  const [form, setForm] = useState({
    titulo: "",
    descricao: "",
    tipo: "MANUAL",
    tipo_ato: "",
    orgao_origem: "",
    versao: "",
    jurisdicao: "",
    vigencia_inicio: "",
    vigencia_fim: "",
    observacoes: "",
  });

  const carregar = useCallback(
    async (mostrarLoading = true) => {
      if (mostrarLoading) {
        setLoading(true);
      }

      setErro("");

      const parametros = new URLSearchParams({
        pagina: String(pagina),
        por_pagina: "20",
      });

      if (grupo) {
        parametros.set("grupo", grupo);
      }

      if (pesquisa.trim()) {
        parametros.set("pesquisa", pesquisa.trim());
      }

      if (categoria) {
        parametros.set("categoria", categoria);
      }

      if (situacao) {
        parametros.set("situacao", situacao);
      }

      if (processamento) {
        parametros.set("status_processamento", processamento);
      }

      if (extracao) {
        parametros.set("situacao_extracao", extracao);
      }

      if (filtroAto) {
        parametros.set("tipo_ato", filtroAto);
      }

      try {
        const response = await apiFetch(
          `/api/documentos?${parametros.toString()}`,
        );

        if (!response) {
          setErro("Não foi possível conectar ao servidor.");
          return;
        }

        if (!response.ok) {
          const retorno = await response.json();

          setErro(
            retorno?.detail || "Não foi possível carregar os documentos.",
          );

          return;
        }

        setDados(await response.json());
      } catch {
        setErro("Não foi possível conectar ao servidor.");
      } finally {
        if (mostrarLoading) {
          setLoading(false);
        }
      }
    },
    [
      pagina,
      grupo,
      pesquisa,
      categoria,
      situacao,
      processamento,
      extracao,
      filtroAto,
    ],
  );

  useEffect(() => {
    const atraso = window.setTimeout(() => {
      void carregar();
    }, 250);

    return () => {
      window.clearTimeout(atraso);
    };
  }, [carregar]);

  useEffect(() => {
    if (!dados.items.some((item) => item.status === "PROCESSANDO")) {
      return;
    }

    const intervalo = window.setInterval(() => {
      void carregar(false);
    }, 3000);

    return () => {
      window.clearInterval(intervalo);
    };
  }, [dados.items, carregar]);

  function alterarFiltro(setter: (valor: string) => void, valor: string) {
    setter(valor);
    setPagina(1);
  }

  function novoDocumento() {
    setErro("");
    setEditando(null);
    setArquivo(null);

    setForm({
      titulo: "",
      descricao: "",
      tipo: "MANUAL",
      tipo_ato: "",
      orgao_origem: "",
      versao: "",
      jurisdicao: "",
      vigencia_inicio: "",
      vigencia_fim: "",
      observacoes: "",
    });

    setModal(true);
  }

  function editar(documento: Documento) {
    if (!podeAdministrar) {
      return;
    }

    setErro("");
    setEditando(documento);
    setArquivo(null);

    setForm({
      titulo: documento.titulo,
      descricao: documento.descricao || "",
      tipo: documento.tipo,
      tipo_ato: documento.tipo_ato || "",
      orgao_origem: documento.orgao_origem || "",
      versao: documento.versao || "",
      jurisdicao: documento.jurisdicao || "",
      vigencia_inicio: documento.vigencia_inicio || "",
      vigencia_fim: documento.vigencia_fim || "",
      observacoes: documento.observacoes || "",
    });

    setModal(true);
  }

  function fecharModal() {
    if (salvando) {
      return;
    }

    setModal(false);
    setEditando(null);
    setArquivo(null);
    setErro("");
  }

  async function salvar(evento: FormEvent) {
    evento.preventDefault();

    if (!form.titulo.trim() || (!editando && !arquivo)) {
      setErro("Informe o título e selecione o arquivo.");
      return;
    }

    if (
      !podeAdministrar &&
      (form.tipo === "ENTENDIMENTO" || form.tipo === "MODELO_MINUTA")
    ) {
      setErro("Esta categoria é exclusiva do perfil ADMIN.");
      return;
    }

    if (form.tipo === "MODELO_MINUTA" && !form.tipo_ato) {
      setErro("Informe o tipo de ato do modelo.");
      return;
    }

    setSalvando(true);
    setErro("");

    try {
      let response: Response | null;

      if (editando) {
        if (!podeAdministrar) {
          setErro("Somente o perfil ADMIN pode editar documentos.");

          return;
        }

        response = await apiFetch(`/api/documentos/${editando.id}`, {
          method: "PATCH",

          body: JSON.stringify({
            ...form,

            tipo_ato: form.tipo === "MODELO_MINUTA" ? form.tipo_ato : null,

            vigencia_inicio: form.vigencia_inicio || null,

            vigencia_fim: form.vigencia_fim || null,
          }),
        });
      } else {
        const corpo = new FormData();

        Object.entries(form).forEach(([chave, valor]) => {
          corpo.append(chave, valor);
        });

        corpo.set(
          "tipo_ato",
          form.tipo === "MODELO_MINUTA" ? form.tipo_ato : "",
        );

        corpo.append("arquivo", arquivo as File);

        response = await apiFetch("/api/documentos", {
          method: "POST",
          body: corpo,
        });
      }

      if (!response) {
        setErro("Não foi possível conectar ao servidor.");
        return;
      }

      if (!response.ok) {
        const retorno = await response.json();

        setErro(retorno?.detail || "Não foi possível salvar o documento.");

        return;
      }

      setModal(false);
      setEditando(null);
      setArquivo(null);

      await carregar();
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setSalvando(false);
    }
  }

  async function governar(documento: Documento, novaSituacao: string) {
    if (!podeAdministrar) {
      return;
    }

    setErro("");

    try {
      const response = await apiFetch(
        `/api/documentos/${documento.id}/governanca`,
        {
          method: "PATCH",

          body: JSON.stringify({
            situacao: novaSituacao,
          }),
        },
      );

      if (!response) {
        setErro("Não foi possível conectar ao servidor.");
        return;
      }

      if (!response.ok) {
        const retorno = await response.json();

        setErro(retorno?.detail || "Não foi possível alterar a situação.");

        return;
      }

      await carregar(false);
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    }
  }

  async function reprocessar(documento: Documento, forcarOcr = false) {
    if (!podeAdministrar) {
      return;
    }

    setErro("");

    try {
      const response = await apiFetch(
        `/api/documentos/${documento.id}/processar${forcarOcr ? "?forcar_ocr=true" : ""}`,
        {
          method: "POST",
        },
      );

      if (!response) {
        setErro("Não foi possível conectar ao servidor.");
        return;
      }

      if (!response.ok) {
        const retorno = await response.json();

        setErro(retorno?.detail || "Não foi possível reprocessar.");

        return;
      }

      await carregar(false);
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    }
  }

  async function baixar(documento: Documento) {
    setErro("");

    try {
      const response = await apiFetch(
        `/api/documentos/${documento.id}/download`,
      );

      if (!response) {
        setErro("Não foi possível conectar ao servidor.");
        return;
      }

      if (!response.ok) {
        const retorno = await response.json();

        setErro(retorno?.detail || "Não foi possível baixar o documento.");

        return;
      }

      const blob = await response.blob();

      const url = URL.createObjectURL(blob);

      const link = window.document.createElement("a");

      link.href = url;

      link.download = documento.nome_arquivo;

      window.document.body.appendChild(link);

      link.click();
      link.remove();

      URL.revokeObjectURL(url);
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    }
  }

  async function excluir(documento: Documento) {
    if (!podeAdministrar) {
      return;
    }

    const confirmou = window.confirm(
      `Excluir definitivamente “${documento.titulo}”?`,
    );

    if (!confirmou) {
      return;
    }

    setExcluindoId(documento.id);

    setErro("");

    try {
      const response = await apiFetch(`/api/documentos/${documento.id}`, {
        method: "DELETE",
      });

      if (!response) {
        setErro("Não foi possível conectar ao servidor.");
        return;
      }

      if (!response.ok) {
        let mensagem = "Não foi possível excluir o documento.";

        try {
          const retorno = await response.json();

          mensagem = retorno?.detail || mensagem;
        } catch {
          // Resposta sem JSON.
        }

        setErro(mensagem);

        return;
      }

      if (dados.items.length === 1 && pagina > 1) {
        setPagina((atual) => atual - 1);
      } else {
        await carregar(false);
      }
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setExcluindoId(null);
    }
  }

  async function liberarSeguranca(documento: Documento) {
    if (!podeAdministrar) {
      return;
    }

    setErro("");

    try {
      const response = await apiFetch(
        `/api/documentos/${documento.id}/seguranca`,
        {
          method: "PATCH",

          body: JSON.stringify({
            status_seguranca: "LIBERADO",
          }),
        },
      );

      if (!response) {
        setErro("Não foi possível conectar ao servidor.");
        return;
      }

      if (!response.ok) {
        const retorno = await response.json();

        setErro(
          retorno?.detail ||
            "Não foi possível concluir a revisão de segurança.",
        );

        return;
      }

      await carregar(false);
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    }
  }

  return (
    <div className="min-h-full bg-slate-100 p-6 text-slate-900 lg:p-8">
      <div className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900">Documentos</h1>
        </div>

        {podeCadastrar && (
          <button
            type="button"
            onClick={novoDocumento}
            className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-700"
          >
            <Upload size={17} />
            Novo documento
          </button>
        )}
      </div>

      <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
        {abas.map(([valor, rotulo]) => (
          <button
            key={valor}
            type="button"
            onClick={() => alterarFiltro(setGrupo, valor)}
            className={`whitespace-nowrap rounded-full px-3 py-2 text-xs font-medium ${
              grupo === valor
                ? "bg-slate-900 text-white"
                : "border border-slate-300 bg-white text-slate-700"
            }`}
          >
            {rotulo}
          </button>
        ))}
      </div>

      <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="grid gap-3 border-b border-slate-200 p-4 md:grid-cols-5">
          <label className="relative md:col-span-2">
            <Search
              size={17}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
            />

            <input
              value={pesquisa}
              onChange={(evento) =>
                alterarFiltro(setPesquisa, evento.target.value)
              }
              placeholder="Título ou nome do arquivo"
              className="w-full rounded-lg border border-slate-300 py-2.5 pl-10 pr-3 text-sm text-slate-900 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
            />
          </label>

          <select
            value={categoria}
            onChange={(evento) =>
              alterarFiltro(setCategoria, evento.target.value)
            }
            className="rounded-lg border border-slate-300 px-3 text-sm text-slate-900"
          >
            <option value="">Todas as categorias</option>

            {categorias.map(([id, nome]) => (
              <option key={id} value={id}>
                {nome}
              </option>
            ))}
          </select>

          <select
            value={situacao}
            onChange={(evento) =>
              alterarFiltro(setSituacao, evento.target.value)
            }
            className="rounded-lg border border-slate-300 px-3 text-sm text-slate-900"
          >
            <option value="">Toda governança</option>

            <option value="RASCUNHO">Rascunho</option>

            <option value="APROVADO">Aprovado</option>

            <option value="REVOGADO">Revogado</option>

            <option value="ARQUIVADO">Arquivado</option>
          </select>

          <select
            value={processamento}
            onChange={(evento) =>
              alterarFiltro(setProcessamento, evento.target.value)
            }
            className="rounded-lg border border-slate-300 px-3 text-sm text-slate-900"
          >
            <option value="">Todo processamento</option>

            <option value="PROCESSANDO">Processando</option>

            <option value="PRONTO">Pronto</option>

            <option value="ERRO">Erro</option>
          </select>

          {(categoria === "MODELO_MINUTA" || grupo === "MODELOS_MINUTA") && (
            <select
              value={filtroAto}
              onChange={(evento) =>
                alterarFiltro(setFiltroAto, evento.target.value)
              }
              className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
            >
              <option value="">Todos os atos</option>

              <option value="COMPRA_VENDA">Compra e Venda</option>

              <option value="DOACAO">Doação</option>
            </select>
          )}

          <select
            aria-label="Situação da extração"
            value={extracao}
            onChange={(evento) =>
              alterarFiltro(setExtracao, evento.target.value)
            }
            className="rounded-lg border border-slate-300 px-3 py-2 text-sm text-slate-900"
          >
            <option value="">Todas as extrações</option>

            {Object.entries(extracoes).map(([valor, rotulo]) => (
              <option key={valor} value={valor}>
                {rotulo}
              </option>
            ))}
          </select>
        </div>

        {erro && !modal && (
          <p className="m-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
            {erro}
          </p>
        )}

        {loading ? (
          <p className="p-10 text-center text-sm text-slate-500">
            Carregando documentos...
          </p>
        ) : dados.items.length === 0 ? (
          <p className="p-10 text-center text-sm text-slate-500">
            Nenhum documento encontrado.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[1000px] text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase text-slate-700">
                <tr>
                  <th className="px-5 py-3">Documento</th>

                  <th className="px-5 py-3">Classificação</th>

                  <th className="px-5 py-3">Governança</th>

                  <th className="px-5 py-3">Processamento</th>

                  <th className="px-5 py-3 text-right">Ações</th>
                </tr>
              </thead>

              <tbody>
                {dados.items.map((documento) => (
                  <tr
                    key={documento.id}
                    className="border-t border-slate-100 align-top"
                  >
                    <td className="px-5 py-4">
                      <p className="font-medium text-slate-900">
                        {documento.titulo}
                      </p>

                      <p className="mt-1 text-xs text-slate-700">
                        {documento.nome_arquivo}
                      </p>

                      <p className="mt-1 text-xs text-slate-600">
                        {documento.orgao_origem || "Origem não informada"}

                        {documento.versao
                          ? ` · versão ${documento.versao}`
                          : ""}
                      </p>
                    </td>

                    <td className="px-5 py-4">
                      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-700">
                        {categoriaLabel(documento.tipo)}
                      </span>

                      {documento.tipo_ato && (
                        <p className="mt-2 text-xs text-slate-700">
                          {documento.tipo_ato === "COMPRA_VENDA"
                            ? "Compra e Venda"
                            : "Doação"}
                        </p>
                      )}
                    </td>

                    <td className="px-5 py-4">
                      <span
                        className={`rounded-full px-2.5 py-1 text-xs font-medium ${
                          documento.situacao === "APROVADO"
                            ? "bg-emerald-50 text-emerald-700"
                            : documento.situacao === "RASCUNHO"
                              ? "bg-amber-50 text-amber-700"
                              : "bg-slate-100 text-slate-600"
                        }`}
                      >
                        {documento.situacao}
                      </span>
                    </td>

                    <td className="px-5 py-4">
                      <p className="text-xs font-medium text-slate-700">
                        {documento.status}
                      </p>

                      <DiagnosticoExtracao documento={documento} />

                      <p
                        className={`mt-2 text-xs font-medium ${
                          documento.status_seguranca === "LIBERADO"
                            ? "text-emerald-700"
                            : documento.status_seguranca === "REVISAO"
                              ? "text-amber-700"
                              : "text-slate-600"
                        }`}
                      >
                        Segurança:{" "}
                        {documento.status_seguranca === "REVISAO"
                          ? "revisão necessária"
                          : documento.status_seguranca.toLowerCase()}
                      </p>

                      {documento.alerta_seguranca && (
                        <p className="mt-1 max-w-xs text-xs text-amber-700">
                          {documento.alerta_seguranca}
                        </p>
                      )}

                      {documento.erro_processamento && (
                        <p className="mt-2 max-w-xs text-xs text-red-600">
                          {documento.erro_processamento}
                        </p>
                      )}
                    </td>

                    <td className="px-5 py-4">
                      <div className="flex flex-wrap justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => void baixar(documento)}
                          title="Baixar documento"
                          aria-label={`Baixar ${documento.titulo}`}
                          className="rounded-lg p-2 text-slate-600 transition hover:bg-slate-100"
                        >
                          <Download size={16} />
                        </button>

                        {podeAdministrar && (
                          <button
                            type="button"
                            onClick={() => editar(documento)}
                            title="Editar metadados"
                            className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100"
                          >
                            <Pencil size={16} />
                          </button>
                        )}

                        {podeAdministrar &&
                          documento.status !== "PROCESSANDO" &&
                          /\.(pdf|docx|txt)$/i.test(documento.nome_arquivo) && (
                            <button
                              type="button"
                              onClick={() => void reprocessar(documento)}
                              title="Reprocessar extração"
                              aria-label={`Reprocessar ${documento.titulo}`}
                              className="rounded-lg p-2 text-slate-600 transition hover:bg-slate-100"
                            >
                              <RefreshCw size={16} />
                            </button>
                          )}

                        {podeAdministrar &&
                          documento.status !== "PROCESSANDO" &&
                          /\.pdf$/i.test(documento.nome_arquivo) && (
                            <button
                              type="button"
                              onClick={() => {
                                if (
                                  window.confirm(
                                    "Executar OCR em todas as páginas deste PDF? A extração, os trechos e os embeddings serão recriados para conferência.",
                                  )
                                ) {
                                  void reprocessar(documento, true);
                                }
                              }}
                              title="Reprocessar PDF com OCR integral"
                              aria-label={`Executar OCR em ${documento.titulo}`}
                              className="rounded-lg p-2 text-indigo-700 transition hover:bg-indigo-50"
                            >
                              <ScanText size={16} />
                            </button>
                          )}

                        {podeAdministrar &&
                          documento.status === "PRONTO" &&
                          documento.status_seguranca !== "LIBERADO" && (
                            <button
                              type="button"
                              onClick={() => void liberarSeguranca(documento)}
                              title="Liberar após revisão de segurança"
                              className="rounded-lg p-2 text-amber-700 transition hover:bg-amber-50"
                            >
                              <ShieldCheck size={16} />
                            </button>
                          )}

                        {podeAdministrar &&
                          documento.situacao === "RASCUNHO" &&
                          documento.status === "PRONTO" &&
                          documento.status_seguranca === "LIBERADO" && (
                            <button
                              type="button"
                              onClick={() =>
                                void governar(documento, "APROVADO")
                              }
                              title="Aprovar"
                              className="rounded-lg p-2 text-emerald-600 transition hover:bg-emerald-50"
                            >
                              <CheckCircle2 size={16} />
                            </button>
                          )}

                        {podeAdministrar &&
                          documento.situacao === "APROVADO" && (
                            <>
                              <button
                                type="button"
                                onClick={() =>
                                  void governar(documento, "REVOGADO")
                                }
                                title="Revogar"
                                className="rounded-lg p-2 text-red-600 transition hover:bg-red-50"
                              >
                                <XCircle size={16} />
                              </button>

                              <button
                                type="button"
                                onClick={() =>
                                  void governar(documento, "ARQUIVADO")
                                }
                                title="Arquivar"
                                className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100"
                              >
                                <Archive size={16} />
                              </button>
                            </>
                          )}

                        {podeAdministrar &&
                          ["REVOGADO", "ARQUIVADO"].includes(
                            documento.situacao,
                          ) && (
                            <button
                              type="button"
                              onClick={() =>
                                void governar(documento, "RASCUNHO")
                              }
                              title="Reativar como rascunho"
                              className="rounded-lg p-2 text-slate-600 transition hover:bg-slate-100"
                            >
                              <RefreshCw size={16} />
                            </button>
                          )}

                        {podeAdministrar && (
                          <button
                            type="button"
                            disabled={excluindoId === documento.id}
                            onClick={() => void excluir(documento)}
                            title="Excluir documento"
                            aria-label={`Excluir ${documento.titulo}`}
                            className="inline-flex items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-medium text-red-700 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            <Trash2 size={16} />

                            {excluindoId === documento.id
                              ? "Excluindo..."
                              : "Excluir"}
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="flex items-center justify-between border-t border-slate-200 px-5 py-4 text-sm text-slate-700">
          <span>{dados.total} documento(s)</span>

          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={pagina <= 1}
              onClick={() => setPagina((atual) => atual - 1)}
              className="rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40"
            >
              Anterior
            </button>

            <span>
              Página {pagina} de {Math.max(dados.total_paginas, 1)}
            </span>

            <button
              type="button"
              disabled={pagina >= dados.total_paginas}
              onClick={() => setPagina((atual) => atual + 1)}
              className="rounded-lg border border-slate-300 px-3 py-1.5 disabled:opacity-40"
            >
              Próxima
            </button>
          </div>
        </div>
      </section>

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
          <form
            onSubmit={salvar}
            className="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white p-6 text-slate-900 shadow-xl"
          >
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">
                  {editando ? "Editar documento" : "Novo documento"}
                </h2>

                {!editando && !podeAdministrar && (
                  <p className="mt-1 text-xs text-slate-600">
                    O documento será enviado como rascunho e dependerá de
                    revisão do ADMIN antes de integrar a base oficial.
                  </p>
                )}
              </div>

              <button
                type="button"
                onClick={fecharModal}
                disabled={salvando}
                className="rounded-lg p-2 text-slate-400 transition hover:bg-slate-100 hover:text-slate-700 disabled:opacity-50"
                aria-label="Fechar"
              >
                <XCircle size={20} />
              </button>
            </div>

            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <label className="text-sm md:col-span-2">
                Título
                <input
                  required
                  value={form.titulo}
                  onChange={(evento) =>
                    setForm({
                      ...form,
                      titulo: evento.target.value,
                    })
                  }
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                />
              </label>

              <label className="text-sm">
                Categoria
                <select
                  value={form.tipo}
                  onChange={(evento) =>
                    setForm({
                      ...form,
                      tipo: evento.target.value,

                      tipo_ato:
                        evento.target.value === "MODELO_MINUTA"
                          ? form.tipo_ato
                          : "",
                    })
                  }
                  disabled={Boolean(editando) && !podeAdministrar}
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900"
                >
                  {categoriasCadastro.map(([id, nome]) => (
                    <option key={id} value={id}>
                      {nome}
                    </option>
                  ))}
                </select>
              </label>

              {form.tipo === "MODELO_MINUTA" && (
                <label className="text-sm">
                  Tipo de ato
                  <select
                    required
                    value={form.tipo_ato}
                    onChange={(evento) =>
                      setForm({
                        ...form,
                        tipo_ato: evento.target.value,
                      })
                    }
                    className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900"
                  >
                    <option value="">Selecione</option>

                    <option value="COMPRA_VENDA">Compra e Venda</option>

                    <option value="DOACAO">Doação</option>
                  </select>
                </label>
              )}

              <label className="text-sm">
                Órgão ou origem
                <input
                  value={form.orgao_origem}
                  onChange={(evento) =>
                    setForm({
                      ...form,
                      orgao_origem: evento.target.value,
                    })
                  }
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900"
                />
              </label>

              <label className="text-sm">
                Versão
                <input
                  value={form.versao}
                  onChange={(evento) =>
                    setForm({
                      ...form,
                      versao: evento.target.value,
                    })
                  }
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900"
                />
              </label>

              <label className="text-sm">
                Jurisdição
                <input
                  value={form.jurisdicao}
                  onChange={(evento) =>
                    setForm({
                      ...form,
                      jurisdicao: evento.target.value,
                    })
                  }
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900"
                />
              </label>

              <label className="text-sm">
                Início de vigência
                <input
                  type="date"
                  value={form.vigencia_inicio}
                  onChange={(evento) =>
                    setForm({
                      ...form,
                      vigencia_inicio: evento.target.value,
                    })
                  }
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900"
                />
              </label>

              <label className="text-sm">
                Fim de vigência
                <input
                  type="date"
                  value={form.vigencia_fim}
                  onChange={(evento) =>
                    setForm({
                      ...form,
                      vigencia_fim: evento.target.value,
                    })
                  }
                  className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900"
                />
              </label>

              <label className="text-sm md:col-span-2">
                Descrição
                <textarea
                  value={form.descricao}
                  onChange={(evento) =>
                    setForm({
                      ...form,
                      descricao: evento.target.value,
                    })
                  }
                  rows={2}
                  className="mt-1 w-full resize-y rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900"
                />
              </label>

              <label className="text-sm md:col-span-2">
                Observações
                <textarea
                  value={form.observacoes}
                  onChange={(evento) =>
                    setForm({
                      ...form,
                      observacoes: evento.target.value,
                    })
                  }
                  rows={3}
                  className="mt-1 w-full resize-y rounded-lg border border-slate-300 px-3 py-2.5 text-slate-900"
                />
              </label>

              {!editando && (
                <label className="text-sm md:col-span-2">
                  Arquivo PDF, DOCX ou TXT
                  <input
                    required
                    type="file"
                    accept=".pdf,.docx,.txt"
                    onChange={(evento) =>
                      setArquivo(evento.target.files?.[0] || null)
                    }
                    className="mt-1 block w-full rounded-lg border border-slate-300 p-3 text-sm text-slate-900"
                  />
                </label>
              )}
            </div>

            {erro && (
              <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
                {erro}
              </p>
            )}

            {editando?.situacao === "APROVADO" && (
              <p className="mt-4 rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
                Ao alterar metadados, o documento voltará para rascunho e
                precisará de nova aprovação.
              </p>
            )}

            <div className="mt-6 flex justify-end gap-3">
              <button
                type="button"
                onClick={fecharModal}
                disabled={salvando}
                className="rounded-lg border border-slate-300 px-4 py-2 text-sm text-slate-700 disabled:opacity-50"
              >
                Cancelar
              </button>

              <button
                type="submit"
                disabled={salvando}
                className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:opacity-50"
              >
                {salvando ? "Salvando..." : "Salvar"}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
