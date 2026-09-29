// INTRODUÇÃO
// GET /api/dashboard/indicadores — os 9 cartões do topo do Dashboard, com o
// valor do período filtrado e do período anterior de mesmo tamanho (para a
// variação %). Os números vêm das MESMAS views que o agente usa
// (analytics.v_funil_mensal e analytics.v_vgv_mensal), garantindo que Dashboard
// e agente nunca divergem.
// SQL sempre parametrizado via montarWhere(); nomes de coluna são fixos aqui.
// RESUMO: devolve { atual: {...9 métricas}, anterior: {...} }.

import { NextRequest, NextResponse } from "next/server";
import { pool } from "@/lib/db";
import { montarWhere, parseFiltros, periodoAnterior } from "@/lib/filtros";

export const dynamic = "force-dynamic";

async function totaisFunil(filtros: ReturnType<typeof parseFiltros>) {
  const { where, valores } = montarWhere(filtros, { cidade: true, finalidade: true, tipo: true, origem: true, equipe: true, corretor: true }, "data_ref");
  const r = await pool.query(
    `SELECT COALESCE(SUM(leads),0)::INT AS leads,
            COALESCE(SUM(visitas),0)::INT AS visitas,
            COALESCE(SUM(propostas),0)::INT AS propostas,
            COALESCE(SUM(fechados),0)::INT AS fechados
     FROM analytics.v_funil_mensal ${where}`,
    valores,
  );
  return r.rows[0] as { leads: number; visitas: number; propostas: number; fechados: number };
}

async function totaisFinanceiros(filtros: ReturnType<typeof parseFiltros>) {
  // Todas as dimensões são aplicadas à camada semântica.
  const { where, valores } = montarWhere(filtros, { cidade: true, finalidade: true, tipo: true, origem: true, equipe: true, corretor: true }, "data_ref");
  const r = await pool.query(
    `SELECT
       COALESCE(SUM(vgv) FILTER (WHERE finalidade = 'venda'), 0)::FLOAT AS vgv,
       COALESCE(SUM(comissao_total), 0)::FLOAT AS receita_comissoes,
       COALESCE(SUM(vgv) FILTER (WHERE finalidade = 'venda')
         / NULLIF(SUM(negocios_fechados) FILTER (WHERE finalidade = 'venda'), 0),
         0)::FLOAT AS ticket_medio,
       COALESCE(SUM(tempo_medio_fechamento_dias * negocios_fechados)
         / NULLIF(SUM(negocios_fechados), 0), 0)::FLOAT AS tempo_medio_fechamento
     FROM analytics.v_vgv_mensal ${where}`,
    valores,
  );
  return r.rows[0] as {
    vgv: number; receita_comissoes: number;
    ticket_medio: number; tempo_medio_fechamento: number;
  };
}

async function indicadores(filtros: ReturnType<typeof parseFiltros>) {
  const [funil, financeiro] = await Promise.all([
    totaisFunil(filtros),
    totaisFinanceiros(filtros),
  ]);
  return {
    leads_recebidos: funil.leads,
    visitas_realizadas: funil.visitas,
    propostas_enviadas: funil.propostas,
    negocios_fechados: funil.fechados,
    vgv: financeiro.vgv,
    receita_comissoes: financeiro.receita_comissoes,
    ticket_medio: financeiro.ticket_medio,
    taxa_conversao: funil.leads > 0 ? funil.fechados / funil.leads : 0,
    tempo_medio_fechamento: financeiro.tempo_medio_fechamento,
  };
}

export async function GET(request: NextRequest) {
  const filtros = parseFiltros(request.nextUrl.searchParams);
  const [atual, anterior] = await Promise.all([
    indicadores(filtros),
    indicadores(periodoAnterior(filtros)),
  ]);
  return NextResponse.json({ atual, anterior, periodo: { de: filtros.de, ate: filtros.ate } });
}
