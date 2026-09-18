"""FastAPI app: routes, middleware, exception handlers (plan Section 9.2)."""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.schemas import InfeasibleError

log = logging.getLogger("gridwise")

MAX_BODY_BYTES = 2 * 1024 * 1024


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > MAX_BODY_BYTES:
                    return JSONResponse(
                        status_code=400,
                        content={"error": "invalid_request", "detail": "body too large"},
                    )
            except ValueError:
                pass
        body = await request.body()
        if len(body) > MAX_BODY_BYTES:
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_request", "detail": "body too large"},
            )
        return await call_next(request)


app = FastAPI()
app.add_middleware(BodySizeLimitMiddleware)


def summarize_field_paths(exc: RequestValidationError) -> str:
    """Safe field-path summary; never echoes input values."""
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", []) if p != "body")
        msg = err.get("msg", "invalid")
        parts.append(f"{loc}: {msg}" if loc else msg)
    return "; ".join(parts) if parts else "invalid request"


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={"error": "invalid_request", "detail": summarize_field_paths(exc)},
    )


@app.exception_handler(InfeasibleError)
async def _infeasible_error_handler(request: Request, exc: InfeasibleError):
    return JSONResponse(status_code=422, content={"error": "infeasible_scenario"})


@app.exception_handler(Exception)
async def _internal_error_handler(request: Request, exc: Exception):
    log.exception("internal error")
    return JSONResponse(status_code=500, content={"error": "internal_error"})


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/optimize-energy")
async def optimize_energy(request: Request):
    raise NotImplementedError
