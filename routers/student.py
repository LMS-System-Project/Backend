from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from database import get_supabase_admin
from schemas import (
    StudentDashboardStats,
    StudentCourseResponse,
    StudentAssignmentResponse,
    StudentSubmissionResponse,
    StudentSubmitRequest,
    ProfileUpdate,
    ProfileResponse,
)
from auth import get_current_user

router = APIRouter(prefix="/api/student", tags=["Student"])


def _require_student(current_user: dict):
    if current_user["role"] != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can access this endpoint",
        )


# ── Dashboard ────────────────────────────────────────────────────────────────

@router.get("/dashboard", response_model=StudentDashboardStats)
async def get_student_dashboard(current_user: dict = Depends(get_current_user)):
    """Aggregated stats for the student's dashboard."""
    _require_student(current_user)

    try:
        admin = get_supabase_admin()
        student_id = current_user["id"]

        # Enrolled courses count
        enrollments_resp = (
            admin.table("enrollments")
            .select("course_id", count="exact")
            .eq("student_id", student_id)
            .execute()
        )
        enrolled_courses = enrollments_resp.count or 0
        course_ids = [e["course_id"] for e in (enrollments_resp.data or [])]

        # Pending assignments (due, not yet submitted by this student)
        pending_assignments = 0
        submitted_count = 0
        graded_count = 0
        if course_ids:
            assignments_resp = (
                admin.table("assignments")
                .select("id")
                .in_("course_id", course_ids)
                .execute()
            )
            assignment_ids = [a["id"] for a in (assignments_resp.data or [])]

            if assignment_ids:
                # All submissions by this student
                subs_resp = (
                    admin.table("submissions")
                    .select("assignment_id, status, grade")
                    .eq("student_id", student_id)
                    .in_("assignment_id", assignment_ids)
                    .execute()
                )
                subs = subs_resp.data or []
                submitted_ids = {s["assignment_id"] for s in subs}
                submitted_count = len(subs)
                graded_count = sum(1 for s in subs if s["status"] == "graded")
                pending_assignments = len(assignment_ids) - len(submitted_ids)

        # Class average from graded submissions
        class_average = "N/A"
        if graded_count > 0:
            graded_resp = (
                admin.table("submissions")
                .select("grade")
                .eq("student_id", student_id)
                .eq("status", "graded")
                .execute()
            )
            grades = [s["grade"] for s in (graded_resp.data or []) if s.get("grade")]
            if grades:
                grade_map = {
                    "A+": 4.3, "A": 4.0, "A-": 3.7,
                    "B+": 3.3, "B": 3.0, "B-": 2.7,
                    "C+": 2.3, "C": 2.0, "C-": 1.7,
                    "D+": 1.3, "D": 1.0, "F": 0.0,
                }
                numeric = [grade_map.get(g, 0) for g in grades]
                avg = sum(numeric) / len(numeric)
                reverse_map = sorted(grade_map.items(), key=lambda x: x[1], reverse=True)
                class_average = "F"
                for letter, val in reverse_map:
                    if avg >= val:
                        class_average = letter
                        break

        return StudentDashboardStats(
            enrolled_courses=enrolled_courses,
            pending_assignments=max(0, pending_assignments),
            submitted_assignments=submitted_count,
            graded_assignments=graded_count,
            average_grade=class_average,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch student dashboard: {str(e)}",
        )


# ── Courses ──────────────────────────────────────────────────────────────────

@router.get("/courses", response_model=List[StudentCourseResponse])
async def list_student_courses(current_user: dict = Depends(get_current_user)):
    """List all courses the student is enrolled in."""
    _require_student(current_user)

    try:
        admin = get_supabase_admin()
        student_id = current_user["id"]

        enrollments_resp = (
            admin.table("enrollments")
            .select("course_id, enrolled_at")
            .eq("student_id", student_id)
            .execute()
        )
        enrollments = enrollments_resp.data or []
        if not enrollments:
            return []

        course_ids = [e["course_id"] for e in enrollments]
        enrolled_at_map = {e["course_id"]: e["enrolled_at"] for e in enrollments}

        courses_resp = (
            admin.table("courses")
            .select("*, profiles(full_name)")
            .in_("id", course_ids)
            .execute()
        )
        courses = courses_resp.data or []

        # Batch: assignment counts per course
        assignments_resp = (
            admin.table("assignments")
            .select("id, course_id")
            .in_("course_id", course_ids)
            .execute()
        )
        assignments = assignments_resp.data or []
        assignment_ids = [a["id"] for a in assignments]
        from collections import Counter
        assignment_count_by_course = Counter(a["course_id"] for a in assignments)

        # Batch: submissions by this student for these assignments
        submitted_ids: set = set()
        graded_by_course: dict = {}
        if assignment_ids:
            subs_resp = (
                admin.table("submissions")
                .select("assignment_id, status")
                .eq("student_id", student_id)
                .in_("assignment_id", assignment_ids)
                .execute()
            )
            assignment_course_map = {a["id"]: a["course_id"] for a in assignments}
            for sub in (subs_resp.data or []):
                submitted_ids.add(sub["assignment_id"])
                course_id = assignment_course_map.get(sub["assignment_id"])
                if course_id and sub["status"] == "graded":
                    graded_by_course[course_id] = graded_by_course.get(course_id, 0) + 1

        result = []
        for course in courses:
            total_assignments = assignment_count_by_course.get(course["id"], 0)
            # Count submitted assignments for this course
            course_assignment_ids = {a["id"] for a in assignments if a["course_id"] == course["id"]}
            submitted_for_course = len(submitted_ids & course_assignment_ids)
            progress = (
                round((submitted_for_course / total_assignments) * 100)
                if total_assignments > 0
                else 0
            )
            instructor_name = None
            if course.get("profiles") and isinstance(course["profiles"], dict):
                instructor_name = course["profiles"].get("full_name")

            result.append(StudentCourseResponse(
                id=course["id"],
                code=course["code"],
                title=course["title"],
                description=course.get("description"),
                status=course["status"],
                instructor_name=instructor_name,
                total_assignments=total_assignments,
                submitted_assignments=submitted_for_course,
                progress=progress,
                enrolled_at=enrolled_at_map.get(course["id"]),
            ))

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch student courses: {str(e)}",
        )


# ── Assignments ───────────────────────────────────────────────────────────────

@router.get("/assignments", response_model=List[StudentAssignmentResponse])
async def list_student_assignments(current_user: dict = Depends(get_current_user)):
    """List all assignments across the student's enrolled courses, with submission status."""
    _require_student(current_user)

    try:
        admin = get_supabase_admin()
        student_id = current_user["id"]

        # Get enrolled course IDs
        enrollments_resp = (
            admin.table("enrollments")
            .select("course_id")
            .eq("student_id", student_id)
            .execute()
        )
        course_ids = [e["course_id"] for e in (enrollments_resp.data or [])]
        if not course_ids:
            return []

        # Get course info
        courses_resp = (
            admin.table("courses")
            .select("id, code, title")
            .in_("id", course_ids)
            .execute()
        )
        course_map = {c["id"]: c for c in (courses_resp.data or [])}

        # Get assignments for enrolled courses
        assignments_resp = (
            admin.table("assignments")
            .select("*")
            .in_("course_id", course_ids)
            .order("due_date", desc=False)
            .execute()
        )
        assignments = assignments_resp.data or []
        if not assignments:
            return []

        assignment_ids = [a["id"] for a in assignments]

        # Get this student's submissions for these assignments
        subs_resp = (
            admin.table("submissions")
            .select("assignment_id, status, grade, submitted_at")
            .eq("student_id", student_id)
            .in_("assignment_id", assignment_ids)
            .execute()
        )
        sub_map = {s["assignment_id"]: s for s in (subs_resp.data or [])}

        result = []
        for a in assignments:
            sub = sub_map.get(a["id"])
            course = course_map.get(a["course_id"], {})
            result.append(StudentAssignmentResponse(
                id=a["id"],
                course_id=a["course_id"],
                course_code=course.get("code"),
                course_title=course.get("title"),
                title=a["title"],
                due_date=a.get("due_date"),
                created_at=a.get("created_at"),
                submission_status=sub["status"] if sub else "not_submitted",
                grade=sub["grade"] if sub else None,
                submitted_at=sub["submitted_at"] if sub else None,
                submission_id=sub["assignment_id"] if sub else None,
            ))

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch student assignments: {str(e)}",
        )


# ── Submissions ───────────────────────────────────────────────────────────────

@router.post("/assignments/{assignment_id}/submit", response_model=StudentSubmissionResponse, status_code=status.HTTP_201_CREATED)
async def submit_assignment(
    assignment_id: str,
    body: StudentSubmitRequest,
    current_user: dict = Depends(get_current_user),
):
    """Submit (or re-submit) an assignment."""
    _require_student(current_user)

    try:
        admin = get_supabase_admin()
        student_id = current_user["id"]

        # Verify the assignment exists and the student is enrolled in its course
        assignment_resp = (
            admin.table("assignments")
            .select("id, title, course_id")
            .eq("id", assignment_id)
            .single()
            .execute()
        )
        if not assignment_resp.data:
            raise HTTPException(status_code=404, detail="Assignment not found")

        assignment = assignment_resp.data
        enrollment_resp = (
            admin.table("enrollments")
            .select("id")
            .eq("course_id", assignment["course_id"])
            .eq("student_id", student_id)
            .execute()
        )
        if not enrollment_resp.data:
            raise HTTPException(status_code=403, detail="You are not enrolled in this course")

        # Check if already submitted — update instead of insert
        existing_resp = (
            admin.table("submissions")
            .select("id")
            .eq("assignment_id", assignment_id)
            .eq("student_id", student_id)
            .execute()
        )

        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()

        if existing_resp.data:
            # Re-submission: reset status to pending
            result = (
                admin.table("submissions")
                .update({"status": "pending", "submitted_at": now})
                .eq("assignment_id", assignment_id)
                .eq("student_id", student_id)
                .execute()
            )
            sub = result.data[0]
        else:
            result = (
                admin.table("submissions")
                .insert({
                    "assignment_id": assignment_id,
                    "student_id": student_id,
                    "status": "pending",
                })
                .execute()
            )
            sub = result.data[0]

        return StudentSubmissionResponse(
            id=sub["id"],
            assignment_id=sub["assignment_id"],
            assignment_title=assignment["title"],
            student_id=student_id,
            status=sub["status"],
            grade=sub.get("grade"),
            submitted_at=sub.get("submitted_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit assignment: {str(e)}",
        )


# ── Profile / Settings ────────────────────────────────────────────────────────

@router.get("/profile", response_model=ProfileResponse)
async def get_student_profile(current_user: dict = Depends(get_current_user)):
    """Get the student's profile."""
    _require_student(current_user)
    return ProfileResponse(
        id=current_user["id"],
        email=current_user.get("email"),
        full_name=current_user["full_name"],
        role=current_user["role"],
        department=current_user.get("department"),
        created_at=current_user.get("created_at"),
    )


@router.put("/profile", response_model=ProfileResponse)
async def update_student_profile(
    body: ProfileUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update the student's profile."""
    _require_student(current_user)

    try:
        admin = get_supabase_admin()
        update_data = {k: v for k, v in body.model_dump().items() if v is not None}
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")

        updated = (
            admin.table("profiles")
            .update(update_data)
            .eq("id", current_user["id"])
            .execute()
        )
        if not updated.data:
            raise HTTPException(status_code=500, detail="Failed to update profile")

        p = updated.data[0]
        return ProfileResponse(
            id=p["id"],
            email=current_user.get("email"),
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
