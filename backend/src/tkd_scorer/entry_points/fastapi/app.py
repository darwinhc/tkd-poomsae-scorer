from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from tkd_scorer.adapters.realtime.fastapi_realtime_adapter import FastApiRealtimeAdapter
from tkd_scorer.adapters.security.credential_cipher import FernetCredentialCipher
from tkd_scorer.entry_points.fastapi.admin_views.labels import make_status_label_filter
from tkd_scorer.entry_points.fastapi.admin_views.routes import router as admin_router
from tkd_scorer.entry_points.fastapi.api.routes import router as api_router
from tkd_scorer.entry_points.fastapi.websocket.routes import router as ws_router
from tkd_scorer.infra.config.runtime_bootstrap import prepare_runtime
from tkd_scorer.infra.config.runtime_paths import package_root
from tkd_scorer.infra.config.settings import get_settings
from tkd_scorer.infra.fastapi.admin_auth import (
    INTERNAL_ADMIN_BASE_PATH,
    is_admin_auth_enabled,
    is_admin_authenticated,
    is_internal_admin_path,
    is_internal_live_admin_path,
    is_internal_public_admin_path,
    is_ip_allowed,
    login_redirect_url,
    to_external_admin_path,
    to_internal_admin_path,
    validate_admin_security_config,
)
from tkd_scorer.infra.fastapi.error_handlers import register_exception_handlers
from tkd_scorer.infra.i18n import make_translator
from tkd_scorer.infra.logging.logger import configure_logging
from tkd_scorer.infra.persistence.session_factory import (
    create_engine_and_session_factory,
    create_schema,
)
from tkd_scorer.infra.websocket.connection_hub import ConnectionHub

PACKAGE_ROOT = package_root()
TEMPLATES_DIR = PACKAGE_ROOT / "infra" / "templates"
STATIC_DIR = PACKAGE_ROOT / "infra" / "static"

if not TEMPLATES_DIR.exists():
    raise RuntimeError(f"Templates directory not found: {TEMPLATES_DIR}")
if not STATIC_DIR.exists():
    raise RuntimeError(f"Static files directory not found: {STATIC_DIR}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    runtime = prepare_runtime(settings)
    if settings.admin_security_fail_fast:
        errors = validate_admin_security_config(settings)
        if errors:
            joined = " | ".join(errors)
            raise RuntimeError(f"Invalid security configuration: {joined}")
    configure_logging(level_name=settings.log_level, log_file_path=runtime.log_file_path)

    engine, session_factory = create_engine_and_session_factory(runtime.database_url)
    create_schema(engine, credential_cipher=FernetCredentialCipher(secret_key=settings.jwt_secret_key))

    app.state.settings = settings
    app.state.runtime = runtime
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.connection_hub = ConnectionHub()
    app.state.realtime = FastApiRealtimeAdapter(app.state.connection_hub)
    app.state.templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    app.state.templates.env.filters["status_label"] = make_status_label_filter(settings.ui_language)
    app.state.templates.env.globals["t"] = make_translator(settings.ui_language)
    app.state.templates.env.globals["ui_language"] = settings.ui_language
    app.state.templates.env.globals["admin_base_path"] = settings.admin_base_path
    yield
    engine.dispose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    @app.middleware("http")
    async def admin_auth_middleware(request: Request, call_next):
        if not hasattr(request.app.state, "settings"):
            return await call_next(request)
        settings = request.app.state.settings
        original_path = request.scope.get("path", request.url.path)
        query = request.scope.get("query_string", b"").decode("utf-8")
        original_external_path = f"{original_path}?{query}" if query else original_path

        internal_path = to_internal_admin_path(original_path, configured_base_path=settings.admin_base_path)
        using_custom_admin_base = settings.admin_base_path != INTERNAL_ADMIN_BASE_PATH

        if using_custom_admin_base and is_internal_admin_path(original_path):
            return PlainTextResponse("Not Found", status_code=404)

        if internal_path != original_path:
            request.scope["path"] = internal_path
            request.scope["raw_path"] = internal_path.encode("utf-8")

        if is_internal_admin_path(internal_path):
            if not is_internal_live_admin_path(internal_path) and not is_ip_allowed(request):
                return PlainTextResponse("Forbidden", status_code=403)
            if (
                is_admin_auth_enabled(request)
                and not is_internal_public_admin_path(internal_path)
                and not is_admin_authenticated(request)
            ):
                return RedirectResponse(
                    url=login_redirect_url(request=request, external_next_path=original_external_path),
                    status_code=303,
                )

        response = await call_next(request)
        location = response.headers.get("location")
        if location:
            rewritten_location = to_external_admin_path(
                location,
                configured_base_path=settings.admin_base_path,
            )
            if rewritten_location != location:
                response.headers["location"] = rewritten_location
        return response

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(api_router)
    app.include_router(admin_router)
    app.include_router(ws_router)
    register_exception_handlers(app)
    return app


app = create_app()
