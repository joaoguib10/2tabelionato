"use client";

import { useEffect, useState } from "react";
import {
  KeyRound,
  Pencil,
  Trash2,
  UserCheck,
  UserPlus,
  UserX,
} from "lucide-react";

import { apiFetch } from "../../../../lib/api";
import { useAuth } from "../../../../context/AuthContext";

type User = {
  id: string;
  nome: string;
  username: string;
  role: "ADMIN" | "USUARIO";
  ativo: boolean;
};

export default function UsuariosPage() {
  const { user } = useAuth();

  const [usuarios, setUsuarios] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [showModal, setShowModal] = useState(false);
  const [showPasswordModal, setShowPasswordModal] = useState(false);

  const [editingUser, setEditingUser] = useState<User | null>(null);

  const [nome, setNome] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<User["role"]>("USUARIO");

  const [newPassword, setNewPassword] = useState("");

  const podeCriarAdmin = user?.role === "ADMIN";

  async function carregarUsuarios() {
    setLoading(true);
    setError("");

    try {
      const response = await apiFetch("/api/usuarios");

      if (!response || !response.ok) {
        setError("Não foi possível carregar os usuários.");
        return;
      }

      const data = await response.json();

      setUsuarios(data);
    } catch {
      setError("Não foi possível conectar ao servidor.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const inicio = window.setTimeout(() => carregarUsuarios(), 0);
    return () => window.clearTimeout(inicio);
  }, []);

  function abrirNovoUsuario() {
    setEditingUser(null);
    setNome("");
    setUsername("");
    setPassword("");
    setRole("USUARIO");
    setShowModal(true);
    setError("");
  }

  function abrirEdicao(usuario: User) {
    setEditingUser(usuario);
    setNome(usuario.nome);
    setUsername(usuario.username);
    setRole(usuario.role);
    setPassword("");
    setShowModal(true);
    setError("");
  }

  function abrirRedefinicaoSenha(usuario: User) {
    setEditingUser(usuario);
    setNewPassword("");
    setShowPasswordModal(true);
    setError("");
  }

  async function excluirUsuario(usuario: User) {
    const confirmar = window.confirm(
      `Tem certeza que deseja excluir o usuário "${usuario.nome}"? Esta ação não poderá ser desfeita.`,
    );

    if (!confirmar) {
      return;
    }

    setError("");

    const response = await apiFetch(`/api/usuarios/${usuario.id}`, {
      method: "DELETE",
    });

    if (!response || !response.ok) {
      const data = response ? await response.json() : null;

      setError(data?.detail || "Não foi possível excluir o usuário.");

      return;
    }

    await carregarUsuarios();
  }

  async function salvarUsuario(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    try {
      if (editingUser) {
        const response = await apiFetch(`/api/usuarios/${editingUser.id}`, {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            nome,
            role,
          }),
        });

        const data = response ? await response.json() : null;

        if (!response || !response.ok) {
          setError(data?.detail || "Não foi possível atualizar o usuário.");
          return;
        }
      } else {
        const response = await apiFetch("/api/usuarios", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            nome,
            username,
            password,
            role,
          }),
        });

        const data = response ? await response.json() : null;

        if (!response || !response.ok) {
          setError(data?.detail || "Não foi possível criar o usuário.");
          return;
        }
      }

      setShowModal(false);
      setEditingUser(null);
      setNome("");
      setUsername("");
      setPassword("");
      setRole("USUARIO");

      await carregarUsuarios();
    } catch {
      setError("Não foi possível conectar ao servidor.");
    }
  }

  async function alterarStatus(usuario: User) {
    setError("");

    const response = await apiFetch(`/api/usuarios/${usuario.id}/status`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ativo: !usuario.ativo,
      }),
    });

    if (!response || !response.ok) {
      const data = response ? await response.json() : null;

      setError(data?.detail || "Não foi possível alterar o status.");

      return;
    }

    await carregarUsuarios();
  }

  async function salvarNovaSenha(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");

    if (!editingUser) {
      return;
    }

    const response = await apiFetch(`/api/usuarios/${editingUser.id}/senha`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        password: newPassword,
      }),
    });

    if (!response || !response.ok) {
      const data = response ? await response.json() : null;

      setError(data?.detail || "Não foi possível redefinir o senha.");

      return;
    }

    setNewPassword("");
    setEditingUser(null);
    setShowPasswordModal(false);
  }

  return (
    <div className="min-h-full bg-slate-100 p-6 text-slate-900 lg:p-8">
      <div className="mb-8 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <p className="text-sm font-medium text-slate-700">Administração</p>

          <h1 className="mt-1 text-2xl font-semibold text-slate-900">
            Usuários
          </h1>

          <p className="mt-2 text-sm text-slate-700">
            Gerencie os usuários e seus acessos ao sistema.
          </p>
        </div>

        <button
          type="button"
          onClick={abrirNovoUsuario}
          className="inline-flex items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800"
        >
          <UserPlus size={17} />
          Novo usuário
        </button>
      </div>

      {error && (
        <div className="mb-5 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px]">
            <thead className="border-b border-slate-200 bg-slate-50">
              <tr>
                <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-700">
                  Usuário
                </th>

                <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-700">
                  Perfil
                </th>

                <th className="px-6 py-4 text-left text-xs font-semibold uppercase tracking-wide text-slate-700">
                  Status
                </th>

                <th className="px-6 py-4 text-right text-xs font-semibold uppercase tracking-wide text-slate-700">
                  Ações
                </th>
              </tr>
            </thead>

            <tbody className="divide-y divide-slate-100">
              {loading ? (
                <tr>
                  <td
                    colSpan={4}
                    className="px-6 py-10 text-center text-sm text-slate-500"
                  >
                    Carregando usuários...
                  </td>
                </tr>
              ) : usuarios.length === 0 ? (
                <tr>
                  <td
                    colSpan={4}
                    className="px-6 py-10 text-center text-sm text-slate-500"
                  >
                    Nenhum usuário encontrado.
                  </td>
                </tr>
              ) : (
                usuarios.map((usuario) => (
                  <tr key={usuario.id} className="transition hover:bg-slate-50">
                    <td className="px-6 py-4">
                      <p className="text-sm font-medium text-slate-900">
                        {usuario.nome}
                      </p>

                      <p className="mt-0.5 text-xs text-slate-700">
                        @{usuario.username}
                      </p>
                    </td>

                    <td className="px-6 py-4">
                      <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-700">
                        {usuario.role}
                      </span>
                    </td>

                    <td className="px-6 py-4">
                      <span
                        className={
                          usuario.ativo
                            ? "inline-flex items-center gap-1.5 text-xs font-medium text-emerald-600"
                            : "inline-flex items-center gap-1.5 text-xs font-medium text-slate-400"
                        }
                      >
                        <span
                          className={
                            usuario.ativo
                              ? "h-2 w-2 rounded-full bg-emerald-500"
                              : "h-2 w-2 rounded-full bg-slate-300"
                          }
                        />

                        {usuario.ativo ? "Ativo" : "Inativo"}
                      </span>
                    </td>

                    <td className="px-6 py-4 text-right">
                      <button
                        type="button"
                        onClick={() => abrirEdicao(usuario)}
                        className="mr-1 inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-100"
                      >
                        <Pencil size={15} />
                        Editar
                      </button>

                      {usuario.role !== "ADMIN" && (
                        <button
                          type="button"
                          onClick={() => abrirRedefinicaoSenha(usuario)}
                          className="mr-1 inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-100"
                        >
                          <KeyRound size={15} />
                          Recuperar acesso
                        </button>
                      )}

                      {usuario.id !== user?.id && (
                        <button
                          type="button"
                          onClick={() => alterarStatus(usuario)}
                          className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-slate-100"
                        >
                          {usuario.ativo ? (
                            <>
                              <UserX size={15} />
                              Desativar
                            </>
                          ) : (
                            <>
                              <UserCheck size={15} />
                              Ativar
                            </>
                          )}
                        </button>
                      )}
                      {user?.role === "ADMIN" && usuario.id !== user.id && (
                        <button
                          type="button"
                          onClick={() => excluirUsuario(usuario)}
                          className="inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-medium text-red-600 transition hover:bg-red-50"
                        >
                          <Trash2 size={15} />
                          Excluir
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
            <div className="mb-6">
              <h2 className="text-lg font-semibold text-slate-900">
                {editingUser ? "Editar usuário" : "Novo usuário"}
              </h2>

              <p className="mt-1 text-sm text-slate-700">
                {editingUser
                  ? "Atualize as informações do usuário."
                  : "Cadastre um novo acesso ao Tabeleão."}
              </p>
            </div>

            <form onSubmit={salvarUsuario} className="space-y-4">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Nome completo
                </label>

                <input
                  value={nome}
                  onChange={(event) => setNome(event.target.value)}
                  required
                  className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                />
              </div>

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Usuário
                </label>

                <input
                  value={username}
                  onChange={(event) =>
                    setUsername(
                      event.target.value.replace(/\s/g, "").toLowerCase(),
                    )
                  }
                  disabled={!!editingUser}
                  required={!editingUser}
                  className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900 outline-none disabled:bg-slate-100 disabled:text-slate-400 focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                />
              </div>

              {!editingUser && (
                <div>
                  <label className="mb-1.5 block text-sm font-medium text-slate-700">
                    senha inicial
                  </label>

                  <input
                    type="password"
                    autoComplete="new-password"
                    minLength={5}
                    maxLength={72}
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                    placeholder="Ao menos 5 caracteres, letras e números"
                    className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                  />
                </div>
              )}

              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Perfil
                </label>

                <select
                  value={role}
                  onChange={(event) =>
                    setRole(event.target.value as User["role"])
                  }
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2.5 text-sm text-slate-900 outline-none focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                >
                  <option value="USUARIO">Usuário</option>

                  {podeCriarAdmin && (
                    <option value="ADMIN">Administrador</option>
                  )}
                </select>
              </div>

              <div className="flex justify-end gap-3 pt-3">
                <button
                  type="button"
                  onClick={() => {
                    setShowModal(false);
                    setEditingUser(null);
                  }}
                  className="rounded-lg px-4 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-100"
                >
                  Cancelar
                </button>

                <button
                  type="submit"
                  className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800"
                >
                  {editingUser ? "Salvar alterações" : "Criar usuário"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {showPasswordModal && editingUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 px-4">
          <div className="w-full max-w-md rounded-2xl bg-white p-6 shadow-xl">
            <div className="mb-6">
              <h2 className="text-lg font-semibold text-slate-900">
                Recuperar acesso
              </h2>

              <p className="mt-1 text-sm text-slate-500">
                Defina uma senha temporária para{" "}
                <strong>{editingUser.nome}</strong>.
              </p>
            </div>

            <form onSubmit={salvarNovaSenha} className="space-y-5">
              <div>
                <label className="mb-1.5 block text-sm font-medium text-slate-700">
                  Novo senha
                </label>

                <input
                  type="password"
                  autoComplete="new-password"
                  minLength={5}
                  maxLength={72}
                  value={newPassword}
                  onChange={(event) => setNewPassword(event.target.value)}
                  required
                  placeholder="Ao menos 5 caracteres, letras e números"
                  className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-slate-500 focus:ring-2 focus:ring-slate-200"
                />
              </div>

              <div className="flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => {
                    setShowPasswordModal(false);
                    setEditingUser(null);
                  }}
                  className="rounded-lg px-4 py-2.5 text-sm font-medium text-slate-600 transition hover:bg-slate-100"
                >
                  Cancelar
                </button>

                <button
                  type="submit"
                  className="rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-slate-800"
                >
                  Salvar senha
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
