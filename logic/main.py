from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from logic.payroll.router import router as payroll_router

UI_DIR = Path(__file__).parent.parent / "ui"

app = FastAPI(
    title="ERP Agent — Logic Layer",
    version="0.1.0",
    description="AI-native business logic engine. All ERP operations flow through here.",
)

app.include_router(payroll_router)
app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")


@app.get("/", include_in_schema=False)
def root():
    return FileResponse(UI_DIR / "payroll" / "index.html")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
