// INTRODUÇÃO
// Botão no padrão shadcn/ui (mínimo): variantes "default" (âmbar), "outline"
// e "ghost", com class-variance-authority para compor classes.
// RESUMO: <Button variant="..."> com estilos do tema.

import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const variantes = cva(
  "inline-flex items-center justify-center gap-2 rounded-md text-sm font-medium transition disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-[var(--destaque)] text-white hover:bg-amber-800",
        outline:
          "border border-[var(--borda)] bg-white hover:bg-slate-50 text-slate-700",
        ghost: "hover:bg-slate-100 text-slate-700",
      },
      size: {
        default: "h-9 px-4",
        sm: "h-8 px-3 text-xs",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof variantes> {}

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return (
    <button
      className={cn(variantes({ variant, size }), className)}
      {...props}
    />
  );
}
