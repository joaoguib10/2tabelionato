"use client";

import {
  Check,
  Clipboard,
  FileArchive,
  LoaderCircle,
  Plus,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch, obterMensagemErroApi } from "../../../lib/api";

type ProcessoAta = {
  id: string;
  titulo: string;
  status: "ABERTO" | "PROCESSANDO" | "PRONTO" | "PRONTO_PARCIAL" | "ERRO";
  nome_arquivo: string | null;
  resultado: string | null;
  diagnostico: Record<string, unknown> | null;
  erro_processamento: string | null;
};

function rotuloStatus(status: ProcessoAta["status"]) {
  return {
    ABERTO: "Aguardando arquivo",
    PROCESSANDO: "Processando",
    PRONTO: "Pronto",
    PRONTO_PARCIAL: "Pronto com pendências",
    ERRO: "Erro no processamento",
  }[status];
}

function numeroDiagnostico(
  diagnostico: Record<string, unknown> | null,
  campo: string,
) {
  const valor = diagnostico?.[campo];
  return typeof valor === "number" ? valor : null;
}

export default function AtaNotarialPage() {
  const [titulo, setTitulo] = useState("");
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [processos, setProcessos] = useState<ProcessoAta[]>([]);
  const [processoSelecionado, setProcessoSelecionado] = useState<string | null>(
    null,
  );
  const [criando, setCriando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");
  const [copiado, setCopiado] = useState<string | null>(null);
  const [reprocessando, setReprocessando] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const carregar = useCallback(async () => {
    try {
      const response = await apiFetch("/api/atas");
      if (!response?.ok) return;
      const retorno = (await response.json()) as { items: ProcessoAta[] };
      setProcessos(retorno.items);
      setProcessoSelecionado((atual) =>
        atual && retorno.items.some((item) => item.id === atual) ? atual : null,
      );
    } catch {
      setErro("Não foi possível carregar os processos de Ata.");
    }
  }, []);

  useEffect(() => {
    const temporizador = window.setTimeout(() => void carregar(), 0);
    return () => window.clearTimeout(temporizador);
  }, [carregar]);

  useEffect(() => {
    if (!processos.some((item) => item.status === "PROCESSANDO")) return;
    const temporizador = window.setTimeout(() => void carregar(), 2500);
    return () => window.clearTimeout(temporizador);
  }, [processos, carregar]);

  const processoAtual = processos.find(
    (item) => item.id === processoSelecionado,
  );
  const audiosTotal = numeroDiagnostico(
    processoAtual?.diagnostico ?? null,
    "audios_total",
  );
  const audiosProcessados = numeroDiagnostico(
    processoAtual?.diagnostico ?? null,
    "audios_processados",
  );
  const audioAtual = numeroDiagnostico(
    processoAtual?.diagnostico ?? null,
    "audio_atual",
  );
  const transcricoesConcluidas = numeroDiagnostico(
    processoAtual?.diagnostico ?? null,
    "transcricoes_concluidas",
  );
  const transcricoesPendentes = numeroDiagnostico(
    processoAtual?.diagnostico ?? null,
    "transcricoes_pendentes",
  );
  const transcricoesSemConfiguracao = numeroDiagnostico(
    processoAtual?.diagnostico ?? null,
    "transcricoes_sem_configuracao",
  );
  const transcricoesComErro = numeroDiagnostico(
    processoAtual?.diagnostico ?? null,
    "transcricoes_com_erro",
  );

  async function criarProcesso() {
    if (!titulo.trim()) {
      setErro("Informe um nome para identificar o processo.");
      return;
    }
    setCriando(true);
    setErro("");
    try {
      const response = await apiFetch("/api/atas/processos", {
        method: "POST",
        body: JSON.stringify({ titulo: titulo.trim() }),
      });
      if (!response?.ok) {
        setErro(
          await obterMensagemErroApi(
            response,
            "Não foi possível criar o processo.",
          ),
        );
        return;
      }
      const novo = (await response.json()) as ProcessoAta;
      setTitulo("");
      setProcessoSelecionado(novo.id);
      setProcessos((atuais) => [novo, ...atuais]);
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setCriando(false);
    }
  }

  async function enviar() {
    if (!processoAtual || !arquivo) return;
    setEnviando(true);
    setErro("");
    try {
      const dados = new FormData();
      dados.append("arquivo", arquivo);
      const response = await apiFetch(`/api/atas/${processoAtual.id}/arquivo`, {
        method: "POST",
        body: dados,
      });
      if (!response?.ok) {
        setErro(
          await obterMensagemErroApi(
            response,
            "Não foi possível enviar a exportação.",
          ),
        );
        return;
      }
      setArquivo(null);
      if (inputRef.current) inputRef.current.value = "";
      await carregar();
    } catch {
      setErro("Não foi possível conectar ao servidor durante o envio.");
    } finally {
      setEnviando(false);
    }
  }

  async function copiar(processo: ProcessoAta) {
    if (!processo.resultado) return;
    await navigator.clipboard.writeText(processo.resultado);
    setCopiado(processo.id);
    window.setTimeout(() => setCopiado(null), 1800);
  }

  async function descartar(processo: ProcessoAta) {
    if (
      !window.confirm(
        "Confirma a conclusão? O arquivo exportado, as mídias extraídas e o resultado temporário serão apagados.",
      )
    )
      return;
    const response = await apiFetch(`/api/atas/${processo.id}`, {
      method: "DELETE",
    });
    if (!response?.ok) {
      setErro(
        await obterMensagemErroApi(
          response,
          "Não foi possível concluir o processo.",
        ),
      );
      return;
    }
    setProcessoSelecionado(null);
    await carregar();
  }

  async function reprocessar(processo: ProcessoAta) {
    setReprocessando(processo.id);
    setErro("");
    try {
      const response = await apiFetch(`/api/atas/${processo.id}/reprocessar`, {
        method: "POST",
      });
      if (!response?.ok) {
        setErro(
          await obterMensagemErroApi(
            response,
            "Não foi possível repetir o processamento local.",
          ),
        );
        return;
      }
      await carregar();
    } catch {
      setErro(
        "Não foi possível conectar ao servidor durante o reprocessamento.",
      );
    } finally {
      setReprocessando(null);
    }
  }

  return (
    <main className="min-h-full bg-slate-100 p-6 text-slate-900 lg:p-8">
      <div className="mx-auto max-w-6xl">
        <div>
          <h1 className="text-2xl font-semibold">Ata Notarial</h1>
          <p className="mt-2 text-sm text-slate-600">
            Crie um processo e anexe a exportação ZIP ou RAR do WhatsApp.
          </p>
        </div>

        {erro && (
          <div className="mt-5 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {erro}
          </div>
        )}

        <section className="mt-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <label className="block">
            <span className="mb-2 block text-sm font-medium">
              Identificação do processo
            </span>
            <div className="flex flex-col gap-3 sm:flex-row">
              <input
                value={titulo}
                onChange={(evento) => setTitulo(evento.target.value)}
                onKeyDown={(evento) => {
                  if (evento.key === "Enter") {
                    evento.preventDefault();
                    void criarProcesso();
                  }
                }}
                maxLength={200}
                placeholder="Número ou nome para localizar a Ata"
                className="min-h-11 min-w-0 flex-1 rounded-lg border border-slate-300 px-3 py-2.5 text-sm outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
              />
              <button
                type="button"
                onClick={() => void criarProcesso()}
                disabled={!titulo.trim() || criando}
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
              >
                {criando ? (
                  <LoaderCircle size={17} className="animate-spin" />
                ) : (
                  <Plus size={17} />
                )}
                Criar processo
              </button>
            </div>
          </label>
        </section>

        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(17rem,0.8fr)_minmax(0,1.7fr)]">
          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
            <div className="border-b border-slate-200 px-5 py-4">
              <h2 className="text-sm font-semibold">Processos de Ata</h2>
            </div>
            {processos.length === 0 ? (
              <p className="p-5 text-sm text-slate-500">
                Nenhum processo criado.
              </p>
            ) : (
              <div className="divide-y divide-slate-100">
                {processos.map((processo) => (
                  <button
                    key={processo.id}
                    type="button"
                    onClick={() => setProcessoSelecionado(processo.id)}
                    className={`block w-full px-5 py-4 text-left transition hover:bg-slate-50 ${
                      processoSelecionado === processo.id
                        ? "bg-slate-50 ring-1 ring-inset ring-slate-300"
                        : ""
                    }`}
                  >
                    <span className="flex items-start gap-3">
                      <FileArchive
                        size={18}
                        className="mt-0.5 shrink-0 text-slate-500"
                      />
                      <span className="min-w-0">
                        <span className="block break-words text-sm font-medium text-slate-900">
                          {processo.titulo}
                        </span>
                        <span className="mt-1 block truncate text-xs text-slate-500">
                          {processo.nome_arquivo ||
                            rotuloStatus(processo.status)}
                        </span>
                        <span className="mt-1 block text-xs text-slate-600">
                          {rotuloStatus(processo.status)}
                        </span>
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="min-w-0 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            {!processoAtual ? (
              <div className="flex min-h-56 items-center justify-center text-center text-sm text-slate-500">
                Crie ou selecione um processo para continuar.
              </div>
            ) : (
              <>
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 pb-4">
                  <div className="min-w-0">
                    <p className="text-xs text-slate-500">Processo</p>
                    <h2 className="mt-1 break-words text-lg font-semibold">
                      {processoAtual.titulo}
                    </h2>
                    {processoAtual.nome_arquivo && (
                      <p className="mt-1 break-all text-xs text-slate-500">
                        {processoAtual.nome_arquivo}
                      </p>
                    )}
                  </div>
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-medium text-slate-700">
                    {rotuloStatus(processoAtual.status)}
                  </span>
                </div>

                {processoAtual.status === "ABERTO" && (
                  <div className="mt-4 flex justify-end">
                    <button
                      type="button"
                      onClick={() => void descartar(processoAtual)}
                      className="inline-flex items-center gap-2 rounded-lg border border-red-300 px-3 py-2 text-sm font-medium text-red-700"
                    >
                      <Trash2 size={15} /> Excluir processo
                    </button>
                  </div>
                )}

                {processoAtual.status === "ABERTO" && (
                  <div className="mt-5 rounded-lg border border-dashed border-slate-300 bg-slate-50 p-5">
                    <label className="block">
                      <span className="mb-2 block text-sm font-medium">
                        Exportação da conversa
                      </span>
                      <input
                        ref={inputRef}
                        type="file"
                        accept=".zip,.rar"
                        onChange={(evento) =>
                          setArquivo(evento.target.files?.[0] || null)
                        }
                        className="block w-full rounded-lg border border-slate-300 bg-white p-2.5 text-sm"
                      />
                    </label>
                    <button
                      type="button"
                      onClick={() => void enviar()}
                      disabled={!arquivo || enviando}
                      className="mt-4 inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-medium text-white disabled:opacity-50"
                    >
                      {enviando ? (
                        <LoaderCircle size={17} className="animate-spin" />
                      ) : (
                        <Upload size={17} />
                      )}
                      {enviando ? "Enviando..." : "Enviar e processar"}
                    </button>
                    <p className="mt-3 text-xs leading-5 text-slate-500">
                      A conversa será organizada em ordem cronológica. Os áudios
                      compatíveis serão transcritos localmente; imagens, vídeos,
                      PDFs e stickers permanecem referenciados no texto.
                    </p>
                  </div>
                )}

                {processoAtual.status === "PROCESSANDO" && (
                  <div
                    role="status"
                    className="mt-5 flex items-center gap-3 rounded-lg border border-blue-200 bg-blue-50 p-4 text-sm text-blue-900"
                  >
                    <LoaderCircle size={18} className="animate-spin" />
                    Extraindo a conversa, organizando as mensagens e verificando
                    os áudios. A atualização é automática.
                    {audiosTotal !== null && audiosTotal > 0 && (
                      <span className="ml-1">
                        {audioAtual !== null && audioAtual > 0
                          ? `Transcrevendo áudio ${audioAtual} de ${audiosTotal}; `
                          : "Transcrevendo áudios localmente; "}
                        {audiosProcessados ?? 0} concluído(s).
                      </span>
                    )}
                  </div>
                )}

                {processoAtual.erro_processamento && (
                  <p className="mt-5 rounded-lg bg-red-50 p-3 text-sm text-red-700">
                    {processoAtual.erro_processamento}
                  </p>
                )}
                {processoAtual.status === "PRONTO_PARCIAL" && (
                  <p className="mt-5 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                    Transcrições: {transcricoesConcluidas ?? 0} concluída(s),{" "}
                    {transcricoesPendentes ?? 0} pendente(s) e{" "}
                    {transcricoesComErro ?? 0} com erro. Confira o resultado e a
                    configuração local do Whisper antes de tentar novamente.
                    {transcricoesSemConfiguracao !== null &&
                      transcricoesSemConfiguracao > 0 &&
                      " O Whisper local ou seu modelo não foi localizado; configure-o para concluir essas transcrições."}
                  </p>
                )}

                {["PRONTO_PARCIAL", "ERRO"].includes(processoAtual.status) &&
                  processoAtual.nome_arquivo && (
                    <button
                      type="button"
                      onClick={() => void reprocessar(processoAtual)}
                      disabled={reprocessando === processoAtual.id}
                      className="mt-4 inline-flex items-center gap-2 rounded-lg border border-amber-300 px-3 py-2 text-sm font-medium text-amber-800 disabled:opacity-50"
                    >
                      {reprocessando === processoAtual.id ? (
                        <LoaderCircle size={16} className="animate-spin" />
                      ) : (
                        <RefreshCw size={16} />
                      )}
                      Tentar novamente
                    </button>
                  )}

                {processoAtual.resultado && (
                  <>
                    <textarea
                      readOnly
                      value={processoAtual.resultado}
                      rows={18}
                      aria-label="Transcrição da conversa"
                      className="mt-5 w-full resize-y rounded-lg border border-slate-300 bg-slate-50 p-4 text-sm leading-7 text-slate-900"
                    />
                    <div className="mt-4 flex flex-wrap justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => void copiar(processoAtual)}
                        className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium"
                      >
                        {copiado === processoAtual.id ? (
                          <Check size={16} />
                        ) : (
                          <Clipboard size={16} />
                        )}
                        {copiado === processoAtual.id
                          ? "Copiado"
                          : "Copiar texto"}
                      </button>
                      <button
                        type="button"
                        onClick={() => void descartar(processoAtual)}
                        className="inline-flex min-h-10 items-center gap-2 rounded-lg border border-red-300 px-3 py-2 text-sm font-medium text-red-700"
                      >
                        <Trash2 size={16} /> Concluir e apagar
                      </button>
                    </div>
                  </>
                )}
              </>
            )}
          </section>
        </div>

        <p className="mt-5 text-xs leading-5 text-slate-500">
          Os processos e arquivos são temporários. Ao concluir, a exportação, as
          mídias extraídas e o texto serão removidos.
        </p>
      </div>
    </main>
  );
}
