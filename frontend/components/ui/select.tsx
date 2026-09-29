// INTRODUÇÃO
// Select estilizado (wrapper do <select> nativo no padrão visual shadcn/ui).
// Optamos pelo select nativo: é acessível, funciona no celular sem JS extra e
// basta para os filtros do Dashboard.
// RESUMO: <Select> com aparência do tema; recebe options nativas como filhos.

import * as React from "react";
import { cn } from "@/lib/utils";

export function Select({
  className,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select
      className={cn(
        "h-9 rounded-md border border-[var(--borda)] bg-white px-2 text-sm",
        "text-slate-700 shadow-sm focus:outline-none focus:ring-2",
        "focus:ring-amber-600/40",
        className,
      )}
      {...props}
    />
  );
}
