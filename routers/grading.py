from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Form
from typing import List, Optional
from database import get_supabase_admin
from schemas import (
    AssignmentCreate,
    AssignmentResponse,
    SubmissionResponse,
    GradeSubmission,
    CourseMaterialResponse,
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
                    description=a.get("description"),
                    instructions=a.get("instructions"),
                    max_marks=a.get("max_marks", 100),
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
        if assignment.description:
            insert_data["description"] = assignment.description
        if assignment.instructions:
            insert_data["instructions"] = assignment.instructions
        if assignment.max_marks is not None:
            insert_data["max_marks"] = assignment.max_marks

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
            description=a.get("description"),
            instructions=a.get("instructions"),
            max_marks=a.get("max_marks", 100),
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

        submissions = submissions_resp.data or []

        # Batch: fetch all student profiles referenced in submissions
        student_ids = list({s["student_id"] for s in submissions})
        student_map = {}
        if student_ids:
            profiles_resp = (
                admin.table("profiles")
                .select("id, full_name")
                .in_("id", student_ids)
                .execute()
            )
            student_map = {p["id"]: p["full_name"] for p in (profiles_resp.data or [])}

        result = []
        for s in submissions:
            assignment = assignment_map.get(s["assignment_id"], {})
            course = course_map.get(assignment.get("course_id", ""), {})

            result.append(
                SubmissionResponse(
                    id=s["id"],
                    assignment_id=s["assignment_id"],
                    assignment_title=assignment.get("title"),
                    course_code=course.get("code"),
                    student_id=s["student_id"],
                    student_name=student_map.get(s["student_id"], "Unknown"),
                    status=s["status"],
                    grade=s.get("grade"),
                    file_url=s.get("file_url"),
                    file_name=s.get("file_name"),
                    notes=s.get("notes"),
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
            file_url=s.get("file_url"),
            file_name=s.get("file_name"),
            notes=s.get("notes"),
            submitted_at=s.get("submitted_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to grade submission: {str(e)}",
        )


# ── Course Materials ──────────────────────────────────────────────────────────

def _require_instructor(current_user: dict):
    if current_user["role"] != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can access this endpoint",
        )


@router.post(
    "/courses/{course_id}/materials",
    response_model=CourseMaterialResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_material(
    course_id: str,
    title: str = Form(...),
    description: Optional[str] = Form(None),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload a study material for a course."""
    _require_instructor(current_user)

    try:
        admin = get_supabase_admin()

        # Verify course ownership
        course_resp = (
            admin.table("courses")
            .select("id")
            .eq("id", course_id)
            .eq("instructor_id", current_user["id"])
            .single()
            .execute()
        )
        if not course_resp.data:
            raise HTTPException(status_code=404, detail="Course not found or not owned by you")

        # Upload file
        from storage import upload_file as store_file, get_file_size
        file_size = get_file_size(file)
        file_name, file_url = await store_file(file, folder="materials")

        # Save to database
        result = (
            admin.table("course_materials")
            .insert({
                "course_id": course_id,
                "title": title,
                "description": description,
                "file_name": file_name,
                "file_url": file_url,
                "file_size": file_size,
                "uploaded_by": current_user["id"],
            })
            .execute()
        )

        m = result.data[0]
        return CourseMaterialResponse(
            id=m["id"],
            course_id=m["course_id"],
            title=m["title"],
            description=m.get("description"),
            file_name=m["file_name"],
            file_url=m["file_url"],
            file_size=m.get("file_size", 0),
            uploaded_by=m.get("uploaded_by"),
            created_at=m.get("created_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload material: {str(e)}",
        )


@router.get("/courses/{course_id}/materials", response_model=List[CourseMaterialResponse])
async def list_materials(
    course_id: str,
    current_user: dict = Depends(get_current_user),
):
    """List all materials for a course."""
    _require_instructor(current_user)

    try:
        admin = get_supabase_admin()

        # Verify course ownership
        course_resp = (
            admin.table("courses")
            .select("id")
            .eq("id", course_id)
            .eq("instructor_id", current_user["id"])
            .single()
            .execute()
        )
        if not course_resp.data:
            raise HTTPException(status_code=404, detail="Course not found or not owned by you")

        materials_resp = (
            admin.table("course_materials")
            .select("*")
            .eq("course_id", course_id)
            .order("created_at", desc=True)
            .execute()
        )

        return [
            CourseMaterialResponse(
                id=m["id"],
                course_id=m["course_id"],
                title=m["title"],
                description=m.get("description"),
                file_name=m["file_name"],
                file_url=m["file_url"],
                file_size=m.get("file_size", 0),
                uploaded_by=m.get("uploaded_by"),
                created_at=m.get("created_at"),
            )
            for m in (materials_resp.data or [])
        ]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch materials: {str(e)}",
        )


@router.delete("/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_material(
    material_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a study material."""
    _require_instructor(current_user)

    try:
        admin = get_supabase_admin()

        # Fetch material and verify ownership
        mat_resp = (
            admin.table("course_materials")
            .select("*, courses(instructor_id)")
            .eq("id", material_id)
            .single()
            .execute()
        )

        if not mat_resp.data:
            raise HTTPException(status_code=404, detail="Material not found")

        course_data = mat_resp.data.get("courses", {})
        if course_data.get("instructor_id") != current_user["id"]:
            raise HTTPException(status_code=403, detail="Not your course material")

        # Delete file from storage
        from storage import delete_file as remove_file
        await remove_file(mat_resp.data["file_url"])

        # Delete from database
        admin.table("course_materials").delete().eq("id", material_id).execute()

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete material: {str(e)}",
        )
