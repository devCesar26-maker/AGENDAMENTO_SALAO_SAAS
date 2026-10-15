# Éclat Studio

SaaS multi-tenant de agendamento e gestão para **salões de beleza e barbearias**.
Projeto em construção — em desenvolvimento ativo, fase a fase.

## Stack

- **Backend**: Python 3.12 · Django 5 · DRF · PostgreSQL · Redis · Celery · SimpleJWT · drf-spectacular
- **Frontend**: React 18 · Vite · TypeScript · TanStack Query · Tailwind · FullCalendar · Recharts
- **Infra**: Docker Compose · GitHub Actions · pre-commit (ruff/black)

## Como rodar (desenvolvimento)

```bash
docker compose up --build
# API:        http://localhost:8000/api/v1/
# Swagger:    http://localhost:8000/api/docs/
# Mailhog:    http://localhost:8025
# Frontend:   http://localhost:5173
```

> Sem Docker, o banco do compose publica **5433** no host
> (`postgres://ecalt:ecalt@localhost:5433/ecalt`) para não brigar com um
> Postgres local na 5432.

## Fase 1 implementada (backend/API)

- **Auth**: registro (User + salão + OWNER numa transação), login/refresh/logout
  (rotação + blacklist do SimpleJWT), reset de senha por e-mail (console/Mailhog).
- **Organizações**: CRUD por `slug`, convites com token de 7 dias, membros com
  roles (`OWNER`/`MANAGER`/`PROFESSIONAL`) e paginação.
- **Segurança**: Argon2, validadores de senha, throttling nas rotas de auth +
  bloqueio temporário de login por e-mail, CORS restrito, CSP, `check --deploy`
  limpo, bandit/pip-audit no CI.
- **Docs OpenAPI**: `/api/docs/` (Swagger) e `/api/schema/` (YAML/JSON).
- **Testes**: pytest + factory_boy, cobertura > 90%, testes de IDOR e de
  escalonamento de privilégio, `django_assert_num_queries` na listagem de membros.

### Endpoints da fase

| Método | Rota | Quem acessa |
|---|---|---|
| POST | `/api/v1/auth/register/` | público |
| POST | `/api/v1/auth/login/` | público |
| POST | `/api/v1/auth/refresh/` | público |
| POST | `/api/v1/auth/logout/` | autenticado |
| POST | `/api/v1/auth/password/reset/` | público |
| POST | `/api/v1/auth/password/reset/confirm/` | público (uidb64+token) |
| GET | `/api/v1/me/` | autenticado |
| GET/PATCH | `/api/v1/organizations/{slug}/` | membro / PATCH: OWNER+MANAGER |
| POST/GET | `/api/v1/organizations/{slug}/invitations/` | OWNER+MANAGER |
| POST | `/api/v1/invitations/{token}/accept/` | público (token = prova) |
| GET | `/api/v1/organizations/{slug}/members/` | membro |
| PATCH | `/api/v1/organizations/{slug}/members/{id}/` | OWNER |

## Arquitetura de multi-tenancy (shared-schema)

Uma única base; toda entidade de negócio tem FK para `Organization`, resolvidos
por dois mecanismos complementares em `core/`:

1. **`TenantScopedQuerySet`/`TenantScopedManager` (core/models.py)** — toda
   entidade herda de `TenantModel` e expose `for_tenant(organization)` /
   `for_user(user)` para escopar consultas explicitamente em qualquer lugar
   (views, selectors, services, Celery).
2. **`TenantModelViewSet` (core/tenant.py)** — resolve o tenant a partir da
   Membership **ativa** do usuário autenticado e filtra o queryset; o
   `organization.id` nas gravações vem do servidor, nunca do payload.
   Falha fechada: sem membership, nenhuma linha visível.

O scoping é **explícito no limite da query** (mixin + NÃO thread-local mágico):
contextos sem request (Celery, admin, commands) e EventLoop async tornam
variáveis de thread propensas a vazamento entre requests — a decisão está
documentada nos docstrings e registrada em testes de IDOR
(`test_tenant_isolation.py`).

### Camadas

- `views` finas: parsing HTTP, permissões, serializers; **nenhuma regra de negócio**;
- `services.py`: regras (@transaction.atomic, bloqueio de último owner etc.);
- `selectors.py`: queries complexas;
- `permissions.py`: papéis reutilizáveis (`IsOrganizationMember`,
  `IsOrganizationManagerOrOwner`, `IsOrganizationOwner`).

## Onde o access token mora no frontend (decisão)

- **Access token**: **em memória apenas** (ex.: um `useState`/var de módulo). NUNCA
  em localStorage/sessionStorage nem em cookie acessível a scripts — XSS lería.
- **Refresh token**: cookie `httpOnly; Secure; SameSite=Strict` enviado a
  `/auth/refresh/`; nesse padrão o access token rota (15 min) e a sessão é
  curta. Este backend já habilita rotação + blacklist
  (SimpleJWT: `ROTATE_REFRESH_TOKENS=True, BLACKLIST_AFTER_ROTATION=True`),
  então um refresh reutilizado é invalidado — proteção contra replay.
- Logout no backend: posterblacklist do refresh em `/auth/logout/`.

## Testes

```bash
# Backend (na raiz do monorepo)
DATABASE_URL="postgres://ecalt:ecalt@localhost:5433/ecalt" SAAS/bin/python -m pytest
# com cobertura:
DATABASE_URL="postgres://ecalt:ecalt@localhost:5433/ecalt" SAAS/bin/python -m pytest --cov=backend --cov-fail-under=80

# Frontend
cd frontend && npm run test:run
```

Lint/format/segurança:

```bash
ruff check backend && black --check backend
bandit -r backend -x "backend/*/migrations/*,backend/config/settings/*,backend/*/tests/*"
pip-audit -r backend/requirements.txt
```

Espinha de CI: lint (ruff/black), testes (com cobertura), bandit/pip-audit,
`manage.py check`/`makemigrations --check` e build de frontend.

## Roadmap

- [x] **Fase 0** — scaffolding, Docker, CI, lint, headers de segurança
- [x] **Fase 1** — auth, salões, memberships, convites, isolamento de tenant
- [ ] Fase 2 — categorias, serviços, profissionais, clientes
- [ ] Fase 3 — motor de disponibilidade e agendamentos multi-serviço
- [ ] Fase 4 — agenda FullCalendar + página pública de reserva
- [ ] Fase 5 — Celery, e-mails, lembretes, lista de espera
- [ ] Fase 6 — planos, limites e cobrança
