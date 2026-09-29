// INTRODUÇÃO
// GET /api/agente/conversas/[sessao] — proxy do histórico da sessão anônima
// (o serviço do agente lê de app.agente_mensagens). Usado ao abrir a aba
// "Agente de IA" para restaurar a conversa.
// RESUMO: repassa GET /conversas/{sessao} do serviço do agente.

import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

const AGENTE_URL = process.env.AGENTE_URL ?? "http://localhost:18100";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ sessao: string }> },
) {
  const { sessao } = await params;
  // A sessão é um uuid gerado no navegador; valida o formato antes de repassar.
  if (!/^[\w-]{8,64}$/.test(sessao)) {
    return NextResponse.json({ mensagens: [] });
  }
  const resposta = await fetch(`${AGENTE_URL}/conversas/${sessao}`);
  const dados = await resposta.json();
  return NextResponse.json(dados, { status: resposta.status });
}
