from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
import uuid


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Adds / propagates X-Correlation-ID header for traceability across services.
    """
    async def dispatch(self, request: Request, call_next):
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        return response


def setup_exception_handlers(app: FastAPI):
    """
    Standardizes error responses across APIs.
    Required by assignment: code, message, correlationId.
    """
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        correlation_id = getattr(request.state, "correlation_id", "unknown")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": str(exc.status_code),
                "message": exc.detail,
                "correlationId": correlation_id
            }
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        correlation_id = getattr(
            request.state,
            "correlation_id",
            request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        )

        cleaned_errors = []
        for err in exc.errors():
            cleaned_errors.append({
                "loc": err.get("loc"),
                "msg": err.get("msg"),
                "type": err.get("type")
            })

        return JSONResponse(
            status_code=422,
            content={
                "code": "422",
                "message": "Validation error",
                "details": cleaned_errors,
                "correlationId": correlation_id
            }
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        correlation_id = getattr(request.state, "correlation_id", "unknown")
        return JSONResponse(
            status_code=500,
            content={
                "code": "500",
                "message": "Internal Server Error",
                "correlationId": correlation_id
            }
        )


def require_role(allowed_roles: list[str]):
    """
    Lightweight RBAC helper for assignment/demo.

    Expected Authorization header format:
    Authorization: Bearer admin_test
    Authorization: Bearer reception_test
    Authorization: Bearer doctor_test

    In real implementation, gateway would validate JWT and services would verify claims.
    """
    def role_checker(authorization: str = Header(default="Bearer admin_test")):
        try:
            scheme, token = authorization.split()
            if scheme.lower() != "bearer":
                raise ValueError()

            # Example token format: admin_test -> role = admin
            role = token.split("_")[0]
        except Exception:
            raise HTTPException(status_code=401, detail="Invalid token format")

        if role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role {role} is not permitted. Allowed: {allowed_roles}"
            )

        return role

    return role_checker