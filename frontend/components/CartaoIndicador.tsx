// INTRODUÇÃO
// Cartão de indicador do Dashboard: título, valor formatado e variação
// percentual sobre o período anterior (seta e cor: verde sobe, vermelho desce;
// para "tempo médio de fechamento" a lógica inverte — subir é ruim).
// RESUMO: <CartaoIndicador titulo valor variacao inverso />.

import { TrendingDown, TrendingUp } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { formatarPercentual } from "@/lib/format";
import { cn } from "@/lib/utils";

export function CartaoIndicador({
  titulo,
  valor,
  variacao,
  inverso = false,
}: {
  titulo: string;
  valor: string;
  variacao: number | null;
  inverso?: boolean;
}) {
  // Bom ou ruim? Para tempo/custo (inverso), queda é positiva.
  const positivo = variacao !== null && (inverso ? variacao < 0 : variacao > 0);
  const neutro = variacao === null || Math.abs(variacao) < 0.05;
  return (
    <Card>
      <CardContent className="p-4">
        <p className="text-xs font-medium text-[var(--texto-suave)]">{titulo}</p>
        <p className="mt-1 truncate text-2xl font-bold tracking-tight">{valor}</p>
        <p
          className={cn(
            "mt-1 flex items-center gap-1 text-xs",
            neutro
              ? "text-slate-400"
              : positivo
                ? "text-emerald-600"
                : "text-red-600",
          )}
          title="Variação sobre o período anterior de mesmo tamanho"
        >
          {!neutro &&
            (variacao! > 0 ? (
              <TrendingUp className="h-3.5 w-3.5" />
            ) : (
              <TrendingDown className="h-3.5 w-3.5" />
            ))}
          {neutro ? "sem base de comparação" : `${formatarPercentual(Math.abs(variacao!))} vs. período anterior`}
        </p>
      </CardContent>
    </Card>
  );
}
