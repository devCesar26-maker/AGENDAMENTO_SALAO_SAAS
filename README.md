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

## Testes

```bash
# Backend (na raiz do monorepo)
SAAS/bin/python -m pytest            # ou: pytest --cov=backend --cov-fail-under=80

# Frontend
cd frontend && npm run test:run
```

## Roadmap

- [x] **Fase 0** — scaffolding, Docker, CI, lint, headers de segurança
- [ ] Fase 1 — auth, salões, memberships, convites, isolamento de tenant
- [ ] Fase 2 — categorias, serviços, profissionais, clientes
- [ ] Fase 3 — motor de disponibilidade e agendamentos multi-serviço
- [ ] Fase 4 — agenda FullCalendar + página pública de reserva
- [ ] Fase 5 — Celery, e-mails, lembretes, lista de espera
- [ ] Fase 6 — planos, limites e cobrança
- [ ] Fase 7 — comissões, métricas, CSV, auditoria
- [ ] Fase 8 — revisão de segurança e performance
- [ ] Fase 9 — polimento, seed, README final, deploy

> Documentação completa (decisões técnicas, diagrama de arquitetura e checklist
> de segurança) será publicada na Fase 9.
