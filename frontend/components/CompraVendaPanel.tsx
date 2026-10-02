"use client";

import {
  AlertTriangle,
  CheckCircle2,
  LoaderCircle,
  Plus,
  RefreshCw,
  Save,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch, obterMensagemErroApi } from "../lib/api";

type Fonte = {
  documento_id: string;
  pagina: number | null;
  localizacao: string | null;
  trecho: string;
};
type Casamento = {
  matricula?: string | null;
  data_registro?: string | null;
  regime_bens?: string | null;
  data_certidao?: string | null;
  selo_digital?: string | null;
};
type Empresa = {
  cnpj?: string | null;
  nire?: string | null;
  endereco?: string | null;
  clausula_poderes?: string | null;
  descricao_poderes?: string | null;
};
type Procuracao = {
  lavrada_em?: string | null;
  livro?: string | null;
  folhas?: string | null;
  tabelionato?: string | null;
  cidade_comarca?: string | null;
  certidao_emitida_em?: string | null;
  selo_digital?: string | null;
  poderes?: string | null;
  valor_minimo?: string | null;
  valor_maximo?: string | null;
};
type Alvara = {
  numero_processo?: string | null;
  juizo?: string | null;
  data_decisao?: string | null;
  data_validade?: string | null;
  representante?: string | null;
  poderes?: string | null;
  valor_minimo?: string | null;
  valor_maximo?: string | null;
};
type Parte = {
  id: string;
  papel: "OUTORGANTE" | "OUTORGADO";
  natureza: "FISICA" | "JURIDICA";
  participacao:
    | "PRINCIPAL"
    | "CONJUGE"
    | "ANUENTE"
    | "REPRESENTANTE"
    | "PROCURADOR";
  principal_id: string | null;
  modo_qualificacao: string;
  nome_completo: string | null;
  nacionalidade: string | null;
  capacidade: string | null;
  estado_civil: string | null;
  uniao_estavel: boolean | null;
  profissao: string | null;
  cpf: string | null;
  endereco: string | null;
  casamento: Casamento;
  empresa: Empresa;
  procuracao: Procuracao;
  alvara: Alvara;
  fontes: Fonte[];
  origem: string;
  confirmado: boolean;
};
type Averbacao = {
  ordem: number;
  rotulo: string;
  resumo: string;
  fonte?: Fonte | null;
};
type Imovel = {
  matricula: string | null;
  logradouro: string | null;
  numero: string | null;
  bairro: string | null;
  cidade: string | null;
  descricao_completa: string | null;
  descricao_utilizada: string | null;
  averbacoes: Averbacao[];
  fontes: Fonte[];
  origem: string;
  confirmado: boolean;
};
type DadosCompraVenda = {
  partes: Parte[];
  imovel: Imovel;
  negocio: {
    valor_escritura: string | null;
    forma_pagamento: string | null;
    moeda: string | null;
    observacoes: string | null;
    fontes: Fonte[];
    confirmado: boolean;
  };
  status: string;
  erro: string | null;
  atualizado_em: string | null;
  qualificacoes: { parte_id: string; texto: string; pendencias: string[] }[];
  pendencias: string[];
  alertas_valor: string[];
};

function novaParte(): Parte {
  return {
    id: crypto.randomUUID(),
    papel: "OUTORGANTE",
    natureza: "FISICA",
    participacao: "PRINCIPAL",
    principal_id: null,
    modo_qualificacao: "INDIVIDUAL",
    nome_completo: null,
    nacionalidade: "brasileiro(a)",
    capacidade: null,
    estado_civil: null,
    uniao_estavel: null,
    profissao: null,
    cpf: null,
    endereco: null,
    casamento: {},
    empresa: {},
    procuracao: {},
    alvara: {},
    fontes: [],
    origem: "MANUAL",
    confirmado: false,
  };
}

function Campo({
  label,
  value,
  onChange,
  pendente = false,
  multiline = false,
  placeholder,
}: {
  label: string;
  value: string | null | undefined;
  onChange: (valor: string) => void;
  pendente?: boolean;
  multiline?: boolean;
  placeholder?: string;
}) {
  const classe = `mt-1.5 w-full rounded-lg border bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:ring-2 ${pendente ? "border-amber-300 focus:border-amber-500 focus:ring-amber-100" : "border-slate-300 focus:border-slate-500 focus:ring-slate-100"}`;
  return (
    <label className="block text-sm font-medium text-slate-800">
      {label}
      {pendente && (
        <span className="ml-2 text-xs font-normal text-amber-700">
          Pendente
        </span>
      )}
      {multiline ? (
        <textarea
          rows={4}
          value={value || ""}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          className={classe}
        />
      ) : (
        <input
          value={value || ""}
          placeholder={placeholder}
          onChange={(e) => onChange(e.target.value)}
          className={classe}
        />
      )}
    </label>
  );
}

export default function CompraVendaPanel({
  casoId,
  casoStatus,
  onUpdated,
}: {
  casoId: string;
  casoStatus: string;
  onUpdated?: () => void | Promise<void>;
}) {
  const [dados, setDados] = useState<DadosCompraVenda | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [salvando, setSalvando] = useState(false);
  const [extraindo, setExtraindo] = useState(false);
  const [erro, setErro] = useState("");
  const [sucesso, setSucesso] = useState("");
  const onUpdatedRef = useRef(onUpdated);
  const editavel = ["EM_PREPARACAO", "AGUARDANDO_CONFERENCIA"].includes(
    casoStatus,
  );

  useEffect(() => {
    onUpdatedRef.current = onUpdated;
  }, [onUpdated]);

  const carregar = useCallback(
    async (silencioso = false) => {
      if (!silencioso) setCarregando(true);
      try {
        const response = await apiFetch(
          `/api/analises/casos/${casoId}/compra-venda`,
        );
        if (!response?.ok) {
          setErro(
            await obterMensagemErroApi(
              response,
              "Não foi possível carregar os dados do ato.",
            ),
          );
          return;
        }
        const retorno = (await response.json()) as DadosCompraVenda;
        setDados(retorno);
        setExtraindo(retorno.status === "PROCESSANDO");
        if (retorno.status !== "PROCESSANDO" && silencioso)
          await onUpdatedRef.current?.();
      } catch {
        setErro("Não foi possível conectar ao servidor.");
      } finally {
        if (!silencioso) setCarregando(false);
      }
    },
    [casoId],
  );

  useEffect(() => {
    const timer = window.setTimeout(() => void carregar(), 0);
    return () => window.clearTimeout(timer);
  }, [carregar]);
  useEffect(() => {
    if (!extraindo) return;
    const timer = window.setInterval(() => void carregar(true), 2500);
    return () => window.clearInterval(timer);
  }, [extraindo, carregar]);

  function atualizarParte(id: string, campo: keyof Parte, valor: unknown) {
    setDados((atual) =>
      atual
        ? {
            ...atual,
            partes: atual.partes.map((parte) =>
              parte.id === id ? { ...parte, [campo]: valor } : parte,
            ),
          }
        : atual,
    );
  }
  function atualizarGrupo(
    id: string,
    grupo: "casamento" | "empresa" | "procuracao" | "alvara",
    campo: string,
    valor: string,
  ) {
    setDados((atual) =>
      atual
        ? {
            ...atual,
            partes: atual.partes.map((parte) =>
              parte.id === id
                ? { ...parte, [grupo]: { ...parte[grupo], [campo]: valor } }
                : parte,
            ),
          }
        : atual,
    );
  }
  function atualizarImovel(campo: keyof Imovel, valor: unknown) {
    setDados((atual) =>
      atual ? { ...atual, imovel: { ...atual.imovel, [campo]: valor } } : atual,
    );
  }
  function atualizarNegocio(
    campo: keyof DadosCompraVenda["negocio"],
    valor: unknown,
  ) {
    setDados((atual) =>
      atual
        ? { ...atual, negocio: { ...atual.negocio, [campo]: valor } }
        : atual,
    );
  }

  async function salvar() {
    if (!dados) return;
    setSalvando(true);
    setErro("");
    setSucesso("");
    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoId}/compra-venda`,
        {
          method: "PUT",
          body: JSON.stringify({
            partes: dados.partes,
            imovel: dados.imovel,
            negocio: dados.negocio,
          }),
        },
      );
      if (!response?.ok) {
        setErro(
          await obterMensagemErroApi(
            response,
            "Não foi possível salvar os dados do ato.",
          ),
        );
        return;
      }
      setDados((await response.json()) as DadosCompraVenda);
      setSucesso(
        "Dados salvos. As pendências continuam visíveis para conferência.",
      );
      await onUpdatedRef.current?.();
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setSalvando(false);
    }
  }

  async function extrair() {
    setExtraindo(true);
    setErro("");
    setSucesso("");
    try {
      const response = await apiFetch(
        `/api/analises/casos/${casoId}/compra-venda/extrair`,
        { method: "POST" },
      );
      if (!response?.ok) {
        setErro(
          await obterMensagemErroApi(
            response,
            "Não foi possível iniciar a leitura estruturada.",
          ),
        );
        setExtraindo(false);
        return;
      }
      const retorno = (await response.json()) as DadosCompraVenda;
      setDados(retorno);
      if (retorno.status !== "PROCESSANDO") {
        setExtraindo(false);
        await carregar(true);
      }
      setSucesso(
        "Leitura solicitada. Confira cada sugestão antes de confirmá-la.",
      );
    } catch {
      setErro("Não foi possível conectar ao servidor.");
      setExtraindo(false);
    }
  }

  if (carregando)
    return (
      <section className="rounded-xl border border-slate-200 p-8 text-center text-sm text-slate-600">
        Carregando preparação da Compra e Venda...
      </section>
    );
  if (!dados)
    return (
      <section className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
        {erro || "Dados do ato indisponíveis."}
      </section>
    );

  return (
    <section className="rounded-xl border border-slate-200 bg-white">
      <div className="flex flex-col gap-4 border-b border-slate-200 p-5 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Sparkles size={18} className="text-indigo-600" />
            <h3 className="font-semibold text-slate-900">
              Preparação da Compra e Venda
            </h3>
          </div>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-slate-600">
            Confira no documento original todas as sugestões da IA.
          </p>
        </div>
        {editavel && (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void extrair()}
              disabled={extraindo}
              className="inline-flex items-center gap-2 rounded-lg border border-indigo-300 px-3 py-2 text-sm font-medium text-indigo-800 disabled:opacity-50"
            >
              {extraindo ? (
                <LoaderCircle size={16} className="animate-spin" />
              ) : (
                <RefreshCw size={16} />
              )}{" "}
              {extraindo
                ? "Lendo documentos..."
                : dados.status === "PRONTO_PARCIAL"
                  ? "Continuar leitura"
                  : "Ler documentos"}
            </button>
            <button
              type="button"
              onClick={() => void salvar()}
              disabled={salvando}
              className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {salvando ? (
                <LoaderCircle size={16} className="animate-spin" />
              ) : (
                <Save size={16} />
              )}{" "}
              Salvar conferência
            </button>
          </div>
        )}
      </div>

      {erro && (
        <div className="m-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {erro}
        </div>
      )}
      {sucesso && (
        <div className="m-5 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          {sucesso}
        </div>
      )}
      {dados.erro && (
        <div className="m-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {dados.erro}
        </div>
      )}

      <div className="space-y-6 p-5">
        <div className="flex items-center justify-between">
          <div>
            <h4 className="font-semibold text-slate-900">Partes</h4>
          </div>
          {editavel && (
            <button
              type="button"
              onClick={() =>
                setDados({ ...dados, partes: [...dados.partes, novaParte()] })
              }
              className="inline-flex items-center gap-2 rounded-lg border border-slate-300 px-3 py-2 text-sm font-medium text-slate-800"
            >
              <Plus size={16} />
              Adicionar parte
            </button>
          )}
        </div>

        {dados.partes.length === 0 ? (
          <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-sm text-slate-600">
            Nenhuma parte identificada. Use “Ler documentos” ou adicione
            manualmente.
          </div>
        ) : (
          dados.partes.map((parte, indice) => {
            const principais = dados.partes.filter(
              (item) =>
                item.id !== parte.id && item.participacao === "PRINCIPAL",
            );
            const qualificacao = dados.qualificacoes.find(
              (item) => item.parte_id === parte.id,
            );
            const pendente = (campo: keyof Parte) => !parte[campo];
            return (
              <article
                key={parte.id}
                className={`rounded-xl border p-4 ${parte.confirmado ? "border-emerald-200 bg-emerald-50/20" : "border-amber-200 bg-amber-50/20"}`}
              >
                <div className="mb-4 flex items-start justify-between gap-3">
                  <div>
                    <h5 className="font-semibold text-slate-900">
                      Parte {indice + 1}
                      {parte.nome_completo ? ` · ${parte.nome_completo}` : ""}
                    </h5>
                    <p className="mt-1 text-xs text-slate-600">
                      Origem:{" "}
                      {parte.origem === "IA"
                        ? "sugestão da IA"
                        : "cadastro manual"}{" "}
                      · {parte.fontes.length} fonte(s)
                    </p>
                  </div>
                  {editavel && (
                    <button
                      type="button"
                      onClick={() =>
                        setDados({
                          ...dados,
                          partes: dados.partes.filter(
                            (item) => item.id !== parte.id,
                          ),
                        })
                      }
                      className="rounded-lg p-2 text-red-600 hover:bg-red-50"
                      aria-label="Remover parte"
                    >
                      <Trash2 size={17} />
                    </button>
                  )}
                </div>
                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                  <label className="text-sm font-medium text-slate-800">
                    Papel no ato
                    <select
                      value={parte.papel}
                      onChange={(e) =>
                        atualizarParte(parte.id, "papel", e.target.value)
                      }
                      className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5"
                    >
                      <option value="OUTORGANTE">Outorgante</option>
                      <option value="OUTORGADO">Outorgado</option>
                    </select>
                  </label>
                  <label className="text-sm font-medium text-slate-800">
                    Natureza
                    <select
                      value={parte.natureza}
                      onChange={(e) =>
                        atualizarParte(parte.id, "natureza", e.target.value)
                      }
                      className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5"
                    >
                      <option value="FISICA">Pessoa física</option>
                      <option value="JURIDICA">Pessoa jurídica</option>
                    </select>
                  </label>
                  <label className="text-sm font-medium text-slate-800">
                    Participação
                    <select
                      value={parte.participacao}
                      onChange={(e) =>
                        atualizarParte(parte.id, "participacao", e.target.value)
                      }
                      className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5"
                    >
                      <option value="PRINCIPAL">Principal</option>
                      <option value="CONJUGE">Cônjuge</option>
                      <option value="ANUENTE">Interveniente anuente</option>
                      <option value="REPRESENTANTE">Representante</option>
                      <option value="PROCURADOR">Procurador</option>
                    </select>
                  </label>
                  {parte.participacao !== "PRINCIPAL" && (
                    <label className="text-sm font-medium text-slate-800">
                      Parte principal relacionada
                      <select
                        value={parte.principal_id || ""}
                        onChange={(e) =>
                          atualizarParte(
                            parte.id,
                            "principal_id",
                            e.target.value || null,
                          )
                        }
                        className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5"
                      >
                        <option value="">Não definida</option>
                        {principais.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.nome_completo || "Parte sem nome"}
                          </option>
                        ))}
                      </select>
                    </label>
                  )}
                  <label className="text-sm font-medium text-slate-800">
                    Modelo de qualificação
                    <select
                      value={parte.modo_qualificacao}
                      onChange={(e) =>
                        atualizarParte(
                          parte.id,
                          "modo_qualificacao",
                          e.target.value,
                        )
                      }
                      className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5"
                    >
                      <option value="INDIVIDUAL">Individual</option>
                      <option value="UNIAO_ESTAVEL">União estável</option>
                      <option value="CASAL_AMBOS_ASSINAM">
                        Casal — ambos assinam
                      </option>
                      <option value="CASAL_COM_ANUENTE">
                        Casal — cônjuge anuente
                      </option>
                      <option value="CASADO_APENAS_UM">
                        Casado — apenas um assina
                      </option>
                      <option value="EMPRESA_REPRESENTADA">
                        Empresa representada
                      </option>
                      <option value="PROCURACAO">
                        Representado por procuração
                      </option>
                      <option value="ALVARA_JUDICIAL">
                        Representado por alvará judicial
                      </option>
                    </select>
                  </label>
                  <Campo
                    label={
                      parte.natureza === "JURIDICA"
                        ? "Nome da empresa"
                        : "Nome completo"
                    }
                    value={parte.nome_completo}
                    onChange={(v) =>
                      atualizarParte(parte.id, "nome_completo", v)
                    }
                    pendente={pendente("nome_completo")}
                  />
                  {parte.natureza === "FISICA" && (
                    <>
                      <Campo
                        label="CPF"
                        value={parte.cpf}
                        onChange={(v) => atualizarParte(parte.id, "cpf", v)}
                        pendente={pendente("cpf")}
                      />
                      <Campo
                        label="Nacionalidade"
                        value={parte.nacionalidade}
                        onChange={(v) =>
                          atualizarParte(parte.id, "nacionalidade", v)
                        }
                      />
                      <Campo
                        label="Capacidade"
                        value={parte.capacidade}
                        onChange={(v) =>
                          atualizarParte(parte.id, "capacidade", v)
                        }
                        placeholder="Ex.: maior e capaz"
                      />
                      <Campo
                        label="Estado civil"
                        value={parte.estado_civil}
                        onChange={(v) =>
                          atualizarParte(parte.id, "estado_civil", v)
                        }
                        pendente={pendente("estado_civil")}
                      />
                      <Campo
                        label="Profissão"
                        value={parte.profissao}
                        onChange={(v) =>
                          atualizarParte(parte.id, "profissao", v)
                        }
                        pendente={pendente("profissao")}
                      />
                      <Campo
                        label="Endereço"
                        value={parte.endereco}
                        onChange={(v) =>
                          atualizarParte(parte.id, "endereco", v)
                        }
                        pendente={pendente("endereco")}
                      />
                      <label className="text-sm font-medium text-slate-800">
                        União estável
                        <select
                          value={
                            parte.uniao_estavel === null
                              ? ""
                              : String(parte.uniao_estavel)
                          }
                          onChange={(e) =>
                            atualizarParte(
                              parte.id,
                              "uniao_estavel",
                              e.target.value === ""
                                ? null
                                : e.target.value === "true",
                            )
                          }
                          className="mt-1.5 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5"
                        >
                          <option value="">Não informado</option>
                          <option value="false">Não</option>
                          <option value="true">Sim</option>
                        </select>
                      </label>
                    </>
                  )}
                </div>

                {[
                  "CASAL_AMBOS_ASSINAM",
                  "CASAL_COM_ANUENTE",
                  "CASADO_APENAS_UM",
                ].includes(parte.modo_qualificacao) && (
                  <div className="mt-5 rounded-lg border border-slate-200 bg-white p-4">
                    <h6 className="mb-3 text-sm font-semibold text-slate-900">
                      Dados da certidão de casamento
                    </h6>
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                      <Campo
                        label="Matrícula"
                        value={parte.casamento.matricula}
                        onChange={(v) =>
                          atualizarGrupo(parte.id, "casamento", "matricula", v)
                        }
                      />
                      <Campo
                        label="Data do registro/celebração"
                        value={parte.casamento.data_registro}
                        onChange={(v) =>
                          atualizarGrupo(
                            parte.id,
                            "casamento",
                            "data_registro",
                            v,
                          )
                        }
                      />
                      <Campo
                        label="Regime de bens"
                        value={parte.casamento.regime_bens}
                        onChange={(v) =>
                          atualizarGrupo(
                            parte.id,
                            "casamento",
                            "regime_bens",
                            v,
                          )
                        }
                      />
                      <Campo
                        label="Data da certidão"
                        value={parte.casamento.data_certidao}
                        onChange={(v) =>
                          atualizarGrupo(
                            parte.id,
                            "casamento",
                            "data_certidao",
                            v,
                          )
                        }
                      />
                      <Campo
                        label="Selo digital"
                        value={parte.casamento.selo_digital}
                        onChange={(v) =>
                          atualizarGrupo(
                            parte.id,
                            "casamento",
                            "selo_digital",
                            v,
                          )
                        }
                      />
                    </div>
                  </div>
                )}
                {parte.natureza === "JURIDICA" && (
                  <div className="mt-5 rounded-lg border border-slate-200 bg-white p-4">
                    <h6 className="mb-3 text-sm font-semibold text-slate-900">
                      Empresa e poderes de representação
                    </h6>
                    <div className="grid gap-4 md:grid-cols-2">
                      <Campo
                        label="CNPJ"
                        value={parte.empresa.cnpj}
                        onChange={(v) =>
                          atualizarGrupo(parte.id, "empresa", "cnpj", v)
                        }
                      />
                      <Campo
                        label="NIRE"
                        value={parte.empresa.nire}
                        onChange={(v) =>
                          atualizarGrupo(parte.id, "empresa", "nire", v)
                        }
                      />
                      <Campo
                        label="Endereço da empresa"
                        value={parte.empresa.endereco}
                        onChange={(v) =>
                          atualizarGrupo(parte.id, "empresa", "endereco", v)
                        }
                      />
                      <Campo
                        label="Cláusula de poderes"
                        value={parte.empresa.clausula_poderes}
                        onChange={(v) =>
                          atualizarGrupo(
                            parte.id,
                            "empresa",
                            "clausula_poderes",
                            v,
                          )
                        }
                      />
                      <div className="md:col-span-2">
                        <Campo
                          label="Trecho dos poderes"
                          value={parte.empresa.descricao_poderes}
                          onChange={(v) =>
                            atualizarGrupo(
                              parte.id,
                              "empresa",
                              "descricao_poderes",
                              v,
                            )
                          }
                          multiline
                        />
                      </div>
                    </div>
                  </div>
                )}
                {parte.modo_qualificacao === "PROCURACAO" && (
                  <div className="mt-5 rounded-lg border border-slate-200 bg-white p-4">
                    <h6 className="mb-1 text-sm font-semibold text-slate-900">
                      Representação por procuração
                    </h6>
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                      <Campo
                        label="Lavrada em"
                        value={parte.procuracao.lavrada_em}
                        onChange={(v) =>
                          atualizarGrupo(
                            parte.id,
                            "procuracao",
                            "lavrada_em",
                            v,
                          )
                        }
                      />
                      <Campo
                        label="Livro"
                        value={parte.procuracao.livro}
                        onChange={(v) =>
                          atualizarGrupo(parte.id, "procuracao", "livro", v)
                        }
                      />
                      <Campo
                        label="Folhas"
                        value={parte.procuracao.folhas}
                        onChange={(v) =>
                          atualizarGrupo(parte.id, "procuracao", "folhas", v)
                        }
                      />
                      <Campo
                        label="Tabelionato"
                        value={parte.procuracao.tabelionato}
                        onChange={(v) =>
                          atualizarGrupo(
                            parte.id,
                            "procuracao",
                            "tabelionato",
                            v,
                          )
                        }
                      />
                      <Campo
                        label="Cidade/comarca"
                        value={parte.procuracao.cidade_comarca}
                        onChange={(v) =>
                          atualizarGrupo(
                            parte.id,
                            "procuracao",
                            "cidade_comarca",
                            v,
                          )
                        }
                      />
                      <Campo
                        label="Emissão da certidão"
                        value={parte.procuracao.certidao_emitida_em}
                        onChange={(v) =>
                          atualizarGrupo(
                            parte.id,
                            "procuracao",
                            "certidao_emitida_em",
                            v,
                          )
                        }
                      />
                      <Campo
                        label="Selo digital"
                        value={parte.procuracao.selo_digital}
                        onChange={(v) =>
                          atualizarGrupo(
                            parte.id,
                            "procuracao",
                            "selo_digital",
                            v,
                          )
                        }
                      />
                      <Campo
                        label="Valor mínimo autorizado"
                        value={parte.procuracao.valor_minimo}
                        onChange={(v) =>
                          atualizarGrupo(
                            parte.id,
                            "procuracao",
                            "valor_minimo",
                            v,
                          )
                        }
                      />
                      <Campo
                        label="Valor máximo autorizado"
                        value={parte.procuracao.valor_maximo}
                        onChange={(v) =>
                          atualizarGrupo(
                            parte.id,
                            "procuracao",
                            "valor_maximo",
                            v,
                          )
                        }
                      />
                      <div className="md:col-span-2 lg:col-span-3">
                        <Campo
                          label="Poderes expressos"
                          value={parte.procuracao.poderes}
                          onChange={(v) =>
                            atualizarGrupo(parte.id, "procuracao", "poderes", v)
                          }
                          multiline
                        />
                      </div>
                    </div>
                  </div>
                )}
                {parte.modo_qualificacao === "ALVARA_JUDICIAL" && (
                  <div className="mt-5 rounded-lg border border-slate-200 bg-white p-4">
                    <h6 className="mb-1 text-sm font-semibold text-slate-900">
                      Representação por alvará judicial
                    </h6>
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                      <Campo
                        label="Número do processo"
                        value={parte.alvara.numero_processo}
                        onChange={(v) =>
                          atualizarGrupo(
                            parte.id,
                            "alvara",
                            "numero_processo",
                            v,
                          )
                        }
                      />
                      <Campo
                        label="Juízo"
                        value={parte.alvara.juizo}
                        onChange={(v) =>
                          atualizarGrupo(parte.id, "alvara", "juizo", v)
                        }
                      />
                      <Campo
                        label="Data da decisão"
                        value={parte.alvara.data_decisao}
                        onChange={(v) =>
                          atualizarGrupo(parte.id, "alvara", "data_decisao", v)
                        }
                      />
                      <Campo
                        label="Validade indicada"
                        value={parte.alvara.data_validade}
                        onChange={(v) =>
                          atualizarGrupo(parte.id, "alvara", "data_validade", v)
                        }
                      />
                      <Campo
                        label="Representante indicado"
                        value={parte.alvara.representante}
                        onChange={(v) =>
                          atualizarGrupo(parte.id, "alvara", "representante", v)
                        }
                      />
                      <Campo
                        label="Valor mínimo autorizado"
                        value={parte.alvara.valor_minimo}
                        onChange={(v) =>
                          atualizarGrupo(parte.id, "alvara", "valor_minimo", v)
                        }
                      />
                      <Campo
                        label="Valor máximo autorizado"
                        value={parte.alvara.valor_maximo}
                        onChange={(v) =>
                          atualizarGrupo(parte.id, "alvara", "valor_maximo", v)
                        }
                      />
                      <div className="md:col-span-2 lg:col-span-3">
                        <Campo
                          label="Poderes e condições"
                          value={parte.alvara.poderes}
                          onChange={(v) =>
                            atualizarGrupo(parte.id, "alvara", "poderes", v)
                          }
                          multiline
                        />
                      </div>
                    </div>
                  </div>
                )}

                <div className="mt-4 flex flex-col gap-3 border-t border-slate-200 pt-4 lg:flex-row lg:items-start lg:justify-between">
                  <label className="inline-flex items-center gap-2 text-sm font-medium text-slate-800">
                    <input
                      type="checkbox"
                      checked={parte.confirmado}
                      onChange={(e) =>
                        atualizarParte(parte.id, "confirmado", e.target.checked)
                      }
                      className="h-4 w-4"
                    />
                    Dados conferidos no documento original
                  </label>
                  {qualificacao && (
                    <details className="max-w-2xl rounded-lg border border-slate-200 bg-white p-3">
                      <summary className="cursor-pointer text-sm font-medium text-slate-800">
                        Prévia da qualificação
                      </summary>
                      <p className="mt-3 text-sm leading-6 text-slate-700">
                        {qualificacao.texto}
                      </p>
                      {qualificacao.pendencias.length > 0 && (
                        <p className="mt-2 text-xs text-amber-700">
                          Pendências: {qualificacao.pendencias.join(", ")}
                        </p>
                      )}
                    </details>
                  )}
                </div>
              </article>
            );
          })
        )}

        <div className="border-t border-slate-200 pt-6">
          <h4 className="font-semibold text-slate-900">Valor do ato</h4>
          <div className="mt-4 grid gap-4 md:grid-cols-3">
            <Campo
              label="Valor da escritura"
              value={dados.negocio.valor_escritura}
              onChange={(v) => atualizarNegocio("valor_escritura", v)}
              placeholder="Ex.: R$ 350.000,00"
            />
            <label className="flex items-end gap-2 pb-2.5 text-sm font-medium text-slate-800">
              <input
                type="checkbox"
                checked={dados.negocio.confirmado}
                onChange={(e) =>
                  atualizarNegocio("confirmado", e.target.checked)
                }
                className="h-4 w-4"
              />
              Valor conferido no documento do negócio
            </label>
            <div className="md:col-span-3">
              <Campo
                label="Forma de pagamento da negociação"
                value={dados.negocio.forma_pagamento}
                onChange={(v) => atualizarNegocio("forma_pagamento", v)}
                multiline
                placeholder="Descreva sinal, parcelas, transferências e demais condições previstas."
              />
            </div>
            <div className="md:col-span-3">
              <Campo
                label="Observações sobre o negócio"
                value={dados.negocio.observacoes}
                onChange={(v) => atualizarNegocio("observacoes", v)}
                multiline
              />
            </div>
          </div>
          {dados.alertas_valor.length > 0 && (
            <div className="mt-4 rounded-lg border-2 border-red-300 bg-red-50 p-4">
              <div className="flex gap-2">
                <AlertTriangle
                  size={19}
                  className="mt-0.5 shrink-0 text-red-700"
                />
                <div>
                  <p className="text-sm font-semibold text-red-900">
                    Conferir limites de representação
                  </p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-red-800">
                    {dados.alertas_valor.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                  <p className="mt-2 text-xs text-red-700">
                    Este alerta é uma comparação numérica, não uma conclusão
                    jurídica.
                  </p>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 pt-6">
          <h4 className="font-semibold text-slate-900">Imóvel e matrícula</h4>
          <div className="mt-4 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
            <Campo
              label="Matrícula"
              value={dados.imovel.matricula}
              onChange={(v) => atualizarImovel("matricula", v)}
              pendente={!dados.imovel.matricula}
            />
            <Campo
              label="Logradouro"
              value={dados.imovel.logradouro}
              onChange={(v) => atualizarImovel("logradouro", v)}
            />
            <Campo
              label="Número"
              value={dados.imovel.numero}
              onChange={(v) => atualizarImovel("numero", v)}
            />
            <Campo
              label="Bairro"
              value={dados.imovel.bairro}
              onChange={(v) => atualizarImovel("bairro", v)}
            />
            <Campo
              label="Cidade"
              value={dados.imovel.cidade}
              onChange={(v) => atualizarImovel("cidade", v)}
            />
            <div className="md:col-span-2 lg:col-span-3">
              <Campo
                label="Descrição completa / última especialidade objetiva"
                value={dados.imovel.descricao_completa}
                onChange={(v) => atualizarImovel("descricao_completa", v)}
                multiline
                pendente={!dados.imovel.descricao_completa}
              />
            </div>
          </div>
          <div className="mt-5 flex items-center justify-between">
            <h5 className="text-sm font-semibold text-slate-900">
              Registros e averbações
            </h5>
            {editavel && (
              <button
                type="button"
                onClick={() =>
                  atualizarImovel("averbacoes", [
                    ...dados.imovel.averbacoes,
                    {
                      ordem: dados.imovel.averbacoes.length + 1,
                      rotulo: `Av.${dados.imovel.averbacoes.length + 1}`,
                      resumo: "",
                    },
                  ])
                }
                className="inline-flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-2 text-xs font-medium"
              >
                <Plus size={14} />
                Adicionar
              </button>
            )}
          </div>
          <div className="mt-3 space-y-3">
            {dados.imovel.averbacoes.map((item, indice) => (
              <div
                key={`${item.rotulo}-${indice}`}
                className="grid gap-3 rounded-lg border border-slate-200 p-3 md:grid-cols-[120px_1fr_auto]"
              >
                <Campo
                  label="R./Av."
                  value={item.rotulo}
                  onChange={(v) =>
                    atualizarImovel(
                      "averbacoes",
                      dados.imovel.averbacoes.map((atual, pos) =>
                        pos === indice ? { ...atual, rotulo: v } : atual,
                      ),
                    )
                  }
                />
                <Campo
                  label="Resumo"
                  value={item.resumo}
                  onChange={(v) =>
                    atualizarImovel(
                      "averbacoes",
                      dados.imovel.averbacoes.map((atual, pos) =>
                        pos === indice ? { ...atual, resumo: v } : atual,
                      ),
                    )
                  }
                />
                {editavel && (
                  <button
                    type="button"
                    onClick={() =>
                      atualizarImovel(
                        "averbacoes",
                        dados.imovel.averbacoes
                          .filter((_, pos) => pos !== indice)
                          .map((atual, pos) => ({ ...atual, ordem: pos + 1 })),
                      )
                    }
                    className="self-end rounded-lg p-2.5 text-red-600"
                  >
                    <Trash2 size={17} />
                  </button>
                )}
              </div>
            ))}
          </div>
          {dados.imovel.descricao_utilizada && (
            <div className="mt-4 rounded-lg border border-blue-200 bg-blue-50 p-4">
              <p className="text-xs font-semibold uppercase text-blue-700">
                Descrição sugerida para conferência
              </p>
              <p className="mt-2 text-sm leading-6 text-blue-950">
                {dados.imovel.descricao_utilizada}
              </p>
            </div>
          )}
          <label className="mt-4 inline-flex items-center gap-2 text-sm font-medium text-slate-800">
            <input
              type="checkbox"
              checked={dados.imovel.confirmado}
              onChange={(e) => atualizarImovel("confirmado", e.target.checked)}
              className="h-4 w-4"
            />
            Matrícula e descrição conferidas no original
          </label>
        </div>

        {dados.pendencias.length > 0 ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
            <div className="flex gap-2">
              <AlertTriangle
                size={18}
                className="mt-0.5 shrink-0 text-amber-700"
              />
              <div>
                <p className="text-sm font-semibold text-amber-900">
                  Pendências não bloqueantes
                </p>
                <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-amber-800">
                  {dados.pendencias.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </div>
            </div>
          </div>
        ) : (
          <div className="flex gap-2 rounded-lg border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
            <CheckCircle2 size={18} />
            Nenhuma pendência estrutural identificada.
          </div>
        )}
      </div>
    </section>
  );
}
