export const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

function textosDoDetalhe(detalhe: unknown): string[] {
  if (typeof detalhe === "string") {
    const texto = detalhe.trim();
    return texto ? [texto] : [];
  }

  if (Array.isArray(detalhe)) {
    return detalhe.flatMap(textosDoDetalhe);
  }

  if (detalhe && typeof detalhe === "object") {
    const objeto = detalhe as Record<string, unknown>;

    if (typeof objeto.msg === "string") {
      return textosDoDetalhe(objeto.msg);
    }

    if (typeof objeto.message === "string") {
      return textosDoDetalhe(objeto.message);
    }

    if ("detail" in objeto) {
      return textosDoDetalhe(objeto.detail);
    }
  }

  return [];
}

export async function obterMensagemErroApi(
  response: Response | null,
  mensagemPadrao: string,
): Promise<string> {
  if (!response) return mensagemPadrao;

  try {
    const corpo = (await response.json()) as unknown;
    const detalhe =
      corpo && typeof corpo === "object" && "detail" in corpo
        ? (corpo as Record<string, unknown>).detail
        : corpo;
    const mensagens = textosDoDetalhe(detalhe);

    if (mensagens.length > 0) {
      return mensagens.slice(0, 3).join(" ");
    }
  } catch {
    // Respostas sem JSON usam a mensagem pública e estável definida pela tela.
  }

  return mensagemPadrao;
}

export async function apiFetch(endpoint: string, options: RequestInit = {}) {
  const headers = new Headers(options.headers);

  if (
    !headers.has("Content-Type") &&
    options.body &&
    !(options.body instanceof FormData)
  ) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API_URL}${endpoint}`, {
    ...options,
    headers,
    credentials: "include",
  });

  if (response.status === 401) {
    window.dispatchEvent(new Event("auth:expired"));
    return null;
  }

  return response;
}
