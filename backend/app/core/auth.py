"""Identity for every protected request. The acting user always comes from a verified credential,
never from the request body. Dev auth exists only for local runs and is refused in production."""

import hashlib
import re

from fastapi import Depends, Request

from app.core.config import Settings, get_settings
from app.core.errors import Forbidden, Unauthorized
from app.jobs.service import User

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_firebase_ready = False


def _firebase():
    global _firebase_ready
    import firebase_admin

    if not _firebase_ready:
        firebase_admin.initialize_app()
        _firebase_ready = True
    return firebase_admin


def current_user(request: Request, settings: Settings = Depends(get_settings)) -> User:
    header = request.headers.get("authorization", "")
    if settings.auth_mode == "dev":
        if settings.env == "production":
            raise Unauthorized("Sign in again.")
        if not header.startswith("Dev "):
            raise Unauthorized("Please sign in to continue.")
        email = header[4:].strip().lower()
        if not _EMAIL.match(email):
            raise Unauthorized("Please sign in to continue.")
        uid = "u_" + hashlib.sha256(email.encode()).hexdigest()[:20]
        return User(uid=uid, email=email, is_admin=email in {e.lower() for e in settings.admin_emails})

    if not header.startswith("Bearer "):
        raise Unauthorized("Please sign in to continue.")
    _firebase()
    from firebase_admin import app_check, auth, exceptions

    try:
        claims = auth.verify_id_token(header[7:], check_revoked=True)
    except (auth.InvalidIdTokenError, auth.ExpiredIdTokenError, auth.RevokedIdTokenError, auth.CertificateFetchError, ValueError) as exc:
        raise Unauthorized("Your session has expired. Please sign in again.") from exc
    if settings.require_app_check:
        token = request.headers.get("x-firebase-appcheck", "")
        try:
            app_check.verify_token(token)
        except (ValueError, exceptions.FirebaseError) as exc:
            raise Unauthorized("This request could not be verified. Refresh the page and try again.", code="APP_CHECK_FAILED") from exc
    return User(uid=claims["uid"], email=claims.get("email", ""), is_admin=claims.get("admin") is True, verified=bool(claims.get("email_verified")))


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise Forbidden("You do not have access to this page.")
    return user
