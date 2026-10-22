# Éclat Studio

SaaS multi-tenant de agendamento e gestão para **salões de beleza e barbearias**.
Projeto em construção — em desenvolvimento ativo, fase a fase.

## Stack

- **Backend**: Python 3.12 · Django 5 · DRF · PostgreSQL · Redis · Celery · SimpleJWT · drf-spectacular
- **Frontend**: React 18 · Vite · TypeScript · TanStack Query · Tailwind · FullCalendar · Recharts
- **Infra**: Docker Compose · GitHub Actions · pre-commit (ruff/black)

## Como rodar (desenvolvimento)

```bash
cp backend/.env.example backend/.env
docker compose up --build
# API:        http://localhost:8000/api/v1/
# Swagger:    http://localhost:8000/api/docs/
# Mailhog:    http://localhost:8025
# Frontend:   http://localhost:5173
```

O Compose é exclusivamente para desenvolvimento local. Em produção use a
imagem `backend/Dockerfile` (Gunicorn, dependências runtime e `collectstatic`),
injete secrets pelo orquestrador e execute migrations como etapa de deploy.
O `.env` local é excluído do contexto de build. A configuração de produção
exige PostgreSQL remoto com `DB_SSL_REQUIRE=1`, Redis remoto, `DRF_NUM_PROXIES`
correto para o ingress e origens HTTPS explícitas para frontend, CORS e CSRF.
O ingress deve sobrescrever os cabeçalhos `X-Forwarded-For` e
`X-Forwarded-Proto` antes de encaminhar as requisições.

> Sem Docker, o banco do compose publica **5433** no host
> (`postgres://ecalt:ecalt@localhost:5433/ecalt`) para não brigar com um
> Postgres local na 5432.

### Subdomínios locais

Defina `PUBLIC_BASE_DOMAIN=lvh.me` no ambiente Django e inclua `*.lvh.me`
(ou `.lvh.me`) em `DJANGO_ALLOWED_HOSTS`. O domínio `lvh.me` resolve para
`127.0.0.1`, então uma chamada à API pode ser testada com um Host como
`studio-ana-ana.lvh.me:8000`. Alternativamente, crie entradas para os nomes
usados em `/etc/hosts`, apontando-os para `127.0.0.1`. O middleware resolve
organizações pelo subdomínio e mantém `/b/<slug>/` como fallback local da
página pública de reserva.

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

## Fase 4 implementada (frontend)

- Agenda de semana/dia com criação por slot, remarcação com reversão visual em
  conflito, alteração de status e filtragem conforme o papel de profissional.
- Reserva pública responsiva, consulta de disponibilidade por tenant,
  consentimento LGPD e tratamento de limite de requisições.

### Notificações e lista de espera (Fase 5)

- Confirmações, cancelamentos e avisos da lista de espera entram numa outbox
  transacional e o Beat entrega os e-mails com retentativa; falha no broker não
  desfaz a requisição. O Beat verifica a cada
  `REMINDER_CRON_SECONDS` (padrão: 900 segundos) os horários na janela de
  23h50–24h10 e registra `reminder_sent_at` para evitar repetição.
- **Endpoints autenticados** (OWNER/MANAGER): `GET/POST /api/v1/waitlist/` e
  `DELETE /api/v1/waitlist/{id}/`. A listagem é paginada e filtrada pelo tenant.
- **Inscrição pública**: `POST /api/v1/public/waitlist/`, resolvida pelo Host ou
  `X-Tenant-Slug` em desenvolvimento. Recebe contato, consentimento, serviço,
  profissional opcional e data desejada. A organização nunca é aceita do corpo.
- **Reserva pública**: `GET /api/v1/public/catalog/`, `GET
  /api/v1/public/professionals/`, `GET /api/v1/public/availability/` e `POST
  /api/v1/public/appointments/`. As rotas são escopadas pelo subdomínio; o
  fallback `X-Tenant-Slug` fica habilitado apenas em dev/test. Não existe busca
  pública de clientes.
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

### Idempotência de requests e notificações

`core.IdempotencyKey` registra chaves por organização e contexto, com hash do
escopo, fingerprint do conteúdo, resultado JSON opcional e validade padrão de
48 horas. O endpoint de reserva pública aceita `Idempotency-Key`: um retry com
a mesma chave e o mesmo conteúdo devolve o mesmo `201` e o mesmo agendamento;
reutilizar a chave com outro conteúdo retorna `409`. Sem o header, a reserva
mantém o comportamento normal. A gravação da reserva e do resultado da chave
participam da mesma transação. A limpeza pode ser executada com
`python manage.py cleanup_idempotency_keys`.

E-mails usam chaves naturais separadas por tipo de evento e agendamento (e por
entrada da lista de espera no aviso de vaga). A reivindicação da notificação é
persistida antes da chamada SMTP; retries e workers retomados não repetem o
envio. Como SMTP e PostgreSQL não compartilham uma transação, isso oferece
semântica de tentativa no máximo uma vez: uma queda depois da reivindicação e
antes do envio, ou um erro ambíguo do SMTP, pode deixar um e-mail por entregar.
Gravar somente depois do SMTP permitiria duplicação se o worker caísse após o
servidor aceitar a mensagem. Webhooks de pagamento reutilizam a tabela com um
contexto global e o ID da notificação Mercado Pago como chave (com fallback
para o ID do recurso); retries devolvem o
resultado armazenado sem aplicar a transição de assinatura novamente.

### Planos, limites e Mercado Pago (sandbox)

Toda organização criada pelo endpoint de registro recebe uma assinatura FREE
na mesma transação. `GET /api/v1/billing/plans/` apresenta o nome comercial
adequado à vertical. O tier é um identificador de API; cobrança e limites usam
o tier, nunca o nome apresentado. Limites `null` significam ilimitado. PLUS e
PREMIUM têm preços iniciais de R$ 29,90 e R$ 59,90 por mês, armazenados em
centavos nos dados seed dos planos.

FREE inclui 1 profissional e 50 agendamentos não cancelados por mês-calendário;
PLUS, 3 profissionais e 300 agendamentos; PREMIUM é ilimitado. A cota mensal
conta agendamentos pela data de criação, exceto os que estão com status
CANCELED. Após downgrade, profissionais e agendamentos existentes acima do
novo limite permanecem intactos; novas criações ficam bloqueadas enquanto o
uso não cancelado estiver no limite.

Configure `MP_ACCESS_TOKEN` e `MP_PUBLIC_KEY` em `backend/.env` com credenciais
de teste do Mercado Pago. `MP_WEBHOOK_SECRET` deve conter o segredo de
assinatura cadastrado para a URL de webhook. O checkout é restrito ao OWNER.
O webhook valida HMAC SHA-256 do header `x-signature` usando `data.id`,
`x-request-id` e `ts`; sem segredo configurado, rejeita os eventos.

Para simular em desenvolvimento, exponha a API com um túnel HTTPS e configure
no painel do Mercado Pago a URL
`https://<host>/api/v1/billing/webhook/mercadopago/`, escolhendo notificações
de assinatura. Envie o header e payload assinados conforme o formato oficial;
payloads inventados sem assinatura válida são rejeitados. A API consulta a
assinatura no Mercado Pago antes de aplicar a mudança: `authorized` ativa o
tier contratado, `cancelled` rebaixa para FREE/CANCELED e `paused` ou `pending`
rebaixa para FREE/PAST_DUE.

### Recursos avançados de agenda

Estes recursos ampliam a agenda e são todos multi-tenant (cada consulta passa
por `for_tenant`/`resolve_membership`; `organization` nunca vem do payload).

**1. Prioridade da lista de espera (FIFO com hold exclusivo).** Ao cancelar um
agendamento, o sistema não avisa mais todos os inscritos compatíveis: escolhe a
**primeira entrada FIFO** entre as que querem o **item compatível** (mesmo
serviço e, se a entrada exigir, mesmo profissional, na **data exata** do horário
liberado) e cria uma `WaitlistOffer` com token. Só essa pessoa recebe o e-mail
com o link `/prioridade/<token>`; o horário fica **reservado** para ela até
`waitlist_priority_window_minutes` (padrão 10, configurável por salão). Se o
prazo expirar, a próxima entrada FIFO é ofertada. A reserva pelo link usa
idempotência e só cria o **item ofertado** — demais itens do cancelamento são
liberados normalmente. O motor de disponibilidade **oculta** horários com hold
ativo, exceto para quem detém o token (`ignore_waitlist_offer_id`).

**2. Insights acionáveis.** `GET /api/v1/insights/` (OWNER/MANAGER, paginado)
devolve sugestões determinísticas em **7 queries fixas** (não cresce com o
volume): baixa ocupação por faixa/período, clientes inativos há N dias, serviço
em queda e desequilíbrio de agenda entre profissionais. Cada item traz
`type`, `severity`, `message` e um `reference` estruturado. São **pistas**, não
ações automáticas. O frontend mostra em `/app/insights`.

**3. Avaliação pós-atendimento.** Ao concluir um agendamento, cria-se um token
`RATE` e envia-se `GET/POST /api/v1/public/ratings/<token>/` (link
`/avaliar/<token>`). A nota (1–5) e o comentário opcional são gravados **uma
única vez**; o token é de uso único (replay → 410). Avaliar exige status
`COMPLETED`.

**4. Match por preferência.** O motor de disponibilidade aceita `customer`
(opcional). Para "qualquer disponível", a ordem dos profissionais usa a **média
de avaliações do cliente com cada profissional**; sem esse histórico, cai na
**média geral do profissional**. Em reservas públicas anônimas não há cliente,
então vale sempre a média geral. É uma **heurística simples** de ordenação — não
promete o "melhor" profissional, apenas prioriza quem o cliente já avaliou bem.

**5. Sugestões de recorrência.** Uma tarefa diária identifica clientes cujo
intervalo médio entre visitas venceu e **não têm agendamento futuro**, e cria um
`Appointment` com status `SUGGESTED` e `suggestion_expires_at`. O cliente recebe
`/sugestao/<token>` para confirmar (vira `CONFIRMED`) ou recusar (vira
`CANCELED`; ao recusar, dispara a prioridade da lista de espera). Sugestões
pendentes **bloqueiam** o horário; as vencidas são canceladas por outra tarefa.

**6. FlashSlot (vagas com desconto).** Uma tarefa gera vagas ociosas próximas
como `FlashSlot`, com desconto em degraus (`10/20/30%`, sempre ≤
`flash_slot_max_discount_percent` do salão, padrão 30%): quanto mais perto, maior
o desconto. O preço com desconto aparece na disponibilidade pública e é
**congelado no item** no momento da reserva (`discount_percent`, `flash_slot`).
Preços são recalculados e vagas vencidas expiradas por tarefas periódicas.

Todas as listagens novas são paginadas (`DefaultPagination`) e os seletores usam
`select_related`/`prefetch_related` validados por `django_assert_num_queries`.

### Split de assinatura no Mercado Pago (marketplace)

O checkout de assinatura pode operar como **marketplace**: o salão (vendedor)
recebe o valor do plano na **própria conta Mercado Pago** e a plataforma retém a
comissão via `marketplace_fee`. O fluxo:

- `GET /api/v1/billing/mercadopago/connect/` (OWNER) devolve a URL de
  autorização OAuth; `DELETE` desconecta a conta.
- `GET /api/v1/billing/mercadopago/callback/` troca o `code` pelos tokens do
  vendedor e os guarda **por organização**. A identificação do salão é feita por
  um `state` **assinado (HMAC) e de validade curta** (10 min) — nunca por um id
  cru da URL. As credenciais **nunca** são expostas pela API.
- No checkout, se o salão conectou a conta, o `preapproval` é criado com o token
  do vendedor e recebe `marketplace_fee` = preço do plano ×
  `platform_fee_percent` (por salão, padrão global em
  `PLATFORM_FEE_DEFAULT_PERCENT`, exibido como somente-leitura). Sem conta
  conectada, o checkout usa as credenciais da plataforma **sem split**, para não
  travar quem ainda não fez OAuth.

**Aviso honesto sobre o ambiente.** Hoje isso funciona apenas em **sandbox**,
com contas de teste do Mercado Pago; a validação manual de webhooks exige túnel
HTTPS, como descrito acima. **Produção exige KYC** (verificação de identidade do
vendedor) e **aprovação prévia como marketplace** no Mercado Pago — sem isso o
`marketplace_fee` não é aplicado de verdade. As credenciais
(`MP_CLIENT_ID`, `MP_CLIENT_SECRET`, `MP_OAUTH_REDIRECT_URI`) vêm do ambiente, e
o `redirect_uri` de autorização e de troca de token precisam ser idênticos,
incluindo o `slug` do salão.

### Métricas, exportação e auditoria

O dashboard autenticado oferece `GET /api/v1/metrics/overview/`,
`/api/v1/metrics/services/` e `/api/v1/metrics/professionals/`; todos aceitam
`data_inicio` e `data_fim` (`YYYY-MM-DD`, inclusivos), com padrão no mês atual.
OWNER/MANAGER veem a organização; PROFESSIONAL vê apenas dados vinculados ao
seu perfil. O faturamento considera itens de agendamentos COMPLETED. Ocupação
é minutos em horários agendados, confirmados, concluídos ou NO_SHOW divididos
pelos minutos do horário semanal de funcionamento da organização multiplicados
pelos profissionais ativos; cancelamentos não ocupam capacidade. A taxa de
no-show usa agendamentos não cancelados como denominador.

OWNER/MANAGER podem baixar `GET /api/v1/exports/appointments/` (filtros de
período, status e `profissional`), `/api/v1/exports/customers/` e
`/api/v1/exports/commissions/`. Os CSVs são transmitidos em lotes. Comissão é
calculada pelo snapshot de preço e percentual guardado no item do agendamento,
sem recalcular atendimentos antigos com a configuração atual.

`GET /api/v1/audit-log/` é paginado e permite filtrar por `action` (ou `acao`), `data_inicio`
e `data_fim`; acesso restrito a OWNER/MANAGER. Registra cancelamentos,
desativação de membros, mudanças de tier e alterações de percentual de comissão.
Webhooks de billing têm ator `null`. O contexto é allowlisted e não guarda
payloads, dados de clientes, senhas, tokens ou informações de pagamento.
Essa trilha cobre esses eventos de negócio; ela não é uma auditoria integral de
autenticação, alterações de dados ou de todos os endpoints do sistema.

O frontend autenticado inclui catálogo de serviços para OWNER/MANAGER, com
criação e edição de serviços e categorias. A aparência escura usa tons carvão
e roxo-índigo (#6366f1) sobre fundo escuro (#0a0a0f); a imagem de fundo pode ser carregada nas preferências visuais e seus
níveis de sombra/desfoque e enquadramento são guardados no navegador, separados por organização.
Essa preferência local ainda não é uma configuração compartilhada entre membros
nem aparece no link público de reservas; isso depende de persistência de marca
por organização no backend e armazenamento de imagem.

## Hosts permitidos por ambiente

No Compose de desenvolvimento, `backend/.env` define `DJANGO_ALLOWED_HOSTS` e é
carregado pelo serviço `api`. Inclua `localhost`, `127.0.0.1` e `api`: o último
é o nome DNS interno usado pelo proxy do Vite (`http://api:8000`). O valor de
`Host` pode chegar como `api:8000`, mas o Django separa a porta antes de validar
`ALLOWED_HOSTS`; configure apenas `api`, sem a porta.

Em produção, configure `DJANGO_ALLOWED_HOSTS` no ambiente de implantação com
os domínios públicos reais da API e do site, conforme o proxy e o domínio
configurado. Não inclua `api` a menos que esse seja realmente um hostname
público e nunca use `*`. O settings de produção exige a variável e valida
`PUBLIC_BASE_DOMAIN` separadamente.

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
pip-audit -r backend/requirements.txt && pip-audit -r backend/requirements-prod.txt
```

O throttling usa `REMOTE_ADDR` por padrão (`DRF_NUM_PROXIES=0`). Se a API
estiver atrás de proxies, configure a quantidade em `DRF_NUM_PROXIES` e faça
o ingress sobrescrever `X-Forwarded-For`; nunca aceite esse cabeçalho enviado
diretamente pelo cliente. O fallback `X-Tenant-Slug` é habilitado apenas em
desenvolvimento; em produção, as rotas públicas devem usar o subdomínio do
tenant.

Espinha de CI: lint (ruff/black), testes (com cobertura), bandit/pip-audit,
`manage.py check`/`makemigrations --check` e build de frontend.

## Roadmap

- [X] **Fase 0** — scaffolding, Docker, CI, lint, headers de segurança
- [X] **Fase 1** — auth, salões, memberships, convites, isolamento de tenant
- [X] **Fase 2** — categorias, serviços, profissionais, clientes (LGPD)
- [X] **Fase 3** — API de disponibilidade e agendamentos multi-serviço
- [X] Fase 4 — agenda FullCalendar + página pública de reserva
- [X] Fase 5 — Celery, e-mails, lembretes, lista de espera
- [X] Fase 6 — planos, limites e cobrança
- [X] Fase 7 — métricas, exportação CSV e auditoria
- [ ] Fase 8 — revisão dedicada de segurança e performance
