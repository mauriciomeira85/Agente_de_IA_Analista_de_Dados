// INTRODUÇÃO
// Aba "Dashboard" (rota /): página única com filtros no topo, 9 cartões de
// indicadores (com variação sobre o período anterior), 7 gráficos ECharts e a
// tabela paginada dos últimos negócios com exportação para Excel. Todos os
// dados vêm dos route handlers /api/dashboard/*, que consultam as mesmas views
// de analytics usadas pelo agente de IA.
// Estados: carregando (skeleton), vazio (aviso) e erro (caixa vermelha) em
// cada bloco. Layout responsivo: 1 coluna no celular, grade no desktop.
// RESUMO: página cliente que orquestra filtros + TanStack Query + componentes
// de cartão, gráfico e tabela.

"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarraFiltros,
  rotulo,
  type EstadoFiltros,
  type Opcoes,
} from "@/components/BarraFiltros";
import { CartaoIndicador } from "@/components/CartaoIndicador";
import { GraficoECharts } from "@/components/GraficoECharts";
import { TabelaNegocios } from "@/components/TabelaNegocios";
import {
  Card, CardContent, CardDescription, CardHeader, CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  calcularVariacao, formatarCompetencia, formatarDataHora, formatarMoeda,
  formatarNumero, formatarPercentual, paraQueryString,
} from "@/lib/format";

/** Busca um endpoint do Dashboard com os filtros na query string. */
async function buscar<T>(caminho: string, filtros: EstadoFiltros): Promise<T> {
  const r = await fetch(`${caminho}${paraQueryString({ ...filtros })}`);
  if (!r.ok) throw new Error(`falha em ${caminho}`);
  return (await r.json()) as T;
}

function inicioPadrao(): { de: string; ate: string } {
  const hoje = new Date();
  const inicio = new Date(
    Date.UTC(hoje.getUTCFullYear(), hoje.getUTCMonth() - 11, 1));
  return {
    de: inicio.toISOString().slice(0, 10),
    ate: hoje.toISOString().slice(0, 10),
  };
}

/** Envoltório de gráfico com estados de carregamento, vazio e erro. */
function CardGrafico({
  titulo, descricao, carregando, erro, vazio, children,
}: {
  titulo: string;
  descricao?: string;
  carregando: boolean;
  erro: boolean;
  vazio: boolean;
  children: React.ReactNode;
  altura?: number;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{titulo}</CardTitle>
        {descricao && <CardDescription>{descricao}</CardDescription>}
      </CardHeader>
      <CardContent>
        {carregando ? (
          <Skeleton className="h-64 w-full" />
        ) : erro ? (
          <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Não foi possível carregar este gráfico.
          </p>
        ) : vazio ? (
          <p className="p-6 text-center text-sm text-slate-400">
            Sem dados no recorte selecionado.
          </p>
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}

export default function PaginaDashboard() {
  const [filtros, setFiltros] = useState<EstadoFiltros>(() => inicioPadrao());

  const qOpcoes = useQuery({
    queryKey: ["opcoes"],
    queryFn: () => buscar<Opcoes>("/api/dashboard/opcoes", {} as EstadoFiltros),
    staleTime: 5 * 60_000,
  });
  const qIndicadores = useQuery({
    queryKey: ["indicadores", filtros],
    queryFn: () =>
      buscar<{ atual: Record<string, number>; anterior: Record<string, number> }>(
        "/api/dashboard/indicadores", filtros),
  });
  const qFunil = useQuery({
    queryKey: ["funil", filtros],
    queryFn: () =>
      buscar<{ leads: number; visitas: number; propostas: number; fechados: number; perdidos: number }>(
        "/api/dashboard/funil", filtros),
  });
  const qVgv = useQuery({
    queryKey: ["vgv-mensal", filtros],
    queryFn: () =>
      buscar<{ competencia: string; vgv: number; negocios: number }[]>(
        "/api/dashboard/vgv-mensal", filtros),
  });
  const qConversao = useQuery({
    queryKey: ["conversao-origem", filtros],
    queryFn: () =>
      buscar<{ origem: string; leads: number; fechados: number; taxa_conversao: number }[]>(
        "/api/dashboard/conversao-origem", filtros),
  });
  const qRanking = useQuery({
    queryKey: ["ranking", filtros],
    queryFn: () =>
      buscar<{ corretor: string; equipe: string; negocios: number; vgv: number }[]>(
        "/api/dashboard/ranking-corretores", filtros),
  });
  const qBairroTipo = useQuery({
    queryKey: ["bairro-tipo", filtros],
    queryFn: () =>
      buscar<{
        por_bairro: { bairro: string; cidade: string; negocios: number; vgv: number }[];
        por_tipo: { tipo: string; negocios: number; vgv: number }[];
      }>("/api/dashboard/bairro-tipo", filtros),
  });
  const qMotivos = useQuery({
    queryKey: ["motivos-perda", filtros],
    queryFn: () =>
      buscar<{ motivo_perda: string; total: number; perc_acumulado: number }[]>(
        "/api/dashboard/motivos-perda", filtros),
  });
  const qMetas = useQuery({
    queryKey: ["realizado-meta", filtros],
    queryFn: () =>
      buscar<{
        competencia: string; equipe: string;
        realizado_negocios: number; meta_negocios: number;
        realizado_vgv: number; meta_vgv: number;
      }[]>("/api/dashboard/realizado-meta", filtros),
  });
  const qStatus = useQuery({
    queryKey: ["status"],
    queryFn: () =>
      buscar<{ atualizado_em: string | null }>("/api/dashboard/status",
        {} as EstadoFiltros),
    refetchInterval: 60_000,
  });

  // Mês de referência do gráfico realizado × meta: o mais recente do recorte.
  const competenciasMeta = useMemo(
    () => [...new Set((qMetas.data ?? []).map((l) => l.competencia))].sort(),
    [qMetas.data],
  );
  const [competenciaMeta, setCompetenciaMeta] = useState<string | null>(null);
  const competenciaSelecionada =
    competenciaMeta && competenciasMeta.includes(competenciaMeta)
      ? competenciaMeta
      : competenciasMeta[competenciasMeta.length - 1];

  const cartoes = useMemo(() => {
    const a = qIndicadores.data?.atual;
    const p = qIndicadores.data?.anterior;
    if (!a || !p) return [];
    return [
      { titulo: "Leads recebidos", valor: formatarNumero(a.leads_recebidos), variacao: calcularVariacao(a.leads_recebidos, p.leads_recebidos) },
      { titulo: "Visitas realizadas", valor: formatarNumero(a.visitas_realizadas), variacao: calcularVariacao(a.visitas_realizadas, p.visitas_realizadas) },
      { titulo: "Propostas enviadas", valor: formatarNumero(a.propostas_enviadas), variacao: calcularVariacao(a.propostas_enviadas, p.propostas_enviadas) },
      { titulo: "Negócios fechados", valor: formatarNumero(a.negocios_fechados), variacao: calcularVariacao(a.negocios_fechados, p.negocios_fechados) },
      { titulo: "VGV", valor: formatarMoeda(a.vgv), variacao: calcularVariacao(a.vgv, p.vgv) },
      { titulo: "Receita de comissões", valor: formatarMoeda(a.receita_comissoes), variacao: calcularVariacao(a.receita_comissoes, p.receita_comissoes) },
      { titulo: "Ticket médio (vendas)", valor: formatarMoeda(a.ticket_medio), variacao: calcularVariacao(a.ticket_medio, p.ticket_medio) },
      { titulo: "Taxa de conversão", valor: formatarPercentual(a.taxa_conversao * 100), variacao: calcularVariacao(a.taxa_conversao, p.taxa_conversao) },
      { titulo: "Tempo médio de fechamento", valor: `${formatarNumero(a.tempo_medio_fechamento)} dias`, variacao: calcularVariacao(a.tempo_medio_fechamento, p.tempo_medio_fechamento), inverso: true },
    ];
  }, [qIndicadores.data]);

  return (
    <div className="flex flex-col gap-4">
      {qOpcoes.data && (
        <BarraFiltros
          filtros={filtros}
          opcoes={qOpcoes.data}
          onChange={setFiltros}
        />
      )}

      {/* Cartões de indicadores */}
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {qIndicadores.isLoading &&
          Array.from({ length: 9 }).map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        {qIndicadores.isError && (
          <p className="col-span-full rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            Não foi possível carregar os indicadores.
          </p>
        )}
        {cartoes.map((c) => (
          <CartaoIndicador key={c.titulo} {...c} />
        ))}
      </section>

      {/* Funil + VGV mensal */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CardGrafico
          titulo="Funil comercial"
          descricao="Leads → visitas → propostas → fechados no recorte"
          carregando={qFunil.isLoading}
          erro={qFunil.isError}
          vazio={!!qFunil.data && qFunil.data.leads === 0}
        >
          <GraficoECharts
            altura={300}
            spec={{
              tooltip: { trigger: "item" },
              series: [{
                type: "funnel",
                left: "8%",
                width: "84%",
                label: { formatter: "{b}: {c}" },
                data: [
                  { name: "Leads", value: qFunil.data?.leads ?? 0 },
                  { name: "Visitas", value: qFunil.data?.visitas ?? 0 },
                  { name: "Propostas", value: qFunil.data?.propostas ?? 0 },
                  { name: "Fechados", value: qFunil.data?.fechados ?? 0 },
                ],
              }],
            }}
          />
        </CardGrafico>

        <CardGrafico
          titulo="VGV e negócios por mês"
          descricao="VGV de vendas (barras) e negócios fechados (linha)"
          carregando={qVgv.isLoading}
          erro={qVgv.isError}
          vazio={!!qVgv.data && qVgv.data.length === 0}
        >
          <GraficoECharts
            altura={300}
            spec={{
              tooltip: { trigger: "axis" },
              legend: {},
              xAxis: {
                type: "category",
                data: (qVgv.data ?? []).map((l) => formatarCompetencia(l.competencia)),
              },
              yAxis: [
                { type: "value", axisLabel: { formatter: (v: number) => `R$ ${(v / 1_000_000).toFixed(0)} mi` } },
                { type: "value" },
              ],
              series: [
                { name: "VGV", type: "bar", data: (qVgv.data ?? []).map((l) => l.vgv), itemStyle: { color: "#b45309" } },
                { name: "Negócios", type: "line", yAxisIndex: 1, smooth: true, data: (qVgv.data ?? []).map((l) => l.negocios), itemStyle: { color: "#0f766e" } },
              ],
            }}
          />
        </CardGrafico>
      </section>

      {/* Conversão por origem + ranking */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CardGrafico
          titulo="Leads e conversão por origem"
          descricao="Volume de leads (barras) e taxa de conversão (linha)"
          carregando={qConversao.isLoading}
          erro={qConversao.isError}
          vazio={!!qConversao.data && qConversao.data.length === 0}
        >
          <GraficoECharts
            altura={320}
            spec={{
              tooltip: { trigger: "axis" },
              legend: {},
              grid: { bottom: 80 },
              xAxis: {
                type: "category",
                data: (qConversao.data ?? []).map((l) => l.origem),
                axisLabel: { rotate: 30 },
              },
              yAxis: [
                { type: "value" },
                { type: "value", axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
              ],
              series: [
                { name: "Leads", type: "bar", data: (qConversao.data ?? []).map((l) => l.leads), itemStyle: { color: "#94a3b8" } },
                { name: "Conversão", type: "line", yAxisIndex: 1, smooth: true, data: (qConversao.data ?? []).map((l) => l.taxa_conversao), itemStyle: { color: "#b45309" } },
              ],
            }}
          />
        </CardGrafico>

        <CardGrafico
          titulo="Ranking de corretores"
          descricao="Negócios fechados (barras) e VGV de vendas (linha)"
          carregando={qRanking.isLoading}
          erro={qRanking.isError}
          vazio={!!qRanking.data && qRanking.data.length === 0}
        >
          <GraficoECharts
            altura={320}
            spec={{
              tooltip: { trigger: "axis" },
              legend: {},
              grid: { bottom: 90 },
              xAxis: {
                type: "category",
                data: (qRanking.data ?? []).map((l) => l.corretor.split(" ")[0]),
                axisLabel: { rotate: 40 },
              },
              yAxis: [
                { type: "value" },
                { type: "value", axisLabel: { formatter: (v: number) => `R$ ${(v / 1_000_000).toFixed(1)} mi` } },
              ],
              series: [
                { name: "Negócios", type: "bar", data: (qRanking.data ?? []).map((l) => l.negocios), itemStyle: { color: "#0f766e" } },
                { name: "VGV", type: "line", yAxisIndex: 1, smooth: true, data: (qRanking.data ?? []).map((l) => l.vgv), itemStyle: { color: "#b45309" } },
              ],
            }}
          />
        </CardGrafico>
      </section>

      {/* Bairros + tipos */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CardGrafico
          titulo="Negócios por bairro (top 10)"
          carregando={qBairroTipo.isLoading}
          erro={qBairroTipo.isError}
          vazio={!!qBairroTipo.data && qBairroTipo.data.por_bairro.length === 0}
        >
          <GraficoECharts
            altura={320}
            spec={{
              tooltip: { trigger: "axis" },
              grid: { left: 120 },
              xAxis: { type: "value" },
              yAxis: {
                type: "category",
                data: (qBairroTipo.data?.por_bairro ?? []).map((l) => l.bairro).reverse(),
              },
              series: [{
                name: "Negócios",
                type: "bar",
                data: (qBairroTipo.data?.por_bairro ?? []).map((l) => l.negocios).reverse(),
                itemStyle: { color: "#b45309" },
              }],
            }}
          />
        </CardGrafico>

        <CardGrafico
          titulo="Negócios por tipo de imóvel"
          carregando={qBairroTipo.isLoading}
          erro={qBairroTipo.isError}
          vazio={!!qBairroTipo.data && qBairroTipo.data.por_tipo.length === 0}
        >
          <GraficoECharts
            altura={320}
            spec={{
              tooltip: { trigger: "item" },
              legend: { bottom: 0 },
              series: [{
                type: "pie",
                radius: ["40%", "65%"],
                data: (qBairroTipo.data?.por_tipo ?? []).map((l) => ({
                  name: rotulo(l.tipo),
                  value: l.negocios,
                })),
              }],
            }}
          />
        </CardGrafico>
      </section>

      {/* Pareto de perdas + realizado x meta */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CardGrafico
          titulo="Motivos de perda (Pareto)"
          descricao="Quantidade por motivo e % acumulado"
          carregando={qMotivos.isLoading}
          erro={qMotivos.isError}
          vazio={!!qMotivos.data && qMotivos.data.length === 0}
        >
          <GraficoECharts
            altura={320}
            spec={{
              tooltip: { trigger: "axis" },
              legend: {},
              grid: { bottom: 90 },
              xAxis: {
                type: "category",
                data: (qMotivos.data ?? []).map((l) => l.motivo_perda),
                axisLabel: { rotate: 25 },
              },
              yAxis: [
                { type: "value" },
                { type: "value", max: 1, axisLabel: { formatter: (v: number) => `${(v * 100).toFixed(0)}%` } },
              ],
              series: [
                { name: "Perdidos", type: "bar", data: (qMotivos.data ?? []).map((l) => l.total), itemStyle: { color: "#dc2626" } },
                { name: "% acumulado", type: "line", yAxisIndex: 1, smooth: true, data: (qMotivos.data ?? []).map((l) => l.perc_acumulado), itemStyle: { color: "#0f172a" } },
              ],
            }}
          />
        </CardGrafico>

        <CardGrafico
          titulo="Realizado × meta do mês por equipe"
          descricao="Metas mensais da equipe inteira; aplica período e equipe. Não há metas por cidade, origem ou tipo."
          carregando={qMetas.isLoading}
          erro={qMetas.isError}
          vazio={!!qMetas.data && qMetas.data.length === 0}
        >
          <div className="mb-2 flex items-center gap-2 text-xs text-[var(--texto-suave)]">
            Mês:
            <select
              className="rounded-md border border-[var(--borda)] px-2 py-1 text-sm"
              value={competenciaSelecionada ?? ""}
              onChange={(e) => setCompetenciaMeta(e.target.value)}
            >
              {competenciasMeta.map((c) => (
                <option key={c} value={c}>{formatarCompetencia(c)}</option>
              ))}
            </select>
          </div>
          <GraficoECharts
            altura={280}
            spec={{
              tooltip: { trigger: "axis" },
              legend: {},
              xAxis: {
                type: "category",
                data: [...new Set((qMetas.data ?? [])
                  .filter((l) => l.competencia === competenciaSelecionada)
                  .map((l) => l.equipe))],
              },
              yAxis: { type: "value" },
              series: [
                {
                  name: "Realizado",
                  type: "bar",
                  data: (qMetas.data ?? [])
                    .filter((l) => l.competencia === competenciaSelecionada)
                    .map((l) => l.realizado_negocios),
                  itemStyle: { color: "#0f766e" },
                },
                {
                  name: "Meta",
                  type: "bar",
                  data: (qMetas.data ?? [])
                    .filter((l) => l.competencia === competenciaSelecionada)
                    .map((l) => l.meta_negocios),
                  itemStyle: { color: "#cbd5e1" },
                },
              ],
            }}
          />
        </CardGrafico>
      </section>

      {/* Tabela de últimos negócios */}
      <Card>
        <CardHeader>
          <CardTitle>Últimos negócios fechados</CardTitle>
          <CardDescription>Paginada e exportável para Excel</CardDescription>
        </CardHeader>
        <CardContent>
          <TabelaNegocios filtros={filtros} />
        </CardContent>
      </Card>

      <footer className="pb-4 pt-2 text-center text-xs text-[var(--texto-suave)]">
        Dados atualizados em {formatarDataHora(qStatus.data?.atualizado_em)} ·
        Serra Clara Imóveis — dados 100% fictícios, gerados para demonstração.
      </footer>
    </div>
  );
}
