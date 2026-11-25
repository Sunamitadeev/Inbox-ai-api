# Architecture Decision Records & Design (ARCHITECTURE.md)
## Projeto: `inbox-ai-api`

---

### 1. Visão Arquitetural

O projeto adota uma arquitetura em camadas simples, pragmática e modular (Layered Architecture), ideal para serviços focados e orientados a microsserviços.

```text
[ Cliente HTTP / Frontend ]
          │ (JSON Request)
          ▼
┌─────────────────────────────────────────────────────────────┐
│                    API Layer (src/main.py)                  │
│       - FastAPI router, lifespan, validação Pydantic        │
└──────────────┬───────────────────────────────┬──────────────┘
               │                               │
               ▼                               ▼
┌──────────────────────────────┐ ┌────────────────────────────┐
│   Service (ai_classifier)    │ │ Repository (ticket_repo)   │
│  - Google Gemini API         │ │ - SQL puro parametrizado   │
│  - Local Deterministic       │ │ - Mapeamento para DTOs     │
│    Fallback                  │ └─────────────┬──────────────┘
└──────────────────────────────┘               │
                                               ▼
                                 ┌────────────────────────────┐
                                 │ Database Engine (SQLite)   │
                                 │ - Context manager          │
                                 │ - PRAGMA foreign_keys      │
                                 └────────────────────────────┘
```

---

### 2. Camadas do Sistema

1. **API / Routers (`src/main.py`):**
   - Responsável pelo ciclo de vida HTTP, endpoints REST (`/triage`, `/tickets`, `/metrics`), injeção de dependências e captura de erros de alto nível.
2. **Schemas / DTOs (`src/schemas.py`):**
   - Contratos de dados baseados em Pydantic v2 com tipagem estrita (`Literal`, `Field`, validadores customizados para strings limpas).
3. **Services (`src/services/ai_classifier.py`):**
   - Regras de negócio de inteligência: interação com SDK `google-genai` usando schema estruturado JSON e mecanismo de fallback determinístico por regras semânticas de palavras-chave.
4. **Repositories (`src/repositories/ticket_repo.py`):**
   - Abstração de persistência: executa queries SQL puras parametrizadas contra SQLite, mantendo queries desacopladas das rotas web.
5. **Database (`src/database.py`):**
   - Gerenciamento de conexão com SQLite utilizando *Context Manager* (`with get_db_connection()`), ativação de `row_factory` para mapeamento tipo dicionário e script `init_db()` executado no lifespan da aplicação.

---

### 3. Architecture Decision Records (ADRs)

#### ADR 01: Escolha do Framework Web — FastAPI
- **Contexto:** Necessidade de construir uma API REST moderna, com alta performance assíncrona, validação nativa de schemas e documentação OpenAPI/Swagger automática.
- **Decisão:** Adotar **FastAPI** em conjunto com **Uvicorn** e **Pydantic v2**.
- **Consequências:**
  - *Positivas:* Validação de dados ultrarrápida (núcleo em Rust via Pydantic v2), geração automática de `/docs`, suporte robusto a lifespan de aplicação.
  - *Mitigações:* Utilizar dependências mínimas para manter a imagem leve.

#### ADR 02: Estratégia de Banco de Dados — SQLite com SQL Puro Parametrizado
- **Contexto:** A aplicação necessita de persistência confiável para desenvolvimento local, prototipação rápida e testes automatizados sem a sobrecarga operacional de subir containers de bancos externos (ex: Postgres). Além disso, busca-se demonstrar clareza no entendimento de SQL, evitando a complexidade desnecessária de ORMs pesados (SQLAlchemy/Django ORM) para um escopo enxuto.
- **Decisão:** Utilizar **SQLite** embutido no Python (`sqlite3`) com **SQL puro estritamente parametrizado (`?`)**.
- **Consequências:**
  - *Positivas:* Zero configuração de infraestrutura adicional; queries explícitas e auditáveis; imunidade contra SQL Injection via bind parameters; facilidade extrema para criar bancos isolados em testes.
  - *Mitigações:* Para eventual escala horizontal com múltiplos nós em produção, o padrão repository já isola a camada de dados, permitindo migração futura para PostgreSQL com alteração restrita ao driver e queries sem impactar as regras de negócio.

#### ADR 03: Resiliência de IA — Google Gemini com Fallback Determinístico Local
- **Contexto:** Chamadas para APIs de Large Language Models (LLMs) são sujeitas a latência variável, exaustão de quota (HTTP 429), instabilidade de conexão ou ausência de chaves de API em ambientes locais de teste. Uma API de atendimento crítico não pode falhar com HTTP 500 por indisponibilidade de serviço terceiro.
- **Decisão:** Implementar padrão de **Graceful Degradation (Fallback Local Determinístico)** dentro do `ai_classifier.py`.
- **Consequências:**
  - *Positivas:* 100% de disponibilidade funcional da API mesmo offline ou sem chave configurada; retorno explícito do campo `used_fallback: bool` para auditoria e observabilidade.
  - *Regras do Fallback:* Heurística semântica baseada em tokens essenciais (ex: cancelamento -> urgência alta; suporte técnico -> análise de erro/sistema; financeiro -> cobrança/fatura/pagamento; dúvida geral -> demais).

#### ADR 04: Estratégia de Testes Automatizados — Pytest com TestClient
- **Contexto:** Garantir que o comportamento da API, regras de fallback, validação de payload inválido e agregação de métricas sejam testados de ponta a ponta sem poluir o banco de dados local de desenvolvimento.
- **Decisão:** Pytest com fixture de banco de dados temporário descartável via `tempfile` e injeção controlada de variáveis de ambiente.
- **Consequências:**
  - *Positivas:* Testes herméticos, determinísticos e paralelizáveis sem efeitos colaterais.
