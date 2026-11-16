"""FastAPI entry point; supports both Uvicorn and direct script launch."""
from pathlib import Path
import sys
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from alembic import command
from alembic.config import Config
from urllib.parse import urlsplit

# Running ``python app/main.py`` does not establish a package context. Add the
# backend directory and use package imports in that case; Uvicorn's normal
# ``app.main:app`` import continues to use relative imports.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app.roles import roles_router
    from app.api import router
    from app.assistant import router as assistant_router
    from app.security import auth_router
    from app.core import settings
else:
    from .roles import roles_router
    from .api import router
    from .assistant import router as assistant_router
    from .security import auth_router
    from .core import settings

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

@asynccontextmanager
async def lifespan(_: FastAPI):
    # Keep direct Uvicorn runs on PostgreSQL in sync with the same schema as Docker.
    # Alembic upgrades are additive and preserve timetable and account records.
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    config.set_main_option("prepend_sys_path", str(BACKEND))
    await asyncio.to_thread(command.upgrade, config, "head")
    yield

production = settings.app_env.lower() == "production"
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="إدارة الجدول المدرسي والاحتياط اليومي",
    lifespan=lifespan,
    docs_url=None if production else "/docs",
    redoc_url=None if production else "/redoc",
    openapi_url=None if production else "/openapi.json",
)
origins = [origin.strip() for origin in settings.cors_origins.split(",")]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(auth_router)
app.include_router(router)
app.include_router(assistant_router)
app.include_router(roles_router)

@app.middleware("http")
async def browser_security_middleware(request, call_next):
    """Reject cross-origin API writes and keep authenticated responses out of caches."""
    if request.url.path.startswith("/api/") and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if not origin and ({"school_admin_session", "school_admin_activation"} & set(request.cookies)):
            response = JSONResponse({"detail": "تعذر التحقق من مصدر الطلب؛ أعد تحميل الصفحة وحاول مجددًا"}, status_code=403)
        elif origin:
            parsed = urlsplit(origin)
            normalized_origin = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}" if parsed.scheme and parsed.netloc else ""
            configured_origins = {
                item.strip().rstrip("/").lower()
                for item in settings.cors_origins.split(",")
                if item.strip() and item.strip() != "*"
            }
            request_origin = f"{request.url.scheme.lower()}://{request.url.netloc.lower()}"
            if normalized_origin not in configured_origins | {request_origin}:
                response = JSONResponse({"detail": "تم رفض الطلب لأسباب أمنية؛ أعد تحميل الصفحة وحاول مجددًا"}, status_code=403)
            else:
                response = await call_next(request)
        else:
            response = await call_next(request)
    else:
        response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; form-action 'self'; "
        "script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https:; "
        "font-src 'self' data:; connect-src 'self' https: http://localhost:* http://127.0.0.1:*",
    )
    if request.url.path.startswith("/api/") or request.url.path in {"/", "/config.js"}:
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

@app.get("/healthz", include_in_schema=False)
def healthz():
    from .database import SessionLocal
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="قاعدة البيانات غير متاحة") from exc
    return {"status": "ok", "database": "connected"}

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND / "assets"), name="assets")

@app.get("/", include_in_schema=False)
def home():
    index = FRONTEND / "index.html"
    return FileResponse(index, headers={"Cache-Control": "no-store"}) if index.exists() else {"message": settings.app_name, "docs": "/docs"}

@app.get("/config.js", include_in_schema=False)
def frontend_config():
    config = FRONTEND / "config.js"
    return FileResponse(config, media_type="application/javascript") if config.exists() else Response("window.APP_CONFIG = Object.freeze({ apiBaseUrl: '' });", media_type="application/javascript")

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=settings.port, reload=False)
