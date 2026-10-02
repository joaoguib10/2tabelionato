"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "../../context/AuthContext";
import { API_URL, obterMensagemErroApi } from "../../lib/api";

type Step = "login" | "password" | "setup" | "verify" | "saved";
type AuthReply = {
  action?: Step;
  challenge_token?: string;
  access_token?: string;
  recovery_codes?: string[];
  secret?: string;
  detail?: unknown;
};

export default function LoginPage() {
  const router = useRouter();
  const { refreshUser } = useAuth();
  const [step, setStep] = useState<Step>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [code, setCode] = useState("");
  const [recovery, setRecovery] = useState(false);
  const [challenge, setChallenge] = useState("");
  const [secret, setSecret] = useState("");
  const [codes, setCodes] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function request(
    path: string,
    body: object | URLSearchParams,
  ): Promise<AuthReply> {
    const form = body instanceof URLSearchParams;
    const response = await fetch(API_URL + "/api/auth" + path, {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": form
          ? "application/x-www-form-urlencoded"
          : "application/json",
      },
      body: form ? body : JSON.stringify(body),
    });
    if (!response.ok) {
      throw new Error(
        await obterMensagemErroApi(
          response,
          response.status >= 500
            ? "O servidor está temporariamente indisponível. Verifique se o banco de dados está ativo."
            : "Confira os campos informados.",
        ),
      );
    }
    try {
      return (await response.json()) as AuthReply;
    } catch {
      throw new Error(
        "O servidor retornou uma resposta inválida. Tente novamente.",
      );
    }
  }

  async function enter() {
    if (!(await refreshUser())) {
      throw new Error("Sessão expirada. Entre novamente.");
    }
    setSecret("");
    setCodes([]);
    router.replace("/consultar");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    try {
      if (step === "saved") {
        await enter();
        return;
      }
      let data: AuthReply;
      if (step === "login") {
        data = await request(
          "/login",
          new URLSearchParams({ username, password }),
        );
      } else if (step === "password") {
        if (password !== confirmation)
          throw new Error("As senhas não coincidem.");
        data = await request("/password", {
          challenge_token: challenge,
          password,
        });
      } else {
        data = await request(
          step === "setup" ? "/mfa/confirm" : "/mfa/verify",
          {
            challenge_token: challenge,
            code,
            recovery: step === "verify" && recovery,
          },
        );
      }
      setPassword("");
      setConfirmation("");
      setCode("");
      if (data.recovery_codes && data.access_token) {
        setCodes(data.recovery_codes);
        setSecret("");
        setStep("saved");
        return;
      }
      if (data.access_token) {
        await enter();
        return;
      }
      if (!data.action || !data.challenge_token)
        throw new Error("Resposta inesperada do servidor.");
      setChallenge(data.challenge_token);
      setStep(data.action);
      if (data.action === "setup") {
        const setup = await request("/mfa/setup", {
          challenge_token: data.challenge_token,
        });
        setSecret(setup.secret || "");
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Não foi possível conectar ao servidor.",
      );
    } finally {
      setLoading(false);
    }
  }

  function restart() {
    setStep("login");
    setChallenge("");
    setPassword("");
    setConfirmation("");
    setCode("");
    setSecret("");
    setCodes([]);
    setSaved(false);
    setRecovery(false);
    setError("");
  }

  const input =
    "w-full rounded-lg border border-slate-300 px-4 py-3 text-slate-900";
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-100 px-4 py-8">
      <div className="w-full max-w-lg rounded-2xl bg-white p-8 text-slate-900 shadow-sm">
        <h1 className="text-3xl font-bold">Tabeleão</h1>
        <p className="my-4">
          {step === "login"
            ? "Acesse com sua senha. No primeiro acesso após a atualização, use seu PIN atual."
            : step === "password"
              ? "Cadastre uma nova senha com ao menos 5 caracteres, contendo letras e números."
              : step === "setup"
                ? "Cadastre o Tabeleão no seu aplicativo autenticador."
                : step === "verify"
                  ? "Confirme o segundo fator."
                  : "Guarde seus códigos de recuperação em local seguro."}
        </p>
        <form onSubmit={handleSubmit} className="space-y-4">
          {step === "login" && (
            <label className="block">
              Usuário
              <input
                className={input}
                value={username}
                autoComplete="username"
                onChange={(e) => setUsername(e.target.value)}
                required
              />
            </label>
          )}
          {(step === "login" || step === "password") && (
            <label className="block">
              {step === "password" ? "Nova senha" : "Senha"}
              <input
                className={input}
                type="password"
                value={password}
                maxLength={72}
                minLength={step === "password" ? 5 : undefined}
                autoComplete={
                  step === "password" ? "new-password" : "current-password"
                }
                onChange={(e) => setPassword(e.target.value)}
                required
              />
            </label>
          )}
          {step === "password" && (
            <label className="block">
              Repita a nova senha
              <input
                className={input}
                type="password"
                autoComplete="new-password"
                value={confirmation}
                onChange={(e) => setConfirmation(e.target.value)}
                required
              />
            </label>
          )}
          {step === "setup" && (
            <div className="space-y-3">
              <p>
                Escolha adicionar uma chave manualmente: conta Tabeleão, baseada
                em tempo, 6 dígitos, intervalo de 30 segundos.
              </p>
              <p>Chave de cadastro (não compartilhe):</p>
              <code className="block break-all rounded bg-slate-100 p-3 select-all">
                {secret ||
                  "Não foi possível carregar a chave. Volte ao início."}
              </code>
              <p>
                O autenticador funciona sem internet. Mantenha o relógio do
                celular correto.
              </p>
            </div>
          )}
          {(step === "setup" || step === "verify") && (
            <label className="block">
              {recovery && step === "verify"
                ? "Código de recuperação"
                : "Código de 6 dígitos"}
              <input
                className={input}
                value={code}
                autoComplete="one-time-code"
                maxLength={64}
                onChange={(e) => setCode(e.target.value)}
                required
              />
            </label>
          )}
          {step === "verify" && (
            <label className="flex gap-2">
              <input
                type="checkbox"
                checked={recovery}
                onChange={(e) => {
                  setRecovery(e.target.checked);
                  setCode("");
                }}
              />
              Perdi o autenticador: usar código de recuperação e cadastrar
              outro.
            </label>
          )}
          {step === "saved" && (
            <>
              <p>
                Exibidos somente agora. Usar um código revoga o autenticador e
                os demais códigos; o novo cadastro gera outra lista.
              </p>
              <pre className="overflow-auto rounded bg-slate-100 p-3 select-all">
                {codes.join("\n")}
              </pre>
              <label className="flex gap-2">
                <input
                  type="checkbox"
                  checked={saved}
                  onChange={(e) => setSaved(e.target.checked)}
                />
                Guardei os códigos em local seguro.
              </label>
            </>
          )}
          {error && (
            <p role="alert" className="rounded bg-red-50 p-3 text-red-800">
              {error}
            </p>
          )}
          <button
            className="w-full rounded-lg bg-slate-900 px-4 py-3 text-white disabled:opacity-50"
            disabled={
              loading ||
              (step === "saved" && !saved) ||
              (step === "setup" && !secret)
            }
          >
            {loading
              ? "Aguarde..."
              : step === "saved"
                ? "Entrar no sistema"
                : "Continuar"}
          </button>
          {step !== "login" && (
            <button
              type="button"
              onClick={restart}
              disabled={loading}
              className="underline"
            >
              Voltar ao início
            </button>
          )}
          <p className="text-sm">
            Sem acesso? Usuários devem procurar o ADMIN. A recuperação do ADMIN
            é feita pelo responsável no servidor.
          </p>
        </form>
      </div>
    </main>
  );
}
