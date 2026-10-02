"use client";

import { FormEvent, useCallback, useEffect, useState } from "react";
import {
  CheckCircle2,
  MinusCircle,
  Search,
  Trash2,
  XCircle,
} from "lucide-react";

import { useAuth } from "../../../context/AuthContext";
import { apiFetch, obterMensagemErroApi } from "../../../lib/api";
import { formatarDataHoraApi } from "../../../lib/datetime";

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

type Registro = {
  id: string;
  usuario_id: string;
  usuario_nome: string;
  usuario_username: string;
  pergunta: string;
  resposta: string;
  situacao_resposta:
    | "EVIDENCIA_SUFFICIENTE"
    | "EVIDENCIA_PARCIAL"
    | "BASE_INSUFICIENTE";
  produtiva: boolean | null;
  feedback_motivo: string | null;
  feedback_comentario: string | null;
  revisao: {
    id: string;
    status: "PENDENTE" | "EM_ANALISE" | "RESPONDIDA" | "ENCERRADA";
    resposta_humana: string | null;
    respondido_por_nome: string | null;
    respondido_por_role: string | null;
    respondida_em: string | null;
    entendimento_documento_id: string | null;
  } | null;
  fontes: Fonte[];
  created_at: string;
};

type Usuario = { id: string; nome: string; username: string };
type Pagina = {
  items: Registro[];
  total: number;
  pagina: number;
  total_paginas: number;
};
type Filtros = {
  usuario_id: string;
  data: string;
  avaliacao: string;
  evidencia: string;
};

const filtrosIniciais: Filtros = {
  usuario_id: "",
  data: "",
  avaliacao: "",
  evidencia: "",
};

const evidenciaLabel = {
  EVIDENCIA_SUFFICIENTE: "Evidência suficiente",
  EVIDENCIA_PARCIAL: "Evidência parcial",
  BASE_INSUFICIENTE: "Base insuficiente",
};

export default function HistoricoPage() {
  const { user } = useAuth();
  const administrativo = user?.role === "ADMIN";
  const [dados, setDados] = useState<Pagina>({
    items: [],
    total: 0,
    pagina: 1,
    total_paginas: 0,
  });
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [pagina, setPagina] = useState(1);
  const [filtros, setFiltros] = useState<Filtros>(filtrosIniciais);
  const [filtrosAplicados, setFiltrosAplicados] = useState<Filtros | null>(
    null,
  );
  const [loading, setLoading] = useState(false);
  const [excluindoId, setExcluindoId] = useState<string | null>(null);
  const [erro, setErro] = useState("");

  const carregar = useCallback(async () => {
    if (!filtrosAplicados) return;
    setLoading(true);
    setErro("");
    const parametros = new URLSearchParams({
      pagina: String(pagina),
      por_pagina: "20",
    });
    if (filtrosAplicados.usuario_id)
      parametros.set("usuario_id", filtrosAplicados.usuario_id);
    if (filtrosAplicados.data) {
      parametros.set("data_inicial", filtrosAplicados.data);
      parametros.set("data_final", filtrosAplicados.data);
    }
    if (filtrosAplicados.avaliacao)
      parametros.set("avaliacao", filtrosAplicados.avaliacao);
    if (filtrosAplicados.evidencia)
      parametros.set("evidencia", filtrosAplicados.evidencia);
    try {
      const response = await apiFetch(`/api/consultar/historico?${parametros}`);
      if (!response?.ok) {
        setErro(
          await obterMensagemErroApi(
            response,
            "Não foi possível carregar o histórico.",
          ),
        );
        return;
      }
      setDados(await response.json());
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setLoading(false);
    }
  }, [pagina, filtrosAplicados]);

  useEffect(() => {
    if (!filtrosAplicados) return;
    const atraso = window.setTimeout(() => void carregar(), 0);
    return () => window.clearTimeout(atraso);
  }, [carregar, filtrosAplicados]);

  useEffect(() => {
    if (!administrativo) return;
    apiFetch("/api/usuarios")
      .then(async (response) => {
        if (response?.ok) setUsuarios(await response.json());
        else setErro("Não foi possível carregar os usuários.");
      })
      .catch(() => setErro("Não foi possível carregar os usuários."));
  }, [administrativo]);

  function filtro(campo: keyof Filtros, valor: string) {
    setFiltros((atuais) => ({ ...atuais, [campo]: valor }));
  }

  function consultar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    if (administrativo && !filtros.usuario_id) {
      setErro("Selecione o usuário cujo histórico deseja consultar.");
      return;
    }
    setErro("");
    setPagina(1);
    setFiltrosAplicados({ ...filtros });
  }

  async function excluir(registro: Registro) {
    if (!window.confirm("Excluir definitivamente esta consulta do histórico?"))
      return;
    setExcluindoId(registro.id);
    setErro("");
    try {
      const response = await apiFetch(
        `/api/consultar/historico/${registro.id}`,
        {
          method: "DELETE",
        },
      );
      if (!response?.ok) {
        setErro(
          await obterMensagemErroApi(
            response,
            "Não foi possível excluir a consulta.",
          ),
        );
        return;
      }
      if (dados.items.length === 1 && pagina > 1)
        setPagina((atual) => atual - 1);
      else await carregar();
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setExcluindoId(null);
    }
  }

  return (
    <div className="min-h-full bg-slate-100 p-6 lg:p-8">
      <div className="mb-7">
        <h1 className="text-2xl font-semibold text-slate-900">
          Histórico de consultas
        </h1>
      </div>

      <form
        onSubmit={consultar}
        className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
      >
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
          {administrativo && (
            <label className="text-sm font-medium text-slate-700">
              Usuário
              <select
                required
                value={filtros.usuario_id}
                onChange={(e) => filtro("usuario_id", e.target.value)}
                className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900"
              >
                <option value="">Selecione o usuário</option>
                {usuarios.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.nome} ({item.username})
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className="text-sm font-medium text-slate-700">
            Data
            <input
              type="date"
              value={filtros.data}
              onChange={(e) => filtro("data", e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900"
            />
          </label>
          <label className="text-sm font-medium text-slate-700">
            Avaliação
            <select
              value={filtros.avaliacao}
              onChange={(e) => filtro("avaliacao", e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900"
            >
              <option value="">Todas</option>
              <option value="UTIL">Útil</option>
              <option value="NAO_UTIL">Não útil</option>
              <option value="SEM_AVALIACAO">Sem avaliação</option>
            </select>
          </label>
          <label className="text-sm font-medium text-slate-700">
            Evidência
            <select
              value={filtros.evidencia}
              onChange={(e) => filtro("evidencia", e.target.value)}
              className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900"
            >
              <option value="">Todas</option>
              <option value="EVIDENCIA_SUFFICIENTE">
                Evidência suficiente
              </option>
              <option value="EVIDENCIA_PARCIAL">Evidência parcial</option>
              <option value="BASE_INSUFICIENTE">Base insuficiente</option>
            </select>
          </label>
          <div className="flex items-end">
            <button
              type="submit"
              disabled={loading}
              className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
            >
              <Search size={17} /> {loading ? "Consultando..." : "Consultar"}
            </button>
          </div>
        </div>
        {erro && (
          <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
            {erro}
          </p>
        )}
      </form>

      {filtrosAplicados && (
        <section className="mt-5 rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="border-b border-slate-200 px-5 py-4">
            <h2 className="text-sm font-semibold text-slate-900">
              Resultado da consulta
            </h2>
          </div>
          <div className="space-y-4 p-4">
            {loading ? (
              <p className="py-10 text-center text-sm text-slate-600">
                Carregando histórico...
              </p>
            ) : dados.items.length === 0 ? (
              <p className="py-10 text-center text-sm text-slate-600">
                Nenhuma consulta encontrada.
              </p>
            ) : (
              dados.items.map((registro) => (
                <article
                  key={registro.id}
                  className="rounded-xl border border-slate-200 p-5"
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-600">
                      <span
                        className={`rounded-full px-2.5 py-1 font-medium ${registro.situacao_resposta === "EVIDENCIA_SUFFICIENTE" ? "bg-emerald-50 text-emerald-700" : registro.situacao_resposta === "EVIDENCIA_PARCIAL" ? "bg-amber-50 text-amber-700" : "bg-slate-100 text-slate-700"}`}
                      >
                        {evidenciaLabel[registro.situacao_resposta]}
                      </span>
                      <span className="inline-flex items-center gap-1">
                        {registro.produtiva === true ? (
                          <>
                            <CheckCircle2
                              size={14}
                              className="text-emerald-600"
                            />{" "}
                            Útil
                          </>
                        ) : registro.produtiva === false ? (
                          <>
                            <XCircle size={14} className="text-red-500" /> Não
                            útil
                          </>
                        ) : (
                          <>
                            <MinusCircle size={14} /> Sem avaliação
                          </>
                        )}
                      </span>
                    </div>
                    {administrativo && (
                      <button
                        type="button"
                        disabled={excluindoId === registro.id}
                        onClick={() => excluir(registro)}
                        className="inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2.5 py-2 text-xs font-medium text-red-700 hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        <Trash2 size={16} />{" "}
                        {excluindoId === registro.id
                          ? "Excluindo..."
                          : "Excluir"}
                      </button>
                    )}
                  </div>
                  <p className="mt-3 text-xs font-medium text-slate-600">
                    Consultado por {registro.usuario_nome} ·{" "}
                    {formatarDataHoraApi(registro.created_at)}
                  </p>
                  <p className="mt-1 text-xs text-slate-600">
                    Usuário: {registro.usuario_username}
                  </p>
                  <h2 className="mt-4 text-sm font-semibold text-slate-900">
                    {registro.pergunta}
                  </h2>
                  <p className="mt-3 whitespace-pre-wrap text-sm leading-6 text-slate-700">
                    {registro.resposta}
                  </p>
                  {registro.revisao?.resposta_humana ? (
                    <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 p-4">
                      <p className="text-xs font-semibold uppercase tracking-wide text-emerald-800">
                        Resposta revisada
                      </p>
                      <p className="mt-2 whitespace-pre-wrap text-sm leading-6 text-slate-800">
                        {registro.revisao.resposta_humana}
                      </p>
                      <p className="mt-3 text-xs text-emerald-800">
                        {registro.revisao.respondido_por_nome ||
                          "Responsável autorizado"}
                        {registro.revisao.respondido_por_role
                          ? ` · ${registro.revisao.respondido_por_role}`
                          : ""}
                        {registro.revisao.respondida_em
                          ? ` · ${formatarDataHoraApi(registro.revisao.respondida_em)}`
                          : ""}
                      </p>
                    </div>
                  ) : registro.revisao &&
                    registro.revisao.status !== "ENCERRADA" ? (
                    <p className="mt-4 rounded-lg bg-blue-50 px-3 py-2 text-xs text-blue-800">
                      Esta resposta está em revisão.
                    </p>
                  ) : null}
                  {(registro.feedback_motivo ||
                    registro.feedback_comentario) && (
                    <div className="mt-4 rounded-lg bg-slate-50 p-3 text-xs text-slate-700">
                      <p>{registro.feedback_motivo?.replaceAll("_", " ")}</p>
                      {registro.feedback_comentario && (
                        <p className="mt-1">{registro.feedback_comentario}</p>
                      )}
                    </div>
                  )}
                  {registro.fontes.some((fonte) => fonte.citada) && (
                    <details className="mt-4 text-xs">
                      <summary className="cursor-pointer font-medium text-slate-700">
                        Conferir fontes utilizadas
                      </summary>
                      <div className="mt-2 space-y-2">
                        {registro.fontes
                          .filter((fonte) => fonte.citada)
                          .map((fonte) => (
                            <div
                              key={fonte.fonte_id}
                              className="rounded-lg bg-slate-50 p-3"
                            >
                              <p className="font-semibold">
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
                </article>
              ))
            )}
          </div>
          <div className="flex items-center justify-between border-t border-slate-200 px-5 py-4 text-sm text-slate-700">
            <span>{dados.total} consulta(s)</span>
            <div className="flex items-center gap-3">
              <button
                disabled={pagina <= 1 || loading}
                onClick={() => setPagina((atual) => atual - 1)}
                className="rounded-lg border px-3 py-1.5 disabled:opacity-40"
              >
                Anterior
              </button>
              <span>
                Página {pagina} de {Math.max(dados.total_paginas, 1)}
              </span>
              <button
                disabled={pagina >= dados.total_paginas || loading}
                onClick={() => setPagina((atual) => atual + 1)}
                className="rounded-lg border px-3 py-1.5 disabled:opacity-40"
              >
                Próxima
              </button>
            </div>
          </div>
        </section>
      )}
    </div>
  );
}
