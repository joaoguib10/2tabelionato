"use client";

import { FormEvent, useEffect, useState } from "react";
import {
  Clipboard,
  Download,
  FileImage,
  LoaderCircle,
  Plus,
  Sparkles,
  Trash2,
} from "lucide-react";

import { apiFetch } from "../../../lib/api";

type Pessoa = {
  nome: string;
  cpf: string;
  endereco: string;
  profissao: string;
  estadoCivil: string;
  regimeBens: string;
  dataEmissaoCertidao: string;
  dataValidadeCertidao: string;
  dataCasamento: string;
  dataRegistroCasamento: string;
};
type Imovel = {
  matricula: string;
  valorIndividual: string;
  observacoes: string;
};
type Modelo = {
  id: string;
  titulo: string;
  tipo_ato: string;
  versao: string | null;
  orgao_origem: string | null;
};
type Analise = {
  arquivo: string;
  finalidade: string;
  conteudo: string;
  dados_extraidos: Record<string, unknown>;
};
type ModeloUsado = {
  id: string;
  titulo: string;
  versao: string | null;
  orgao_origem: string | null;
};

const pessoaVazia = (): Pessoa => ({
  nome: "",
  cpf: "",
  endereco: "",
  profissao: "",
  estadoCivil: "",
  regimeBens: "",
  dataEmissaoCertidao: "",
  dataValidadeCertidao: "",
  dataCasamento: "",
  dataRegistroCasamento: "",
});
const imovelVazio = (): Imovel => ({
  matricula: "",
  valorIndividual: "",
  observacoes: "",
});

function valorTexto(valor: unknown): string {
  return typeof valor === "string" ? valor : "";
}

function extrairPessoas(analise: Analise): Partial<Pessoa>[] {
  const dados = analise.dados_extraidos || {};
  const lista = Array.isArray(dados.pessoas) ? dados.pessoas : [];
  const comuns = {
    estadoCivil: valorTexto(dados.estado_civil),
    regimeBens: valorTexto(dados.regime_bens),
    dataEmissaoCertidao: valorTexto(dados.data_emissao),
    dataValidadeCertidao: valorTexto(dados.data_validade),
    dataCasamento: valorTexto(dados.data_casamento),
    dataRegistroCasamento: valorTexto(dados.data_registro_casamento),
  };
  return lista
    .filter(
      (item): item is Record<string, unknown> =>
        !!item && typeof item === "object",
    )
    .map((item) => ({
      ...comuns,
      nome: valorTexto(item.nome),
      cpf: valorTexto(item.cpf),
      estadoCivil: valorTexto(item.estado_civil) || comuns.estadoCivil,
      regimeBens: valorTexto(item.regime_bens) || comuns.regimeBens,
      dataCasamento: valorTexto(item.data_casamento) || comuns.dataCasamento,
      dataRegistroCasamento:
        valorTexto(item.data_registro_casamento) ||
        comuns.dataRegistroCasamento,
    }));
}

function mesclarPessoas(
  atuais: Pessoa[],
  extraidas: Partial<Pessoa>[],
): Pessoa[] {
  if (!extraidas.length) return atuais;
  const quantidade = Math.max(atuais.length, extraidas.length);
  return Array.from({ length: quantidade }, (_, indice) => {
    const atual = atuais[indice] || pessoaVazia();
    const extraida = extraidas[indice] || {};
    return Object.fromEntries(
      Object.entries(atual).map(([campo, valor]) => [
        campo,
        valor || extraida[campo as keyof Pessoa] || "",
      ]),
    ) as Pessoa;
  });
}

function Campo({
  label,
  value,
  onChange,
  required = false,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (valor: string) => void;
  required?: boolean;
  type?: string;
}) {
  return (
    <label className="block text-sm text-slate-700">
      {label}
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900"
      />
    </label>
  );
}

export default function MinutaPage() {
  const [tipoAto, setTipoAto] = useState<"COMPRA_VENDA" | "DOACAO">(
    "COMPRA_VENDA",
  );
  const [modelos, setModelos] = useState<Modelo[]>([]);
  const [modeloId, setModeloId] = useState("");
  const [carregandoModelos, setCarregandoModelos] = useState(true);
  const [etapa, setEtapa] = useState<"DADOS" | "CONFERENCIA" | "RESULTADO">(
    "DADOS",
  );
  const [alienantes, setAlienantes] = useState<Pessoa[]>([pessoaVazia()]);
  const [adquirentes, setAdquirentes] = useState<Pessoa[]>([pessoaVazia()]);
  const [imoveis, setImoveis] = useState<Imovel[]>([imovelVazio()]);
  const [certidoesAlienantes, setCertidoesAlienantes] = useState<File[]>([]);
  const [certidoesAdquirentes, setCertidoesAdquirentes] = useState<File[]>([]);
  const [matriculas, setMatriculas] = useState<File[]>([]);
  const [pagamento, setPagamento] = useState("");
  const [valorNegociacao, setValorNegociacao] = useState("");
  const [houveCorretor, setHouveCorretor] = useState(false);
  const [dadosCorretor, setDadosCorretor] = useState("");
  const [tributoValor, setTributoValor] = useState("");
  const [tributoData, setTributoData] = useState("");
  const [parcelado, setParcelado] = useState(false);
  const [autorizacaoLavratura, setAutorizacaoLavratura] = useState("");
  const [analises, setAnalises] = useState<Analise[]>([]);
  const [confirmado, setConfirmado] = useState(false);
  const [processando, setProcessando] = useState(false);
  const [erro, setErro] = useState("");
  const [avisos, setAvisos] = useState<string[]>([]);
  const [minuta, setMinuta] = useState("");
  const [modeloUsado, setModeloUsado] = useState<ModeloUsado | null>(null);

  useEffect(() => {
    const inicio = window.setTimeout(() => {
      setCarregandoModelos(true);
      setModeloId("");
      apiFetch(`/api/minutas/modelos?tipo_ato=${tipoAto}`)
        .then(async (response) => {
          if (!response?.ok) {
            setModelos([]);
            setErro("Não foi possível carregar os modelos aprovados.");
            return;
          }
          const retorno = (await response.json()) as Modelo[];
          setModelos(retorno);
          setModeloId(retorno.length === 1 ? retorno[0].id : "");
        })
        .catch(() => setErro("Não foi possível conectar ao servidor."))
        .finally(() => setCarregandoModelos(false));
    }, 0);
    return () => window.clearTimeout(inicio);
  }, [tipoAto]);

  function dadosAtuais() {
    return {
      alienantes,
      adquirentes,
      imoveis,
      negociacao: { valor: valorNegociacao, descricaoPagamento: pagamento },
      corretor:
        tipoAto === "COMPRA_VENDA"
          ? { houve: houveCorretor, dados: dadosCorretor }
          : null,
      tributo: {
        tipo: tipoAto === "COMPRA_VENDA" ? "ITBI" : "ITCMD",
        valor: tributoValor,
        dataPagamento: tributoData,
        parcelado,
        autorizacaoLavratura:
          tipoAto === "COMPRA_VENDA" && parcelado ? autorizacaoLavratura : null,
      },
    };
  }

  function atualizarPessoa(
    grupo: "alienantes" | "adquirentes",
    indice: number,
    campo: keyof Pessoa,
    valor: string,
  ) {
    const setter = grupo === "alienantes" ? setAlienantes : setAdquirentes;
    setter((atuais) =>
      atuais.map((pessoa, posicao) =>
        posicao === indice ? { ...pessoa, [campo]: valor } : pessoa,
      ),
    );
  }

  function pessoas(
    titulo: string,
    grupo: "alienantes" | "adquirentes",
    itens: Pessoa[],
  ) {
    const setter = grupo === "alienantes" ? setAlienantes : setAdquirentes;
    return (
      <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-slate-900">{titulo}</h2>
          <button
            type="button"
            onClick={() => setter((atuais) => [...atuais, pessoaVazia()])}
            className="inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-xs"
          >
            <Plus size={14} /> Adicionar
          </button>
        </div>
        <div className="mt-4 space-y-4">
          {itens.map((pessoa, indice) => (
            <div key={indice} className="rounded-lg bg-slate-50 p-4">
              <div className="mb-3 flex justify-between text-xs text-slate-500">
                <span>Parte {indice + 1}</span>
                {itens.length > 1 && (
                  <button
                    type="button"
                    onClick={() =>
                      setter((atuais) =>
                        atuais.filter((_, posicao) => posicao !== indice),
                      )
                    }
                    aria-label="Remover parte"
                  >
                    <Trash2 size={15} />
                  </button>
                )}
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <Campo
                  label="Nome completo"
                  value={pessoa.nome}
                  onChange={(v) => atualizarPessoa(grupo, indice, "nome", v)}
                />
                <Campo
                  label="CPF"
                  value={pessoa.cpf}
                  onChange={(v) => atualizarPessoa(grupo, indice, "cpf", v)}
                />
                <Campo
                  label="Endereço"
                  value={pessoa.endereco}
                  onChange={(v) =>
                    atualizarPessoa(grupo, indice, "endereco", v)
                  }
                />
                <Campo
                  label="Profissão"
                  value={pessoa.profissao}
                  onChange={(v) =>
                    atualizarPessoa(grupo, indice, "profissao", v)
                  }
                />
                <Campo
                  label="Estado civil"
                  value={pessoa.estadoCivil}
                  onChange={(v) =>
                    atualizarPessoa(grupo, indice, "estadoCivil", v)
                  }
                />
                <Campo
                  label="Regime de bens"
                  value={pessoa.regimeBens}
                  onChange={(v) =>
                    atualizarPessoa(grupo, indice, "regimeBens", v)
                  }
                />
                <Campo
                  type="date"
                  label="Emissão da certidão"
                  value={pessoa.dataEmissaoCertidao}
                  onChange={(v) =>
                    atualizarPessoa(grupo, indice, "dataEmissaoCertidao", v)
                  }
                />
                <Campo
                  type="date"
                  label="Validade da certidão"
                  value={pessoa.dataValidadeCertidao}
                  onChange={(v) =>
                    atualizarPessoa(grupo, indice, "dataValidadeCertidao", v)
                  }
                />
                <Campo
                  type="date"
                  label="Casamento celebrado em"
                  value={pessoa.dataCasamento}
                  onChange={(v) =>
                    atualizarPessoa(grupo, indice, "dataCasamento", v)
                  }
                />
                <Campo
                  type="date"
                  label="Casamento registrado em"
                  value={pessoa.dataRegistroCasamento}
                  onChange={(v) =>
                    atualizarPessoa(grupo, indice, "dataRegistroCasamento", v)
                  }
                />
              </div>
            </div>
          ))}
        </div>
      </section>
    );
  }

  function anexos(formData: FormData) {
    certidoesAlienantes.forEach((arquivo) =>
      formData.append("certidoes_alienantes", arquivo),
    );
    certidoesAdquirentes.forEach((arquivo) =>
      formData.append("certidoes_adquirentes", arquivo),
    );
    matriculas.forEach((arquivo) => formData.append("matriculas", arquivo));
  }

  async function analisar(evento: FormEvent) {
    evento.preventDefault();
    if (!modeloId) {
      setErro("Selecione um modelo de minuta aprovado.");
      return;
    }
    setProcessando(true);
    setErro("");
    setAvisos([]);
    const formData = new FormData();
    anexos(formData);
    try {
      const response = await apiFetch("/api/minutas/analisar", {
        method: "POST",
        body: formData,
      });
      if (!response) return;
      const retorno = await response.json();
      if (!response.ok) {
        setErro(retorno.detail || "Não foi possível analisar os documentos.");
        return;
      }
      const documentosAnalisados = (retorno.documentos || []) as Analise[];
      setAnalises(documentosAnalisados);
      const dadosAlienantes = documentosAnalisados
        .filter((item) => item.finalidade.includes("vendedor/doador"))
        .flatMap(extrairPessoas);
      const dadosAdquirentes = documentosAnalisados
        .filter((item) => item.finalidade.includes("comprador/donatário"))
        .flatMap(extrairPessoas);
      setAlienantes((atuais) => mesclarPessoas(atuais, dadosAlienantes));
      setAdquirentes((atuais) => mesclarPessoas(atuais, dadosAdquirentes));
      const imoveisExtraidos = documentosAnalisados
        .filter((item) => item.finalidade.includes("matrícula"))
        .map((item) => ({
          matricula: valorTexto(item.dados_extraidos.matricula),
          valorIndividual: "",
          observacoes: valorTexto(item.dados_extraidos.descricao_imovel),
        }));
      if (imoveisExtraidos.length) {
        setImoveis((atuais) =>
          atuais
            .map((item, indice) => ({
              ...item,
              matricula:
                item.matricula || imoveisExtraidos[indice]?.matricula || "",
              observacoes:
                item.observacoes || imoveisExtraidos[indice]?.observacoes || "",
            }))
            .concat(imoveisExtraidos.slice(atuais.length)),
        );
      }
      setAvisos(retorno.avisos || []);
      setConfirmado(false);
      setEtapa("CONFERENCIA");
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setProcessando(false);
    }
  }

  async function gerar() {
    if (!confirmado) {
      setErro("Confirme que os dados foram conferidos.");
      return;
    }
    setProcessando(true);
    setErro("");
    const formData = new FormData();
    formData.append("tipo_ato", tipoAto);
    formData.append("modelo_id", modeloId);
    formData.append("dados_json", JSON.stringify(dadosAtuais()));
    formData.append("documentos_json", JSON.stringify(analises));
    formData.append("confirmado", "true");
    try {
      const response = await apiFetch("/api/minutas/gerar", {
        method: "POST",
        body: formData,
      });
      if (!response) return;
      const retorno = await response.json();
      if (!response.ok) {
        setErro(retorno.detail || "Não foi possível gerar a minuta.");
        return;
      }
      setMinuta(retorno.minuta);
      setAvisos(retorno.avisos || []);
      setModeloUsado(retorno.modelo_utilizado);
      setEtapa("RESULTADO");
    } catch {
      setErro("Não foi possível conectar ao servidor.");
    } finally {
      setProcessando(false);
    }
  }

  async function copiar() {
    try {
      await navigator.clipboard.writeText(minuta);
    } catch {
      setErro("Não foi possível copiar a minuta.");
    }
  }

  async function exportar() {
    const response = await apiFetch("/api/minutas/exportar", {
      method: "POST",
      body: JSON.stringify({ minuta, titulo: "Minuta" }),
    });
    if (!response?.ok) {
      setErro("Não foi possível exportar a minuta.");
      return;
    }
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = "minuta-tabeleao.docx";
    link.click();
    URL.revokeObjectURL(url);
  }

  const modeloSelecionado = modelos.find((modelo) => modelo.id === modeloId);

  return (
    <div className="min-h-full bg-slate-100 p-6 text-slate-900 lg:p-8">
      <div className="mx-auto max-w-5xl">
        <div className="mb-7">
          <p className="text-sm font-medium text-slate-700">Escrituras</p>
          <h1 className="mt-1 text-2xl font-semibold text-slate-900">
            Nova minuta
          </h1>
          <p className="mt-2 text-sm text-slate-700">
            Anexe, confira e gere um rascunho com base em um modelo aprovado. Os
            anexos temporários não são salvos.
          </p>
        </div>
        <div className="mb-6 grid grid-cols-3 gap-2 text-center text-xs font-medium">
          <span
            className={`rounded-lg p-2 ${etapa === "DADOS" ? "bg-slate-900 text-white" : "bg-white text-slate-500"}`}
          >
            1. Dados
          </span>
          <span
            className={`rounded-lg p-2 ${etapa === "CONFERENCIA" ? "bg-slate-900 text-white" : "bg-white text-slate-500"}`}
          >
            2. Conferência
          </span>
          <span
            className={`rounded-lg p-2 ${etapa === "RESULTADO" ? "bg-slate-900 text-white" : "bg-white text-slate-500"}`}
          >
            3. Rascunho
          </span>
        </div>

        {etapa === "DADOS" && (
          <form onSubmit={analisar} className="space-y-6">
            <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="font-semibold text-slate-900">
                Tipo de ato e modelo
              </h2>
              <div className="mt-4 grid gap-3 sm:grid-cols-2">
                {(
                  [
                    ["COMPRA_VENDA", "Compra e Venda"],
                    ["DOACAO", "Doação"],
                  ] as const
                ).map(([valor, rotulo]) => (
                  <button
                    key={valor}
                    type="button"
                    onClick={() => setTipoAto(valor)}
                    className={`rounded-xl border p-4 text-left text-sm font-semibold ${tipoAto === valor ? "border-slate-900 bg-slate-900 text-white" : "border-slate-300 text-slate-700"}`}
                  >
                    {rotulo}
                  </button>
                ))}
              </div>
              <div className="mt-5">
                {carregandoModelos ? (
                  <p className="text-sm text-slate-500">
                    Carregando modelos...
                  </p>
                ) : modelos.length === 0 ? (
                  <p className="rounded-lg bg-amber-50 p-4 text-sm text-amber-800">
                    Ainda não existe modelo aprovado para este ato. Cadastre e
                    aprove um modelo em Documentos.
                  </p>
                ) : modelos.length === 1 ? (
                  <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-4">
                    <p className="text-sm font-semibold text-emerald-900">
                      {modelos[0].titulo}
                    </p>
                    <p className="mt-1 text-xs text-emerald-700">
                      {modelos[0].versao
                        ? `Versão ${modelos[0].versao}`
                        : "Sem versão informada"}{" "}
                      · {modelos[0].orgao_origem || "Origem não informada"}
                    </p>
                  </div>
                ) : (
                  <label className="text-sm text-slate-700">
                    Modelo aprovado
                    <select
                      required
                      value={modeloId}
                      onChange={(e) => setModeloId(e.target.value)}
                      className="mt-1 w-full rounded-lg border px-3 py-2.5"
                    >
                      <option value="">Selecione o modelo</option>
                      {modelos.map((modelo) => (
                        <option key={modelo.id} value={modelo.id}>
                          {modelo.titulo}
                          {modelo.versao ? ` · versão ${modelo.versao}` : ""}
                          {modelo.orgao_origem
                            ? ` · ${modelo.orgao_origem}`
                            : ""}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </div>
            </section>
            {pessoas(
              tipoAto === "COMPRA_VENDA" ? "Vendedores" : "Doadores",
              "alienantes",
              alienantes,
            )}
            <label className="block rounded-xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-700">
              <FileImage size={18} className="mb-2" />
              Certidões dos vendedores/doadores — PDF, JPG, JPEG ou PNG
              <input
                type="file"
                multiple
                accept=".pdf,.jpg,.jpeg,.png"
                onChange={(e) =>
                  setCertidoesAlienantes(Array.from(e.target.files || []))
                }
                className="mt-2 block w-full text-xs"
              />
            </label>
            {pessoas(
              tipoAto === "COMPRA_VENDA" ? "Compradores" : "Donatários",
              "adquirentes",
              adquirentes,
            )}
            <label className="block rounded-xl border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-700">
              <FileImage size={18} className="mb-2" />
              Certidões dos compradores/donatários
              <input
                type="file"
                multiple
                accept=".pdf,.jpg,.jpeg,.png"
                onChange={(e) =>
                  setCertidoesAdquirentes(Array.from(e.target.files || []))
                }
                className="mt-2 block w-full text-xs"
              />
            </label>
            <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex justify-between">
                <h2 className="font-semibold text-slate-900">Imóveis</h2>
                <button
                  type="button"
                  onClick={() =>
                    setImoveis((atuais) => [...atuais, imovelVazio()])
                  }
                  className="inline-flex items-center gap-1 rounded-lg border px-3 py-2 text-xs text-slate-900"
                >
                  <Plus size={14} /> Adicionar
                </button>
              </div>
              <div className="mt-4 space-y-3">
                {imoveis.map((imovel, indice) => (
                  <div
                    key={indice}
                    className="grid gap-3 rounded-lg bg-slate-50 p-4 md:grid-cols-3"
                  >
                    <Campo
                      label="Matrícula"
                      value={imovel.matricula}
                      onChange={(v) =>
                        setImoveis((atuais) =>
                          atuais.map((item, posicao) =>
                            posicao === indice
                              ? { ...item, matricula: v }
                              : item,
                          ),
                        )
                      }
                    />
                    <Campo
                      label="Valor individual"
                      value={imovel.valorIndividual}
                      onChange={(v) =>
                        setImoveis((atuais) =>
                          atuais.map((item, posicao) =>
                            posicao === indice
                              ? { ...item, valorIndividual: v }
                              : item,
                          ),
                        )
                      }
                    />
                    <Campo
                      label="Observações"
                      value={imovel.observacoes}
                      onChange={(v) =>
                        setImoveis((atuais) =>
                          atuais.map((item, posicao) =>
                            posicao === indice
                              ? { ...item, observacoes: v }
                              : item,
                          ),
                        )
                      }
                    />
                  </div>
                ))}
              </div>
              <label className="mt-4 block rounded-lg border border-dashed p-4 text-sm text-slate-700">
                Anexar matrículas
                <input
                  type="file"
                  multiple
                  accept=".pdf,.jpg,.jpeg,.png"
                  onChange={(e) =>
                    setMatriculas(Array.from(e.target.files || []))
                  }
                  className="mt-2 block w-full text-xs"
                />
              </label>
            </section>
            <section className="grid gap-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm md:grid-cols-2">
              <h2 className="md:col-span-2 font-semibold">
                Negociação, pagamento e tributo
              </h2>
              <Campo
                label="Valor total"
                value={valorNegociacao}
                onChange={setValorNegociacao}
              />
              <label className="md:col-span-2 text-sm">
                Forma de pagamento
                <textarea
                  required
                  value={pagamento}
                  onChange={(e) => setPagamento(e.target.value)}
                  rows={3}
                  className="mt-1 w-full rounded-lg border px-3 py-2.5"
                />
              </label>
              {tipoAto === "COMPRA_VENDA" && (
                <div className="md:col-span-2">
                  <label className="flex gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={houveCorretor}
                      onChange={(e) => setHouveCorretor(e.target.checked)}
                    />{" "}
                    Houve corretor de imóveis
                  </label>
                  {houveCorretor && (
                    <div className="mt-3">
                      <Campo
                        label="Dados do corretor"
                        value={dadosCorretor}
                        onChange={setDadosCorretor}
                      />
                    </div>
                  )}
                </div>
              )}
              <Campo
                label={
                  tipoAto === "COMPRA_VENDA"
                    ? "Valor do ITBI"
                    : "Valor do ITCMD"
                }
                value={tributoValor}
                onChange={setTributoValor}
              />
              <Campo
                type="date"
                label="Data de pagamento"
                value={tributoData}
                onChange={setTributoData}
              />
              <label className="flex gap-2 text-sm md:col-span-2">
                <input
                  type="checkbox"
                  checked={parcelado}
                  onChange={(e) => setParcelado(e.target.checked)}
                />{" "}
                Pagamento parcelado
              </label>
              {tipoAto === "COMPRA_VENDA" && parcelado && (
                <div className="md:col-span-2">
                  <Campo
                    label="Autorização de lavratura da prefeitura"
                    value={autorizacaoLavratura}
                    onChange={setAutorizacaoLavratura}
                    required
                  />
                </div>
              )}
            </section>
            {erro && (
              <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
                {erro}
              </p>
            )}
            <button
              disabled={processando || modelos.length === 0}
              className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white disabled:opacity-50"
            >
              {processando ? (
                <LoaderCircle size={18} className="animate-spin" />
              ) : (
                <Sparkles size={18} />
              )}
              {processando ? "Analisando..." : "Analisar documentos"}
            </button>
          </form>
        )}

        {etapa === "CONFERENCIA" && (
          <section className="space-y-5">
            <div className="rounded-xl border border-slate-200 bg-white p-6">
              <h2 className="font-semibold text-slate-900">
                Confira antes de gerar
              </h2>
              <p className="mt-2 text-sm text-slate-600">
                Os campos abaixo foram preenchidos sem substituir dados já
                digitados. Corrija qualquer leitura incorreta antes de
                confirmar.
              </p>
              <p className="mt-4 text-sm font-medium text-slate-800">
                Modelo: {modeloSelecionado?.titulo}
                {modeloSelecionado?.versao
                  ? ` · versão ${modeloSelecionado.versao}`
                  : ""}
              </p>
            </div>
            {pessoas(
              tipoAto === "COMPRA_VENDA"
                ? "Vendedores extraídos"
                : "Doadores extraídos",
              "alienantes",
              alienantes,
            )}
            {pessoas(
              tipoAto === "COMPRA_VENDA"
                ? "Compradores extraídos"
                : "Donatários extraídos",
              "adquirentes",
              adquirentes,
            )}
            {analises.length === 0 ? (
              <p className="rounded-xl bg-white p-6 text-sm text-slate-600">
                Nenhum anexo foi enviado. Confira os dados digitados antes de
                continuar.
              </p>
            ) : (
              analises.map((analise, indice) => (
                <article
                  key={`${analise.arquivo}-${indice}`}
                  className="rounded-xl border border-slate-200 bg-white p-6"
                >
                  <h3 className="font-semibold text-slate-900">
                    {analise.arquivo}
                  </h3>
                  <p className="mt-1 text-xs text-slate-600">
                    {analise.finalidade}
                  </p>
                  <label className="mt-4 block text-sm text-slate-700">
                    Texto extraído para conferência
                    <textarea
                      value={analise.conteudo}
                      onChange={(e) =>
                        setAnalises((atuais) =>
                          atuais.map((item, posicao) =>
                            posicao === indice
                              ? { ...item, conteudo: e.target.value }
                              : item,
                          ),
                        )
                      }
                      rows={7}
                      className="mt-1 w-full rounded-lg border px-3 py-2.5 text-sm"
                    />
                  </label>
                </article>
              ))
            )}
            {!!avisos.length && (
              <div className="rounded-lg bg-amber-50 p-4 text-sm text-amber-800">
                {avisos.map((aviso) => (
                  <p key={aviso}>{aviso}</p>
                ))}
              </div>
            )}
            <label className="flex items-start gap-3 rounded-xl border border-slate-200 bg-white p-5 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={confirmado}
                onChange={(e) => setConfirmado(e.target.checked)}
                className="mt-0.5"
              />{" "}
              Conferi os dados, documentos, datas, partes, valores, tributos e
              averbações.
            </label>
            {erro && (
              <p className="rounded-lg bg-red-50 p-3 text-sm text-red-700">
                {erro}
              </p>
            )}
            <div className="flex gap-3">
              <button
                type="button"
                onClick={() => setEtapa("DADOS")}
                className="flex-1 rounded-xl border bg-white px-5 py-3 text-sm font-medium"
              >
                Voltar e corrigir dados
              </button>
              <button
                type="button"
                onClick={gerar}
                disabled={processando || !confirmado}
                className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-slate-900 px-5 py-3 text-sm font-semibold text-white disabled:opacity-50"
              >
                {processando ? (
                  <LoaderCircle size={18} className="animate-spin" />
                ) : (
                  <Sparkles size={18} />
                )}{" "}
                Gerar rascunho
              </button>
            </div>
          </section>
        )}

        {etapa === "RESULTADO" && (
          <section className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="font-semibold text-slate-900">Rascunho da minuta</h2>
            {modeloUsado && (
              <p className="mt-2 text-sm text-slate-500">
                Modelo utilizado: {modeloUsado.titulo}
                {modeloUsado.versao ? ` · versão ${modeloUsado.versao}` : ""}
                {modeloUsado.orgao_origem
                  ? ` · ${modeloUsado.orgao_origem}`
                  : ""}
              </p>
            )}
            <textarea
              value={minuta}
              onChange={(e) => setMinuta(e.target.value)}
              rows={24}
              className="mt-5 w-full rounded-xl border border-slate-300 p-4 text-sm leading-6 text-slate-800"
            />
            {!!avisos.length && (
              <div className="mt-4 rounded-lg bg-amber-50 p-4 text-xs text-amber-800">
                {avisos.map((aviso) => (
                  <p key={aviso}>{aviso}</p>
                ))}
              </div>
            )}
            {erro && (
              <p className="mt-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
                {erro}
              </p>
            )}
            <div className="mt-5 flex flex-wrap gap-3">
              <button
                type="button"
                onClick={copiar}
                className="inline-flex items-center gap-2 rounded-lg border px-4 py-2.5 text-sm"
              >
                <Clipboard size={16} /> Copiar
              </button>
              <button
                type="button"
                onClick={exportar}
                className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm text-white"
              >
                <Download size={16} /> Exportar DOCX
              </button>
              <button
                type="button"
                onClick={() => setEtapa("CONFERENCIA")}
                className="rounded-lg border px-4 py-2.5 text-sm"
              >
                Voltar à conferência
              </button>
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
