// INTRODUÇÃO
// GET /api/agente/arquivo/[nome] — proxy de download dos PDFs/planilhas gerados
// pelo agente (o serviço valida o nome e a validade de 24 h). O navegador baixa
// pela mesma origem do site, sem expor o serviço do agente.
// RESUMO: repassa GET /arquivos/{nome} com os headers de conteúdo do serviço.

import { NextRequest } from "next/server";

export const dynamic = "force-dynamic";

const AGENTE_URL = process.env.AGENTE_URL ?? "http://localhost:18100";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ nome: string }> },
) {
  const { nome } = await params;
  if (!/^[a-f0-9]{32}\.(pdf|xlsx)$/.test(nome)) {
    return new Response("não encontrado", { status: 404 });
  }
  const resposta = await fetch(`${AGENTE_URL}/arquivos/${nome}`);
  if (!resposta.ok) {
    return new Response("arquivo expirado ou inexistente", {
      status: resposta.status,
    });
  }
  return new Response(resposta.body, {
    headers: {
      "Content-Type":
        resposta.headers.get("Content-Type") ?? "application/octet-stream",
      "Content-Disposition": `attachment; filename="${nome}"`,
    },
  });
}
