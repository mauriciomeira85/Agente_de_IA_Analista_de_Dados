// INTRODUÇÃO
// Utilitário `cn` no padrão shadcn/ui: junta classes Tailwind condicionais com
// clsx e resolve conflitos com tailwind-merge (ex.: "p-2" + "p-4" -> "p-4").
// Usado por todos os componentes de components/ui para permitir sobrescrita de
// estilo via prop className sem duplicar nem brigar entre utilitários.
// RESUMO: exporta cn(...classes) -> string de classes mesclada.

import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...entradas: ClassValue[]): string {
  return twMerge(clsx(entradas));
}
