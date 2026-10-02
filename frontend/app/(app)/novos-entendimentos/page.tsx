"use client";

import {
  BookOpen,
  CheckCircle2,
  LoaderCircle,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { useAuth } from "../../../context/AuthContext";
import { apiFetch } from "../../../lib/api";

type EntendimentoItem = {
  id: string;
  titulo: string;
  descricao: string | null;
  situacao: string;
  status: string;
  status_seguranca: string;
  ativo: boolean;
  origem: string | null;
  abrangencia: string | null;
  versao: string | null;
  aprovado_em: string | null;
  created_at: string;
  updated_at: string;
};

type EntendimentoListResponse = {
  items: EntendimentoItem[];
  total: number;
  pagina: number;
  por_pagina: number;
  total_paginas: number;
};

type EntendimentoDetalhe = EntendimentoItem & {
  conteudo: string;
  observacao: string | null;
};

export default function NovosEntendimentosPage() {
  const { user } = useAuth();

  const isMaster = user?.role === "ADMIN";

  const [pagina, setPagina] = useState(1);
  const [totalPaginas, setTotalPaginas] = useState(0);
  const [total, setTotal] = useState(0);
  const [revisaoLista, setRevisaoLista] = useState(0);

  const [entendimentos, setEntendimentos] = useState<EntendimentoItem[]>([]);

  const [carregando, setCarregando] = useState(true);

  const [erro, setErro] = useState("");

  const [sucesso, setSucesso] = useState("");

  const [mostrarFormulario, setMostrarFormulario] = useState(false);

  const [entendimentoAberto, setEntendimentoAberto] =
    useState<EntendimentoDetalhe | null>(null);

  const [carregandoDetalheId, setCarregandoDetalheId] = useState<string | null>(
    null,
  );

  const [salvando, setSalvando] = useState(false);

  const [publicandoId, setPublicandoId] = useState<string | null>(null);

  const [excluindoId, setExcluindoId] = useState<string | null>(null);

  const [editandoId, setEditandoId] = useState<string | null>(null);

  const [titulo, setTitulo] = useState("");

  const [origem, setOrigem] = useState("Entendimento interno do tabelião");

  const [abrangencia, setAbrangencia] = useState("Geral");

  const [versao, setVersao] = useState("1.0");

  const [observacao, setObservacao] = useState("");

  const [texto, setTexto] = useState("");

  const carregarEntendimentos = useCallback((silencioso = false) => {
    if (!silencioso) setCarregando(true);
    setRevisaoLista((anterior) => anterior + 1);
  }, []);

  useEffect(() => {
    if (!user) return;
    const controller = new AbortController();
    void apiFetch(
      `/api/documentos/entendimentos?pagina=${pagina}&por_pagina=20`,
      { signal: controller.signal },
    )
      .then(async (response) => {
        if (!response) return;
        const dados = await response.json();
        if (controller.signal.aborted) return;
        setErro("");
        if (!response.ok) {
          setErro(
            dados.detail || "Não foi possível carregar os entendimentos.",
          );
          return;
        }
        const resultado = dados as EntendimentoListResponse;
        if (pagina > 1 && pagina > resultado.total_paginas) {
          setPagina(Math.max(1, resultado.total_paginas));
          return;
        }
        setTotal(resultado.total);
        setTotalPaginas(resultado.total_paginas);
        setEntendimentos(resultado.items);
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setErro("Não foi possível conectar ao servidor.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setCarregando(false);
      });
    return () => controller.abort();
  }, [pagina, revisaoLista, user]);

  useEffect(() => {
    if (!isMaster) {
      return;
    }

    const existeProcessando = entendimentos.some(
      (item) => item.status === "PROCESSANDO",
    );

    if (!existeProcessando) {
      return;
    }

    const intervalo = window.setInterval(() => {
      void carregarEntendimentos(true);
    }, 4000);

    return () => {
      window.clearInterval(intervalo);
    };
  }, [entendimentos, isMaster, carregarEntendimentos]);

  function limparFormulario() {
    setEditandoId(null);

    setTitulo("");

    setOrigem("Entendimento interno do tabelião");

    setAbrangencia("Geral");

    setVersao("1.0");

    setObservacao("");

    setTexto("");
  }

  function abrirNovoEntendimento() {
    setErro("");
    setSucesso("");

    limparFormulario();

    setMostrarFormulario(true);
  }

  function fecharFormulario() {
    if (salvando) {
      return;
    }

    setMostrarFormulario(false);

    limparFormulario();
  }

  async function buscarEntendimento(
    id: string,
  ): Promise<EntendimentoDetalhe | null> {
    setCarregandoDetalheId(id);

    setErro("");

    try {
      const response = await apiFetch(`/api/documentos/entendimentos/${id}`);

      if (!response) {
        return null;
      }

      const dados = await response.json();

      if (!response.ok) {
        setErro(dados.detail || "Não foi possível abrir o entendimento.");

        return null;
      }

      return dados as EntendimentoDetalhe;
    } catch {
      setErro("Não foi possível conectar ao servidor.");

      return null;
    } finally {
      setCarregandoDetalheId(null);
    }
  }

  async function abrirEntendimento(id: string) {
    const entendimento = await buscarEntendimento(id);

    if (!entendimento) {
      return;
    }

    setEntendimentoAberto(entendimento);
  }

  async function editarEntendimento(entendimento: EntendimentoItem) {
    if (!isMaster) {
      return;
    }

    setErro("");
    setSucesso("");

    const detalhe = await buscarEntendimento(entendimento.id);

    if (!detalhe) {
      return;
    }

    setEditandoId(detalhe.id);

    setTitulo(detalhe.titulo);

    setOrigem(detalhe.origem || "Entendimento interno do tabelião");

    setAbrangencia(detalhe.abrangencia || "Geral");

    setVersao(detalhe.versao || "1.0");

    setObservacao(detalhe.observacao || "");

    setTexto(detalhe.conteudo || "");

    setMostrarFormulario(true);
  }

  async function salvarEntendimento(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();

    if (!isMaster) {
      return;
    }

    setSalvando(true);
    setErro("");
    setSucesso("");

    const corpo = {
      titulo: titulo.trim(),

      texto_generalizado: texto.trim(),

      origem: origem.trim(),

      abrangencia: abrangencia.trim(),

      versao: versao.trim(),

      observacao: observacao.trim() || null,
    };

    try {
      const response = await apiFetch(
        editandoId
          ? `/api/documentos/entendimentos/${editandoId}`
          : "/api/documentos/entendimentos",
        {
          method: editandoId ? "PATCH" : "POST",

          body: JSON.stringify(corpo),
        },
      );

      if (!response) {
        return;
      }

      const dados = await response.json();

      if (!response.ok) {
        setErro(
          dados.detail ||
            (editandoId
              ? "Não foi possível editar o entendimento."
              : "Não foi possível criar o entendimento."),
        );

        return;
      }

      const foiEdicao = Boolean(editandoId);

      setMostrarFormulario(false);

      limparFormulario();

      if (foiEdicao) {
        setSucesso(
          "Entendimento alterado. O conteúdo voltou para rascunho e está sendo processado novamente. Após a conclusão, será necessária uma nova publicação.",
        );
      } else {
        setSucesso(
          "Entendimento criado como rascunho. Aguarde o processamento antes de publicá-lo.",
        );
      }

      await carregarEntendimentos();
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setSalvando(false);
    }
  }

  async function publicarEntendimento(entendimento: EntendimentoItem) {
    if (!isMaster) {
      return;
    }

    setPublicandoId(entendimento.id);

    setErro("");
    setSucesso("");

    try {
      const response = await apiFetch(
        `/api/documentos/${entendimento.id}/governanca`,
        {
          method: "PATCH",

          body: JSON.stringify({
            situacao: "APROVADO",
          }),
        },
      );

      if (!response) {
        return;
      }

      const dados = await response.json();

      if (!response.ok) {
        setErro(dados.detail || "Não foi possível publicar o entendimento.");

        return;
      }

      setSucesso(
        "Entendimento publicado. Ele já poderá ser consultado pelos usuários e utilizado pela base autorizada quando elegível.",
      );

      await carregarEntendimentos();
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setPublicandoId(null);
    }
  }

  async function excluirEntendimento(entendimento: EntendimentoItem) {
    if (!isMaster) {
      return;
    }

    const confirmou = window.confirm(
      `Excluir definitivamente “${entendimento.titulo}”? O entendimento será removido da base atual e deixará de ser utilizado pelo RAG.`,
    );

    if (!confirmou) {
      return;
    }

    setExcluindoId(entendimento.id);

    setErro("");
    setSucesso("");

    try {
      const response = await apiFetch(`/api/documentos/${entendimento.id}`, {
        method: "DELETE",
      });

      if (!response) {
        return;
      }

      if (!response.ok) {
        let detalhe = "Não foi possível excluir o entendimento.";

        try {
          const dados = await response.json();

          detalhe = dados.detail || detalhe;
        } catch {
          // Resposta sem JSON.
        }

        setErro(detalhe);

        return;
      }

      if (entendimentoAberto?.id === entendimento.id) {
        setEntendimentoAberto(null);
      }

      if (editandoId === entendimento.id) {
        fecharFormulario();
      }

      setSucesso(
        "Entendimento excluído. Ele deixou de integrar a base atual do Tabeleão.",
      );

      await carregarEntendimentos();
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setExcluindoId(null);
    }
  }

  function formatarData(data: string | null) {
    if (!data) {
      return null;
    }

    return new Intl.DateTimeFormat("pt-BR", {
      dateStyle: "short",

      timeStyle: "short",
    }).format(new Date(data));
  }

  function classeSituacao(situacao: string) {
    if (situacao === "APROVADO") {
      return "border-green-200 " + "bg-green-50 " + "text-green-700";
    }

    if (situacao === "RASCUNHO") {
      return "border-amber-200 " + "bg-amber-50 " + "text-amber-700";
    }

    if (situacao === "REVOGADO" || situacao === "ARQUIVADO") {
      return "border-slate-300 " + "bg-slate-100 " + "text-slate-600";
    }

    return "border-slate-200 " + "bg-slate-50 " + "text-slate-600";
  }

  return (
    <div className="min-h-full bg-slate-100 p-6 text-slate-900 lg:p-8">
      <div className="mx-auto max-w-6xl">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold text-slate-900">
              Novos entendimentos
            </h1>
          </div>

          {isMaster && (
            <button
              type="button"
              onClick={abrirNovoEntendimento}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white transition hover:bg-slate-700"
            >
              <Plus size={17} />
              Novo entendimento
            </button>
          )}
        </div>

        {erro && (
          <div className="mt-6 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {erro}
          </div>
        )}

        {sucesso && (
          <div className="mt-6 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
            {sucesso}
          </div>
        )}

        <div className="mt-8 flex items-center justify-between">
          <h2 className="text-base font-semibold text-slate-900">
            {isMaster
              ? "Entendimentos cadastrados"
              : "Entendimentos publicados"}
          </h2>

          <button
            type="button"
            onClick={() => {
              setCarregando(true);
              void carregarEntendimentos();
            }}
            disabled={carregando}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
          >
            <RefreshCw size={15} className={carregando ? "animate-spin" : ""} />
            Atualizar
          </button>
        </div>

        {carregando ? (
          <div className="mt-6 flex min-h-40 items-center justify-center rounded-xl border border-slate-200 bg-white">
            <div className="flex items-center gap-2 text-sm text-slate-600">
              <LoaderCircle size={18} className="animate-spin" />
              Carregando entendimentos...
            </div>
          </div>
        ) : entendimentos.length === 0 ? (
          <div className="mt-6 rounded-xl border border-dashed border-slate-300 bg-white px-6 py-12 text-center">
            <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full bg-slate-100 text-slate-500">
              <BookOpen size={20} />
            </div>

            <p className="mt-4 text-sm font-medium text-slate-800">
              Nenhum entendimento disponível
            </p>

            <p className="mt-1 text-sm text-slate-500">
              {isMaster
                ? "Crie o primeiro entendimento interno do tabelião."
                : "Ainda não há novos entendimentos publicados."}
            </p>
          </div>
        ) : (
          <div className="mt-5 grid gap-4">
            {entendimentos.map((entendimento) => {
              const podePublicar =
                isMaster &&
                entendimento.situacao === "RASCUNHO" &&
                entendimento.status === "PRONTO" &&
                entendimento.status_seguranca === "LIBERADO";

              const processando = entendimento.status === "PROCESSANDO";

              const carregandoEste = carregandoDetalheId === entendimento.id;

              const excluindoEste = excluindoId === entendimento.id;

              return (
                <article
                  key={entendimento.id}
                  className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
                >
                  <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <h3 className="text-base font-semibold text-slate-900">
                          {entendimento.titulo}
                        </h3>

                        {isMaster && (
                          <span
                            className={`rounded-full border px-2.5 py-1 text-xs font-medium ${classeSituacao(
                              entendimento.situacao,
                            )}`}
                          >
                            {entendimento.situacao}
                          </span>
                        )}
                      </div>

                      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                        {entendimento.versao && (
                          <span>Versão {entendimento.versao}</span>
                        )}

                        {entendimento.origem && (
                          <span>{entendimento.origem}</span>
                        )}

                        {entendimento.aprovado_em && (
                          <span>
                            Publicado em{" "}
                            {formatarData(entendimento.aprovado_em)}
                          </span>
                        )}
                      </div>

                      {isMaster && entendimento.status !== "PRONTO" && (
                        <p className="mt-3 text-xs font-medium text-amber-700">
                          Processamento: {entendimento.status}
                        </p>
                      )}
                    </div>

                    <div className="flex shrink-0 flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => void abrirEntendimento(entendimento.id)}
                        disabled={carregandoEste}
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        {carregandoEste ? (
                          <LoaderCircle size={16} className="animate-spin" />
                        ) : (
                          <BookOpen size={16} />
                        )}
                        Ler
                      </button>

                      {isMaster && (
                        <button
                          type="button"
                          onClick={() => void editarEntendimento(entendimento)}
                          disabled={
                            processando || carregandoEste || excluindoEste
                          }
                          title={
                            processando
                              ? "Aguarde o processamento para editar."
                              : "Editar entendimento"
                          }
                          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-40"
                        >
                          <Pencil size={16} />
                          Editar
                        </button>
                      )}

                      {podePublicar && (
                        <button
                          type="button"
                          onClick={() =>
                            void publicarEntendimento(entendimento)
                          }
                          disabled={publicandoId === entendimento.id}
                          className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {publicandoId === entendimento.id ? (
                            <LoaderCircle size={16} className="animate-spin" />
                          ) : (
                            <CheckCircle2 size={16} />
                          )}
                          Publicar
                        </button>
                      )}

                      {isMaster && (
                        <button
                          type="button"
                          onClick={() => void excluirEntendimento(entendimento)}
                          disabled={excluindoEste}
                          className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-red-700 transition hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {excluindoEste ? (
                            <LoaderCircle size={16} className="animate-spin" />
                          ) : (
                            <Trash2 size={16} />
                          )}

                          {excluindoEste ? "Excluindo..." : "Excluir"}
                        </button>
                      )}
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>

      <nav
        aria-label="Paginação dos entendimentos"
        className="mx-auto mt-5 flex max-w-5xl items-center justify-between gap-3 text-sm text-slate-800"
      >
        <span>
          {total} entendimento(s) · Página {pagina} de{" "}
          {Math.max(1, totalPaginas)}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={carregando || pagina <= 1}
            onClick={() => {
              setCarregando(true);
              setPagina(pagina - 1);
            }}
            className="rounded-lg border border-slate-300 px-3 py-2 disabled:opacity-40"
          >
            Anterior
          </button>
          <button
            type="button"
            disabled={carregando || pagina >= totalPaginas}
            onClick={() => {
              setCarregando(true);
              setPagina(pagina + 1);
            }}
            className="rounded-lg border border-slate-300 px-3 py-2 disabled:opacity-40"
          >
            Próxima
          </button>
        </div>
      </nav>

      {mostrarFormulario && isMaster && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
          <div className="max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white shadow-xl">
            <div className="flex items-start justify-between border-b border-slate-200 px-6 py-5">
              <div>
                <h2 className="text-lg font-semibold text-slate-900">
                  {editandoId ? "Editar entendimento" : "Novo entendimento"}
                </h2>

                <p className="mt-1 text-sm text-slate-500">
                  {editandoId
                    ? "Ao salvar a alteração, o entendimento voltará para rascunho, será processado novamente e precisará de nova publicação."
                    : "O conteúdo será criado como rascunho e somente entrará na base após publicação pelo ADMIN."}
                </p>
              </div>

              <button
                type="button"
                onClick={fecharFormulario}
                disabled={salvando}
                className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900 disabled:opacity-50"
                aria-label="Fechar"
              >
                <X size={20} />
              </button>
            </div>

            <form onSubmit={salvarEntendimento} className="space-y-5 p-6">
              <div>
                <label className="text-sm font-medium text-slate-800">
                  Título
                </label>

                <input
                  value={titulo}
                  onChange={(evento) => setTitulo(evento.target.value)}
                  required
                  minLength={3}
                  maxLength={200}
                  className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                  placeholder="Ex.: Venda de ascendente para descendente"
                />
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <div>
                  <label className="text-sm font-medium text-slate-800">
                    Origem
                  </label>

                  <input
                    value={origem}
                    onChange={(evento) => setOrigem(evento.target.value)}
                    required
                    minLength={3}
                    maxLength={200}
                    className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                  />
                </div>

                <div>
                  <label className="text-sm font-medium text-slate-800">
                    Abrangência
                  </label>

                  <input
                    value={abrangencia}
                    onChange={(evento) => setAbrangencia(evento.target.value)}
                    required
                    minLength={2}
                    maxLength={150}
                    className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                  />
                </div>

                <div>
                  <label className="text-sm font-medium text-slate-800">
                    Versão
                  </label>

                  <input
                    value={versao}
                    onChange={(evento) => setVersao(evento.target.value)}
                    required
                    minLength={1}
                    maxLength={100}
                    className="mt-2 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                  />
                </div>
              </div>

              <div>
                <label className="text-sm font-medium text-slate-800">
                  Entendimento
                </label>

                <textarea
                  value={texto}
                  onChange={(evento) => setTexto(evento.target.value)}
                  required
                  minLength={20}
                  maxLength={100000}
                  rows={12}
                  className="mt-2 w-full resize-y rounded-lg border border-slate-300 bg-white px-3 py-3 text-sm leading-6 text-slate-900 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                  placeholder="Registre aqui o entendimento generalizado, sem dados pessoais ou particularidades desnecessárias de um caso específico."
                />
              </div>

              <div>
                <label className="text-sm font-medium text-slate-800">
                  Observação
                  <span className="ml-1 font-normal text-slate-500">
                    opcional
                  </span>
                </label>

                <textarea
                  value={observacao}
                  onChange={(evento) => setObservacao(evento.target.value)}
                  maxLength={4000}
                  rows={3}
                  className="mt-2 w-full resize-y rounded-lg border border-slate-300 bg-white px-3 py-3 text-sm leading-6 text-slate-900 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                />
              </div>

              {editandoId && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
                  A versão atualmente publicada deixará de ser utilizada pela IA
                  assim que a alteração for salva. O conteúdo editado precisará
                  concluir o processamento e ser publicado novamente.
                </div>
              )}

              <div className="flex justify-end gap-3 border-t border-slate-200 pt-5">
                <button
                  type="button"
                  onClick={fecharFormulario}
                  disabled={salvando}
                  className="rounded-lg border border-slate-300 bg-white px-4 py-2.5 text-sm font-medium text-slate-700 transition hover:bg-slate-50 disabled:opacity-50"
                >
                  Cancelar
                </button>

                <button
                  type="submit"
                  disabled={salvando}
                  className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {salvando && (
                    <LoaderCircle size={16} className="animate-spin" />
                  )}

                  {salvando
                    ? "Salvando..."
                    : editandoId
                      ? "Salvar alterações"
                      : "Criar entendimento"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {entendimentoAberto && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/50 p-4">
          <div className="max-h-[90vh] w-full max-w-4xl overflow-y-auto rounded-2xl bg-white shadow-xl">
            <div className="sticky top-0 flex items-start justify-between border-b border-slate-200 bg-white px-6 py-5">
              <div>
                <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                  Entendimento interno
                </p>

                <h2 className="mt-1 text-xl font-semibold text-slate-900">
                  {entendimentoAberto.titulo}
                </h2>

                <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-slate-500">
                  {entendimentoAberto.versao && (
                    <span>Versão {entendimentoAberto.versao}</span>
                  )}

                  {entendimentoAberto.origem && (
                    <span>{entendimentoAberto.origem}</span>
                  )}

                  {entendimentoAberto.abrangencia && (
                    <span>Abrangência: {entendimentoAberto.abrangencia}</span>
                  )}
                </div>
              </div>

              <button
                type="button"
                onClick={() => setEntendimentoAberto(null)}
                className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-900"
                aria-label="Fechar"
              >
                <X size={20} />
              </button>
            </div>

            <div className="p-6">
              <div className="whitespace-pre-wrap text-sm leading-7 text-slate-800">
                {entendimentoAberto.conteudo ||
                  "O conteúdo ainda não está disponível para leitura."}
              </div>

              {entendimentoAberto.observacao && (
                <div className="mt-8 border-t border-slate-200 pt-5">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
                    Observação
                  </p>

                  <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">
                    {entendimentoAberto.observacao}
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
