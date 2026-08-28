import {
  Home,
  Search,
  BookOpen,
  FileText,
  History,
  Settings,
} from "lucide-react";

export default function Sidebar() {
  return (
    <aside className="flex min-h-screen w-64 flex-col bg-slate-950 text-white">
      {/* Logo */}
      <div className="px-6 py-6">
        <h1 className="text-xl font-bold tracking-tight">
          Cartório IA
        </h1>

        <p className="mt-1 text-xs text-slate-400">
          Assistente do tabelionato
        </p>
      </div>

      {/* Menu principal */}
      <nav className="flex-1 px-3">
        <p className="px-3 pb-2 text-xs font-semibold uppercase tracking-wider text-slate-500">
          Principal
        </p>

        <div className="space-y-1">
          <a
            href="#"
            className="flex items-center gap-3 rounded-lg bg-slate-800 px-3 py-2.5 text-sm font-medium"
          >
            <Home size={18} />
            <span>Início</span>
          </a>

          <a
            href="#"
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-slate-300 transition-colors hover:bg-slate-800 hover:text-white"
          >
            <Search size={18} />
            <span>Consultar</span>
          </a>

          <a
            href="#"
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-slate-300 transition-colors hover:bg-slate-800 hover:text-white"
          >
            <BookOpen size={18} />
            <span>Base de conhecimento</span>
          </a>

          <a
            href="#"
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-slate-300 transition-colors hover:bg-slate-800 hover:text-white"
          >
            <FileText size={18} />
            <span>Documentos</span>
          </a>

          <a
            href="#"
            className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-slate-300 transition-colors hover:bg-slate-800 hover:text-white"
          >
            <History size={18} />
            <span>Histórico</span>
          </a>
        </div>
      </nav>

      {/* Configurações */}
      <div className="border-t border-slate-800 p-3">
        <a
          href="#"
          className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm text-slate-300 transition-colors hover:bg-slate-800 hover:text-white"
        >
          <Settings size={18} />
          <span>Configurações</span>
        </a>
      </div>
    </aside>
  );
}