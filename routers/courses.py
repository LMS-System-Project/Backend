from fastapi import APIRouter, HTTPException, status, Depends
from typing import List
from database import get_supabase_admin
from schemas import CourseCreate, CourseUpdate, CourseResponse
from auth import get_current_user

router = APIRouter(prefix="/api/instructor/courses", tags=["Instructor Courses"])


@router.get("", response_model=List[CourseResponse])
async def list_courses(current_user: dict = Depends(get_current_user)):
    """List all courses for the authenticated instructor, with student counts."""
    if current_user["role"] != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can access this endpoint",
        )

    try:
        admin = get_supabase_admin()
        user_id = current_user["id"]

        # Fetch courses
        courses_resp = (
            admin.table("courses")
            .select("*")
            .eq("instructor_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )

        courses = courses_resp.data or []

        if not courses:
            return []

        # Batch: get all enrollments for these courses in ONE query
        course_ids = [c["id"] for c in courses]
        enrollments_resp = (
            admin.table("enrollments")
            .select("course_id")
            .in_("course_id", course_ids)
            .execute()
        )

        # Count enrollments per course in Python
        from collections import Counter
        counts = Counter(e["course_id"] for e in (enrollments_resp.data or []))

        result = []
        for course in courses:
            result.append(
                CourseResponse(
                    id=course["id"],
                    instructor_id=course["instructor_id"],
                    code=course["code"],
                    title=course["title"],
                    description=course.get("description"),
                    status=course["status"],
                    student_count=counts.get(course["id"], 0),
                    created_at=course.get("created_at"),
                )
            )

        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch courses: {str(e)}",
        )


@router.post("", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
async def create_course(
    course: CourseCreate, current_user: dict = Depends(get_current_user)
):
    """Create a new course for the authenticated instructor."""
    if current_user["role"] != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only instructors can create courses",
        )

    try:
        admin = get_supabase_admin()
        new_course = (
            admin.table("courses")
            .insert(
                {
                    "instructor_id": current_user["id"],
                    "code": course.code,
                    "title": course.title,
                    "description": course.description,
                    "status": course.status,
                }
            )
            .execute()
        )

        if not new_course.data:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create course",
            )

        created = new_course.data[0]
        return CourseResponse(
            id=created["id"],
            instructor_id=created["instructor_id"],
            code=created["code"],
            title=created["title"],
            description=created.get("description"),
            status=created["status"],
            student_count=0,
            created_at=created.get("created_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create course: {str(e)}",
        )


@router.get("/{course_id}", response_model=CourseResponse)
async def get_course(
    course_id: str, current_user: dict = Depends(get_current_user)
):
    """Get a single course by ID."""
    try:
        admin = get_supabase_admin()
        course_resp = (
            admin.table("courses")
            .select("*")
            .eq("id", course_id)
            .eq("instructor_id", current_user["id"])
            .single()
            .execute()
        )

        if not course_resp.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found",
            )

        course = course_resp.data
        count_resp = (
            admin.table("enrollments")
            .select("id", count="exact")
            .eq("course_id", course["id"])
            .execute()
        )
        student_count = count_resp.count if count_resp.count is not None else 0

        return CourseResponse(
            id=course["id"],
            instructor_id=course["instructor_id"],
            code=course["code"],
            title=course["title"],
            description=course.get("description"),
            status=course["status"],
            student_count=student_count,
            created_at=course.get("created_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch course: {str(e)}",
        )


@router.put("/{course_id}", response_model=CourseResponse)
async def update_course(
    course_id: str,
    course: CourseUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update a course owned by the authenticated instructor."""
    try:
        admin = get_supabase_admin()

        # Build update payload (only non-None fields)
        update_data = {k: v for k, v in course.model_dump().items() if v is not None}

        if not update_data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No fields to update",
            )

        updated = (
            admin.table("courses")
            .update(update_data)
            .eq("id", course_id)
            .eq("instructor_id", current_user["id"])
            .execute()
        )

        if not updated.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found or not owned by you",
            )

        c = updated.data[0]
        return CourseResponse(
            id=c["id"],
            instructor_id=c["instructor_id"],
            code=c["code"],
            title=c["title"],
            description=c.get("description"),
            status=c["status"],
            student_count=0,
            created_at=c.get("created_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update course: {str(e)}",
        )


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_course(
    course_id: str, current_user: dict = Depends(get_current_user)
):
    """Delete a course owned by the authenticated instructor."""
    try:
        admin = get_supabase_admin()
        result = (
            admin.table("courses")
            .delete()
            .eq("id", course_id)
            .eq("instructor_id", current_user["id"])
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Course not found or not owned by you",
            )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete course: {str(e)}",
        )
