"use client";

import {
  ClipboardCheck,
  FilePenLine,
  FileText,
  History,
  Lightbulb,
  Search,
  Settings,
} from "lucide-react";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "../context/AuthContext";

export default function Sidebar() {
  const { user } = useAuth();
  const pathname = usePathname();

  const isAdmin = user?.role === "ADMIN";

  function linkClass(href: string) {
    const ativo = pathname === href || pathname.startsWith(`${href}/`);

    return `flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
      ativo
        ? "bg-slate-800 text-white"
        : "text-slate-300 hover:bg-slate-800 hover:text-white"
    }`;
  }

  return (
    <aside className="sticky top-0 flex h-screen w-64 shrink-0 flex-col bg-slate-950 text-white">
      <div className="border-b border-slate-800 px-6 py-6">
        <h1 className="text-xl font-bold tracking-tight">Tabeleão</h1>

        <p className="mt-1 text-xs text-slate-400">
          Assistente inteligente do tabelionato
        </p>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-5">
        <div className="space-y-1">
          <Link href="/consultar" className={linkClass("/consultar")}>
            <Search size={18} />
            <span>Consulta</span>
          </Link>

          <Link
            href="/novos-entendimentos"
            className={linkClass("/novos-entendimentos")}
          >
            <Lightbulb size={18} />
            <span>Novos entendimentos</span>
          </Link>

          <Link href="/documentos" className={linkClass("/documentos")}>
            <FileText size={18} />
            <span>Documentos</span>
          </Link>

          <Link href="/analise" className={linkClass("/analise")}>
            <ClipboardCheck size={18} />
            <span>Análise</span>
          </Link>

          <Link href="/ata-notarial" className={linkClass("/ata-notarial")}>
            <FilePenLine size={18} />
            <span>Ata Notarial</span>
          </Link>

          <Link href="/historico" className={linkClass("/historico")}>
            <History size={18} />
            <span>Histórico</span>
          </Link>
        </div>

        {isAdmin && (
          <div className="space-y-1">
            <Link href="/revisoes" className={linkClass("/revisoes")}>
              <ClipboardCheck size={18} />
              <span>Revisões</span>
            </Link>

            <Link href="/configuracoes" className={linkClass("/configuracoes")}>
              <Settings size={18} />
              <span>Configurações</span>
            </Link>
          </div>
        )}
      </nav>

      <div className="border-t border-slate-800 px-6 py-4">
        <p className="text-xs text-slate-500">Tabeleão</p>

        <p className="mt-1 text-xs text-slate-600">Sistema interno</p>
      </div>
    </aside>
  );
}
