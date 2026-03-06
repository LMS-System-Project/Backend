from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime, timedelta

from database import get_supabase_admin
from auth import require_role

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# ── Response Models ───────────────────────────────────────────

class AdminDashboardResponse(BaseModel):
    total_students: int = 0
    total_instructors: int = 0
    active_courses: int = 0
    total_assignments: int = 0
    pending_submissions: int = 0


class AdminUserResponse(BaseModel):
    id: str
    full_name: str
    role: str
    department: Optional[str] = None
    created_at: Optional[str] = None


# ── Admin Endpoints ───────────────────────────────────────────

@router.get("/dashboard", response_model=AdminDashboardResponse)
def admin_dashboard(payload: dict = Depends(require_role("admin"))):
    """University-wide analytics for admin dashboard."""
    admin = get_supabase_admin()

    # Count students
    students = admin.table("profiles").select("id", count="exact").eq("role", "student").execute()
    total_students = students.count if students.count else 0

    # Count instructors
    instructors = admin.table("profiles").select("id", count="exact").eq("role", "instructor").execute()
    total_instructors = instructors.count if instructors.count else 0

    # Count active courses
    courses = admin.table("courses").select("id", count="exact").eq("status", "active").execute()
    active_courses = courses.count if courses.count else 0

    # Count assignments
    assignments = admin.table("assignments").select("id", count="exact").execute()
    total_assignments = assignments.count if assignments.count else 0

    # Count pending submissions
    pending = admin.table("submissions").select("id", count="exact").eq("status", "pending").execute()
    pending_submissions = pending.count if pending.count else 0

    return AdminDashboardResponse(
        total_students=total_students,
        total_instructors=total_instructors,
        active_courses=active_courses,
        total_assignments=total_assignments,
        pending_submissions=pending_submissions,
    )


@router.get("/users", response_model=List[AdminUserResponse])
def list_users(
    role: Optional[str] = None,
    department: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    payload: dict = Depends(require_role("admin")),
):
    """List all users with optional filters."""
    admin = get_supabase_admin()

    query = admin.table("profiles").select("*")

    if role:
        query = query.eq("role", role)
    if department:
        query = query.eq("department", department)

    result = query.range(skip, skip + limit - 1).execute()

    if not result.data:
        return []

    return [
        AdminUserResponse(
            id=u["id"],
            full_name=u["full_name"],
            role=u["role"],
            department=u.get("department"),
            created_at=u.get("created_at"),
        )
        for u in result.data
    ]


@router.get("/students", response_model=List[AdminUserResponse])
def list_students(
    department: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    payload: dict = Depends(require_role("admin")),
):
    """List all students."""
    return list_users(role="student", department=department, skip=skip, limit=limit, payload=payload)


@router.get("/instructors", response_model=List[AdminUserResponse])
def list_instructors(
    department: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    payload: dict = Depends(require_role("admin")),
):
    """List all instructors."""
    return list_users(role="instructor", department=department, skip=skip, limit=limit, payload=payload)


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    payload: dict = Depends(require_role("admin")),
):
    """Delete a user."""
    if user_id == payload.get("sub"):
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    admin = get_supabase_admin()
    admin.table("profiles").delete().eq("id", user_id).execute()

    return {"message": "User deleted successfully"}


@router.get("/courses")
def list_all_courses(
    status: Optional[str] = None,
    payload: dict = Depends(require_role("admin")),
):
    """List all courses (admin view)."""
    admin = get_supabase_admin()

    query = admin.table("courses").select("*")

    if status:
        query = query.eq("status", status)

    result = query.execute()
    return result.data or []


@router.get("/stats")
def get_system_stats(payload: dict = Depends(require_role("admin"))):
    """Get system-wide statistics."""
    admin = get_supabase_admin()

    students = admin.table("profiles").select("id", count="exact").eq("role", "student").execute()
    instructors = admin.table("profiles").select("id", count="exact").eq("role", "instructor").execute()
    admins = admin.table("profiles").select("id", count="exact").eq("role", "admin").execute()

    active_courses = admin.table("courses").select("id", count="exact").eq("status", "active").execute()
    draft_courses = admin.table("courses").select("id", count="exact").eq("status", "draft").execute()

    total_submissions = admin.table("submissions").select("id", count="exact").execute()
    graded_submissions = admin.table("submissions").select("id", count="exact").eq("status", "graded").execute()

    return {
        "users": {
            "students": students.count or 0,
            "instructors": instructors.count or 0,
            "admins": admins.count or 0,
        },
        "courses": {
            "active": active_courses.count or 0,
            "draft": draft_courses.count or 0,
        },
        "submissions": {
            "total": total_submissions.count or 0,
            "graded": graded_submissions.count or 0,
        },
    }


# ── Seed Data Endpoint (Development Only) ────────────────────

@router.post("/seed-data")
def seed_sample_data():
    """
    Seed the database with sample courses, assignments, and enrollments.
    WARNING: This is for development/demo purposes only!
    """
    admin = get_supabase_admin()

    try:
        # Get the first user to act as instructor
        profiles = admin.table("profiles").select("id, full_name, role").execute()

        if not profiles.data:
            raise HTTPException(status_code=400, detail="No users found. Please register at least one user first.")

        # Find an instructor or use first user
        instructor = next((p for p in profiles.data if p["role"] == "instructor"), profiles.data[0])
        instructor_id = instructor["id"]

        # Find students
        students = [p for p in profiles.data if p["role"] == "student"]

        # Check if courses already exist
        existing = admin.table("courses").select("id").limit(1).execute()
        if existing.data:
            return {"message": "Sample data already exists!", "courses": len(existing.data)}

        # Create sample courses
        courses_data = [
            {
                "instructor_id": instructor_id,
                "code": "CS101",
                "title": "Introduction to Programming",
                "description": "Learn the fundamentals of programming using Python.",
                "status": "active",
            },
            {
                "instructor_id": instructor_id,
                "code": "CS201",
                "title": "Data Structures & Algorithms",
                "description": "Master essential data structures and learn algorithm analysis.",
                "status": "active",
            },
            {
                "instructor_id": instructor_id,
                "code": "WEB301",
                "title": "Full Stack Web Development",
                "description": "Build modern web applications using React, Node.js, and PostgreSQL.",
                "status": "active",
            },
            {
                "instructor_id": instructor_id,
                "code": "AI401",
                "title": "Machine Learning Fundamentals",
                "description": "Introduction to machine learning concepts and hands-on projects.",
                "status": "active",
            },
        ]

        courses_result = admin.table("courses").insert(courses_data).execute()
        created_courses = courses_result.data

        # Create enrollments for students
        enrollments_created = 0
        for student in students[:5]:
            for course in created_courses[:3]:
                try:
                    admin.table("enrollments").insert({
                        "course_id": course["id"],
                        "student_id": student["id"],
                    }).execute()
                    enrollments_created += 1
                except Exception:
                    pass

        # Create assignments
        now = datetime.utcnow()
        assignments_data = []

        for i, course in enumerate(created_courses):
            assignments_data.extend([
                {
                    "course_id": course["id"],
                    "title": f"Quiz {i + 1}: Chapter 1 Review",
                    "due_date": (now + timedelta(days=3 + i)).isoformat(),
                },
                {
                    "course_id": course["id"],
                    "title": f"Lab Assignment {i + 1}",
                    "due_date": (now + timedelta(days=7 + i * 2)).isoformat(),
                },
            ])

        assignments_result = admin.table("assignments").insert(assignments_data).execute()

        return {
            "message": "Sample data created successfully!",
            "courses_created": len(created_courses),
            "enrollments_created": enrollments_created,
            "assignments_created": len(assignments_result.data),
            "instructor": instructor["full_name"],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error seeding data: {str(e)}")
