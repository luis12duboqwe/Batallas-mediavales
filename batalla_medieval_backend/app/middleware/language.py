"""Language middleware that resolves translations based on user or headers."""

from typing import Callable, Optional

from fastapi import Request
from jose import JWTError, jwt
from starlette.middleware.base import BaseHTTPMiddleware

from ..config import get_settings
from ..database import SessionLocal
from ..models import User
from ..services.i18n import DEFAULT_LANGUAGE, available_languages, get_translator


class LanguageMiddleware(BaseHTTPMiddleware):
    """Resolve the preferred language for each request."""

    def __init__(self, app, default_language: str = DEFAULT_LANGUAGE):
        super().__init__(app)
        self.default_language = default_language
        self.settings = get_settings()

    def _get_language_from_header(self, request: Request) -> Optional[str]:
        """Parse the Accept-Language header for a supported language code."""

        header = request.headers.get("Accept-Language")
        if not header:
            return None
        preferred = header.split(",")[0].strip().lower()
        preferred = preferred.split("-")[0]
        return preferred if preferred in available_languages() else None

    def _get_language_from_user(self, request: Request) -> Optional[str]:
        """Return a user's preferred language when a valid token is provided."""

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.lower().startswith("bearer "):
            return None
        token = auth_header.split()[1]
        try:
            payload = jwt.decode(
                token,
                self.settings.secret_key,
                algorithms=[self.settings.algorithm],
                options={"verify_exp": True},
            )
        except JWTError:
            return None

        username = payload.get("sub")
        if not username:
            return None

        with SessionLocal() as db:
            user = db.query(User).filter(User.username == username).first()
            if user and user.language in available_languages():
                return user.language
        return None

    async def dispatch(self, request: Request, call_next: Callable):
        """Attach translator helpers to the request state and set response headers."""

        language = (
            self._get_language_from_user(request)
            or self._get_language_from_header(request)
            or self.default_language
        )
        request.state.language = language
        request.state.translate = get_translator(language, self.default_language)
        response = await call_next(request)
        response.headers["Content-Language"] = language
        return response
