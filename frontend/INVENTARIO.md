# Inventário atual do frontend

Levantamento feito em 16/10/2026. Documento descritivo; não representa uma alteração funcional do frontend.

## Stack e dependências

- Framework: React `^18.3.1` (instalado `18.3.1`) e React DOM `^18.3.1` (`18.3.1`).
- Linguagem: TypeScript (`~6.0.2`; instalado `6.0.3`). O código da aplicação está em `.tsx`/`.ts`.
- Bundler e servidor de desenvolvimento: Vite (`^8.3.0`; instalado `8.3.1`), com `@vitejs/plugin-react` (`^6.1.1`; `6.1.1`).
- Estilos: Tailwind CSS 4 (`^4.3.3`; `4.3.3`) com plugin `@tailwindcss/vite` (`^4.3.3`; `4.3.3`), mais uma pequena regra CSS global em `src/index.css`. Não há styled-components.
- Runtime observado: Node `v24.18.0`, npm `11.16.0`.

Dependências de runtime declaradas em `package.json`:

| Pacote                        | Versão declarada | Versão instalada no levantamento |
| ----------------------------- | ----------------: | --------------------------------: |
| `@fullcalendar/core`        |       `^6.1.21` |                        `6.1.21` |
| `@fullcalendar/daygrid`     |       `^6.1.21` |                        `6.1.21` |
| `@fullcalendar/interaction` |       `^6.1.21` |                        `6.1.21` |
| `@fullcalendar/react`       |        `^7.1.0` |                         `7.1.0` |
| `@fullcalendar/timegrid`    |       `^6.1.21` |                        `6.1.21` |
| `@hookform/resolvers`       |        `^5.9.1` |                         `5.9.1` |
| `@tanstack/react-query`     |      `^5.103.2` |                       `5.103.2` |
| `axios`                     |       `^1.20.0` |                        `1.20.0` |
| `react`                     |       `^18.3.1` |                        `18.3.1` |
| `react-dom`                 |       `^18.3.1` |                        `18.3.1` |
| `react-hook-form`           |       `^7.88.0` |                        `7.88.0` |
| `react-router-dom`          |       `^7.18.4` |                        `7.18.4` |
| `recharts`                  |       `^3.10.1` |                        `3.10.1` |
| `zod`                       |        `^4.6.5` |                         `4.6.5` |

Dependências de desenvolvimento declaradas:

| Pacote                          | Versão declarada | Versão instalada no levantamento |
| ------------------------------- | ----------------: | --------------------------------: |
| `@tailwindcss/vite`           |        `^4.3.3` |                         `4.3.3` |
| `@testing-library/jest-dom`   |        `^6.9.1` |                         `6.9.1` |
| `@testing-library/react`      |       `^16.3.3` |                        `16.3.3` |
| `@testing-library/user-event` |       `^14.6.7` |                        `14.6.7` |
| `@types/node`                 |      `^24.13.3` |                       `24.13.6` |
| `@types/react`                |      `^18.3.31` |                       `18.3.31` |
| `@types/react-dom`            |       `^18.3.7` |                        `18.3.7` |
| `@vitejs/plugin-react`        |        `^6.1.1` |                         `6.1.1` |
| `jsdom`                       |       `^29.1.1` |                        `29.1.1` |
| `oxlint`                      |       `^1.81.0` |                        `1.85.0` |
| `tailwindcss`                 |        `^4.3.3` |                         `4.3.3` |
| `typescript`                  |        `~6.0.2` |                         `6.0.3` |
| `vite`                        |        `^8.3.0` |                         `8.3.1` |
| `vitest`                      |       `^4.1.11` |                        `4.1.11` |

Scripts existentes: `dev` (Vite), `build` (TypeScript + Vite; não executado neste levantamento), `lint` (Oxlint), `preview` (Vite preview), `test` e `test:run` (Vitest).

## Navegação e comunicação com API

- Roteamento: `react-router-dom` v7 com `BrowserRouter`; rotas atuais `/login`, `/app/agenda`, `/app` (redireciona), `/b/:slug`, `/` e fallback.
- Data fetching/cache: TanStack React Query v5 está instalado e o `QueryClientProvider` está montado em `App.tsx`; ainda não há uso de queries nas páginas atuais.
- Cliente HTTP: Axios v1, encapsulado em `src/lib/api.ts`, base URL `/api/v1`, credenciais habilitadas e interceptors para access token em memória/refresh via cookie. Não foi encontrado uso de `fetch` nativo.
- Desenvolvimento: `vite.config.ts` encaminha `/api` para `http://localhost:8000`.
- Variáveis: não foi encontrada configuração `VITE_*`, leitura de `import.meta.env` ou arquivo `.env*` dentro de `frontend/`. A URL de API usa caminho relativo.

## Conteúdo já construído

O frontend não é apenas o boilerplate puro: existem telas/componentes com identidade e fluxos iniciais do AgendaHub/Éclat Studio:

- `src/pages/LoginPage.tsx`: formulário de login com React Hook Form/Zod e mensagens de erro.
- `src/lib/auth.tsx`, `src/lib/api.ts` e `src/components/ProtectedRoute.tsx`: contexto de sessão, cliente API e proteção de rotas.
- `src/pages/AgendaPage.tsx`: cabeçalho Éclat Studio, usuário/role e estado-placeholder para a agenda da Fase 4.
- `src/pages/PublicBookingPage.tsx`: placeholder da reserva pública mostrando o slug; o fluxo está indicado como Fase 4.
- `src/test/LoginPage.test.tsx`: testes do formulário de login.

Não há agenda visual funcional nem fluxo de reserva pública completo. Ainda permanecem assets padrão (`public/vite.svg`, `src/assets/vite.svg`) e o `frontend/README.md` continua sendo o README padrão “React + TypeScript + Vite”.

## Execução observada

- `npm install`: concluiu após solicitação de execução fora do sandbox; informou “changed 2 packages” e 1 vulnerabilidade de severidade alta no audit. Não alterou arquivos versionados do frontend (`git status` ficou limpo antes da criação deste inventário); houve atualização de pacotes instalados em `node_modules`.
- `npm run dev -- --host 127.0.0.1`: Vite `8.3.1` iniciou e exibiu `http://127.0.0.1:5173/` e “ready in 557 ms”. Uma tentativa de acessar a porta com `curl` de outro contexto isolado não conectou, então a confirmação disponível é a inicialização reportada pelo próprio Vite.
- Nenhum build de produção foi executado.

## Docker, CI e deploy

- Não há Dockerfile, Compose ou arquivo `.env*` dentro de `frontend/`.
- O CI está em `.github/workflows/ci.yml`. O job de frontend roda quando há alterações em `frontend/**`: usa Node 20, `npm ci`, lint, build, testes e `npm audit --audit-level=high`. Portanto, a configuração existe, embora o comentário no workflow ainda chame o frontend de scaffold e diga que está desativado nesta fase.
- Há configurações de deploy SPA na raiz do repositório: `vercel.json` (headers de segurança e rewrite para `index.html`) e `netlify.toml` (headers de segurança e redirect SPA). Não são arquivos dentro de `frontend/`.
