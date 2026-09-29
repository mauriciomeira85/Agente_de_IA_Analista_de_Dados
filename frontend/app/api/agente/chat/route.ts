// INTRODUÇÃO
// POST /api/agente/chat — proxy de STREAMING entre o navegador e o serviço do
// agente (FastAPI). O navegador nunca fala direto com o serviço: este route
// handler repassa a pergunta (com o IP real do visitante em CF-Connecting-IP,
// para o limite de uso por IP funcionar atrás do túnel) e devolve o corpo SSE
// sem bufferizar (os tokens chegam ao chat conforme o modelo gera).
// RESUMO: repassa POST /chat e devolve o fluxo text/event-stream.

import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const AGENTE_URL = process.env.AGENTE_URL ?? "http://localhost:18100";

export async function POST(request: NextRequest) {
  const corpo = await request.json();
  const ip =
    request.headers.get("cf-connecting-ip") ??
    "127.0.0.1";
  const resposta = await fetch(`${AGENTE_URL}/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "CF-Connecting-IP": ip,
    },
    body: JSON.stringify(corpo),
  });
  if (!resposta.ok || !resposta.body) {
    const detalhe = await resposta.text().catch(() => "");
    return new Response(
      JSON.stringify({ erro: detalhe || "agente indisponível" }),
      { status: resposta.status, headers: { "Content-Type": "application/json" } },
    );
  }
  return new Response(resposta.body, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
}
