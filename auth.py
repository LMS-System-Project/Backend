from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from database import get_supabase_admin
from config import SUPABASE_KEY

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Validate the Supabase JWT from the Authorization header.
    Returns the user profile dict from the profiles table.
    """
    token = credentials.credentials

    try:
        # Supabase JWTs are signed with the JWT secret which equals the
        # anon key for verification. We decode to get the 'sub' (user id).
        # For Supabase, the JWT secret is derived from the project.
        # We'll verify by calling Supabase's auth.get_user() with the token.
        supabase = get_supabase_admin()
        user_response = supabase.auth.get_user(token)

        if not user_response or not user_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )

        user_id = user_response.user.id

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

        return profile.data

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
        )
