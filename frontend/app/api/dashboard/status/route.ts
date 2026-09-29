// INTRODUÇÃO
// GET /api/dashboard/status — data/hora da última carga de dados (rodapé
// "Dados atualizados em ..."). Fonte: audit.cargas (o app_dashboard tem SELECT
// nessa tabela justamente para isto).
// RESUMO: { atualizado_em, semente } da carga mais recente.

import { NextResponse } from "next/server";
import { pool } from "@/lib/db";

export const dynamic = "force-dynamic";

export async function GET() {
  const r = await pool.query(
    "SELECT executada_em, semente FROM audit.cargas ORDER BY carga_id DESC LIMIT 1",
  );
  return NextResponse.json({
    atualizado_em: r.rows[0]?.executada_em ?? null,
    semente: r.rows[0]?.semente ?? null,
  });
}
