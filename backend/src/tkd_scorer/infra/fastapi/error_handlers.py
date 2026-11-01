from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from tkd_scorer.domain.exceptions.errors import (
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)


def _error_response(status_code: int, exc: DomainError) -> JSONResponse:
    content: dict[str, str] = {"detail": str(exc)}
    if exc.code:
        # Machine-readable reason (e.g. "match_closed") so clients can stop retrying definitive rejections.
        content["code"] = exc.code
    return JSONResponse(status_code=status_code, content=content)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return _error_response(404, exc)

    @app.exception_handler(UnauthorizedError)
    async def _unauthorized(_: Request, exc: UnauthorizedError) -> JSONResponse:
        return _error_response(401, exc)

    @app.exception_handler(ForbiddenError)
    async def _forbidden(_: Request, exc: ForbiddenError) -> JSONResponse:
        return _error_response(403, exc)

    @app.exception_handler(ConflictError)
    async def _conflict(_: Request, exc: ConflictError) -> JSONResponse:
        return _error_response(409, exc)

    @app.exception_handler(ValidationError)
    async def _validation(_: Request, exc: ValidationError) -> JSONResponse:
        return _error_response(422, exc)

    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return _error_response(400, exc)
