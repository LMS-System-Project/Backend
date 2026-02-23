from fastapi import APIRouter, HTTPException, status, Depends
from database import get_supabase_admin
from schemas import ProfileUpdate, ProfileResponse
from auth import get_current_user

router = APIRouter(prefix="/api/instructor", tags=["Instructor Settings"])


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(current_user: dict = Depends(get_current_user)):
    """Get the instructor's profile."""
    return ProfileResponse(
        id=current_user["id"],
        full_name=current_user["full_name"],
        role=current_user["role"],
        department=current_user.get("department"),
        created_at=current_user.get("created_at"),
    )


@router.put("/profile", response_model=ProfileResponse)
async def update_profile(
    body: ProfileUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update the instructor's profile (full_name, department)."""
    try:
        admin = get_supabase_admin()

        update_data = {k: v for k, v in body.model_dump().items() if v is not None}
        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update",
            )

        updated = (
            admin.table("profiles")
            .update(update_data)
            .eq("id", current_user["id"])
            .execute()
        )

        if not updated.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update profile",
            )

        p = updated.data[0]
        return ProfileResponse(
            id=p["id"],
            full_name=p["full_name"],
            role=p["role"],
            department=p.get("department"),
            created_at=p.get("created_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update profile: {str(e)}",
        )
