// INTRODUÇÃO
// Menu de abas da aplicação (Dashboard | Agente de IA). É um componente de
// cliente porque usa usePathname para destacar a aba ativa.
// RESUMO: dois links com estilo de aba; a aba da rota atual fica destacada.

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";

const ABAS = [
  { href: "/", rotulo: "Dashboard" },
  { href: "/agente", rotulo: "Agente de IA" },
];

export function Navegacao() {
  const caminho = usePathname();
  return (
    <nav className="flex gap-1 rounded-lg bg-slate-100 p-1">
      {ABAS.map((aba) => (
        <Link
          key={aba.href}
          href={aba.href}
          className={cn(
            "rounded-md px-4 py-1.5 text-sm font-medium text-slate-600 transition",
            caminho === aba.href
              ? "bg-white text-[var(--destaque)] shadow-sm"
              : "hover:text-slate-900",
          )}
        >
          {aba.rotulo}
        </Link>
      ))}
    </nav>
  );
}
