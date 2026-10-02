const FUSO_EXPLICITO = /(?:Z|[+-]\d{2}:?\d{2})$/i;

export function formatarDataHoraApi(valor: string): string {
  const texto = valor.trim();
  const data = new Date(FUSO_EXPLICITO.test(texto) ? texto : `${texto}Z`);

  if (Number.isNaN(data.getTime())) return valor;

  return data.toLocaleString("pt-BR");
}
