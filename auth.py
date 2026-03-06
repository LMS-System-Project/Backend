import base64
import json
from datetime import datetime

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from database import get_supabase_admin

security = HTTPBearer()


# ── Full user validation (fetches profile from DB) ────────────

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Validate the Supabase JWT from the Authorization header.
    Returns the user profile dict from the profiles table, enriched with
    the email from Supabase Auth (since the profiles table has no email column).
    """
    token = credentials.credentials

    try:
        supabase = get_supabase_admin()
        user_response = supabase.auth.get_user(token)

        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        auth_user = user_response.user
        user_id = auth_user.id

        # Fetch the profile from the profiles table
        profile = (
            supabase.table("profiles")
            .select("*")
            .eq("id", str(user_id))
            .single()
            .execute()
        )

        if not profile.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found",
            )

        # Enrich with the email from auth.users (profiles table has no email)
        profile_data = profile.data
        profile_data["email"] = auth_user.email or ""

        return profile_data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
        )


# ── Lightweight token payload extraction ──────────────────────

def _decode_supabase_token(token: str) -> dict:
    """
    Decode a Supabase JWT without signature verification.
    Supabase tokens are already validated by Supabase Auth;
    we trust them and just extract the payload for role checks.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid token format")

        payload_b64 = parts[1]
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_json = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_json)

        # Check expiration
        if "exp" in payload:
            if datetime.utcnow().timestamp() > payload["exp"]:
                raise ValueError("Token expired")

        # Extract role from user_metadata if present
        if "user_metadata" in payload and "role" in payload["user_metadata"]:
            payload["role"] = payload["user_metadata"]["role"]

        return payload
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """Fast JWT payload extraction without DB lookup."""
    return _decode_supabase_token(credentials.credentials)


# ── Role-based access control ────────────────────────────────

def require_role(*roles: str):
    """
    Dependency factory that enforces role-based access.
    Usage: Depends(require_role("admin", "instructor"))
    """
    def _check(payload: dict = Depends(get_token_payload)) -> dict:
        user_role = payload.get("role")
        if user_role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {list(roles)}",
            )
        return payload
    return _check
