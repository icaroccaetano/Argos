"""Entrypoint da aplicação FastAPI.

Implementa: RF-01-01, RT-01-02, RT-01-06
"""

from fastapi import FastAPI

from api.routers import curricula, evaluations

app = FastAPI(
    title="Argos",
    description="API de scoring de currículo × vaga",
    version="0.1.0",
)

app.include_router(curricula.router, prefix="/v1/curricula", tags=["curricula"])
app.include_router(evaluations.router, prefix="/v1/evaluations", tags=["evaluations"])


@app.get("/health")
async def health() -> dict[str, str]:
    """Endpoint operacional, fora do versionamento e sem dependências externas."""
    return {"status": "ok"}
