"""오류 응답 — 기획서 Part 1 7.1 「응답 형식 예시」의 오류 모양으로 통일한다.

    {"success": false, "error": {"code": "ACCOUNT_NOT_FOUND", "message": "계좌를 찾을 수 없어요."}}

성공 응답은 감싸지 않는다(Part 2 9.1·9.2, Part 5 16장 예시가 모두 본문 그대로).
오류 코드는 기획서에 있는 이름을 먼저 쓴다(Part 2 9.3, Part 5 13장).
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str):
        self.status_code = status_code
        self.code = code
        self.message = message


def _body(code: str, message: str, **extra) -> dict:
    return {"success": False, "error": {"code": code, "message": message, **extra}}


# --- 자주 쓰는 오류 ---------------------------------------------------------------
def unauthorized() -> ApiError:
    return ApiError(401, "UNAUTHORIZED", "로그인이 필요합니다.")


def not_found(code: str, message: str) -> ApiError:
    """없는 것과 남의 것을 똑같이 404 로 답한다 — 존재 여부가 드러나지 않게(Part 2 ACCT-F02 예외/오류)."""
    return ApiError(404, code, message)


def account_not_found() -> ApiError:
    return not_found("ACCOUNT_NOT_FOUND", "계좌를 찾을 수 없어요.")


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        return JSONResponse(_body(exc.code, exc.message), status_code=exc.status_code)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "reason": e["msg"]} for e in exc.errors()]
        return JSONResponse(_body("VALIDATION_ERROR", "요청 값을 확인해 주세요.", details=details), status_code=422)
