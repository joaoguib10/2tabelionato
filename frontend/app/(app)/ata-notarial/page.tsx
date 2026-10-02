"use client";

import {
  Check,
  Clipboard,
  FileArchive,
  LoaderCircle,
  RefreshCw,
  Trash2,
  Upload,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch, obterMensagemErroApi } from "../../../lib/api";

type TrabalhoAta = {
  id: string;
  status: "PROCESSANDO" | "PRONTO" | "PRONTO_PARCIAL" | "ERRO";
  nome_arquivo: string;
  resultado: string | null;
  diagnostico: Record<string, unknown> | null;
  erro_processamento: string | null;
};

export default function AtaNotarialPage() {
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [trabalhos, setTrabalhos] = useState<TrabalhoAta[]>([]);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState("");
  const [copiado, setCopiado] = useState<string | null>(null);
  const [reprocessando, setReprocessando] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const carregar = useCallback(async () => {
    try {
      const response = await apiFetch("/api/atas");
      if (!response?.ok) return;
      const retorno = (await response.json()) as { items: TrabalhoAta[] };
      setTrabalhos(retorno.items);
    } catch {
      setErro("Não foi possível carregar os trabalhos temporários.");
    }
  }, []);

  useEffect(() => {
    const temporizador = window.setTimeout(() => void carregar(), 0);
    return () => window.clearTimeout(temporizador);
  }, [carregar]);

  useEffect(() => {
    if (!trabalhos.some((item) => item.status === "PROCESSANDO")) return;
    const temporizador = window.setTimeout(() => void carregar(), 2500);
    return () => window.clearTimeout(temporizador);
  }, [trabalhos, carregar]);

  async function enviar() {
    if (!arquivo) return;
    setEnviando(true);
    setErro("");
    try {
      const dados = new FormData();
      dados.append("arquivo", arquivo);
      const response = await apiFetch("/api/atas", {
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

  async function copiar(trabalho: TrabalhoAta) {
    if (!trabalho.resultado) return;
    await navigator.clipboard.writeText(trabalho.resultado);
    setCopiado(trabalho.id);
    window.setTimeout(() => setCopiado(null), 1800);
  }

  async function descartar(trabalho: TrabalhoAta) {
    if (
      !window.confirm(
        "Confirma que o resultado foi conferido? A conversa, as mídias e o texto temporário serão excluídos.",
      )
    )
      return;
    const response = await apiFetch(`/api/atas/${trabalho.id}`, {
      method: "DELETE",
    });
    if (!response?.ok) {
      setErro(
        await obterMensagemErroApi(
          response,
          "Não foi possível descartar o trabalho.",
        ),
      );
      return;
    }
    await carregar();
  }

  async function reprocessar(trabalho: TrabalhoAta) {
    setReprocessando(trabalho.id);
    setErro("");
    try {
      const response = await apiFetch(`/api/atas/${trabalho.id}/reprocessar`, {
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
        <h1 className="text-2xl font-semibold">Ata Notarial</h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
          Envie o ZIP ou RAR do WhatsApp para organizar as mensagens e
          transcrever os áudios localmente.
        </p>

        <section className="mt-8 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <label className="flex-1">
              <span className="mb-2 block text-sm font-medium">
                Exportação do WhatsApp
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
              className="inline-flex h-11 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white disabled:opacity-50"
            >
              {enviando ? (
                <LoaderCircle size={17} className="animate-spin" />
              ) : (
                <Upload size={17} />
              )}
              {enviando ? "Enviando..." : "Processar exportação"}
            </button>
          </div>
          <p className="mt-3 text-xs leading-5 text-slate-500">
            O resultado não é arquivado. Após a conferência, use “Concluir e
            apagar” para remover o arquivo, as mídias extraídas e o texto
            temporário.
          </p>
        </section>

        {erro && (
          <div className="mt-5 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {erro}
          </div>
        )}

        <section className="mt-6 space-y-4">
          {trabalhos.length === 0 ? (
            <div className="rounded-xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-600">
              Nenhum trabalho temporário.
            </div>
          ) : (
            trabalhos.map((trabalho) => (
              <article
                key={trabalho.id}
                className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
              >
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <FileArchive size={20} className="text-slate-500" />
                    <div>
                      <p className="font-medium">{trabalho.nome_arquivo}</p>
                      <p className="text-xs text-slate-500">
                        {trabalho.status.replaceAll("_", " ")}
                      </p>
                    </div>
                  </div>
                  {trabalho.status === "PROCESSANDO" && (
                    <LoaderCircle
                      size={20}
                      className="animate-spin text-slate-500"
                    />
                  )}
                </div>
                {trabalho.erro_processamento && (
                  <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
                    {trabalho.erro_processamento}
                  </p>
                )}
                {trabalho.status === "PRONTO_PARCIAL" && (
                  <p className="mt-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-800">
                    Não foi possível concluir uma ou mais transcrições locais.
                    Confira o arquivo e tente processar novamente.
                  </p>
                )}
                {["PRONTO_PARCIAL", "ERRO"].includes(trabalho.status) && (
                  <button
                    type="button"
                    onClick={() => void reprocessar(trabalho)}
                    disabled={reprocessando === trabalho.id}
                    className="mt-4 inline-flex items-center gap-2 rounded-lg border border-amber-300 px-3 py-2 text-sm font-medium text-amber-800 disabled:opacity-50"
                  >
                    {reprocessando === trabalho.id ? (
                      <LoaderCircle size={16} className="animate-spin" />
                    ) : (
                      <RefreshCw size={16} />
                    )}
                    Tentar novamente
                  </button>
                )}
                {trabalho.resultado && (
                  <>
                    <textarea
                      readOnly
                      value={trabalho.resultado}
                      rows={14}
                      className="mt-4 w-full rounded-lg border border-slate-300 bg-slate-50 p-4 text-sm leading-7 text-slate-900"
                    />
                    <div className="mt-4 flex flex-wrap justify-end gap-2">
                      <button
                        type="button"
                        onClick={() => void copiar(trabalho)}
                        className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium"
                      >
                        {copiado === trabalho.id ? (
                          <Check size={16} />
                        ) : (
                          <Clipboard size={16} />
                        )}
                        {copiado === trabalho.id ? "Copiado" : "Copiar tudo"}
                      </button>
                      <button
                        type="button"
                        onClick={() => void descartar(trabalho)}
                        className="inline-flex items-center gap-2 rounded-lg border border-red-300 px-3 py-2 text-sm font-medium text-red-700"
                      >
                        <Trash2 size={16} /> Concluir e apagar
                      </button>
                    </div>
                  </>
                )}
              </article>
            ))
          )}
        </section>
      </div>
    </main>
  );
}
