"use client";

import { LogOut, UserCircle } from "lucide-react";

import { useAuth } from "../context/AuthContext";

export default function Header() {
  const { user, logout } = useAuth();

  return (
    <header className="flex h-16 items-center justify-end border-b border-slate-200 bg-white px-6">
      <div className="flex items-center gap-3">
        <UserCircle size={30} className="text-slate-400" />

        <div className="hidden sm:block">
          <p className="text-sm font-medium text-slate-900">{user?.nome}</p>
        </div>

        <button
          type="button"
          onClick={logout}
          className="rounded-lg p-2 text-slate-500 transition-colors hover:bg-slate-100 hover:text-red-600"
          aria-label="Sair"
          title="Sair"
        >
          <LogOut size={18} />
        </button>
      </div>
    </header>
  );
}
