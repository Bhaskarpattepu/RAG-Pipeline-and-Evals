# Enterprise AI Support Engineer

> **Project status: development prototype, not production-ready.** This project demonstrates
> support chat, policy retrieval, commerce lookups, MCP tools, a ticket-approval flow, and AI
> evaluation. It does not yet provide the security, operations, or data controls needed for
> public deployment or real customer data. See [Known gaps and improvement plan](#known-gaps-and-improvement-plan).

## What is in the repository

- React/Vite dashboard in [`frontend/`](frontend/)
- FastAPI API and LangGraph-based support agent in [`backend/app/`](backend/app/)
- MCP stdio server in [`mcp-server/server.py`](mcp-server/server.py)
- Example policies in [`sample-documents/`](sample-documents/)
- Golden evaluation dataset and runners in [`evaluation/`](evaluation/)
- GitHub Actions workflows in [`.github/workflows/`](.github/workflows/)

The backend uses SQLAlchemy models for demo tenants, customers, users, products, orders,
payments, refunds, tickets, and approval requests. OpenAI is used for generated chat responses and
embeddings when configured. LangSmith tracing is optional.

## Project workflows

### Chat and data lookup

```text
Browser -> Vite development server -> FastAPI /api/v1/chat
                                      |-> policy retrieval
                                      |-> tenant-ID-based demo-record lookups
                                      |-> OpenAI response
                                      `-> sources and optional approval request
```

The chat route puts retrieved policy text and matching records into the model prompt and returns
source references. Refund-window wording has a deterministic safeguard so a request window is
not represented as a refund approval. The chat route and `/api/v1/agent/run` are separate
entrypoints: the latter uses LangGraph and rule-based tool selection to invoke MCP tools. Do not
assume that every tool result is connected to a live business system; see the limitations below.

### Policy retrieval

Documents can be submitted through the document endpoints, divided into text chunks, and indexed.
The RAG service can use OpenAI embeddings and Qdrant; local/in-memory behavior also exists. The
current upload and retrieval APIs are demo interfaces, not a secured document-management system.

### Ticket approval

The chat and `/api/v1/agent/run` paths can create a durable pending approval only after resolving
the customer and optional order in the tenant's records. Repeated pending requests for the same
target reuse the existing approval. An approval action then creates the ticket. This is still a
prototype workflow, not a security boundary: other API paths currently permit ticket creation or
approval without a verified identity. Do not use it to authorize real support actions.

### Evaluation, CI, and tracing

- Offline evaluation checks the golden dataset, scenario coverage, and approval-related
  expectations. It does not establish that model answers are factually correct or safe in
  production.
- Live evaluation and live LLM tests make billable OpenAI calls. Live evaluation can optionally
  export traces to LangSmith.
- The CI workflow runs Python checks, offline evaluation, and a frontend build. The separate
  live-evaluation job runs only when its required GitHub secret is configured.

## Run locally on Windows

The commands below use PowerShell and assume Python 3.11 and Node.js 20 are installed. Those
versions match the current CI configuration. Use synthetic/demo records only.

### 1. Configure the backend

From the repository root:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set `OPENAI_API_KEY` if you want generated chat responses, embeddings, or live
evaluation. Never put API keys in frontend files or commit `.env`. LangSmith is optional; enable
it only after deciding what request metadata may be sent to that service.

Create and activate a virtual environment, then install backend dependencies:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
```

For local work, use a SQLite database outside the repository so the app does not write into the
tracked database files:

```powershell
$localDb = Join-Path $env:TEMP "enterprise-ai-support-local.db"
$env:DATABASE_URL = "sqlite:///" + $localDb.Replace('\', '/')
$env:USE_SQLITE_FALLBACK = "0"
$env:PYTHONPATH = Join-Path $PWD "backend"
```

Start the API from the repository root in this same PowerShell session:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The app creates database tables and seeds demo records at startup. The database path is held in
the current shell's environment; repeat the environment setup when opening another terminal.
`/api/v1/health` is a basic liveness endpoint, not a check that all dependencies are ready.

### 2. Start the frontend

Open a second PowerShell window:

```powershell
Set-Location "C:\path\to\your\clone\frontend"
npm ci
npm run dev -- --host 127.0.0.1
```

Replace the example path with the location of your checkout.
Open [http://localhost:5173](http://localhost:5173). The Vite development server proxies API
requests to `http://localhost:8000`. The API documentation is at
[http://localhost:8000/docs](http://localhost:8000/docs).

Sample demo identifiers include `ORD-2005`, `CUST-1001`, `PROD-1001` / `SKU-1001`, and
`USER-1001`; refund `REF-1005`. Without `OPENAI_API_KEY`, database-backed dashboard views
and basic health checks may work, but generated chat responses are unavailable.

### Optional: enable document indexing

The chat demo can retrieve the checked-in sample policies without Qdrant. The document upload
endpoints use Qdrant and OpenAI embeddings; they need a reachable Qdrant service and a configured
OpenAI key. For a local-only Qdrant instance with Docker installed, start the vector service in a
third terminal:

```powershell
docker run --rm -p 6333:6333 qdrant/qdrant:v1.10.0
```

Redis is listed in configuration/Compose but is not currently used by the application. The
Compose stack as checked in is not a supported local-run command; see the deployment gap below.

### 3. Run tests and the offline evaluation

Run these commands from the repository root with the virtual environment activated. The full
suite skips billable live LLM tests unless `RUN_LIVE_LLM_TESTS=true` is explicitly set. Tests use
a fresh temporary SQLite database to avoid state in the tracked/shared test database:

```powershell
$testDb = Join-Path $env:TEMP ("enterprise-ai-support-test-" + [guid]::NewGuid().ToString("N") + ".db")
$env:DATABASE_URL = "sqlite:///" + $testDb.Replace('\', '/')
$env:USE_SQLITE_FALLBACK = "0"
python -m pytest -q
$testExit = $LASTEXITCODE
Remove-Item -LiteralPath $testDb -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "$testDb-wal" -ErrorAction SilentlyContinue
Remove-Item -LiteralPath "$testDb-shm" -ErrorAction SilentlyContinue
if ($testExit -ne 0) { exit $testExit }
```

Validate dataset size, coverage, and offline quality gates (no model call):

```powershell
python -m evaluation.run_evaluation --quality-gate
```

Build the frontend:

```powershell
Set-Location frontend
npm ci
npm run build
Set-Location ..
```

### 4. Optional live evaluation

Live evaluation makes billable model calls. Configure `OPENAI_API_KEY` in the environment or
repository-root `.env` before running it:

```powershell
python -m evaluation.run_evaluation --live --provider both --output evaluation/reports/latest.json
```

To run the marked live smoke tests explicitly, configure a valid `OPENAI_API_KEY`, opt in, and
run:

```powershell
$env:RUN_LIVE_LLM_TESTS = "true"
python -m pytest -q -m live_llm
Remove-Item Env:RUN_LIVE_LLM_TESTS
```

These tests make external model calls and may incur charges. To enable LangSmith, configure
`LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, and
`LANGSMITH_PROJECT`. Review tracing and retention settings before sending any customer or
otherwise sensitive content to a third party.

## GitHub Actions

The CI workflow runs on pushes, pull requests, and manual dispatch. It compiles Python, runs a
Ruff check on a configured subset of files, executes tests and the offline evaluation gate, and
builds the frontend. A separate live job runs live LLM tests and DeepEval/RAGAS when
`OPENAI_API_KEY` is configured as a GitHub Actions secret; those calls can incur charges.
LangSmith needs the optional `LANGSMITH_API_KEY` secret and tracing repository variable.

Configure secrets under **GitHub repository → Settings → Secrets and variables → Actions**. Do
not put credentials in workflow files. Pull requests from forks generally do not receive
repository secrets, so their live jobs may be skipped or unavailable.

## Known gaps and improvement plan

This is a repository-level review of observed code and configuration, not a penetration test or
proof that every possible defect has been found. Priorities:

### P0 — block public or real-customer-data deployment

1. **No authentication or authorization.** API routes do not show an authentication dependency.
   Commerce/user writes, ticket operations, approval decisions, document ingestion, agent runs,
   and live evaluation are therefore not protected by verified user identity or role checks.
   Add an identity provider (OIDC/OAuth2), role-based access control, and route-level permission
   tests. See [`backend/app/api/routes/`](backend/app/api/routes/).
2. **Tenant IDs are caller-controlled or default to the demo tenant.** Chat, agent, RAG, MCP, and
   commerce flows accept request-supplied tenant identifiers or default to `tenant-demo`. Derive
   the tenant from the authenticated identity and enforce tenant filters on every read and write.
   Audit support-ticket queries and all MCP tools for the same boundary.
3. **Ticket approval can be bypassed.** The direct ticket-create endpoint does not require
   approval. Approval decisions accept a caller-provided approver ID without verifying the
   caller's identity or role. `/api/v1/agent/run` can return an in-memory approval state instead
   of creating the durable approval record used by chat. Route every ticket-creation path through
   one authorized, auditable approval service and test bypass attempts.
4. **CORS is broadly configured.** The app allows all origins, methods, and headers while also
   enabling credentials. Restrict origins and methods to the deployed UI and required API
   operations; never treat CORS as authentication.
5. **The included Compose deployment is not ready to deploy.** It refers to a backend image
   build, but there is no backend Dockerfile. The database resolver falls back to SQLite for
   non-SQLite URLs unless `USE_SQLITE_FALLBACK=0`; Compose does not set that flag, so the declared
   Postgres service may not be used. Compose also uses a development password and `--reload`.
   Add a production Dockerfile, explicit database configuration, health-based dependencies, and
   production secrets before documenting Compose as a deployment option.

### P1 — required before a controlled production pilot

6. **Schema creation and demo seeding happen during application import/startup.** `create_all`
   is not a schema migration strategy, and demo data should not be seeded into production.
   Add reviewed Alembic migrations and a separate, explicitly enabled development-seed command.
   The current `backend/alembic/versions/` directory has no migration revisions.
7. **MCP tools use demo application data, not live business systems.** Ticket search, ticket
   status updates, and refund lookup use the local database. A refund example is seeded for
   development, but no payment-provider/refund-system integration exists. Do not treat these
   records as live customer data; connect the tools to authoritative services before real use.
   See [`mcp-server/server.py`](mcp-server/server.py).
8. **Document ingestion lacks production controls.** The upload path reads the whole file into
   memory, accepts content based mainly on MIME type, and has no visible file-size, ownership,
   malware/content validation, retention, or deletion workflow. Add streaming size limits,
   authenticated tenant ownership, robust parsing, audit events, and document lifecycle APIs.
9. **RAG persistence and retrieval need operational guarantees.** Some paths use process memory;
   this is lost on restart and is not shared across workers. Add durable document/chunk metadata,
   indexing status and retries, deletion propagation, model/vector dimension validation, and
   documented degraded behavior. Test retrieval quality and tenant isolation with real service
   dependencies.
10. **Errors and API contracts need hardening.** Chat returns exception text in an API error
    response. Replace raw internal errors with stable public error codes and a request ID, while
    recording sanitized server-side diagnostics. Tighten validation for status transitions,
    pagination, document names, and business invariants.
11. **Demo and test SQLite files are tracked.** The repository contains tracked
    `enterprise_ai_local.db` and `enterprise_ai_test.db` files. They can accumulate state, make
    tests non-hermetic, and risk committing real data later. Remove database artifacts from
    version control, add appropriate ignore rules, and use isolated temporary databases in CI and
    local tests.
12. **No visible service-level protection for cost or abuse.** Add request rate limits, upload
    quotas, per-tenant model budgets, concurrency limits, explicit upstream timeouts, retry
    policy, circuit breakers, and cancellation handling. Redis is configured but no rate-limit or
    cache usage is visible in the application.
13. **Health and observability are incomplete.** `/api/v1/health` always reports `ok` and does
    not check Postgres, Qdrant, or OpenAI availability. Add separate liveness/readiness checks,
    structured logs, metrics, alerts, trace correlation, and privacy-aware retention/redaction.
14. **Approval and business workflows need more invariants.** Verify customer/order ownership,
    prevent duplicate actions with idempotency keys, enforce valid status transitions, record who
    did what, and test concurrency/transaction failure cases. Order creation does not implement
    inventory reservation/decrement or payment/refund processing.

### P2 — reliability, quality, and maintainability

15. **The agent and chat do not share one orchestration contract.** Chat builds its own prompt and
    database context; the LangGraph route uses rule-based intent selection and MCP. Consolidate
    the intended business flow, input/output schemas, error handling, approval behavior, and
    tool-result validation so UI and API callers get consistent behavior.
16. **Model and retrieval safety need broader evidence.** The 35-case golden dataset and offline
    gate do not prove answer correctness, resilience to prompt injection, retrieval relevance,
    or safe behavior under ambiguous/malicious documents. Expand adversarial and tenant-isolation
    tests; evaluate groundedness, refusal behavior, citation accuracy, and regression cases on
    representative data.
17. **Conversation and frontend behavior are prototype-level.** Conversation history is supplied
    by the client and is not a durable, access-controlled server-side conversation store. The UI
    contains hardcoded demo identities and tenant values, an absolute localhost evaluation URL,
    and a fabricated 100% offline evaluation snapshot. Add configurable API origins, real identity
    handling, honest loading/error states, accessibility checks, and frontend tests.
18. **The tool transport is costly to scale.** The backend starts an MCP subprocess for each tool
    call. Consider a managed/persistent tool service or another bounded, observable transport,
    with request timeouts, concurrency controls, and safe shutdown.
19. **CI and dependency governance are incomplete.** Ruff only checks a subset of files, Python
    dependencies are not locked as a reproducible production set, and no security/dependency
    scanning, SBOM, artifact signing, or deployment gate is visible. Expand lint/type coverage,
    lock and regularly update dependencies, add scanning and provenance controls, and test the
    actual deployment image.
20. **There is no production deployment/operations runbook.** Define supported environments,
    secrets rotation, TLS/network policy, backups and restore drills, retention/deletion, incident
    response, SLOs, load tests, and rollback procedures.

## Production-readiness checklist

Do not call this production-ready until the following are implemented and verified:

- [ ] Authentication, role-based authorization, and identity-derived tenant isolation
- [ ] No ticket, refund, or other protected action can bypass durable authorized approval
- [ ] Migrations and production configuration; no startup demo seeding or tracked database files
- [ ] Real integrations for every enabled MCP tool
- [ ] Secure document ingestion, data retention/deletion, and privacy-reviewed tracing
- [ ] Rate/cost limits, timeouts, monitoring, readiness checks, backups, and incident procedures
- [ ] CI security checks, deployment-image tests, authorization/tenant tests, and load tests
- [ ] A staging rollout with synthetic data followed by a reviewed, limited pilot

Until then, use only local or network-isolated environments with synthetic data and rotated,
least-privilege development credentials.
