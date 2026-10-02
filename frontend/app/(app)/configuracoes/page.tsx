import Link from "next/link";
import { Users } from "lucide-react";

export default function ConfiguracoesPage() {
  return (
    <div className="min-h-full bg-slate-100 p-6 lg:p-8">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold text-slate-900">Configurações</h1>
      </div>

      <div className="grid max-w-5xl gap-4 md:grid-cols-2">
        <Link
          href="/configuracoes/usuarios"
          className="group rounded-xl border border-slate-200 bg-white p-6 shadow-sm transition hover:-translate-y-0.5 hover:border-slate-300 hover:shadow-md"
        >
          <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-slate-100 text-slate-700">
            <Users size={21} />
          </div>

          <h2 className="mt-5 text-base font-semibold text-slate-900">
            Usuários
          </h2>

          <p className="mt-2 text-sm leading-6 text-slate-500">
            Crie, edite, ative ou desative os usuários do sistema.
          </p>
        </Link>
      </div>
    </div>
  );
}
