"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import { CheckCircle2, FilePlus2, LoaderCircle, Search } from "lucide-react";

import { useAuth } from "../../../context/AuthContext";
import { apiFetch, obterMensagemErroApi } from "../../../lib/api";
import { formatarDataHoraApi } from "../../../lib/datetime";

type StatusRevisao = "PENDENTE" | "EM_ANALISE" | "RESPONDIDA" | "ENCERRADA";

type Fonte = {
  fonte_id: string;
  titulo_documento: string;
  versao_documento: string | null;
  pagina: number | null;
  localizacao: string | null;
  artigo: string | null;
  trecho: string;
  citada: boolean;
};

type Revisao = {
  id: string;
  consulta_id: string;
  status: StatusRevisao;
  responsavel_id: string | null;
  responsavel_nome: string | null;
  resposta_humana: string | null;
  respondido_por_nome: string | null;
  respondido_por_role: string | null;
  respondida_em: string | null;
  entendimento_documento_id: string | null;
  created_at: string;
  usuario_id: string;
  usuario_nome: string;
  usuario_username: string;
  pergunta: string;
  resposta_ia: string;
  situacao_resposta: string;
  feedback_motivo: string | null;
  feedback_comentario: string | null;
  fontes: Fonte[];
};

type PaginaRevisoes = {
  items: Revisao[];
  total: number;
  pagina: number;
  por_pagina: number;
  total_paginas: number;
};

type Usuario = { id: string; nome: string; username: string };

type EntendimentoForm = {
  titulo: string;
  texto_generalizado: string;
  origem: string;
  abrangencia: string;
  versao: string;
  observacao: string;
};

const entendimentoInicial: EntendimentoForm = {
  titulo: "",
  texto_generalizado: "",
  origem: "Entendimento interno do tabelião",
  abrangencia: "Serventia local",
  versao: "1.0",
  observacao: "",
};

const statusLabel: Record<StatusRevisao, string> = {
  PENDENTE: "Pendente",
  EM_ANALISE: "Em análise",
  RESPONDIDA: "Respondida",
  ENCERRADA: "Encerrada",
};

const statusClass: Record<StatusRevisao, string> = {
  PENDENTE: "bg-amber-50 text-amber-800",
  EM_ANALISE: "bg-blue-50 text-blue-800",
  RESPONDIDA: "bg-emerald-50 text-emerald-800",
  ENCERRADA: "bg-slate-100 text-slate-700",
};

export default function RevisoesPage() {
  const { user, loading: carregandoUsuario } = useAuth();
  const administrativo = user?.role === "ADMIN";
  const [dados, setDados] = useState<PaginaRevisoes>({
    items: [],
    total: 0,
    pagina: 1,
    por_pagina: 20,
    total_paginas: 0,
  });
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [pagina, setPagina] = useState(1);
  const [situacao, setSituacao] = useState("PENDENTE");
  const [usuarioId, setUsuarioId] = useState("");
  const [texto, setTexto] = useState("");
  const [textoAplicado, setTextoAplicado] = useState("");
  const [respostas, setRespostas] = useState<Record<string, string>>({});
  const [entendimentoId, setEntendimentoId] = useState<string | null>(null);
  const [entendimento, setEntendimento] =
    useState<EntendimentoForm>(entendimentoInicial);
  const [carregando, setCarregando] = useState(false);
  const [salvandoId, setSalvandoId] = useState<string | null>(null);
  const [erro, setErro] = useState("");
  const [sucesso, setSucesso] = useState("");

  const carregar = useCallback(async () => {
    if (!administrativo) return;
    setCarregando(true);
    setErro("");
    const parametros = new URLSearchParams({
      pagina: String(pagina),
      por_pagina: "20",
    });
    if (situacao) parametros.set("situacao", situacao);
    if (usuarioId) parametros.set("usuario_id", usuarioId);
    if (textoAplicado) parametros.set("texto", textoAplicado);
    try {
      const response = await apiFetch(`/api/revisoes?${parametros}`);
      if (!response?.ok) {
        setErro(
          await obterMensagemErroApi(
            response,
            "Não foi possível carregar as revisões.",
          ),
        );
        return;
      }
      const atualizados = (await response.json()) as PaginaRevisoes;
      setDados(atualizados);
      const ultimaPagina = Math.max(atualizados.total_paginas, 1);
      if (pagina > ultimaPagina) setPagina(ultimaPagina);
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setCarregando(false);
    }
  }, [administrativo, pagina, situacao, textoAplicado, usuarioId]);

  useEffect(() => {
    if (!administrativo) return;
    const atraso = window.setTimeout(() => void carregar(), 0);
    return () => window.clearTimeout(atraso);
  }, [administrativo, carregar]);

  useEffect(() => {
    if (!administrativo) return;
    apiFetch("/api/usuarios")
      .then(async (response) => {
        if (response?.ok) setUsuarios(await response.json());
      })
      .catch(() => setErro("Não foi possível carregar os usuários."));
  }, [administrativo]);

  function pesquisar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    setPagina(1);
    setTextoAplicado(texto.trim());
  }

  function substituirRevisao(atualizada: Revisao) {
    setDados((atuais) => ({
      ...atuais,
      items: atuais.items.map((item) =>
        item.id === atualizada.id ? atualizada : item,
      ),
    }));
  }

  async function alterarStatus(revisao: Revisao, novoStatus: StatusRevisao) {
    setSalvandoId(revisao.id);
    setErro("");
    setSucesso("");
    try {
      const response = await apiFetch(`/api/revisoes/${revisao.id}/status`, {
        method: "PATCH",
        body: JSON.stringify({ status: novoStatus }),
      });
      if (!response?.ok) {
        setErro(
          await obterMensagemErroApi(
            response,
            "Não foi possível atualizar a revisão.",
          ),
        );
        return;
      }
      await carregar();
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setSalvandoId(null);
    }
  }

  async function responder(revisao: Revisao) {
    if (revisao.resposta_humana) return;
    const resposta = (respostas[revisao.id] ?? "").trim();
    if (resposta.length < 3) {
      setErro("Digite a resposta revisada.");
      return;
    }
    setSalvandoId(revisao.id);
    setErro("");
    setSucesso("");
    try {
      const response = await apiFetch(`/api/revisoes/${revisao.id}/resposta`, {
        method: "POST",
        body: JSON.stringify({ resposta_humana: resposta }),
      });
      if (!response?.ok) {
        setErro(
          await obterMensagemErroApi(
            response,
            "Não foi possível registrar a resposta.",
          ),
        );
        return;
      }
      setRespostas((atuais) => {
        const atualizadas = { ...atuais };
        delete atualizadas[revisao.id];
        return atualizadas;
      });
      setSucesso(
        "Resposta revisada registrada sem alterar a resposta original da IA.",
      );
      await carregar();
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setSalvandoId(null);
    }
  }

  function abrirEntendimento(revisaoId: string) {
    setEntendimentoId(revisaoId);
    setEntendimento(entendimentoInicial);
    setErro("");
    setSucesso("");
  }

  async function transformar(
    evento: FormEvent<HTMLFormElement>,
    revisao: Revisao,
  ) {
    evento.preventDefault();
    if (entendimento.texto_generalizado.trim().length < 20) {
      setErro(
        "Redija manualmente um entendimento geral com pelo menos 20 caracteres.",
      );
      return;
    }
    setSalvandoId(revisao.id);
    setErro("");
    setSucesso("");
    try {
      const response = await apiFetch(
        `/api/revisoes/${revisao.id}/entendimento`,
        {
          method: "POST",
          body: JSON.stringify(entendimento),
        },
      );
      if (!response?.ok) {
        setErro(
          await obterMensagemErroApi(
            response,
            "Não foi possível criar o entendimento.",
          ),
        );
        return;
      }
      const documento = await response.json();
      substituirRevisao({
        ...revisao,
        entendimento_documento_id: documento.id,
      });
      setEntendimentoId(null);
      setEntendimento(entendimentoInicial);
      setSucesso(
        "Entendimento criado como rascunho. Revise-o em Documentos antes da aprovação.",
      );
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setSalvandoId(null);
    }
  }

  if (carregandoUsuario) {
    return <p className="p-8 text-sm text-slate-600">Carregando...</p>;
  }

  if (!administrativo) {
    return (
      <div className="min-h-full bg-slate-100 p-6 lg:p-8">
        <h1 className="text-2xl font-semibold text-slate-900">Revisões</h1>
        <p className="mt-2 text-sm text-slate-700">
          Esta área é destinada ao perfil ADMIN.
        </p>
      </div>
    );
  }

  return (
    <div className="min-h-full bg-slate-100 p-6 lg:p-8">
      <div className="mb-7">
        <h1 className="text-2xl font-semibold text-slate-900">Revisões</h1>
      </div>

      <form
        onSubmit={pesquisar}
        className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <label className="text-sm font-medium text-slate-700">
            Situação
            <select
              value={situacao}
              onChange={(evento) => {
                setSituacao(evento.target.value);
                setPagina(1);
              }}
              className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900"
            >
              <option value="">Todas</option>
              {Object.entries(statusLabel).map(([valor, rotulo]) => (
                <option key={valor} value={valor}>
                  {rotulo}
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-medium text-slate-700">
            Usuário
            <select
              value={usuarioId}
              onChange={(evento) => {
                setUsuarioId(evento.target.value);
                setPagina(1);
              }}
              className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900"
            >
              <option value="">Todos</option>
              {usuarios.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.nome} ({item.username})
                </option>
              ))}
            </select>
          </label>
          <label className="text-sm font-medium text-slate-700">
            Pergunta ou comentário
            <input
              value={texto}
              onChange={(evento) => setTexto(evento.target.value)}
              className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900"
            />
          </label>
          <div className="flex items-end">
            <button
              type="submit"
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white"
            >
              <Search size={17} /> Consultar
            </button>
          </div>
        </div>
      </form>

      {erro && (
        <p className="mt-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {erro}
        </p>
      )}
      {sucesso && (
        <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          {sucesso}
        </p>
      )}

      <section className="mt-5 space-y-4">
        {carregando ? (
          <p className="rounded-xl border border-slate-200 bg-white py-12 text-center text-sm text-slate-600">
            <LoaderCircle size={18} className="mr-2 inline animate-spin" />{" "}
            Carregando revisões...
          </p>
        ) : dados.items.length === 0 ? (
          <p className="rounded-xl border border-slate-200 bg-white py-12 text-center text-sm text-slate-600">
            Nenhuma revisão encontrada.
          </p>
        ) : (
          dados.items.map((revisao) => (
            <article
              key={revisao.id}
              className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <span
                    className={`rounded-full px-2.5 py-1 text-xs font-medium ${statusClass[revisao.status]}`}
                  >
                    {statusLabel[revisao.status]}
                  </span>
                  <p className="mt-3 text-xs font-medium text-slate-600">
                    Enviada por {revisao.usuario_nome} · @
                    {revisao.usuario_username} ·{" "}
                    {formatarDataHoraApi(revisao.created_at)}
                  </p>
                  {revisao.responsavel_nome && (
                    <p className="mt-1 text-xs text-slate-600">
                      Responsável: {revisao.responsavel_nome}
                    </p>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  {revisao.status === "PENDENTE" && (
                    <button
                      type="button"
                      disabled={salvandoId === revisao.id}
                      onClick={() => alterarStatus(revisao, "EM_ANALISE")}
                      className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700"
                    >
                      Assumir revisão
                    </button>
                  )}
                  {revisao.status !== "ENCERRADA" &&
                    revisao.resposta_humana && (
                      <button
                        type="button"
                        disabled={salvandoId === revisao.id}
                        onClick={() => alterarStatus(revisao, "ENCERRADA")}
                        className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700"
                      >
                        Encerrar
                      </button>
                    )}
                  {revisao.status === "ENCERRADA" && (
                    <button
                      type="button"
                      disabled={salvandoId === revisao.id}
                      onClick={() => alterarStatus(revisao, "EM_ANALISE")}
                      className="rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium text-slate-700"
                    >
                      Reabrir
                    </button>
                  )}
                </div>
              </div>

              <h2 className="mt-5 text-base font-semibold text-slate-900">
                {revisao.pergunta}
              </h2>
              <div className="mt-3 rounded-lg bg-slate-50 p-4">
                <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">
                  Resposta original da IA
                </p>
                <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-700">
                  {revisao.resposta_ia}
                </p>
              </div>
              {(revisao.feedback_motivo || revisao.feedback_comentario) && (
                <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                  {revisao.feedback_motivo && (
                    <p className="font-medium">
                      {revisao.feedback_motivo.replaceAll("_", " ")}
                    </p>
                  )}
                  {revisao.feedback_comentario && (
                    <p className="mt-1">{revisao.feedback_comentario}</p>
                  )}
                </div>
              )}
              {revisao.fontes.some((fonte) => fonte.citada) && (
                <details className="mt-3 text-xs text-slate-600">
                  <summary className="cursor-pointer font-medium">
                    Conferir fontes citadas
                  </summary>
                  <div className="mt-2 space-y-2">
                    {revisao.fontes
                      .filter((fonte) => fonte.citada)
                      .map((fonte) => (
                        <div
                          key={fonte.fonte_id}
                          className="rounded-lg bg-slate-50 p-3"
                        >
                          <p className="font-semibold text-slate-800">
                            {fonte.titulo_documento}
                            {fonte.versao_documento
                              ? ` · versão ${fonte.versao_documento}`
                              : ""}
                            {fonte.artigo
                              ? ` — ${fonte.artigo}`
                              : fonte.pagina
                                ? ` — pág. ${fonte.pagina}`
                                : fonte.localizacao
                                  ? ` — ${fonte.localizacao}`
                                  : ""}
                          </p>
                          <mark className="mt-2 block bg-amber-50 text-slate-700">
                            {fonte.trecho}
                          </mark>
                        </div>
                      ))}
                  </div>
                </details>
              )}

              {revisao.resposta_humana ? (
                <>
                  <label className="mt-5 block text-sm font-medium text-slate-700">
                    Resposta revisada
                    <textarea
                      readOnly
                      rows={5}
                      value={revisao.resposta_humana}
                      className="mt-1.5 w-full rounded-lg border border-slate-300 bg-slate-50 px-3 py-2.5 text-sm leading-6 text-slate-900"
                    />
                  </label>
                  {revisao.respondido_por_nome && (
                    <p className="mt-3 text-xs text-slate-600">
                      Respondida por {revisao.respondido_por_nome}
                      {revisao.respondido_por_role
                        ? ` · ${revisao.respondido_por_role}`
                        : ""}
                      {revisao.respondida_em
                        ? ` · ${formatarDataHoraApi(revisao.respondida_em)}`
                        : ""}
                    </p>
                  )}
                </>
              ) : (
                <>
                  <label className="mt-5 block text-sm font-medium text-slate-700">
                    Resposta revisada
                    <textarea
                      rows={5}
                      maxLength={20000}
                      value={respostas[revisao.id] ?? ""}
                      onChange={(evento) =>
                        setRespostas((atuais) => ({
                          ...atuais,
                          [revisao.id]: evento.target.value,
                        }))
                      }
                      className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm leading-6 text-slate-900"
                      placeholder="Registre a orientação humana para esta consulta."
                    />
                  </label>
                  <div className="mt-3 flex flex-wrap items-center gap-3">
                    <button
                      type="button"
                      disabled={salvandoId === revisao.id}
                      onClick={() => responder(revisao)}
                      className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
                    >
                      <CheckCircle2 size={17} />{" "}
                      {salvandoId === revisao.id
                        ? "Salvando..."
                        : "Salvar resposta revisada"}
                    </button>
                  </div>
                </>
              )}

              {revisao.entendimento_documento_id ? (
                <p className="mt-4 rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800">
                  Entendimento criado como rascunho. Após o processamento,
                  confira e publique em{" "}
                  <a className="underline" href="/novos-entendimentos">
                    Novos entendimentos
                  </a>
                  . Só então ele será usado pela Consulta.
                </p>
              ) : user?.role === "ADMIN" && revisao.resposta_humana ? (
                entendimentoId === revisao.id ? (
                  <form
                    onSubmit={(evento) => transformar(evento, revisao)}
                    className="mt-5 rounded-xl border border-blue-200 bg-blue-50 p-4"
                  >
                    <h3 className="font-semibold text-slate-900">
                      Preparar entendimento interno
                    </h3>
                    <p className="mt-1 text-xs text-slate-700">
                      Redija uma orientação geral. Nenhum dado do caso é copiado
                      automaticamente.
                    </p>
                    <div className="mt-4 grid gap-3 md:grid-cols-2">
                      <label className="text-sm font-medium text-slate-700">
                        Título
                        <input
                          required
                          minLength={3}
                          maxLength={200}
                          value={entendimento.titulo}
                          onChange={(evento) =>
                            setEntendimento((atual) => ({
                              ...atual,
                              titulo: evento.target.value,
                            }))
                          }
                          className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                        />
                      </label>
                      <label className="text-sm font-medium text-slate-700">
                        Origem
                        <input
                          required
                          minLength={3}
                          maxLength={200}
                          value={entendimento.origem}
                          onChange={(evento) =>
                            setEntendimento((atual) => ({
                              ...atual,
                              origem: evento.target.value,
                            }))
                          }
                          className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                        />
                      </label>
                      <label className="text-sm font-medium text-slate-700">
                        Abrangência
                        <input
                          required
                          minLength={2}
                          maxLength={150}
                          value={entendimento.abrangencia}
                          onChange={(evento) =>
                            setEntendimento((atual) => ({
                              ...atual,
                              abrangencia: evento.target.value,
                            }))
                          }
                          className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                        />
                      </label>
                      <label className="text-sm font-medium text-slate-700">
                        Versão
                        <input
                          required
                          minLength={1}
                          maxLength={100}
                          value={entendimento.versao}
                          onChange={(evento) =>
                            setEntendimento((atual) => ({
                              ...atual,
                              versao: evento.target.value,
                            }))
                          }
                          className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                        />
                      </label>
                    </div>
                    <label className="mt-3 block text-sm font-medium text-slate-700">
                      Texto generalizado
                      <textarea
                        required
                        minLength={20}
                        maxLength={100000}
                        rows={6}
                        value={entendimento.texto_generalizado}
                        onChange={(evento) =>
                          setEntendimento((atual) => ({
                            ...atual,
                            texto_generalizado: evento.target.value,
                          }))
                        }
                        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm leading-6"
                      />
                    </label>
                    <label className="mt-3 block text-sm font-medium text-slate-700">
                      Observação
                      <textarea
                        maxLength={4000}
                        rows={2}
                        value={entendimento.observacao}
                        onChange={(evento) =>
                          setEntendimento((atual) => ({
                            ...atual,
                            observacao: evento.target.value,
                          }))
                        }
                        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                      />
                    </label>
                    <div className="mt-4 flex gap-2">
                      <button
                        type="submit"
                        disabled={salvandoId === revisao.id}
                        className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
                      >
                        Criar como rascunho
                      </button>
                      <button
                        type="button"
                        onClick={() => setEntendimentoId(null)}
                        className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm text-slate-700"
                      >
                        Cancelar
                      </button>
                    </div>
                  </form>
                ) : (
                  <button
                    type="button"
                    onClick={() => abrirEntendimento(revisao.id)}
                    className="mt-4 inline-flex items-center gap-2 rounded-lg border border-blue-300 px-4 py-2.5 text-sm font-medium text-blue-800 hover:bg-blue-50"
                  >
                    <FilePlus2 size={17} /> Transformar em entendimento interno
                  </button>
                )
              ) : null}
            </article>
          ))
        )}
      </section>

      <div className="mt-5 flex items-center justify-between rounded-xl border border-slate-200 bg-white px-5 py-4 text-sm text-slate-700">
        <span>{dados.total} revisão(ões)</span>
        <div className="flex items-center gap-3">
          <button
            type="button"
            disabled={pagina <= 1 || carregando}
            onClick={() => setPagina((atual) => atual - 1)}
            className="rounded-lg border px-3 py-1.5 disabled:opacity-40"
          >
            Anterior
          </button>
          <span>
            Página {pagina} de {Math.max(dados.total_paginas, 1)}
          </span>
          <button
            type="button"
            disabled={pagina >= dados.total_paginas || carregando}
            onClick={() => setPagina((atual) => atual + 1)}
            className="rounded-lg border px-3 py-1.5 disabled:opacity-40"
          >
            Próxima
          </button>
        </div>
      </div>
    </div>
  );
}
