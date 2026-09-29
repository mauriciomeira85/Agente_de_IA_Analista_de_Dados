// INTRODUÇÃO
// Skeleton de carregamento (padrão shadcn/ui): bloco cinza animado usado nos
// estados de loading dos cartões, gráficos e tabela do Dashboard.
// RESUMO: <Skeleton className="h-24" /> -> div pulsante.

import { cn } from "@/lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn("animate-pulse rounded-md bg-slate-200", className)}
      aria-hidden
    />
  );
}
