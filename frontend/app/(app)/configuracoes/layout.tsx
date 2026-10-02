"use client";
import { useAuth } from "../../../context/AuthContext";

export default function ConfiguracoesLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const { user } = useAuth();
  if (user?.role !== "ADMIN")
    return <p className="p-8 text-slate-900">Área exclusiva do ADMIN.</p>;
  return children;
}
