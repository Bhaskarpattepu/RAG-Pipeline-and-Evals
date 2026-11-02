from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.models
from app.api.routes import agent, approval, chat, commerce, evaluation, health, rag, support
from app.db.base import Base
from app.db.seed import seed_demo_data
from app.db.session import SessionLocal, engine

Base.metadata.create_all(bind=engine)
with SessionLocal() as db:
    seed_demo_data(db)

app = FastAPI(title="Enterprise AI Support", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat.router, prefix="/api/v1")
app.include_router(commerce.router, prefix="/api/v1")
app.include_router(support.router, prefix="/api/v1")
app.include_router(rag.router, prefix="/api/v1")
app.include_router(agent.router, prefix="/api/v1")
app.include_router(approval.router, prefix="/api/v1")
app.include_router(evaluation.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Enterprise AI Support API", "status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", reload=True, host="0.0.0.0", port=8000)
