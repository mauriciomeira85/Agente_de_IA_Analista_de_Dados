// INTRODUÇÃO
// Configuração do PostCSS do frontend. Com o Tailwind CSS v4 basta o plugin
// `@tailwindcss/postcss`: ele processa o `@import "tailwindcss"` do globals.css
// e gera as utilidades usadas pelos componentes (inclusive os estilo shadcn/ui).
// RESUMO: PostCSS com um único plugin, o do Tailwind v4.

const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
