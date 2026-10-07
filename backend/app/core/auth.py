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


def _firebase(settings: Settings):
    """Firebase is pinned to the application project (GCP_PROJECT). Never inferred: Vertex runs in a
    project of its own, and an inferred project could verify sign-ins against the wrong one."""
    global _firebase_ready
    import firebase_admin

    if not _firebase_ready:
        firebase_admin.initialize_app(options={"projectId": settings.gcp_project} if settings.gcp_project else None)
        _firebase_ready = True
    return firebase_admin


def current_user(request: Request, settings: Settings = Depends(get_settings)) -> User:
    return _verified_user(request, settings, need_app_check=True)


def _verified_user(request: Request, settings: Settings, need_app_check: bool) -> User:
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
    _firebase(settings)
    from firebase_admin import app_check, auth, exceptions

    try:
        claims = auth.verify_id_token(header[7:], check_revoked=True)
    except (auth.InvalidIdTokenError, auth.ExpiredIdTokenError, auth.RevokedIdTokenError, auth.CertificateFetchError, ValueError) as exc:
        raise Unauthorized("Your session has expired. Please sign in again.") from exc
    if settings.require_app_check and need_app_check:
        token = request.headers.get("x-firebase-appcheck", "")
        try:
            app_check.verify_token(token)
        except (ValueError, exceptions.FirebaseError) as exc:
            raise Unauthorized("This request could not be verified. Refresh the page and try again.", code="APP_CHECK_FAILED") from exc
    return User(uid=claims["uid"], email=claims.get("email", ""), is_admin=claims.get("admin") is True, verified=bool(claims.get("email_verified")))


def optional_user(request: Request, settings: Settings = Depends(get_settings)) -> User | None:
    """The signed-in user when the request carries a valid ID token, otherwise None. Only for public
    endpoints that personalise a harmless answer (which services this visitor may use). App Check is
    not required here: waiting for a fresh reCAPTCHA attestation held the whole app on its splash
    screen after an hour away. Every endpoint that acts or reads a user's data still requires it."""
    if not request.headers.get("authorization"):
        return None
    try:
        return _verified_user(request, settings, need_app_check=False)
    except Unauthorized:
        return None


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise Forbidden("You do not have access to this page.")
    return user
