// INTRODUÇÃO
// Barra de filtros do topo do Dashboard: período (de/até), cidade, finalidade,
// tipo de imóvel, origem do lead e equipe/corretor. As opções vêm de
// /api/dashboard/opcoes; o filtro de corretor é limitado pela equipe escolhida.
// Mudou qualquer filtro -> onChange devolve o novo estado completo e a página
// refaz as consultas (TanStack Query cuida do cache por combinação de filtros).
// RESUMO: <BarraFiltros filtros opcoes onChange /> controlada pela página.

"use client";

import { Select } from "@/components/ui/select";

export interface EstadoFiltros {
  de: string;
  ate: string;
  cidade_id?: number;
  finalidade?: string;
  tipo?: string;
  origem_id?: number;
  equipe_id?: number;
  corretor_id?: number;
}

export interface Opcoes {
  cidades: { cidade_id: number; cidade: string }[];
  origens: { origem_id: number; nome_origem: string }[];
  equipes: { equipe_id: number; nome_equipe: string }[];
  corretores: { corretor_id: number; nome_corretor: string; equipe_id: number }[];
  tipos: string[];
  finalidades: string[];
}

const ROTULOS: Record<string, string> = {
  venda: "Venda",
  locacao: "Locação",
  apartamento: "Apartamento",
  casa: "Casa",
  sala_comercial: "Sala comercial",
  terreno: "Terreno",
};

export function rotulo(valor: string): string {
  return ROTULOS[valor] ?? valor;
}

export function BarraFiltros({
  filtros,
  opcoes,
  onChange,
}: {
  filtros: EstadoFiltros;
  opcoes: Opcoes;
  onChange: (novos: EstadoFiltros) => void;
}) {
  const definir = (chave: keyof EstadoFiltros, valor: string) => {
    const numero = valor === "" ? undefined : Number(valor);
    const novos: EstadoFiltros = {
      ...filtros,
      [chave]: ["cidade_id", "origem_id", "equipe_id", "corretor_id"].includes(chave)
        ? numero
        : valor === ""
          ? undefined
          : valor,
    };
    // Trocou de equipe -> zera o corretor (evita combinação inválida).
    if (chave === "equipe_id") novos.corretor_id = undefined;
    onChange(novos);
  };

  const corretoresDaEquipe = filtros.equipe_id
    ? opcoes.corretores.filter((c) => c.equipe_id === filtros.equipe_id)
    : opcoes.corretores;

  return (
    <div className="grid grid-cols-2 gap-2 rounded-xl border border-[var(--borda)] bg-white p-3 shadow-sm sm:grid-cols-3 lg:grid-cols-7">
      <label className="flex flex-col gap-1 text-xs text-[var(--texto-suave)]">
        De
        <input
          type="date"
          value={filtros.de}
          onChange={(e) => definir("de", e.target.value)}
          className="h-9 rounded-md border border-[var(--borda)] px-2 text-sm"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-[var(--texto-suave)]">
        Até
        <input
          type="date"
          value={filtros.ate}
          onChange={(e) => definir("ate", e.target.value)}
          className="h-9 rounded-md border border-[var(--borda)] px-2 text-sm"
        />
      </label>
      <label className="flex flex-col gap-1 text-xs text-[var(--texto-suave)]">
        Cidade
        <Select
          value={filtros.cidade_id ?? ""}
          onChange={(e) => definir("cidade_id", e.target.value)}
        >
          <option value="">Todas</option>
          {opcoes.cidades.map((c) => (
            <option key={c.cidade_id} value={c.cidade_id}>
              {c.cidade}
            </option>
          ))}
        </Select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-[var(--texto-suave)]">
        Finalidade
        <Select
          value={filtros.finalidade ?? ""}
          onChange={(e) => definir("finalidade", e.target.value)}
        >
          <option value="">Todas</option>
          {opcoes.finalidades.map((f) => (
            <option key={f} value={f}>
              {rotulo(f)}
            </option>
          ))}
        </Select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-[var(--texto-suave)]">
        Tipo de imóvel
        <Select
          value={filtros.tipo ?? ""}
          onChange={(e) => definir("tipo", e.target.value)}
        >
          <option value="">Todos</option>
          {opcoes.tipos.map((t) => (
            <option key={t} value={t}>
              {rotulo(t)}
            </option>
          ))}
        </Select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-[var(--texto-suave)]">
        Origem do lead
        <Select
          value={filtros.origem_id ?? ""}
          onChange={(e) => definir("origem_id", e.target.value)}
        >
          <option value="">Todas</option>
          {opcoes.origens.map((o) => (
            <option key={o.origem_id} value={o.origem_id}>
              {o.nome_origem}
            </option>
          ))}
        </Select>
      </label>
      <label className="flex flex-col gap-1 text-xs text-[var(--texto-suave)]">
        Equipe / corretor
        <span className="flex gap-1">
          <Select
            value={filtros.equipe_id ?? ""}
            onChange={(e) => definir("equipe_id", e.target.value)}
            className="w-1/2"
          >
            <option value="">Equipes</option>
            {opcoes.equipes.map((eq) => (
              <option key={eq.equipe_id} value={eq.equipe_id}>
                {eq.nome_equipe}
              </option>
            ))}
          </Select>
          <Select
            value={filtros.corretor_id ?? ""}
            onChange={(e) => definir("corretor_id", e.target.value)}
            className="w-1/2"
          >
            <option value="">Corretores</option>
            {corretoresDaEquipe.map((c) => (
              <option key={c.corretor_id} value={c.corretor_id}>
                {c.nome_corretor.split(" ")[0]}
              </option>
            ))}
          </Select>
        </span>
      </label>
    </div>
  );
}
