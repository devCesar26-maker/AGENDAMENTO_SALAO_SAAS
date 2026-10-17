r

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

### Subdomínios locais

Defina `PUBLIC_BASE_DOMAIN=lvh.me` no ambiente Django e inclua `*.lvh.me`
(ou `.lvh.me`) em `DJANGO_ALLOWED_HOSTS`. O domínio `lvh.me` resolve para
`127.0.0.1`, então uma chamada à API pode ser testada com um Host como
`studio-ana-ana.lvh.me:8000`. Alternativamente, crie entradas para os nomes
usados em `/etc/hosts`, apontando-os para `127.0.0.1`. O middleware resolve
organizações nas rotas `/b/`; a página de reserva será integrada nessa fase.

## Deploy com subdomínio curinga

Configure `PUBLIC_BASE_DOMAIN` com o domínio público (por exemplo,
`eclatstudio.com.br`) e `DJANGO_ALLOWED_HOSTS` com os hosts da API e do serviço.
Na zona DNS, crie `*.DOMINIO_BASE` apontando para o serviço hospedado no Render
ou Railway. Uma configuração recomendada é usar Cloudflare na frente: mantenha
o registro curinga com o proxy ativo para obter SSL curinga gratuito no edge.
Certificados curinga automáticos têm limitações nos planos gratuitos do Render
e Railway, portanto o TLS deve ser planejado também entre Cloudflare e o serviço
de origem conforme o modo SSL escolhido. Essa escolha é de infraestrutura, não
de código; o middleware resolve o tenant pelo Host independentemente de onde o
SSL é terminado.

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

| Método   | Rota                                           | Quem acessa                   |
| --------- | ---------------------------------------------- | ----------------------------- |
| POST      | `/api/v1/auth/register/`                     | público                      |
| POST      | `/api/v1/auth/login/`                        | público                      |
| POST      | `/api/v1/auth/refresh/`                      | público                      |
| POST      | `/api/v1/auth/logout/`                       | autenticado                   |
| POST      | `/api/v1/auth/password/reset/`               | público                      |
| POST      | `/api/v1/auth/password/reset/confirm/`       | público (uidb64+token)       |
| GET       | `/api/v1/me/`                                | autenticado                   |
| GET/PATCH | `/api/v1/organizations/{slug}/`              | membro / PATCH: OWNER+MANAGER |
| POST/GET  | `/api/v1/organizations/{slug}/invitations/`  | OWNER+MANAGER                 |
| POST      | `/api/v1/invitations/{token}/accept/`        | público (token = prova)      |
| GET       | `/api/v1/organizations/{slug}/members/`      | membro                        |
| PATCH     | `/api/v1/organizations/{slug}/members/{id}/` | OWNER                         |

## Fase 2 implementada (backend/API)

- **Catálogo**: categorias e serviços (com duração, preço e *buffer*
  pós-atendimento), profissionais (com ou sem login vinculado), vínculo
  serviço–profissional com overrides de preço/duração e comissão, horários
  de trabalho semanais (múltiplas janelas por dia — unidas pelo motor da
  Fase 3) e folgas/bloqueios.
- **Clientes**: CRM com busca (`search`) por nome/telefone/e-mail, como:
  filtragem, observações sanitizadas e consentimento LGPD versionado por
  carimbo (`lgpd_consent_at`).
- **Segurança/tenancy**: tudo em `for_tenant(...)` escopado explicitamente;
  `organization` nunca vem do payload; permissões object-level novas
  (PROFESSIONAL edita só o próprio perfil/agenda); FKs entre apps validadas
  contra o tenant (categoria/serviço de outro salão → 400; objeto de outro
  tenant → 404/403).
- **Sanitização**: texto livre (observações, descrição, motivo de folga) tem
  tags HTML removidas no backend (`core/sanitization.py`);
  `SANITIZE_ALLOWLIST_TAGS` fica reservado para HTML rico futuro (bleach).
- **Performance**: `django_assert_num_queries` nas listagens (3–4 queries
  fixas, sem N+1) com `select_related`/`prefetch_related`; paginação
  obrigatória.

### Endpoints da fase 2

| Método | Rota                                     | Quem acessa                                  |
| ------ | ---------------------------------------- | -------------------------------------------- |
| POST/GET | `/api/v1/service-categories/`          | POST: OWNER/MANAGER · GET: membro            |
| GET/PATCH/DELETE | `/api/v1/service-categories/{id}/` | LEITURA: membro · escrita: OWNER/MANAGER   |
| POST/GET | `/api/v1/services/` (`?category=`, `?is_active=`) | POST: OWNER/MANAGER · GET: membro  |
| GET/PATCH/DELETE | `/api/v1/services/{id}/`        | LEITURA: membro · escrita: OWNER/MANAGER     |
| POST/GET | `/api/v1/professionals/` (`?is_active=`) | POST: OWNER/MANAGER · GET: membro            |
| GET/PATCH/DELETE | `/api/v1/professionals/{id}/`   | LEITURA: membro · PATCH: OWNER/MANAGER ou PROFESSIONAL nos PRÓPRIOS dados básicos · DELETE: OWNER/MANAGER |
| POST/GET | `/api/v1/professionals/{id}/services/`  | POST: OWNER/MANAGER ou PROFESSIONAL no próprio · GET: membro |
| PATCH/DELETE | `/api/v1/professional-services/{id}/` | OWNER/MANAGER em qualquer um; PROFESSIONAL só o próprio (senão 403) |
| POST/GET | `/api/v1/professionals/{id}/working-hours/` | idem vínculos                        |
| PATCH/DELETE | `/api/v1/working-hours/{id}/`       | idem vínculos                                |
| POST/GET | `/api/v1/professionals/{id}/time-offs/` | idem vínculos                                |
| PATCH/DELETE | `/api/v1/time-offs/{id}/`           | idem vínculos                                |
| POST/GET | `/api/v1/customers/` (`?search=`)       | todo membro do salão                         |
| GET/PATCH/DELETE | `/api/v1/customers/{id}/`       | todo membro do salão                         |
| POST | `/api/v1/customers/{id}/lgpd-consent/`      | todo membro do salão (carimbo no servidor)  |

## Fase 3 implementada (backend/API)

- **Disponibilidade**: slots em intervalos de 15 minutos, no fuso da
  organização, considerando horário do salão e dos profissionais, vínculos
  serviço–profissional, folgas, duração/overrides, buffers e agendamentos
  existentes. Horários locais inexistentes durante a mudança de DST são
  ignorados; períodos noturnos podem cruzar a meia-noite.
- **Agendamentos**: cabeçalho e itens sequenciais com profissional por item,
  preço, comissão e buffer em snapshot. Criação revalida a disponibilidade
  dentro de transação e serializa concorrência com lock dos profissionais e dos itens
  existentes. Se o slot foi ocupado, a API retorna HTTP 409.
- **Acesso**: OWNER/MANAGER veem e alteram agendamentos da organização;
  PROFESSIONAL só vê e altera agendamentos com item atribuído ao próprio
  perfil. Os filtros e a paginação ficam escopados ao tenant.
- **Cancelamento**: agendamento não é removido. Use a action de cancelamento,
  que altera o status para `CANCELED` e preserva o histórico.

| Método | Rota | Uso |
| ------ | ---- | --- |
| GET | `/api/v1/availability/?services=<ids>&professional=<id\|any>&date=<YYYY-MM-DD>` | Slots e atribuição por serviço |
| POST/GET | `/api/v1/appointments/` | Criar / listar com filtros `date`, `professional`, `status`, `customer` |
| GET | `/api/v1/appointments/{id}/` | Detalhe e itens |
| PATCH | `/api/v1/appointments/{id}/status/` | Alterar status |
| POST | `/api/v1/appointments/{id}/cancel/` | Cancelar preservando histórico |

`PUBLIC_PAGE` é a origem registrada pelo servidor para agendamentos criados na
página pública de reserva.

### Notificações e lista de espera (Fase 5)

- Confirmações, lembretes 24h antes e cancelamentos são enviados por tasks
  Celery depois do commit da transação. O Beat verifica a cada
  `REMINDER_CRON_SECONDS` (padrão: 900 segundos) os horários na janela de
  23h50–24h10 e registra `reminder_sent_at` para evitar repetição.
- **Endpoints autenticados** (OWNER/MANAGER): `GET/POST /api/v1/waitlist/` e
  `DELETE /api/v1/waitlist/{id}/`. A listagem é paginada e filtrada pelo tenant.
- **Inscrição pública**: `POST /api/v1/public/waitlist/`, resolvida pelo Host ou
  `X-Tenant-Slug` em desenvolvimento. Recebe contato, consentimento, serviço,
  profissional opcional e data desejada. A organização nunca é aceita do corpo.
- Ao cancelar um agendamento, entradas ainda não notificadas que coincidam
  com serviço, profissional (ou qualquer profissional) e data local recebem um
  e-mail. A vaga não fica reservada: **quem concluir o agendamento primeiro
  garante o horário**, inclusive outra pessoa pela página pública.
- `converted_at` é marcado quando o próprio cliente da lista cria um
  agendamento compatível para aquele serviço/profissional/data.

#### E-mail local e produção

No Compose, o backend e o worker enviam via SMTP para Mailhog
(`EMAIL_HOST=mailhog`, porta `1025`); consulte as mensagens em
<http://localhost:8025>. O backend de testes substitui SMTP por
`django.core.mail.backends.locmem.EmailBackend`, sem dependência de rede.

Para trocar o backend, configure `EMAIL_BACKEND` no ambiente. Em
desenvolvimento, mantenha `django.core.mail.backends.smtp.EmailBackend` com
`EMAIL_HOST=mailhog` e `EMAIL_PORT=1025`, ou use
`django.core.mail.backends.console.EmailBackend` para imprimir as mensagens no
terminal. Em produção, `config.settings.prod` usa o relay SMTP da Brevo por
padrão (`smtp-relay.brevo.com:587`, TLS), configurado com:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
BREVO_SMTP_HOST=smtp-relay.brevo.com
BREVO_SMTP_PORT=587
BREVO_SMTP_LOGIN=
BREVO_SMTP_PASSWORD=
DEFAULT_FROM_EMAIL=naoresponda@seu-dominio-verificado.example
```

`BREVO_SMTP_PASSWORD` deve conter a **chave SMTP** da Brevo, nunca a senha da
conta. Antes do envio em produção, verifique o domínio remetente no painel da
Brevo e publique os registros SPF/DKIM solicitados. Nunca inclua credenciais
reais no repositório.

Para testar localmente: `docker compose up --build`, crie um agendamento com
um cliente que tenha e-mail, cancele outro com entradas compatíveis na espera
e acompanhe as mensagens em Mailhog. Para verificar um lembrete sem aguardar
24h, crie um AppointmentItem com início dentro da janela e invoque
`notifications.tasks.send_appointment_reminders` pelo shell Django.

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
- **Refresh token**: cookie `httpOnly` restrito a `/api/v1/auth/`, renovado no
  login e em cada refresh. A API não devolve o refresh no JSON. O refresh inclui
  também o perfil do usuário para o frontend reconstruir o contexto de sessão
  após F5. Este backend habilita rotação + blacklist
  (SimpleJWT: `ROTATE_REFRESH_TOKENS=True, BLACKLIST_AFTER_ROTATION=True`),
  então um refresh reutilizado é invalidado — proteção contra replay.
- Logout no backend: blacklista o refresh recebido pelo cookie e remove o cookie.
- **Desenvolvimento local**: acesse o Vite por `http://localhost:5173` e deixe
  `VITE_API_BASE_URL` sem definir em `frontend/.env`. O Axios usa `/api/v1` e o
  proxy do Vite encaminha as chamadas ao backend, mantendo o cookie same-origin.
  O cookie usa `SameSite=Lax`, `Secure=False` e sem `Domain` por padrão local;
  as portas diferentes não tornam as origens cross-site.
- **Produção**: `config.settings.prod` força `Secure=True`. O padrão
  `SameSite=Lax` atende frontend e API no mesmo site; para domínios realmente
  cross-site, configure explicitamente `REFRESH_TOKEN_COOKIE_SAMESITE=None`,
  HTTPS e CORS com credenciais/origens explícitas. `VITE_API_BASE_URL` só é
  necessário quando frontend e API não são servidos pelo mesmo domínio/origem
  (por exemplo, preview deploys).

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

- [X] **Fase 0** — scaffolding, Docker, CI, lint, headers de segurança
- [X] **Fase 1** — auth, salões, memberships, convites, isolamento de tenant
- [X] **Fase 2** — categorias, serviços, profissionais, clientes (LGPD)
- [X] **Fase 3** — API de disponibilidade e agendamentos multi-serviço
- [X] Fase 4 — agenda FullCalendar + página pública de reserva
- [X] Fase 5 — Celery, e-mails, lembretes, lista de espera
- [ ] Fase 6 — planos, limites e cobrança
