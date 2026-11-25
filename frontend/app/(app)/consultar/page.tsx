"use client";

import {
  useCallback,
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
  History,
  LoaderCircle,
  MessageSquarePlus,
  Send,
  ThumbsDown,
  ThumbsUp,
  UserRound,
} from "lucide-react";
import Link from "next/link";

import { useAuth } from "../../../context/AuthContext";
import { apiFetch, obterMensagemErroApi } from "../../../lib/api";
import { gerarId } from "../../../lib/id";
import { formatarDataHoraApi } from "../../../lib/datetime";

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
  conversa_id: string;
  resposta: string;
  situacao_resposta:
    | "EVIDENCIA_SUFFICIENTE"
    | "EVIDENCIA_PARCIAL"
    | "BASE_INSUFICIENTE";
  resultados: Fonte[];
};

type ConversaResumo = {
  id: string;
  titulo: string;
  updated_at: string;
};

type ConversaMensagem = {
  id: string;
  pergunta: string;
  resposta: string;
  situacao_resposta: RespostaConsulta["situacao_resposta"];
  fontes: {
    fonte_id: string;
    titulo_documento: string;
    pagina: number | null;
    localizacao: string | null;
    artigo: string | null;
    trecho: string;
    citada: boolean;
  }[];
  produtiva: boolean | null;
};

type ConversaResponse = {
  id: string;
  titulo: string;
  usuario_id: string;
  usuario_nome: string;
  somente_leitura: boolean;
  items: ConversaMensagem[];
  pagina: number;
  por_pagina: number;
  total: number;
  total_paginas: number;
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

function renderizarTextoInline(texto: string): ReactNode[] {
  return texto
    .split(/(\*\*[^*]+\*\*|__[^_]+__|\*[^*\n]+\*|_[^_\n]+_)/g)
    .map((parte, indice) => {
      if (
        (parte.startsWith("**") && parte.endsWith("**")) ||
        (parte.startsWith("__") && parte.endsWith("__"))
      ) {
        return <strong key={indice}>{parte.slice(2, -2)}</strong>;
      }
      if (
        (parte.startsWith("*") && parte.endsWith("*")) ||
        (parte.startsWith("_") && parte.endsWith("_"))
      ) {
        return <em key={indice}>{parte.slice(1, -1)}</em>;
      }
      return parte;
    });
}

function renderizarResposta(texto: string): ReactNode {
  return texto
    .replace(/\s+([•●])\s+/g, "\n$1 ")
    .split("\n")
    .map((linha, indice) => {
      const conteudo = linha.trim();
      if (!conteudo) return <div key={indice} className="h-2" />;
      if (/^#{1,6}\s+/.test(conteudo))
        return (
          <h3 key={indice} className="mt-3 font-semibold text-slate-900">
            {renderizarTextoInline(conteudo.replace(/^#{1,6}\s+/, ""))}
          </h3>
        );
      if (conteudo === "Fundamentação")
        return (
          <h3 key={indice} className="mt-4 font-semibold text-slate-900">
            {conteudo}
          </h3>
        );
      if (/^[-*•●]\s+/.test(conteudo))
        return (
          <div key={indice} className="flex gap-2 pl-2">
            <span aria-hidden>•</span>
            <p>{renderizarTextoInline(conteudo.replace(/^[-*•●]\s+/, ""))}</p>
          </div>
        );
      const fundamentacao = conteudo.match(/^Fundamentação:\s*(.*)$/i);
      if (fundamentacao)
        return (
          <p
            key={indice}
            className="mt-3 border-t border-slate-100 pt-2 text-xs text-slate-500"
          >
            <strong>Fundamentação:</strong>{" "}
            {renderizarTextoInline(fundamentacao[1])}
          </p>
        );
      return <p key={indice}>{renderizarTextoInline(conteudo)}</p>;
    });
}

async function lerRespostaConsultaStream(
  response: Response,
): Promise<RespostaConsulta> {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("A conexão da consulta não forneceu uma resposta.");
  }

  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    let separador = buffer.indexOf("\n\n");
    while (separador >= 0) {
      const evento = buffer.slice(0, separador);
      buffer = buffer.slice(separador + 2);
      const dados = evento
        .split(/\r?\n/)
        .filter((linha) => linha.startsWith("data:"))
        .map((linha) => linha.slice(5).trimStart())
        .join("\n");
      if (dados) {
        const payload = JSON.parse(dados) as {
          type?: string;
          result?: RespostaConsulta;
          message?: string;
        };
        if (payload.type === "error") {
          throw new Error(payload.message || "A consulta não foi concluída.");
        }
        if (payload.type === "result" && payload.result) {
          return payload.result;
        }
      }
      separador = buffer.indexOf("\n\n");
    }
    if (done) break;
  }

  throw new Error(
    "A conexão foi interrompida antes da resposta. Tente novamente mantendo a página aberta.",
  );
}

export default function ConsultarPage() {
  const { user } = useAuth();
  const [consulta, setConsulta] = useState("");
  const [mensagens, setMensagens] = useState<Mensagem[]>([]);
  const [conversaId, setConversaId] = useState<string | null>(null);
  const [conversaTitulo, setConversaTitulo] = useState("");
  const [conversaSomenteLeitura, setConversaSomenteLeitura] = useState(false);
  const [usuarioConversa, setUsuarioConversa] = useState("");
  const [conversas, setConversas] = useState<ConversaResumo[]>([]);
  const [carregandoConversas, setCarregandoConversas] = useState(true);
  const [carregandoConversa, setCarregandoConversa] = useState(false);
  const [paginaConversa, setPaginaConversa] = useState(1);
  const [totalPaginasConversa, setTotalPaginasConversa] = useState(1);
  const [carregando, setCarregando] = useState(false);
  const [erro, setErro] = useState("");
  const [feedbackAberto, setFeedbackAberto] = useState<string | null>(null);
  const [feedbacks, setFeedbacks] = useState<Record<string, FeedbackRascunho>>(
    {},
  );
  const [feedbacksEnviando, setFeedbacksEnviando] = useState<
    Record<string, boolean>
  >({});
  const areaMensagensRef = useRef<HTMLDivElement>(null);
  const preservarRolagemRef = useRef(false);
  const inicializacaoConversaRef = useRef(false);

  const carregarConversas = useCallback(async () => {
    setCarregandoConversas(true);
    try {
      const response = await apiFetch("/api/consultar/conversas");
      if (!response?.ok) {
        setErro(
          await obterMensagemErroApi(
            response,
            "Não foi possível carregar suas conversas.",
          ),
        );
        return;
      }
      const retorno = (await response.json()) as {
        items: ConversaResumo[];
      };
      setConversas(retorno.items);
    } catch {
      setErro("Não foi possível carregar suas conversas.");
    } finally {
      setCarregandoConversas(false);
    }
  }, []);

  useEffect(() => {
    if (preservarRolagemRef.current) {
      preservarRolagemRef.current = false;
      return;
    }
    const areaMensagens = areaMensagensRef.current;
    areaMensagens?.scrollTo({
      top: areaMensagens.scrollHeight,
      behavior: "smooth",
    });
  }, [mensagens, carregando]);

  const converterMensagensConversa = useCallback(
    (items: ConversaMensagem[]): Mensagem[] =>
      items.flatMap((item) => [
      {
        id: item.id + ":pergunta",
        papel: "usuario" as const,
        conteudo: item.pergunta,
      },
      {
        id: item.id + ":resposta",
        papel: "assistente" as const,
        conteudo: item.resposta,
        consultaId: item.id,
        situacao: item.situacao_resposta,
        fontes: item.fontes
          .filter((fonte) => fonte.citada)
          .map((fonte) => ({
            fonte_id: fonte.fonte_id,
            documento: fonte.titulo_documento,
            pagina: fonte.pagina,
            localizacao: fonte.localizacao,
            artigo: fonte.artigo,
            conteudo: fonte.trecho,
          })),
        produtiva: item.produtiva,
      },
      ]),
    [],
  );

  const abrirConversa = useCallback(
    async (
      id: string,
      pagina = 1,
      anexarMensagensAnteriores = false,
    ) => {
      if (carregandoConversa || carregando) return;
      setCarregandoConversa(true);
      setErro("");
      try {
        const response = await apiFetch(
          "/api/consultar/conversas/" +
            id +
            "?pagina=" +
            pagina +
            "&por_pagina=50",
        );
        if (!response?.ok) {
          setErro(
            await obterMensagemErroApi(
              response,
              "Não foi possível abrir essa conversa.",
            ),
          );
          void carregarConversas();
          return;
        }
        const retorno = (await response.json()) as ConversaResponse;
        const novasMensagens = converterMensagensConversa(retorno.items);
        setMensagens((atuais) =>
          anexarMensagensAnteriores
            ? [...novasMensagens, ...atuais]
            : novasMensagens,
        );
        setConversaId(retorno.id);
        setConversaTitulo(retorno.titulo);
        setConversaSomenteLeitura(retorno.somente_leitura);
        setUsuarioConversa(retorno.usuario_nome);
        setPaginaConversa(retorno.pagina);
        setTotalPaginasConversa(retorno.total_paginas);
        setFeedbackAberto(null);
        setFeedbacks({});
        if (anexarMensagensAnteriores) preservarRolagemRef.current = true;
      } catch {
        setErro("Não foi possível conectar ao servidor.");
      } finally {
        setCarregandoConversa(false);
      }
    },
    [carregandoConversa, carregando, converterMensagensConversa, carregarConversas],
  );

  useEffect(() => {
    if (inicializacaoConversaRef.current) return;
    inicializacaoConversaRef.current = true;
    const conversaInicial = new URLSearchParams(
      window.location.search,
    ).get("conversa_id");
    const temporizador = window.setTimeout(() => {
      if (conversaInicial) void abrirConversa(conversaInicial);
      else void carregarConversas();
    }, 0);
    return () => window.clearTimeout(temporizador);
  }, [abrirConversa, carregarConversas]);

  async function realizarConsulta(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault();
    const texto = consulta.trim();
    if (texto.length < 3 || carregando) {
      setErro("Digite uma pergunta com pelo menos 3 caracteres.");
      return;
    }
    setMensagens((atuais) => [
      ...atuais,
      { id: gerarId(), papel: "usuario", conteudo: texto },
    ]);
    setConsulta("");
    setCarregando(true);
    setErro("");
    try {
      const response = await apiFetch("/api/consultar/stream", {
        method: "POST",
        body: JSON.stringify({
          consulta: texto,
          conversa_id: conversaId,
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
      const resultado = await lerRespostaConsultaStream(response);
      setConversaId(resultado.conversa_id);
      setConversaTitulo(
        conversas.find((item) => item.id === resultado.conversa_id)?.titulo ||
          texto,
      );
      setPaginaConversa(1);
      const turnosCarregados = mensagens.filter(
        (mensagem) => mensagem.papel === "usuario",
      ).length;
      setTotalPaginasConversa((atual) =>
        Math.max(atual, Math.ceil((turnosCarregados + 1) / 50)),
      );
      setMensagens((atuais) => [
        ...atuais,
        {
          id: gerarId(),
          papel: "assistente",
          conteudo: resultado.resposta,
          consultaId: resultado.id,
          situacao: resultado.situacao_resposta,
          fontes: resultado.resultados,
          produtiva: null,
        },
      ]);
      void carregarConversas();
    } catch (erroConsulta) {
      void carregarConversas();
      setErro(
        erroConsulta instanceof Error
          ? erroConsulta.message
          : "Não foi possível conectar ao servidor.",
      );
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
    if (carregando || carregandoConversa) return;
    setConversaId(null);
    setConversaTitulo("");
    setConversaSomenteLeitura(false);
    setUsuarioConversa("");
    setPaginaConversa(1);
    setTotalPaginasConversa(1);
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
    <div className="h-full min-h-0 overflow-hidden bg-slate-100">
      <div className="mx-auto grid h-full min-h-0 w-full max-w-screen-2xl grid-cols-1 grid-rows-[auto_minmax(0,1fr)] gap-5 px-4 py-5 xl:grid-rows-[minmax(0,1fr)] xl:grid-cols-[minmax(0,1fr)_19rem] xl:px-6">
        <aside className="order-first flex max-h-72 min-h-0 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm xl:sticky xl:top-5 xl:order-last xl:h-full xl:max-h-none">
          {conversaSomenteLeitura ? (
            <>
              <div className="border-b border-slate-200 px-4 py-4">
                <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                  Visualização administrativa
                </p>
                <h2 className="mt-1 text-sm font-semibold text-slate-900">
                  Conversa de {usuarioConversa}
                </h2>
              </div>
              <p className="flex-1 px-4 py-4 text-xs leading-5 text-slate-500">
                Esta conversa está aberta somente para consulta. As mensagens e
                respostas não podem ser alteradas por esta visualização.
              </p>
              <Link
                href="/historico"
                className="flex items-center gap-2 border-t border-slate-200 px-4 py-3 text-xs font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
              >
                <History size={15} />
                Voltar ao histórico
              </Link>
            </>
          ) : (
            <>
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-4">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-slate-400">
                Histórico
              </p>
              <h2 className="mt-1 text-sm font-semibold text-slate-900">
                Suas conversas
              </h2>
            </div>
            <button
              type="button"
              onClick={novaConversa}
              disabled={carregando || carregandoConversa}
              className="inline-flex h-9 items-center gap-2 rounded-lg bg-slate-900 px-3 text-xs font-medium text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <MessageSquarePlus size={15} />
              Nova
            </button>
          </div>
          <div className="min-h-0 flex-1 space-y-1 overflow-y-auto p-2">
            {carregandoConversas ? (
              <div className="flex items-center gap-2 px-3 py-4 text-xs text-slate-500">
                <LoaderCircle size={15} className="animate-spin" />
                Carregando conversas...
              </div>
            ) : conversas.length === 0 ? (
              <p className="px-3 py-4 text-xs leading-5 text-slate-500">
                Suas perguntas aparecerão aqui depois da primeira consulta.
              </p>
            ) : (
              conversas.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => void abrirConversa(item.id)}
                  disabled={carregando || carregandoConversa}
                  className={
                    conversaId === item.id
                      ? "w-full rounded-xl bg-slate-900 px-3 py-3 text-left text-white transition disabled:cursor-wait disabled:opacity-60"
                      : "w-full rounded-xl px-3 py-3 text-left text-slate-700 transition hover:bg-slate-100 disabled:cursor-wait disabled:opacity-60"
                  }
                >
                  <span className="block truncate text-sm font-medium">
                    {item.titulo}
                  </span>
                  <time
                    className={
                      conversaId === item.id
                        ? "mt-1 block text-[11px] text-slate-300"
                        : "mt-1 block text-[11px] text-slate-400"
                    }
                  >
                    {formatarDataHoraApi(item.updated_at)}
                  </time>
                </button>
              ))
            )}
          </div>
          <Link
            href="/historico"
            className="flex items-center gap-2 border-t border-slate-200 px-4 py-3 text-xs font-medium text-slate-600 transition hover:bg-slate-50 hover:text-slate-900"
          >
            <History size={15} />
            Abrir Histórico de Consultas
          </Link>
            </>
          )}
        </aside>

        <main className="order-last flex h-full min-h-0 min-w-0 flex-col xl:order-first">
          <div className="mb-4 flex shrink-0 items-center justify-between gap-3 px-1">
            <div className="min-w-0">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-400">
                Consulta
              </p>
              {conversaTitulo && (
                <p className="mt-1 truncate text-sm font-medium text-slate-600">
                  {conversaTitulo}
                </p>
              )}
              {conversaSomenteLeitura && (
                <p className="mt-1 text-xs text-slate-500">
                  Visualização administrativa · {usuarioConversa}
                </p>
              )}
            </div>
            {carregandoConversa && (
              <span className="inline-flex items-center gap-2 text-xs text-slate-500">
                <LoaderCircle size={15} className="animate-spin" />
                Abrindo conversa...
              </span>
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
          <div
            ref={areaMensagensRef}
            className="min-h-0 flex-1 space-y-6 overflow-y-auto overscroll-contain pb-6 pr-1"
            role="region"
            aria-label="Conversa"
            aria-live="polite"
          >
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
                        {!conversaSomenteLeitura && (
                          <>
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
                          </>
                        )}
                      </div>
                      {!conversaSomenteLeitura &&
                        feedbackAberto === mensagem.id && (
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
                                    : fonte.localizacao?.startsWith("Bloco lógico")
                                      ? ` — ${fonte.localizacao}`
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
            {conversaId && paginaConversa < totalPaginasConversa && (
              <div className="flex justify-center">
                <button
                  type="button"
                  onClick={() =>
                    void abrirConversa(conversaId, paginaConversa + 1, true)
                  }
                  disabled={carregandoConversa}
                  className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-50 disabled:opacity-50"
                >
                  Carregar perguntas anteriores
                </button>
              </div>
            )}
            {carregando && (
              <div
                role="status"
                aria-label="Pensando na resposta"
                className="flex items-center gap-3 text-sm text-slate-500"
              >
                <LoaderCircle size={18} className="shrink-0 animate-spin" />
                <span>Pensando...</span>
              </div>
            )}
          </div>
        )}
        {erro && (
          <p className="mb-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {erro}
          </p>
        )}
        {conversaSomenteLeitura ? (
          <p className="mt-4 shrink-0 rounded-xl border border-slate-200 bg-white px-4 py-3 text-xs text-slate-500">
            Visualização administrativa somente leitura.
          </p>
        ) : (
        <form
          onSubmit={realizarConsulta}
          className="mt-4 flex w-full shrink-0 items-end gap-3 rounded-2xl border border-slate-300 bg-white p-3 shadow-lg focus-within:border-slate-400 focus-within:ring-2 focus-within:ring-slate-200"
        >
          <textarea
            id="consulta"
            rows={2}
            data-transparent-background="true"
            placeholder="Digite sua pergunta"
            value={consulta}
            onChange={(evento) => setConsulta(evento.target.value)}
            onKeyDown={tratarEnter}
            disabled={carregando}
            className="min-h-14 flex-1 resize-none rounded-xl border-0 bg-transparent px-3 py-2 text-sm leading-6 text-slate-900 outline-none placeholder:text-slate-400"
          />
          <button
            type="submit"
            disabled={carregando || consulta.trim().length < 3}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-slate-900 text-white transition hover:bg-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
            aria-label="Enviar pergunta"
          >
            {carregando ? (
              <LoaderCircle size={18} className="animate-spin" />
            ) : (
              <Send size={18} />
            )}
          </button>
        </form>
        )}
        </main>
      </div>
    </div>
  );
}
