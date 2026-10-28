"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, ShieldCheck } from "lucide-react";

import { apiFetch, obterMensagemErroApi } from "../../../../lib/api";

type StatusConsulta = {
  provedor: string;
  modelo: string;
  disponivel_no_ambiente: boolean;
  chave_configurada: boolean;
  confirmacao_nivel_gratuito: boolean;
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

export default function StatusConsultaPage() {
  const [status, setStatus] = useState<StatusConsulta | null>(null);
  const [tarefas, setTarefas] = useState<TarefaExterna[]>([]);
  const [carregando, setCarregando] = useState(true);
  const [erro, setErro] = useState("");

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
            "Não foi possível carregar o estado da Consulta.",
          ),
        );
        return;
      }
      if (!respostaFila.ok) {
        setErro(
          await obterMensagemErroApi(
            respostaFila,
            "Não foi possível carregar a sincronização das fontes.",
          ),
        );
        return;
      }
      setStatus((await respostaStatus.json()) as StatusConsulta);
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
          "Não foi possível reprocessar a sincronização.",
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
          <h1 className="text-2xl font-semibold">Status da Consulta</h1>
          <p className="mt-1 text-sm text-slate-600">
            A Consulta usa o Gemini e as fontes institucionais liberadas.
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

      {carregando || !status ? (
        <section className="rounded-xl border border-slate-200 bg-white p-6 text-sm text-slate-600">
          Carregando estado da Consulta...
        </section>
      ) : (
        <div className="max-w-4xl space-y-5">
          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <div className="flex items-start gap-3">
              <ShieldCheck className="mt-0.5 text-slate-600" size={20} />
              <div>
                <h2 className="font-semibold">Provedor e fontes</h2>
                <p className="mt-2 text-sm leading-6 text-slate-700">
                  A consulta é enviada diretamente ao Gemini quando o servidor está
                  configurado. A busca percorre entendimentos, revisões humanas e
                  documentos, nessa ordem. Somente conteúdo institucional aprovado,
                  liberado pelo ADMIN e sincronizado pode fundamentar uma resposta.
                  Não há geração local de respostas nem fallback para Ollama.
                </p>
                <p className="mt-2 text-sm leading-6 text-amber-800">
                  A chave deve pertencer a um projeto sem faturamento ativo. O nível
                  gratuito pode usar conteúdo para melhoria do serviço e revisão
                  humana; não libere informações pessoais, confidenciais ou sensíveis.
                  A aplicação não verifica o plano da conta.
                </p>
              </div>
            </div>
            <dl className="mt-5 grid gap-3 border-t border-slate-100 pt-4 text-sm sm:grid-cols-2">
              <div><dt className="text-slate-500">Provedor</dt><dd>{status.provedor}</dd></div>
              <div><dt className="text-slate-500">Modelo</dt><dd>{status.modelo}</dd></div>
              <div><dt className="text-slate-500">Servidor</dt><dd>{status.disponivel_no_ambiente ? "Disponível" : "Não configurado"}</dd></div>
              <div><dt className="text-slate-500">Chave no servidor</dt><dd>{status.chave_configurada ? "Configurada" : "Ausente"}</dd></div>
              <div><dt className="text-slate-500">Confirmação de nível gratuito</dt><dd>{status.confirmacao_nivel_gratuito ? "Sim" : "Não"}</dd></div>
              <div><dt className="text-slate-500">Índice institucional</dt><dd>{status.store_institucional}</dd></div>
              <div><dt className="text-slate-500">Fontes sincronizadas</dt><dd>{status.fontes_indexadas}</dd></div>
            </dl>
            {!status.disponivel_no_ambiente && (
              <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900">
                Configure a chave e a confirmação do nível gratuito no ambiente do
                backend. Não existe ativação pela interface.
              </p>
            )}
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="font-semibold">Sincronização de fontes</h2>
            <p className="mt-1 text-sm text-slate-600">
              Acompanhe o envio e a remoção das fontes liberadas pelo ADMIN.
            </p>
            {tarefas.length === 0 ? (
              <p className="mt-4 text-sm text-slate-600">Nenhuma tarefa cadastrada.</p>
            ) : (
              <div className="mt-4 divide-y divide-slate-100">
                {tarefas.map((tarefa) => (
                  <div
                    key={tarefa.id}
                    className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"
                  >
                    <div>
                      <p className="font-medium">
                        {tarefa.acao.replaceAll("_", " ")} · {tarefa.status}
                      </p>
                      <p className="mt-1 text-xs text-slate-600">
                        Tentativas: {tarefa.tentativas}
                        {tarefa.erro_codigo ? ` · ${tarefa.erro_codigo}` : ""}
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
            Análise e Ata Notarial permanecem separadas e não enviam casos ao Gemini.
          </p>
        </div>
      )}
    </div>
  );
}
