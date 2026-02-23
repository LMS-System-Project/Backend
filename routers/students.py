from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from database import get_supabase_admin
from schemas import StudentResponse
from auth import get_current_user

router = APIRouter(prefix="/api/instructor", tags=["Instructor Students"])


@router.get("/students", response_model=List[StudentResponse])
async def list_students(current_user: dict = Depends(get_current_user)):
    """List all students enrolled across the instructor's courses."""
    if current_user["role"] != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can access this endpoint",
        )

    try:
        admin = get_supabase_admin()
        user_id = current_user["id"]

        # Get instructor's courses
        courses_resp = (
            admin.table("courses")
            .select("id, code, title")
            .eq("instructor_id", user_id)
            .execute()
        )
        courses = courses_resp.data or []

        if not courses:
            return []

        course_map = {c["id"]: c for c in courses}
        course_ids = list(course_map.keys())

        # Batch: get ALL enrollments across all courses in one query
        enrollments_resp = (
            admin.table("enrollments")
            .select("student_id, course_id, enrolled_at")
            .in_("course_id", course_ids)
            .execute()
        )
        enrollments = enrollments_resp.data or []

        if not enrollments:
            return []

        # Batch: get ALL student profiles in one query
        student_ids = list({e["student_id"] for e in enrollments})
        profiles_resp = (
            admin.table("profiles")
            .select("id, full_name, department")
            .in_("id", student_ids)
            .execute()
        )
        profile_map = {p["id"]: p for p in (profiles_resp.data or [])}

        # Assemble results in Python
        result = []
        for enrollment in enrollments:
            student = profile_map.get(enrollment["student_id"])
            if student:
                course = course_map[enrollment["course_id"]]
                result.append(
                    StudentResponse(
                        id=student["id"],
                        full_name=student["full_name"],
                        department=student.get("department"),
                        course_id=enrollment["course_id"],
                        course_code=course["code"],
                        course_title=course["title"],
                        enrolled_at=enrollment.get("enrolled_at"),
                    )
                )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch students: {str(e)}",
        )
