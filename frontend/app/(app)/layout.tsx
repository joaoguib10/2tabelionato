"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";

import Sidebar from "../../components/Sidebar";
import Header from "../../components/Header";
import PilotPreview from "../../components/PilotPreview";
import { useAuth } from "../../context/AuthContext";
import { apiFetch } from "../../lib/api";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  const [consultaOnlyMode, setConsultaOnlyMode] = useState<boolean | null>(
    null,
  );

  useEffect(() => {
    let ativo = true;
    apiFetch("/api/status")
      .then(async (response) => {
        if (!response?.ok) return true;
        const status = (await response.json()) as {
          consulta_only_mode?: boolean;
        };
        return status.consulta_only_mode !== false;
      })
      .catch(() => true)
      .then((modo) => {
        if (ativo) setConsultaOnlyMode(modo);
      });
    return () => {
      ativo = false;
    };
  }, []);

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  const rotaForaDoPiloto = ["/minuta", "/orcamentos"].some(
    (rota) => pathname === rota || pathname.startsWith(`${rota}/`),
  );
  const paginaDemonstrativa =
    pathname === "/analise"
      ? "analise"
      : pathname === "/ata-notarial"
        ? "ata-notarial"
        : null;

  useEffect(() => {
    if (consultaOnlyMode && rotaForaDoPiloto) {
      router.replace("/consultar");
    }
  }, [consultaOnlyMode, rotaForaDoPiloto, router]);

  if (loading || consultaOnlyMode === null) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-100">
        <p className="text-sm text-slate-500">Carregando sistema...</p>
      </div>
    );
  }

  if (!user || (consultaOnlyMode && rotaForaDoPiloto)) {
    return null;
  }

  return (
    <div className="flex min-h-screen bg-slate-100">
      <Sidebar consultaOnlyMode={consultaOnlyMode} />

      <div className="flex min-w-0 flex-1 flex-col">
        <Header />

        <main className="min-w-0 flex-1">
          {consultaOnlyMode && paginaDemonstrativa ? (
            <PilotPreview pagina={paginaDemonstrativa} />
          ) : (
            children
          )}
        </main>
      </div>
    </div>
  );
}
