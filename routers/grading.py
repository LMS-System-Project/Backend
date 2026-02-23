from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from database import get_supabase_admin
from schemas import (
    AssignmentCreate,
    AssignmentResponse,
    SubmissionResponse,
    GradeSubmission,
)
from auth import get_current_user

router = APIRouter(prefix="/api/instructor", tags=["Instructor Grading"])


@router.get("/assignments", response_model=List[AssignmentResponse])
async def list_assignments(current_user: dict = Depends(get_current_user)):
    """List all assignments across the instructor's courses."""
    if current_user["role"] != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can access this endpoint",
        )

    try:
        admin = get_supabase_admin()
        user_id = current_user["id"]

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

        assignments_resp = (
            admin.table("assignments")
            .select("*")
            .in_("course_id", course_ids)
            .order("created_at", desc=True)
            .execute()
        )

        result = []
        for a in assignments_resp.data or []:
            course = course_map.get(a["course_id"], {})
            result.append(
                AssignmentResponse(
                    id=a["id"],
                    course_id=a["course_id"],
                    course_code=course.get("code"),
                    course_title=course.get("title"),
                    title=a["title"],
                    due_date=a.get("due_date"),
                    created_at=a.get("created_at"),
                )
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch assignments: {str(e)}",
        )


@router.post(
    "/assignments",
    response_model=AssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_assignment(
    assignment: AssignmentCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a new assignment for one of the instructor's courses."""
    if current_user["role"] != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can create assignments",
        )

    try:
        admin = get_supabase_admin()

        # Verify the course belongs to this instructor
        course_resp = (
            admin.table("courses")
            .select("id, code, title")
            .eq("id", assignment.course_id)
            .eq("instructor_id", current_user["id"])
            .single()
            .execute()
        )

        if not course_resp.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found or not owned by you",
            )

        insert_data = {
            "course_id": assignment.course_id,
            "title": assignment.title,
        }
        if assignment.due_date:
            insert_data["due_date"] = assignment.due_date

        new_assignment = (
            admin.table("assignments").insert(insert_data).execute()
        )

        if not new_assignment.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create assignment",
            )

        a = new_assignment.data[0]
        course = course_resp.data
        return AssignmentResponse(
            id=a["id"],
            course_id=a["course_id"],
            course_code=course.get("code"),
            course_title=course.get("title"),
            title=a["title"],
            due_date=a.get("due_date"),
            created_at=a.get("created_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create assignment: {str(e)}",
        )


@router.get("/submissions", response_model=List[SubmissionResponse])
async def list_submissions(current_user: dict = Depends(get_current_user)):
    """List all submissions across the instructor's courses."""
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
            .select("id, code")
            .eq("instructor_id", user_id)
            .execute()
        )
        courses = courses_resp.data or []
        if not courses:
            return []

        course_map = {c["id"]: c for c in courses}
        course_ids = list(course_map.keys())

        # Get assignments for those courses
        assignments_resp = (
            admin.table("assignments")
            .select("id, title, course_id")
            .in_("course_id", course_ids)
            .execute()
        )
        assignments = assignments_resp.data or []
        if not assignments:
            return []

        assignment_map = {a["id"]: a for a in assignments}
        assignment_ids = list(assignment_map.keys())

        # Get submissions
        submissions_resp = (
            admin.table("submissions")
            .select("*")
            .in_("assignment_id", assignment_ids)
            .order("submitted_at", desc=True)
            .execute()
        )

        result = []
        for s in submissions_resp.data or []:
            assignment = assignment_map.get(s["assignment_id"], {})
            course = course_map.get(assignment.get("course_id", ""), {})

            # Get student name
            student_name = "Unknown"
            try:
                student_resp = (
                    admin.table("profiles")
                    .select("full_name")
                    .eq("id", s["student_id"])
                    .single()
                    .execute()
                )
                if student_resp.data:
                    student_name = student_resp.data["full_name"]
            except Exception:
                pass

            result.append(
                SubmissionResponse(
                    id=s["id"],
                    assignment_id=s["assignment_id"],
                    assignment_title=assignment.get("title"),
                    course_code=course.get("code"),
                    student_id=s["student_id"],
                    student_name=student_name,
                    status=s["status"],
                    grade=s.get("grade"),
                    submitted_at=s.get("submitted_at"),
                )
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch submissions: {str(e)}",
        )


@router.put("/submissions/{submission_id}/grade", response_model=SubmissionResponse)
async def grade_submission(
    submission_id: str,
    body: GradeSubmission,
    current_user: dict = Depends(get_current_user),
):
    """Grade a submission (set grade and status)."""
    if current_user["role"] != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can grade submissions",
        )

    try:
        admin = get_supabase_admin()

        # Get the submission and verify ownership chain
        sub_resp = (
            admin.table("submissions")
            .select("*, assignment_id")
            .eq("id", submission_id)
            .single()
            .execute()
        )
        if not sub_resp.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Submission not found",
            )

        submission = sub_resp.data
        assignment_resp = (
            admin.table("assignments")
            .select("id, title, course_id")
            .eq("id", submission["assignment_id"])
            .single()
            .execute()
        )
        if not assignment_resp.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Assignment not found",
            )

        assignment = assignment_resp.data
        course_resp = (
            admin.table("courses")
            .select("id, code")
            .eq("id", assignment["course_id"])
            .eq("instructor_id", current_user["id"])
            .single()
            .execute()
        )

        if not course_resp.data:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not own this course",
            )

        # Update the submission
        updated = (
            admin.table("submissions")
            .update({"grade": body.grade, "status": body.status})
            .eq("id", submission_id)
            .execute()
        )

        if not updated.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to update submission",
            )

        s = updated.data[0]

        # Get student name
        student_name = "Unknown"
        try:
            student_resp = (
                admin.table("profiles")
                .select("full_name")
                .eq("id", s["student_id"])
                .single()
                .execute()
            )
            if student_resp.data:
                student_name = student_resp.data["full_name"]
        except Exception:
            pass

        return SubmissionResponse(
            id=s["id"],
            assignment_id=s["assignment_id"],
            assignment_title=assignment.get("title"),
            course_code=course_resp.data.get("code"),
            student_id=s["student_id"],
            student_name=student_name,
            status=s["status"],
            grade=s.get("grade"),
            submitted_at=s.get("submitted_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to grade submission: {str(e)}",
        )
