import {
  ClipboardCheck,
  FileArchive,
  FilePenLine,
  FileText,
  Plus,
  Search,
  Upload,
} from "lucide-react";

type PilotPreviewProps = {
  pagina: "analise" | "ata-notarial";
};

const campo =
  "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-500 disabled:cursor-not-allowed";

function AvisoPreview() {
  return (
    <div
      role="status"
      className="mt-6 rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-900"
    >
      <strong>Em refatoração.</strong> Este módulo ainda não está funcionando.
    </div>
  );
}

function AnalisePreview() {
  return (
    <div className="min-h-full bg-slate-100 p-6 text-slate-900 lg:p-8">
      <div className="mx-auto max-w-7xl">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h1 className="text-2xl font-semibold">Análise</h1>
          <button
            type="button"
            disabled
            className="inline-flex min-h-10 items-center gap-2 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white opacity-50"
          >
            <Plus size={17} /> Nova análise
          </button>
        </div>
        <AvisoPreview />

        <section className="mt-6 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          <div className="grid gap-3 border-b border-slate-200 p-4 md:grid-cols-[1fr_16rem_auto]">
            <label className="relative">
              <Search
                size={17}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400"
              />
              <input
                disabled
                placeholder="Pesquisar análises"
                aria-label="Pesquisar análises"
                className={`${campo} pl-10`}
              />
            </label>
            <select disabled aria-label="Filtrar por status" className={campo}>
              <option>Todos os status</option>
            </select>
            <button
              type="button"
              disabled
              className="rounded-lg border border-slate-300 bg-white px-4 text-sm text-slate-600 opacity-50"
            >
              Atualizar
            </button>
          </div>

          <div className="flex min-h-48 flex-col items-center justify-center px-6 py-12 text-center">
            <ClipboardCheck size={25} className="text-slate-400" />
            <p className="mt-4 text-sm font-medium text-slate-800">
              Lista de análises
            </p>
            <p className="mt-1 max-w-md text-sm text-slate-500">
              Os casos e documentos não são carregados nesta visualização.
            </p>
          </div>
        </section>

        <section className="mt-6 grid gap-4 md:grid-cols-3">
          {[
            ["Documentos", "Arquivos e páginas vinculados ao caso."],
            ["Conferência", "Fatos e pendências para revisão humana."],
            ["Análise jurídica", "Fundamentos e decisão do responsável."],
          ].map(([titulo, descricao]) => (
            <div
              key={titulo}
              className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm"
            >
              <FileText size={18} className="text-slate-500" />
              <h2 className="mt-3 text-sm font-semibold">{titulo}</h2>
              <p className="mt-1 text-sm text-slate-500">{descricao}</p>
            </div>
          ))}
        </section>
      </div>
    </div>
  );
}

function AtaNotarialPreview() {
  return (
    <div className="min-h-full bg-slate-100 p-6 text-slate-900 lg:p-8">
      <div className="mx-auto max-w-6xl">
        <div className="flex items-center gap-3">
          <FilePenLine size={24} className="text-slate-600" />
          <h1 className="text-2xl font-semibold">Ata Notarial</h1>
        </div>
        <p className="mt-2 text-sm text-slate-600">
          Organização de uma conversa exportada para apoio à elaboração da ata.
        </p>
        <AvisoPreview />

        <section className="mt-6 rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
          <label className="block text-sm font-medium">
            Identificação do processo
            <div className="mt-2 flex flex-col gap-3 sm:flex-row">
              <input
                disabled
                placeholder="Número ou nome para localizar a Ata"
                className={`${campo} min-w-0 flex-1`}
              />
              <button
                type="button"
                disabled
                className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 text-sm text-white opacity-50"
              >
                <Plus size={17} /> Criar processo
              </button>
            </div>
          </label>
        </section>

        <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(17rem,0.8fr)_minmax(0,1.7fr)]">
          <section className="min-h-64 rounded-xl border border-slate-200 bg-white shadow-sm">
            <h2 className="border-b border-slate-200 px-5 py-4 text-sm font-semibold">
              Processos de Ata
            </h2>
            <div className="flex items-center gap-3 p-5 text-sm text-slate-500">
              <FileArchive size={18} /> Nenhum processo carregado nesta prévia.
            </div>
          </section>

          <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
            <h2 className="text-sm font-semibold">Exportação da conversa</h2>
            <p className="mt-1 text-sm text-slate-500">
              Área de envio e acompanhamento do processamento.
            </p>
            <div className="mt-5 rounded-lg border border-dashed border-slate-300 bg-slate-50 p-5">
              <label className="block text-sm font-medium">
                Arquivo ZIP ou RAR
                <input
                  disabled
                  type="file"
                  accept=".zip,.rar"
                  className="mt-2 block w-full rounded-lg border border-slate-300 bg-white p-2.5 text-sm text-slate-500"
                />
              </label>
              <button
                type="button"
                disabled
                className="mt-4 inline-flex min-h-11 items-center gap-2 rounded-lg bg-slate-900 px-4 text-sm text-white opacity-50"
              >
                <Upload size={17} /> Enviar e processar
              </button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default function PilotPreview({ pagina }: PilotPreviewProps) {
  return pagina === "analise" ? <AnalisePreview /> : <AtaNotarialPreview />;
}
