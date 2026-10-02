import { Calculator } from "lucide-react";

export default function OrcamentosPage() {
  return (
    <div className="min-h-full bg-slate-100 p-6 lg:p-8">
      <div className="mx-auto max-w-4xl">
        <p className="text-sm font-medium text-slate-500">Atendimento</p>
        <h1 className="mt-1 text-2xl font-semibold text-slate-900">
          Orçamentos
        </h1>
        <div className="mt-8 flex min-h-80 flex-col items-center justify-center rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
          <div className="flex h-14 w-14 items-center justify-center rounded-full bg-slate-100 text-slate-600">
            <Calculator size={25} />
          </div>
          <h2 className="mt-5 text-lg font-semibold text-slate-900">
            Módulo em preparação
          </h2>
          <p className="mt-2 max-w-md text-sm leading-6 text-slate-500">
            A página de orçamentos já está reservada. Os cálculos e tabelas de
            emolumentos serão implementados em uma próxima etapa.
          </p>
        </div>
      </div>
    </div>
  );
}
