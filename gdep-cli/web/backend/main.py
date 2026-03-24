"""
gdep FastAPI 백엔드
실행: uvicorn main:app --reload --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.project import router as project_router
from routers.classes  import router as classes_router
from routers.flow     import router as flow_router
from routers.agent    import router as agent_router
from routers.unity    import router as unity_router
from routers.llm      import router as llm_router
from routers.ue5      import router as ue5_router
from routers.engine   import router as engine_router
from routers.watch    import router as watch_router

app = FastAPI(
    title="gdep API",
    description="게임 클라이언트 코드베이스 분석 API",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(project_router, prefix="/api/project", tags=["project"])
app.include_router(classes_router, prefix="/api/classes", tags=["classes"])
app.include_router(flow_router,    prefix="/api/flow",    tags=["flow"])
app.include_router(agent_router,   prefix="/api/agent",   tags=["agent"])
app.include_router(unity_router,   prefix="/api/unity",   tags=["unity"])
app.include_router(llm_router,     prefix="/api/llm",     tags=["llm"])
app.include_router(ue5_router,     prefix="/api/ue5",     tags=["ue5"])
app.include_router(engine_router,  prefix="/api/engine",  tags=["engine"])
app.include_router(watch_router,   prefix="/api",         tags=["watch"])


@app.get("/")
def root():
    return {"status": "ok", "message": "gdep API running"}