"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, ShieldCheck } from "lucide-react";

import { apiFetch, obterMensagemErroApi } from "../../../../lib/api";

type StatusExterno = {
  provedor: string;
  modelo: string;
  disponivel_no_ambiente: boolean;
  chave_configurada: boolean;
  confirmacao_nivel_gratuito: boolean;
  consulta_habilitada: boolean;
  store_institucional: string;
  fontes_indexadas: number;
  fila: Record<string, number>;
};

type TarefaExterna = {
  id: string;
  acao: string;
  status: string;
  tentativas: number;
  erro_codigo: string | null;
  created_at: string;
  concluido_em: string | null;
};

export default function ConsultaExternaPage() {
  const [status, setStatus] = useState<StatusExterno | null>(null);
  const [tarefas, setTarefas] = useState<TarefaExterna[]>([]);
  const [confirmacao, setConfirmacao] = useState(false);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState("");
  const [mensagem, setMensagem] = useState("");

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErro("");
    try {
      const [respostaStatus, respostaFila] = await Promise.all([
        apiFetch("/api/ia-externa/status"),
        apiFetch("/api/ia-externa/fila"),
      ]);
      if (!respostaStatus || !respostaFila) {
        setErro("A sessão expirou. Entre novamente para continuar.");
        return;
      }
      if (!respostaStatus.ok) {
        setErro(
          await obterMensagemErroApi(
            respostaStatus,
            "Não foi possível carregar as configurações.",
          ),
        );
        return;
      }
      if (!respostaFila.ok) {
        setErro(
          await obterMensagemErroApi(
            respostaFila,
            "Não foi possível carregar a fila de sincronização.",
          ),
        );
        return;
      }
      setStatus((await respostaStatus.json()) as StatusExterno);
      setTarefas((await respostaFila.json()) as TarefaExterna[]);
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    const atraso = window.setTimeout(() => void carregar(), 0);
    return () => window.clearTimeout(atraso);
  }, [carregar]);

  async function alterarConsulta(habilitada: boolean) {
    if (!status || salvando) return;
    if (
      habilitada &&
      (!confirmacao ||
        !window.confirm(
          "A Consulta enviará perguntas gerais e consultará somente fontes liberadas individualmente pelo ADMIN. Confirme que o projeto Google não possui faturamento ativo e que as fontes não contêm dados pessoais, confidenciais ou sensíveis. Deseja continuar?",
        ))
    ) {
      return;
    }

    setSalvando(true);
    setErro("");
    setMensagem("");
    try {
      const response = await apiFetch("/api/ia-externa/configuracao", {
        method: "PATCH",
        body: JSON.stringify({
          consulta_habilitada: habilitada,
          confirmou_politica_de_dados: habilitada,
        }),
      });
      if (!response) {
        setErro("A sessão expirou. Entre novamente para continuar.");
        return;
      }
      if (!response.ok) {
        setErro(
          await obterMensagemErroApi(
            response,
            "Não foi possível atualizar a configuração.",
          ),
        );
        return;
      }
      setStatus((await response.json()) as StatusExterno);
      setMensagem(
        habilitada
          ? "Consulta externa habilitada. Apenas fontes liberadas serão pesquisadas."
          : "Consulta externa desabilitada. O fluxo local permanece disponível.",
      );
      setConfirmacao(false);
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setSalvando(false);
    }
  }

  async function reprocessar(id: string) {
    setErro("");
    const response = await apiFetch(`/api/ia-externa/fila/${id}/reprocessar`, {
      method: "POST",
    });
    if (!response) {
      setErro("A sessão expirou. Entre novamente para continuar.");
      return;
    }
    if (!response.ok) {
      setErro(
        await obterMensagemErroApi(
          response,
          "Não foi possível reprocessar a tarefa.",
        ),
      );
      return;
    }
    await carregar();
  }

  return (
    <div className="min-h-full bg-slate-100 p-6 text-slate-900 lg:p-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold">Consulta externa</h1>
          <p className="mt-1 text-sm text-slate-600">
            Gerencie a sincronização de fontes institucionais públicas ou sintéticas.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void carregar()}
          disabled={carregando}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm disabled:opacity-50"
        >
          <RefreshCw size={16} /> Atualizar
        </button>
      </div>

      {erro && (
        <p className="mb-4 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
          {erro}
        </p>
      )}
      {mensagem && (
        <p className="mb-4 rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800">
          {mensagem}
        </p>
      )}

      {carregando || !status ? (
        <section className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
          Carregando configurações...
        </section>
      ) : (
        <div className="max-w-4xl space-y-5">
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 text-slate-600" size={20} />
              <div>
                <h2 className="font-semibold">Privacidade e uso</h2>
                <p className="mt-2 text-sm leading-6 text-slate-700">
                  O provedor não recebe acesso ao banco local. O ADMIN escolhe individualmente quais fontes aprovadas serão indexadas para a Consulta. O conteúdo selecionado é enviado ao Google uma vez para indexação; depois, cada pergunta consulta esse acervo. Use apenas material público ou autorizado que não contenha dados pessoais, confidenciais ou sensíveis.
                </p>
                <p className="mt-2 text-sm leading-6 text-amber-800">
                  O nível gratuito pode usar o conteúdo para melhoria do serviço e revisão humana. Use uma chave de um projeto Google sem faturamento ativo. A aplicação não consegue verificar o plano da conta; se a cota gratuita acabar, a Consulta segue pelo fluxo local, sem alternar para um plano pago. Não habilite faturamento neste projeto.
                </p>
              </div>
            </div>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="font-semibold">Estado do gateway</h2>
            <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
              <div><dt className="text-slate-500">Provedor</dt><dd>{status.provedor}</dd></div>
              <div><dt className="text-slate-500">Modelo</dt><dd>{status.modelo}</dd></div>
              <div><dt className="text-slate-500">Servidor configurado</dt><dd>{status.disponivel_no_ambiente ? "Sim" : "Não"}</dd></div>
              <div><dt className="text-slate-500">Confirmação de nível gratuito</dt><dd>{status.confirmacao_nivel_gratuito ? "Sim" : "Não"}</dd></div>
              <div><dt className="text-slate-500">Índice institucional</dt><dd>{status.store_institucional}</dd></div>
              <div><dt className="text-slate-500">Fontes indexadas</dt><dd>{status.fontes_indexadas}</dd></div>
            </dl>

            <div className="mt-5 border-t border-slate-200 pt-4">
              <label className="flex items-start gap-3 text-sm text-slate-800">
                <input
                  type="checkbox"
                  checked={confirmacao}
                  onChange={(evento) => setConfirmacao(evento.target.checked)}
                  className="mt-1"
                  disabled={status.consulta_habilitada}
                />
                <span>
                  Confirmo que o projeto Google está sem faturamento ativo e que as fontes escolhidas podem ser enviadas ao Google, sem dados pessoais, confidenciais ou sensíveis.
                </span>
              </label>
              <button
                type="button"
                onClick={() => void alterarConsulta(!status.consulta_habilitada)}
                disabled={
                  salvando ||
                  (!status.consulta_habilitada &&
                    (!status.disponivel_no_ambiente || !confirmacao))
                }
                className={`mt-4 rounded-lg px-4 py-2 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-50 ${status.consulta_habilitada ? "bg-red-700 hover:bg-red-800" : "bg-slate-900 hover:bg-slate-700"}`}
              >
                {salvando
                  ? "Salvando..."
                  : status.consulta_habilitada
                    ? "Desabilitar Consulta externa"
                    : "Habilitar Consulta externa"}
              </button>
              {!status.disponivel_no_ambiente && (
                <p className="mt-2 text-xs text-slate-600">
                  Configure no servidor uma chave de projeto sem faturamento ativo e confirme o nível gratuito no ambiente. O sistema não consegue conferir essa condição sozinho.
                </p>
              )}
            </div>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="font-semibold">Sincronização</h2>
            <p className="mt-1 text-sm text-slate-600">
              Tarefas guardam somente identificadores e estados. Erros não registram conteúdo de documentos.
            </p>
            {tarefas.length === 0 ? (
              <p className="mt-4 text-sm text-slate-600">Nenhuma tarefa cadastrada.</p>
            ) : (
              <div className="mt-4 divide-y divide-slate-100">
                {tarefas.map((tarefa) => (
                  <div key={tarefa.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
                    <div>
                      <p className="font-medium">{tarefa.acao.replaceAll("_", " ")} · {tarefa.status}</p>
                      <p className="mt-1 text-xs text-slate-600">
                        Tentativas: {tarefa.tentativas}{tarefa.erro_codigo ? ` · ${tarefa.erro_codigo}` : ""}
                      </p>
                    </div>
                    {tarefa.status === "ERRO" && (
                      <button
                        type="button"
                        onClick={() => void reprocessar(tarefa.id)}
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-1.5 text-xs hover:bg-slate-50"
                      >
                        <RefreshCw size={14} /> Reprocessar
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </section>

          <p className="text-xs leading-5 text-slate-600">
            A Análise de casos, a Ata Notarial e os anexos privados permanecem na VM. Nesta etapa, somente a Consulta pode usar fontes selecionadas pelo ADMIN.
          </p>
        </div>
      )}
    </div>
  );
}
