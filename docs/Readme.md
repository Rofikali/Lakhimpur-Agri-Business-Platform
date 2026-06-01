# Lakhimpur Agri-Business Platform — Documentation

> Farm-direct rice and traditional Assamese petha sold online and offline  
> from Lakhimpur district, Assam. Built by a solo engineer.

---

## Index

| File | What it covers |
|---|---|
| [business-context.md](./business-context.md) | Why this exists, products, cost model, CA/MBA framework |
| [architecture/hld.md](./architecture/hld.md) | System overview, tech stack, deployment, data flow |
| [architecture/lld.md](./architecture/lld.md) | DB schema, modules, design patterns, algorithms |
| [architecture/decisions.md](./architecture/decisions.md) | Architecture Decision Records (ADRs) — every key choice with rationale |
| [security.md](./security.md) | STRIDE threat model, OWASP Top 10, auth, secrets, input validation |
| [observability.md](./observability.md) | Metrics, tracing, structured logging, health checks, alerting |
| [development.md](./development.md) | Setup, env vars, daily workflow, testing, Git conventions |
| [governance.md](./governance.md) | Code standards, review process, data retention, financial compliance |
| [api-reference.md](./api-reference.md) | Every endpoint — method, path, request, response, errors |

---

## Quick orientation

```
lakhimpur-biz/
├── backend/          FastAPI (Python 3.12) — 9 modules
├── frontend/         NuxtJS 3 (Vue 3 + TypeScript)
├── docs/             ← you are here
├── Makefile          all dev commands
└── docker-compose.yml  local dev (optional)
```

**One sentence:** A monolith with two faces — `/shop` for customers (SSR, public)
and `/dashboard` for the owner (SPA, auth-gated) — backed by a single FastAPI
service that handles orders, stock, P&L, farm seasons, and petha batches.

---

## SDLC stages completed

| Stage | Status | Notes |
|---|---|---|
| 0 · Idea | ✅ | Business validated, products scoped |
| 1 · Whiteboard | ✅ | Monolith architecture decided |
| 2 · Requirements | ✅ | 38 FRs, 18 edge cases, 15 user stories |
| 3 · HLD | ✅ | Tech stack, 6 key flows, deployment |
| 4 · LLD | ✅ | 14 tables, 9 modules, all algorithms |
| 5 · Dev Setup | ✅ | uv, Arch Linux, Codespaces, Makefile |
| 6 · Code | ⚠️ | Backend done · Frontend pending |
| 7 · Testing | ✅ | Unit + integration + edge cases |
| 8 · Staging | ⬜ | Railway + Vercel |
| 9 · Ship | ⬜ | Production |