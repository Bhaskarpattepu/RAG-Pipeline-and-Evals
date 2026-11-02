# Enterprise AI Support Engineer

This repository contains a production-style enterprise AI support platform prototype focused on a staged implementation of backend orchestration, evaluation, and human-in-the-loop operations.

## Included
- FastAPI backend with a live `/api/v1/chat` endpoint
- Interactive support chatbot grounded in policy documents and verified order, payment, product, customer, and user records
- CRUD APIs for orders, products, and staff users, with seeded demo records
- Durable ticket approval requests; approval creates a ticket only after a reviewer approves it
- Settings using `pydantic-settings`
- SQLAlchemy models and database session setup
- Initial support ticket APIs
- OpenAI integration layer with LangSmith tracing
- DeepEval and RAGAS live evaluation with JSON report export
- Golden dataset with agent tool-call and human-approval quality gates
- LangSmith run/case trace metadata for evaluation dashboards
- Evaluation API routes and an offline golden-dataset validation mode
- Example Docker Compose setup
- Pytest coverage for chat, ticket, agent, RAG, approval, and evaluation flows

## Quick start

1. Copy `.env.example` to `backend/.env` and enter your OpenAI API key. Keep the key on the
   backend; do not put it in frontend code or commit the `.env` file.
2. Create a virtual environment and install dependencies:
   `python -m venv .venv && .\.venv\Scripts\Activate.ps1 && pip install -r backend/requirements.txt`
3. Start the API in one terminal:
   `cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`
4. Start the web app in a second terminal:
   `cd frontend && npm run dev`
   Open `http://localhost:5173`. Ask about refund eligibility, refund timelines, or payment
   failures; the backend retrieves matching policy text and returns citations. An OpenAI API key
   is required for generated responses.
5. Explore the management endpoints at `http://localhost:8000/docs`. Sample demo records include
   order `ORD-2005`, product `PROD-1001` / SKU `SKU-1001`, and user `USER-1001`.
   - `GET /api/v1/orders` and `GET /api/v1/orders/ORD-2005`
   - `GET /api/v1/products`; use `POST`, `PATCH`, and `DELETE` to manage products
   - `GET /api/v1/users`; use `POST`, `PATCH`, and `DELETE` to manage staff-user records
   - `POST /api/v1/orders` creates an order with product line items; `PATCH /api/v1/orders/{order_number}` updates its status
   - Ask the chatbot “What is the status of order ORD-2005?” or “Check product stock for SKU-1001.”
   - For a ticket request, include a valid order number or customer ID. The app creates a pending
     approval request; it does not create a ticket until an approver approves it in the dashboard.
6. Run tests:
   `python -m pytest -q`
7. Validate the evaluation dataset and its quality gates without model calls:
   `python -m evaluation.run_evaluation --quality-gate`
8. Generate live scores and an exportable report (API calls incur charges; default score threshold is 0.70):
   `python -m evaluation.run_evaluation --live --provider both --output evaluation/reports/latest.json`

## GitHub Actions

The `CI` workflow runs on every push and pull request. It installs Python dependencies, compiles
the backend and evaluation packages, runs the offline test suite and dataset quality gates, and
builds the frontend. Live OpenAI checks run automatically after those checks pass when the repository has an
`OPENAI_API_KEY` Actions secret configured. Without that secret, CI still validates the offline
code and reports the live evaluation as skipped.

To enable live checks, open the GitHub repository's **Settings → Secrets and variables → Actions**
and add a repository secret named `OPENAI_API_KEY`. Live tests and DeepEval/RAGAS scoring make
billable API calls on each qualifying push; do not use a restricted or low-quota key. Optional
LangSmith tracing requires the `LANGSMITH_API_KEY` secret and a repository variable
`LANGSMITH_TRACING` set to `true`. The resulting live evaluation JSON is uploaded as a workflow
artifact. Live CI fails if any agent tool-call or human-approval safety check fails, or if either
the DeepEval or RAGAS mean score is below 0.70.

## Notes
- `OPENAI_API_KEY` is required for live LLM calls.
- The development app seeds a demo tenant, customer, user, product, failed order, and payment into the configured database at startup. Local default uses SQLite.
- The user-management API is a prototype directory, not authentication/authorization. Do not expose the API publicly or use real customer records until access control and tenant enforcement are added.
- Live evaluation uses `OPENAI_MODEL` for answers and `OPENAI_EVALUATION_MODEL` for provider scoring; live runs incur API costs.
- Enable LangSmith with `LANGSMITH_TRACING=true`, `LANGSMITH_API_KEY`, and `LANGSMITH_PROJECT`. Each report includes an `evaluation_run_id` to filter its traces.
- See [evaluation/README.md](evaluation/README.md) for provider details and the manual GitHub Actions workflow.
