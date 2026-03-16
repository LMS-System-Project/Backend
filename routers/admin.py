from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta

from database import get_supabase_client, get_supabase_admin
from auth import require_role

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ── Request / Response Models ─────────────────────────────────

class AdminDashboardResponse(BaseModel):
    total_students: int = 0
    total_instructors: int = 0
    total_admins: int = 0
    active_courses: int = 0
    draft_courses: int = 0
    total_assignments: int = 0
    total_submissions: int = 0
    graded_submissions: int = 0
    pending_submissions: int = 0


class AdminUserResponse(BaseModel):
    id: str
    email: str = ""
    full_name: str
    role: str
    department: Optional[str] = None
    created_at: Optional[str] = None


class AdminCourseResponse(BaseModel):
    id: str
    code: str
    title: str
    description: Optional[str] = None
    status: str
    instructor_id: str
    instructor_name: str = ""
    student_count: int = 0
    created_at: Optional[str] = None


class CreateUserRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "student"
    department: Optional[str] = None


class UpdateUserRequest(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    department: Optional[str] = None


# ── Dashboard ─────────────────────────────────────────────────

@router.get("/dashboard", response_model=AdminDashboardResponse)
def admin_dashboard(payload: dict = Depends(require_role("admin"))):
    """University-wide stats for admin dashboard."""
    admin = get_supabase_admin()

    students = admin.table("profiles").select("id", count="exact").eq("role", "student").execute()
    instructors = admin.table("profiles").select("id", count="exact").eq("role", "instructor").execute()
    admins_q = admin.table("profiles").select("id", count="exact").eq("role", "admin").execute()

    active_courses = admin.table("courses").select("id", count="exact").eq("status", "active").execute()
    draft_courses = admin.table("courses").select("id", count="exact").eq("status", "draft").execute()

    assignments = admin.table("assignments").select("id", count="exact").execute()
    total_subs = admin.table("submissions").select("id", count="exact").execute()
    graded = admin.table("submissions").select("id", count="exact").eq("status", "graded").execute()
    pending = admin.table("submissions").select("id", count="exact").eq("status", "pending").execute()

    return AdminDashboardResponse(
        total_students=students.count or 0,
        total_instructors=instructors.count or 0,
        total_admins=admins_q.count or 0,
        active_courses=active_courses.count or 0,
        draft_courses=draft_courses.count or 0,
        total_assignments=assignments.count or 0,
        total_submissions=total_subs.count or 0,
        graded_submissions=graded.count or 0,
        pending_submissions=pending.count or 0,
    )


# ── Users CRUD ────────────────────────────────────────────────

@router.get("/users", response_model=List[AdminUserResponse])
def list_users(
    role: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    payload: dict = Depends(require_role("admin")),
):
    """List all users with optional role filter and search."""
    admin = get_supabase_admin()

    query = admin.table("profiles").select("*").order("created_at", desc=True)

    if role:
        query = query.eq("role", role)

    result = query.range(skip, skip + limit - 1).execute()

    if not result.data:
        return []

    # Get emails from auth.users via admin API
    email_map: dict = {}
    try:
        auth_users = admin.auth.admin.list_users()
        for u in auth_users:
            email_map[str(u.id)] = u.email or ""
    except Exception:
        pass

    users = []
    for u in result.data:
        full_name = u.get("full_name", "")
        email = email_map.get(u["id"], "")

        if search:
            q = search.lower()
            if q not in full_name.lower() and q not in email.lower() and q not in (u.get("department") or "").lower():
                continue

        users.append(AdminUserResponse(
            id=u["id"],
            email=email,
            full_name=full_name,
            role=u["role"],
            department=u.get("department"),
            created_at=u.get("created_at"),
        ))

    return users


@router.post("/users", response_model=AdminUserResponse, status_code=201)
def create_user(req: CreateUserRequest, payload: dict = Depends(require_role("admin"))):
    """Admin creates a new user (Supabase Auth + profile)."""
    admin = get_supabase_admin()

    if req.role not in ("student", "instructor", "admin"):
        raise HTTPException(status_code=400, detail="Role must be student, instructor, or admin")

    try:
        auth_resp = admin.auth.admin.create_user({
            "email": req.email,
            "password": req.password,
            "email_confirm": True,
            "user_metadata": {"role": req.role},
        })

        if not auth_resp or not auth_resp.user:
            raise HTTPException(status_code=400, detail="Failed to create auth user")

        user_id = str(auth_resp.user.id)

        admin.table("profiles").insert({
            "id": user_id,
            "full_name": req.full_name,
            "role": req.role,
            "department": req.department,
        }).execute()

        return AdminUserResponse(
            id=user_id,
            email=req.email,
            full_name=req.full_name,
            role=req.role,
            department=req.department,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to create user: {str(e)}")


@router.put("/users/{user_id}", response_model=AdminUserResponse)
def update_user(
    user_id: str,
    req: UpdateUserRequest,
    payload: dict = Depends(require_role("admin")),
):
    """Update a user's profile (name, role, department)."""
    admin = get_supabase_admin()

    update_data: dict = {}
    if req.full_name is not None:
        update_data["full_name"] = req.full_name
    if req.role is not None:
        if req.role not in ("student", "instructor", "admin"):
            raise HTTPException(status_code=400, detail="Invalid role")
        update_data["role"] = req.role
    if req.department is not None:
        update_data["department"] = req.department

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = admin.table("profiles").update(update_data).eq("id", user_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="User not found")

    if req.role:
        try:
            admin.auth.admin.update_user_by_id(user_id, {"user_metadata": {"role": req.role}})
        except Exception:
            pass

    u = result.data[0]

    email = ""
    try:
        auth_user = admin.auth.admin.get_user_by_id(user_id)
        email = auth_user.user.email or ""
    except Exception:
        pass

    return AdminUserResponse(
        id=u["id"],
        email=email,
        full_name=u["full_name"],
        role=u["role"],
        department=u.get("department"),
        created_at=u.get("created_at"),
    )


@router.delete("/users/{user_id}")
def delete_user(user_id: str, payload: dict = Depends(require_role("admin"))):
    """Delete a user (profile + auth account)."""
    if user_id == payload.get("sub"):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    admin = get_supabase_admin()
    admin.table("profiles").delete().eq("id", user_id).execute()

    try:
        admin.auth.admin.delete_user(user_id)
    except Exception:
        pass

    return {"message": "User deleted successfully"}


# ── Courses (admin view) ──────────────────────────────────────

@router.get("/courses", response_model=List[AdminCourseResponse])
def list_all_courses(
    status: Optional[str] = None,
    payload: dict = Depends(require_role("admin")),
):
    """List all courses with instructor names and student counts."""
    admin = get_supabase_admin()

    query = admin.table("courses").select("*").order("created_at", desc=True)
    if status:
        query = query.eq("status", status)

    result = query.execute()
    courses = result.data or []

    if not courses:
        return []

    instructor_ids = list({c["instructor_id"] for c in courses})
    profiles = admin.table("profiles").select("id, full_name").in_("id", instructor_ids).execute()
    name_map = {p["id"]: p["full_name"] for p in (profiles.data or [])}

    enrollment_counts: dict = {}
    for c in courses:
        count_q = admin.table("enrollments").select("id", count="exact").eq("course_id", c["id"]).execute()
        enrollment_counts[c["id"]] = count_q.count or 0

    return [
        AdminCourseResponse(
            id=c["id"],
            code=c["code"],
            title=c["title"],
            description=c.get("description"),
            status=c["status"],
            instructor_id=c["instructor_id"],
            instructor_name=name_map.get(c["instructor_id"], "Unknown"),
            student_count=enrollment_counts.get(c["id"], 0),
            created_at=c.get("created_at"),
        )
        for c in courses
    ]


@router.delete("/courses/{course_id}")
def delete_course(course_id: str, payload: dict = Depends(require_role("admin"))):
    """Admin can delete any course."""
    admin = get_supabase_admin()
    admin.table("courses").delete().eq("id", course_id).execute()
    return {"message": "Course deleted successfully"}
