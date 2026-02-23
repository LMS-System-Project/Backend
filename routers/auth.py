from fastapi import APIRouter, HTTPException, status, Depends
from database import get_supabase_client, get_supabase_admin
from schemas import LoginRequest, RegisterRequest, AuthResponse, UserResponse
from auth import get_current_user

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """Authenticate a user with email and password via Supabase Auth."""
    try:
        supabase = get_supabase_client()
        auth_response = supabase.auth.sign_in_with_password(
            {"email": request.email, "password": request.password}
        )

        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        user_id = str(auth_response.user.id)
        access_token = auth_response.session.access_token

        # Fetch profile using admin client (bypasses RLS)
        admin = get_supabase_admin()
        profile = (
            admin.table("profiles")
            .select("*")
            .eq("id", user_id)
            .single()
            .execute()
        )

        if not profile.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User profile not found",
            )

        return AuthResponse(
            user=UserResponse(
                id=profile.data["id"],
                email=request.email,
                full_name=profile.data["full_name"],
                role=profile.data["role"],
                department=profile.data.get("department"),
            ),
            access_token=access_token,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Login failed: {str(e)}",
        )


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """Register a new user via Supabase Auth and create a profile."""
    try:
        supabase = get_supabase_client()

        # Create auth user
        auth_response = supabase.auth.sign_up(
            {"email": request.email, "password": request.password}
        )

        if not auth_response.user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Registration failed",
            )

        user_id = str(auth_response.user.id)

        # Create profile using admin client (bypasses RLS)
        admin = get_supabase_admin()
        admin.table("profiles").insert(
            {
                "id": user_id,
                "full_name": request.full_name,
                "role": request.role,
                "department": request.department,
            }
        ).execute()

        access_token = (
            auth_response.session.access_token if auth_response.session else ""
        )

        return AuthResponse(
            user=UserResponse(
                id=user_id,
                email=request.email,
                full_name=request.full_name,
                role=request.role,
                department=request.department,
            ),
            access_token=access_token,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Registration failed: {str(e)}",
        )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get the currently authenticated user's profile."""
    return UserResponse(
        id=current_user["id"],
        email=current_user.get("email", ""),
        full_name=current_user["full_name"],
        role=current_user["role"],
        department=current_user.get("department"),
    )
