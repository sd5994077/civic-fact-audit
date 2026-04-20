from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.v1.router import router as v1_router
from app.core.config import settings
from app.core.errors import AppError
from app.db.database import get_engine

app = FastAPI(title=settings.app_name, version=settings.app_version)
app.include_router(v1_router)


@app.exception_handler(AppError)
async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={'error': {'code': exc.code, 'message': exc.message, 'details': exc.details}},
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            'error': {
                'code': 'validation_error',
                'message': 'Request validation failed.',
                'details': {'errors': exc.errors()},
            }
        },
    )


@app.exception_handler(SQLAlchemyError)
async def db_error_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            'error': {
                'code': 'database_error',
                'message': 'Database operation failed.',
                'details': {'reason': str(exc.__class__.__name__)},
            }
        },
    )


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


@app.get('/version')
def version() -> dict[str, str]:
    return {'version': settings.app_version, 'env': settings.app_env}


@app.on_event('startup')
def startup_check() -> None:
    with get_engine().connect() as connection:
        connection.execute(text('SELECT 1'))
