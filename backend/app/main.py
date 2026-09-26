"""FastAPI entry point; supports both Uvicorn and direct script launch."""
from pathlib import Path
import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Running ``python app/main.py`` does not establish a package context. Add the
# backend directory and use package imports in that case; Uvicorn's normal
# ``app.main:app`` import continues to use relative imports.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.api import router
    from app.security import auth_router
    from app.core import settings
else:
    from .api import router
    from .security import auth_router
    from .core import settings

app = FastAPI(title=settings.app_name, version="1.0.0", description="إدارة الجدول المدرسي والاحتياط اليومي")
origins = [origin.strip() for origin in settings.cors_origins.split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router)
app.include_router(router)
FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

@app.get("/", include_in_schema=False)
def home():
    index = FRONTEND / "index.html"
    return FileResponse(index) if index.exists() else {"message": settings.app_name, "docs": "/docs"}

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=settings.port, reload=False)
