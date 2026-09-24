"""Grant or revoke PaperAid admin access (Firebase custom claim `admin`). Production only.

Usage (with Application Default Credentials for the project):
    python scripts/set_admin.py someone@example.com          # grant
    python scripts/set_admin.py someone@example.com --revoke # revoke
The user must sign out and in again for the change to reach their browser.
"""

import sys

import firebase_admin
from firebase_admin import auth


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    email, revoke = sys.argv[1], "--revoke" in sys.argv
    firebase_admin.initialize_app()
    user = auth.get_user_by_email(email)
    claims = dict(user.custom_claims or {})
    if revoke:
        claims.pop("admin", None)
    else:
        claims["admin"] = True
    auth.set_custom_user_claims(user.uid, claims)
    print(f"{'Revoked' if revoke else 'Granted'} admin for {email} ({user.uid}).")


if __name__ == "__main__":
    main()
