// INTRODUÇÃO
// Provedores de contexto do lado cliente. Hoje só o TanStack Query (cache e
// estado de carregamento/erro das chamadas às APIs do Dashboard), encapsulado
// aqui para o layout raiz continuar sendo Server Component.
// RESUMO: envolve children com QueryClientProvider (staleTime de 30 s).

"use client";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";

export function Provedores({ children }: { children: React.ReactNode }) {
  // Um QueryClient por montagem (useState garante estabilidade entre renders).
  const [cliente] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );
  return <QueryClientProvider client={cliente}>{children}</QueryClientProvider>;
}
