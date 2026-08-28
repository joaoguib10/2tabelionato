import { Bell, UserCircle } from "lucide-react";

export default function Header() {
  return (
    <header className="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-6">
      <div>
        <h2 className="text-sm font-semibold text-slate-900">
          Início
        </h2>

        <p className="text-xs text-slate-500">
          Visão geral do Cartório IA
        </p>
      </div>

      <div className="flex items-center gap-4">
        <button
          type="button"
          className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-slate-900"
        >
          <Bell size={19} />
        </button>

        <div className="flex items-center gap-2 border-l border-slate-200 pl-4">
          <UserCircle size={28} className="text-slate-500" />

          <div className="hidden sm:block">
            <p className="text-sm font-medium text-slate-900">
              Usuário
            </p>

            <p className="text-xs text-slate-500">
              Tabelionato
            </p>
          </div>
        </div>
      </div>
    </header>
  );
}