"use client";

import {
  FormEvent,
  KeyboardEvent,
  ReactNode,
  useEffect,
  useRef,
  useState,
} from "react";
import {
  Bot,
  Copy,
  LoaderCircle,
  MessageSquarePlus,
  Send,
  ThumbsDown,
  ThumbsUp,
  UserRound,
} from "lucide-react";

import { useAuth } from "../../../context/AuthContext";
import { apiFetch, obterMensagemErroApi } from "../../../lib/api";

type Fonte = {
  fonte_id: string;
  documento: string;
  pagina: number | null;
  localizacao: string | null;
  artigo: string | null;
  conteudo: string;
};

type RespostaConsulta = {
  id: string;
  resposta: string;
  situacao_resposta:
    | "EVIDENCIA_SUFFICIENTE"
    | "EVIDENCIA_PARCIAL"
    | "BASE_INSUFICIENTE";
  resultados: Fonte[];
};

type Mensagem = {
  id: string;
  papel: "usuario" | "assistente";
  conteudo: string;
  consultaId?: string;
  situacao?: RespostaConsulta["situacao_resposta"];
  fontes?: Fonte[];
  produtiva?: boolean | null;
};

type FeedbackRascunho = {
  motivo: string;
  comentario: string;
};

const feedbackInicial: FeedbackRascunho = {
  motivo: "",
  comentario: "",
};

const situacoes = {
  EVIDENCIA_SUFFICIENTE: {
    texto: "Evidência suficiente",
    classe: "bg-emerald-50 text-emerald-700",
  },
  EVIDENCIA_PARCIAL: {
    texto: "Evidência parcial",
    classe: "bg-amber-50 text-amber-700",
  },
  BASE_INSUFICIENTE: {
    texto: "Base insuficiente",
    classe: "bg-slate-100 text-slate-600",
  },
};

function renderizarResposta(texto: string): ReactNode {
  return texto.split("\n").map((linha, indice) => {
    const conteudo = linha.trim();
    if (!conteudo) return <div key={indice} className="h-2" />;
    if (/^#{1,6}\s+/.test(conteudo))
      return (
        <h3 key={indice} className="mt-3 font-semibold text-slate-900">
          {conteudo.replace(/^#{1,6}\s+/, "")}
        </h3>
      );
    if (conteudo === "Fundamentação")
      return (
        <h3 key={indice} className="mt-4 font-semibold text-slate-900">
          {conteudo}
        </h3>
      );
    if (/^[-*]\s+/.test(conteudo))
      return (
        <div key={indice} className="flex gap-2 pl-2">
          <span aria-hidden>•</span>
          <p>{conteudo.replace(/^[-*]\s+/, "")}</p>
        </div>
      );
    return <p key={indice}>{conteudo}</p>;
  });
}

export default function ConsultarPage() {
  const { user } = useAuth();
  const [consulta, setConsulta] = useState("");
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState("");
  const [feedbackAberto, setFeedbackAberto] = useState<string | null>(null);
  const [feedbacks, setFeedbacks] = useState<Record<string, FeedbackRascunho>>(
    {},
  );
  const [feedbacksEnviando, setFeedbacksEnviando] = useState<
    Record<string, boolean>
  >({});
  const fimConversa = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fimConversa.current?.scrollIntoView({ behavior: "smooth" });
  }, [mensagens, carregando]);

  async function realizarConsulta(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const texto = consulta.trim();
    if (texto.length < 3 || carregando) {
      setErro("Digite uma pergunta com pelo menos 3 caracteres.");
      return;
    }
    const anteriores = mensagens.slice(-10);
    setMensagens((atuais) => [
      ...atuais,
      { id: crypto.randomUUID(), papel: "usuario", conteudo: texto },
    ]);
    setConsulta("");
    setCarregando(true);
    setErro("");
    try {
      const response = await apiFetch("/api/consultar", {
        method: "POST",
        body: JSON.stringify({
          consulta: texto,
          historico: anteriores.map((mensagem) => ({
            papel: mensagem.papel,
            conteudo: mensagem.conteudo,
          })),
        }),
      });
      if (!response) return;
      if (!response.ok) {
        setErro(
          await obterMensagemErroApi(
            response,
            "Não foi possível realizar a consulta.",
          ),
        );
        return;
      }
      const dados = await response.json();
      const resultado = dados as RespostaConsulta;
      setMensagens((atuais) => [
        ...atuais,
        {
          id: crypto.randomUUID(),
          papel: "assistente",
          conteudo: resultado.resposta,
          consultaId: resultado.id,
          situacao: resultado.situacao_resposta,
          fontes: resultado.resultados,
          produtiva: null,
        },
      ]);
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setCarregando(false);
    }
  }

  function tratarEnter(evento: KeyboardEvent<HTMLTextAreaElement>) {
    if (
      (evento.key === "Enter" || evento.key === "NumpadEnter") &&
      !evento.shiftKey
    ) {
      evento.preventDefault();
      evento.currentTarget.form?.requestSubmit();
    }
  }

  async function avaliar(mensagemId: string, produtiva: boolean) {
    const mensagem = mensagens.find((item) => item.id === mensagemId);
    if (!mensagem?.consultaId || feedbacksEnviando[mensagemId]) return;

    const rascunho = feedbacks[mensagemId] ?? { motivo: "", comentario: "" };
    setFeedbacksEnviando((atuais) => ({ ...atuais, [mensagemId]: true }));
    setErro("");

    try {
      const response = await apiFetch(
        `/api/consultar/${mensagem.consultaId}/feedback`,
        {
          method: "PATCH",
          body: JSON.stringify({
            produtiva,
            motivo: produtiva ? null : rascunho.motivo || null,
            comentario: produtiva ? null : rascunho.comentario.trim() || null,
          }),
        },
      );
      if (!response?.ok) {
        setErro(
          await obterMensagemErroApi(
            response,
            "Não foi possível registrar sua avaliação.",
          ),
        );
        return;
      }
      setMensagens((atuais) =>
        atuais.map((item) =>
          item.id === mensagemId ? { ...item, produtiva } : item,
        ),
      );
      setFeedbackAberto((atual) => (atual === mensagemId ? null : atual));
      setFeedbacks((atuais) => {
        const atualizados = { ...atuais };
        delete atualizados[mensagemId];
        return atualizados;
      });
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setFeedbacksEnviando((atuais) => {
        const atualizados = { ...atuais };
        delete atualizados[mensagemId];
        return atualizados;
      });
    }
  }

  function novaConversa() {
    setMensagens([]);
    setConsulta("");
    setErro("");
    setFeedbackAberto(null);
    setFeedbacks({});
  }

  async function copiar(texto: string) {
    try {
      await navigator.clipboard.writeText(texto);
    } catch {
      setErro("Não foi possível copiar a resposta.");
    }
  }

  return (
    <div className="min-h-full bg-slate-100">
      <div className="mx-auto flex min-h-[calc(100vh-4rem)] w-full max-w-5xl flex-col px-5 py-8">
        <div className="mb-4 flex justify-end">
          {mensagens.length > 0 && (
            <button
              type="button"
              onClick={novaConversa}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-600"
            >
              <MessageSquarePlus size={15} /> Nova conversa
            </button>
          )}
        </div>
        {mensagens.length === 0 ? (
          <div className="flex flex-1 flex-col items-center justify-center pb-8 text-center">
            <h1 className="text-2xl font-semibold tracking-tight text-slate-900">
              Olá, {user?.nome}.
            </h1>
            <p className="mt-2 text-base text-slate-700">
              Como posso lhe ajudar?
            </p>
          </div>
        ) : (
          <section className="flex-1 space-y-6 pb-8" aria-live="polite">
            {mensagens.map((mensagem) => (
              <article
                key={mensagem.id}
                className={`flex gap-3 ${mensagem.papel === "usuario" ? "justify-end" : "justify-start"}`}
              >
                {mensagem.papel === "assistente" && (
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white">
                    <Bot size={18} />
                  </div>
                )}
                <div
                  className={`max-w-[86%] rounded-2xl px-5 py-4 shadow-sm ${mensagem.papel === "usuario" ? "bg-slate-900 text-white" : "border border-slate-200 bg-white text-slate-700"}`}
                >
                  <div className="space-y-1 text-sm leading-6">
                    {mensagem.papel === "assistente"
                      ? renderizarResposta(mensagem.conteudo)
                      : mensagem.conteudo}
                  </div>
                  {mensagem.papel === "assistente" && mensagem.situacao && (
                    <>
                      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-slate-100 pt-3">
                        <span
                          className={`rounded-full px-2.5 py-1 text-xs font-medium ${situacoes[mensagem.situacao].classe}`}
                        >
                          {situacoes[mensagem.situacao].texto}
                        </span>
                        <button
                          type="button"
                          onClick={() => copiar(mensagem.conteudo)}
                          className="ml-auto rounded-lg p-2 text-slate-400 hover:bg-slate-100"
                          aria-label="Copiar resposta"
                        >
                          <Copy size={16} />
                        </button>
                        <span className="text-xs text-slate-400">
                          Foi útil?
                        </span>
                        <button
                          type="button"
                          disabled={!!feedbacksEnviando[mensagem.id]}
                          onClick={() => avaliar(mensagem.id, true)}
                          className={`rounded-lg p-2 disabled:cursor-not-allowed disabled:opacity-50 ${mensagem.produtiva === true ? "bg-emerald-100 text-emerald-700" : "text-slate-400 hover:bg-slate-100"}`}
                          aria-label="Aprovar resposta"
                        >
                          <ThumbsUp size={16} />
                        </button>
                        <button
                          type="button"
                          disabled={!!feedbacksEnviando[mensagem.id]}
                          onClick={() => {
                            setFeedbackAberto(mensagem.id);
                            setFeedbacks((atuais) => ({
                              ...atuais,
                              [mensagem.id]: { ...feedbackInicial },
                            }));
                          }}
                          className={`rounded-lg p-2 disabled:cursor-not-allowed disabled:opacity-50 ${mensagem.produtiva === false ? "bg-red-100 text-red-700" : "text-slate-400 hover:bg-slate-100"}`}
                          aria-label="Reprovar resposta"
                        >
                          <ThumbsDown size={16} />
                        </button>
                      </div>
                      {feedbackAberto === mensagem.id && (
                        <div className="mt-3 space-y-2 rounded-lg bg-slate-50 p-3">
                          <select
                            disabled={!!feedbacksEnviando[mensagem.id]}
                            value={feedbacks[mensagem.id]?.motivo ?? ""}
                            onChange={(e) =>
                              setFeedbacks((atuais) => ({
                                ...atuais,
                                [mensagem.id]: {
                                  ...(atuais[mensagem.id] ?? feedbackInicial),
                                  motivo: e.target.value,
                                },
                              }))
                            }
                            className="w-full rounded-lg border px-3 py-2 text-xs disabled:opacity-50"
                          >
                            <option value="">Motivo opcional</option>
                            <option value="FONTE_INCORRETA">
                              Fonte incorreta
                            </option>
                            <option value="RESPOSTA_INCOMPLETA">
                              Resposta incompleta
                            </option>
                            <option value="INFORMACAO_DESATUALIZADA">
                              Informação desatualizada
                            </option>
                            <option value="RESPOSTA_CONFUSA">
                              Resposta confusa
                            </option>
                            <option value="OUTRO">Outro</option>
                          </select>
                          <textarea
                            disabled={!!feedbacksEnviando[mensagem.id]}
                            maxLength={500}
                            value={feedbacks[mensagem.id]?.comentario ?? ""}
                            onChange={(e) =>
                              setFeedbacks((atuais) => ({
                                ...atuais,
                                [mensagem.id]: {
                                  ...(atuais[mensagem.id] ?? feedbackInicial),
                                  comentario: e.target.value,
                                },
                              }))
                            }
                            placeholder="Comentário opcional"
                            rows={2}
                            className="w-full rounded-lg border px-3 py-2 text-xs disabled:opacity-50"
                          />
                          <button
                            type="button"
                            disabled={!!feedbacksEnviando[mensagem.id]}
                            onClick={() => avaliar(mensagem.id, false)}
                            className="rounded-lg bg-slate-900 px-3 py-2 text-xs font-medium text-white disabled:cursor-not-allowed disabled:opacity-50"
                          >
                            {feedbacksEnviando[mensagem.id]
                              ? "Registrando..."
                              : "Registrar como não útil"}
                          </button>
                        </div>
                      )}
                      {!!mensagem.fontes?.length && (
                        <details className="mt-3 text-xs text-slate-500">
                          <summary className="cursor-pointer font-medium text-slate-600">
                            Conferir {mensagem.fontes.length} fonte(s)
                            utilizada(s)
                          </summary>
                          <div className="mt-2 space-y-2">
                            {mensagem.fontes.map((fonte) => (
                              <div
                                key={fonte.fonte_id}
                                className="rounded-lg bg-slate-50 p-3"
                              >
                                <p className="font-semibold text-slate-700">
                                  {fonte.documento}
                                  {fonte.artigo
                                    ? ` — ${fonte.artigo}`
                                    : fonte.pagina
                                      ? ` — pág. ${fonte.pagina}`
                                      : fonte.localizacao
                                        ? ` — ${fonte.localizacao}`
                                        : ""}
                                </p>
                                <mark className="mt-2 block bg-amber-50 leading-5 text-slate-700">
                                  {fonte.conteudo}
                                </mark>
                              </div>
                            ))}
                          </div>
                        </details>
                      )}
                    </>
                  )}
                </div>
                {mensagem.papel === "usuario" && (
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white text-slate-500 shadow-sm">
                    <UserRound size={18} />
                  </div>
                )}
              </article>
            ))}
            {carregando && (
              <div className="flex items-center gap-3 text-sm text-slate-500">
                <LoaderCircle size={18} className="animate-spin" /> Consultando
                a base aprovada...
              </div>
            )}
            <div ref={fimConversa} />
          </section>
        )}
        {erro && (
          <p className="mb-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {erro}
          </p>
        )}
        <form
          onSubmit={realizarConsulta}
          className="sticky bottom-5 flex w-full items-end gap-3 rounded-2xl border border-slate-300 bg-white p-3 shadow-lg focus-within:border-slate-400 focus-within:ring-2 focus-within:ring-slate-200"
        >
          <textarea
            id="consulta"
            rows={2}
            placeholder="Digite sua pergunta"
            value={consulta}
            onChange={(evento) => setConsulta(evento.target.value)}
            onKeyDown={tratarEnter}
            disabled={carregando}
            className="min-h-14 flex-1 resize-none border-0 bg-transparent px-3 py-2 text-sm leading-6 text-slate-900 outline-none placeholder:text-slate-400"
          />
          <button
            type="submit"
            disabled={carregando || consulta.trim().length < 3}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg bg-slate-900 text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Enviar pergunta"
          >
            {carregando ? (
              <LoaderCircle size={18} className="animate-spin" />
            ) : (
              <Send size={18} />
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
