from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Form
from typing import List, Optional
from database import get_supabase_admin
from schemas import (
    StudentDashboardStats,
    StudentCourseResponse,
    StudentAssignmentResponse,
    StudentSubmissionResponse,
    StudentSubmitRequest,
    ProfileUpdate,
    ProfileResponse,
    ChatRequest,
    ChatResponse,
    ResumeRequest,
    ResumeResponse,
    JobListing,
    StudyGroup,
    StudyPartner,
    CatalogCourseResponse,
    CourseMaterialResponse,
    EnrollmentResponse,
)
from auth import get_current_user
from config import GEMINI_API_KEY, JSEARCH_API_KEY

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
    notes: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user),
):
    """Submit (or re-submit) an assignment. Supports optional file upload."""
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

        # Handle file upload if provided
        file_url = None
        file_name = None
        if file and file.filename:
            from storage import upload_file as store_file
            file_name, file_url = await store_file(file, folder="submissions")

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

        update_data = {"status": "pending", "submitted_at": now}
        if notes is not None:
            update_data["notes"] = notes
        if file_url:
            update_data["file_url"] = file_url
            update_data["file_name"] = file_name

        if existing_resp.data:
            result = (
                admin.table("submissions")
                .update(update_data)
                .eq("assignment_id", assignment_id)
                .eq("student_id", student_id)
                .execute()
            )
            sub = result.data[0]
        else:
            insert_data = {
                "assignment_id": assignment_id,
                "student_id": student_id,
                **update_data,
            }
            result = (
                admin.table("submissions")
                .insert(insert_data)
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
            file_url=sub.get("file_url"),
            file_name=sub.get("file_name"),
            notes=sub.get("notes"),
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


# ── AI Chat (Gemini-powered study assistant) ──────────────────────────────────

@router.post("/ai/chat", response_model=ChatResponse)
async def ai_chat(
    body: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """AI-powered study assistant that helps students with their coursework."""
    _require_student(current_user)

    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI chat is not configured. Please set GEMINI_API_KEY in .env",
        )

    try:
        import google.generativeai as genai

        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel("gemini-2.0-flash")

        student_name = current_user.get("full_name", "Student")

        system_prompt = (
            f"You are Sage, a friendly and knowledgeable AI study assistant for "
            f"the GradeFlow LMS platform. You are helping {student_name}. "
            f"You can help with explaining concepts, solving problems, "
            f"providing study tips, and answering academic questions. "
            f"Keep your responses concise, clear, and encouraging. "
            f"If a question is outside academic scope, politely redirect."
        )

        chat = model.start_chat(history=[])
        response = chat.send_message(f"{system_prompt}\n\nStudent: {body.message}")

        return ChatResponse(response=response.text)

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AI chat error: {str(e)}",
        )


# ── Career Hub: Resume Generator ──────────────────────────────────────────────

@router.post("/career/generate-resume", response_model=ResumeResponse)
async def generate_resume(
    body: ResumeRequest,
    current_user: dict = Depends(get_current_user),
):
    """Generate a resume based on the student's courses and performance."""
    _require_student(current_user)

    try:
        admin = get_supabase_admin()
        student_id = current_user["id"]

        # Fetch enrolled courses
        enrollments_resp = (
            admin.table("enrollments")
            .select("course_id")
            .eq("student_id", student_id)
            .execute()
        )
        course_ids = [e["course_id"] for e in (enrollments_resp.data or [])]

        courses = []
        skills = []
        if course_ids:
            courses_resp = (
                admin.table("courses")
                .select("code, title, description")
                .in_("id", course_ids)
                .execute()
            )
            courses = [f"{c['code']} — {c['title']}" for c in (courses_resp.data or [])]

            # Derive skills from course titles
            skill_keywords = {
                "programming": ["Python", "Problem Solving"],
                "data": ["Data Analysis", "SQL"],
                "web": ["HTML/CSS", "JavaScript", "React", "Node.js"],
                "machine learning": ["Machine Learning", "TensorFlow"],
                "algorithm": ["Algorithm Design", "Data Structures"],
                "database": ["SQL", "Database Management"],
            }
            for c in (courses_resp.data or []):
                title_lower = c["title"].lower()
                for keyword, skills_list in skill_keywords.items():
                    if keyword in title_lower:
                        skills.extend(skills_list)
            skills = list(set(skills)) or ["Critical Thinking", "Communication"]

        student_name = current_user.get("full_name", "Student")
        target = body.target_role or "Software Engineering"

        resume_md = f"""# {student_name}

## Objective
Motivated student seeking a {target} position.

## Education
- **GradeFlow University**
  - Completed {len(courses)} courses

## Relevant Coursework
{chr(10).join(f"- {c}" for c in courses) if courses else "- No courses yet"}

## Skills
{chr(10).join(f"- {s}" for s in skills)}

## Projects
- Academic projects completed through GradeFlow coursework
"""

        return ResumeResponse(
            resume_markdown=resume_md,
            skills=skills,
            courses=courses,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate resume: {str(e)}",
        )


# ── Career Hub: Job Listings ──────────────────────────────────────────────────

@router.get("/career/jobs", response_model=List[JobListing])
async def get_job_listings(
    query: str = "software developer",
    location: str = "India",
    current_user: dict = Depends(get_current_user),
):
    """Get job listings from JSearch API."""
    _require_student(current_user)

    if not JSEARCH_API_KEY:
        # Return sample data when API key is not configured
        return [
            JobListing(
                id="sample-1",
                title="Junior Software Developer",
                company="Tech Corp",
                location="Remote",
                type="full-time",
                skills=["Python", "JavaScript", "SQL"],
                description="Looking for a motivated junior developer to join our team.",
                apply_url="https://example.com/apply",
            ),
            JobListing(
                id="sample-2",
                title="Software Engineering Intern",
                company="StartupXYZ",
                location="Bangalore, India",
                type="internship",
                skills=["React", "Node.js", "Git"],
                description="6-month internship with mentorship and hands-on projects.",
                apply_url="https://example.com/apply",
            ),
        ]

    try:
        import httpx

        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://jsearch.p.rapidapi.com/search",
                params={
                    "query": f"{query} in {location}",
                    "num_pages": "1",
                },
                headers={
                    "X-RapidAPI-Key": JSEARCH_API_KEY,
                    "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
                },
            )

        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to fetch job listings")

        data = response.json()
        jobs = data.get("data", [])

        return [
            JobListing(
                id=str(i),
                title=job.get("job_title", "Unknown"),
                company=job.get("employer_name", "Unknown"),
                location=job.get("job_city", "Remote"),
                type=job.get("job_employment_type", "full-time").lower(),
                skills=job.get("job_required_skills") or [],
                description=(job.get("job_description", "")[:200] + "...") if job.get("job_description") else "",
                apply_url=job.get("job_apply_link", ""),
            )
            for i, job in enumerate(jobs[:10])
        ]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch jobs: {str(e)}",
        )


# ── CollabMesh: Study Groups ─────────────────────────────────────────────────

@router.get("/collab/study-groups", response_model=List[StudyGroup])
async def get_study_groups(current_user: dict = Depends(get_current_user)):
    """Get study groups for the student's enrolled courses."""
    _require_student(current_user)

    try:
        admin = get_supabase_admin()
        student_id = current_user["id"]

        # Get enrolled courses
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

        # Get all enrollments for these courses (other students)
        all_enrollments = (
            admin.table("enrollments")
            .select("course_id, student_id")
            .in_("course_id", course_ids)
            .execute()
        )

        # Get all student profiles in one batch
        all_student_ids = list({e["student_id"] for e in (all_enrollments.data or [])})
        profiles = {}
        if all_student_ids:
            profiles_resp = (
                admin.table("profiles")
                .select("id, full_name")
                .in_("id", all_student_ids)
                .execute()
            )
            profiles = {p["id"]: p["full_name"] for p in (profiles_resp.data or [])}

        # Build study groups by course
        from collections import defaultdict
        course_students = defaultdict(list)
        for e in (all_enrollments.data or []):
            course_students[e["course_id"]].append(e["student_id"])

        groups = []
        for course_id, students_in_course in course_students.items():
            course = course_map.get(course_id, {})
            members = [
                {"id": sid, "name": profiles.get(sid, "Unknown")}
                for sid in students_in_course
            ]
            groups.append(StudyGroup(
                id=course_id,
                course_id=course_id,
                course_title=course.get("title", "Unknown"),
                course_code=course.get("code", "N/A"),
                member_count=len(members),
                members=members,
            ))

        return groups

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch study groups: {str(e)}",
        )


# ── CollabMesh: Study Partners ───────────────────────────────────────────────

@router.get("/collab/study-partners", response_model=List[StudyPartner])
async def get_study_partners(current_user: dict = Depends(get_current_user)):
    """Find study partners based on shared courses."""
    _require_student(current_user)

    try:
        admin = get_supabase_admin()
        student_id = current_user["id"]

        # Get the student's enrolled courses
        enrollments_resp = (
            admin.table("enrollments")
            .select("course_id")
            .eq("student_id", student_id)
            .execute()
        )
        course_ids = [e["course_id"] for e in (enrollments_resp.data or [])]
        if not course_ids:
            return []

        # Get course info for display
        courses_resp = (
            admin.table("courses")
            .select("id, code, title")
            .in_("id", course_ids)
            .execute()
        )
        course_title_map = {c["id"]: c["title"] for c in (courses_resp.data or [])}

        # Get all other students in the same courses
        all_enrollments = (
            admin.table("enrollments")
            .select("course_id, student_id")
            .in_("course_id", course_ids)
            .execute()
        )

        # Count shared courses per student
        from collections import defaultdict
        shared_courses_map = defaultdict(list)
        for e in (all_enrollments.data or []):
            if e["student_id"] != student_id:
                shared_courses_map[e["student_id"]].append(
                    course_title_map.get(e["course_id"], "Unknown")
                )

        if not shared_courses_map:
            return []

        # Fetch profiles in one batch
        other_ids = list(shared_courses_map.keys())
        profiles_resp = (
            admin.table("profiles")
            .select("id, full_name")
            .in_("id", other_ids)
            .execute()
        )
        profile_map = {p["id"]: p["full_name"] for p in (profiles_resp.data or [])}

        # Build partners list, sorted by most shared courses
        partners = [
            StudyPartner(
                id=sid,
                full_name=profile_map.get(sid, "Unknown"),
                shared_courses=courses,
                match_score=len(courses),
            )
            for sid, courses in shared_courses_map.items()
        ]
        partners.sort(key=lambda x: x.match_score, reverse=True)

        return partners[:20]  # Limit to top 20 matches

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to find study partners: {str(e)}",
        )


# ── Course Catalog ────────────────────────────────────────────────────────────

@router.get("/catalog", response_model=List[CatalogCourseResponse])
async def browse_catalog(current_user: dict = Depends(get_current_user)):
    """Browse all active courses with enrollment status."""
    _require_student(current_user)

    try:
        admin = get_supabase_admin()
        student_id = current_user["id"]

        # Fetch all active courses
        courses_resp = (
            admin.table("courses")
            .select("*")
            .eq("status", "active")
            .order("created_at", desc=True)
            .execute()
        )
        courses = courses_resp.data or []
        if not courses:
            return []

        # Get enrollment status for this student
        enrollments_resp = (
            admin.table("enrollments")
            .select("course_id")
            .eq("student_id", student_id)
            .execute()
        )
        enrolled_ids = {e["course_id"] for e in (enrollments_resp.data or [])}

        # Get student counts per course
        course_ids = [c["id"] for c in courses]
        all_enrollments_resp = (
            admin.table("enrollments")
            .select("course_id")
            .in_("course_id", course_ids)
            .execute()
        )
        from collections import Counter
        counts = Counter(e["course_id"] for e in (all_enrollments_resp.data or []))

        # Get instructor names
        instructor_ids = list({c["instructor_id"] for c in courses})
        profiles_resp = (
            admin.table("profiles")
            .select("id, full_name")
            .in_("id", instructor_ids)
            .execute()
        )
        name_map = {p["id"]: p["full_name"] for p in (profiles_resp.data or [])}

        result = []
        for c in courses:
            result.append(CatalogCourseResponse(
                id=c["id"],
                code=c["code"],
                title=c["title"],
                description=c.get("description"),
                status=c["status"],
                instructor_name=name_map.get(c["instructor_id"]),
                student_count=counts.get(c["id"], 0),
                is_enrolled=c["id"] in enrolled_ids,
                created_at=c.get("created_at"),
            ))
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to browse catalog: {str(e)}",
        )


# ── Course Enrollment ─────────────────────────────────────────────────────────

@router.post("/enroll/{course_id}", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
async def enroll_in_course(course_id: str, current_user: dict = Depends(get_current_user)):
    """Enroll in a course."""
    _require_student(current_user)

    try:
        admin = get_supabase_admin()
        student_id = current_user["id"]

        # Check course exists and is active
        course_resp = (
            admin.table("courses")
            .select("id, status")
            .eq("id", course_id)
            .single()
            .execute()
        )
        if not course_resp.data:
            raise HTTPException(status_code=404, detail="Course not found")
        if course_resp.data["status"] != "active":
            raise HTTPException(status_code=400, detail="Course is not active")

        # Check if already enrolled
        existing = (
            admin.table("enrollments")
            .select("id")
            .eq("course_id", course_id)
            .eq("student_id", student_id)
            .execute()
        )
        if existing.data:
            raise HTTPException(status_code=409, detail="Already enrolled in this course")

        # Create enrollment
        result = (
            admin.table("enrollments")
            .insert({
                "course_id": course_id,
                "student_id": student_id,
            })
            .execute()
        )
        enrollment = result.data[0]
        return EnrollmentResponse(
            id=enrollment["id"],
            course_id=enrollment["course_id"],
            student_id=enrollment["student_id"],
            enrolled_at=enrollment.get("enrolled_at"),
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enroll: {str(e)}",
        )


# ── Course Materials (Student View) ──────────────────────────────────────────

@router.get("/courses/{course_id}/materials", response_model=List[CourseMaterialResponse])
async def get_course_materials(course_id: str, current_user: dict = Depends(get_current_user)):
    """List study materials for a course the student is enrolled in."""
    _require_student(current_user)

    try:
        admin = get_supabase_admin()
        student_id = current_user["id"]

        # Verify enrollment
        enrollment = (
            admin.table("enrollments")
            .select("id")
            .eq("course_id", course_id)
            .eq("student_id", student_id)
            .execute()
        )
        if not enrollment.data:
            raise HTTPException(status_code=403, detail="You are not enrolled in this course")

        # Fetch materials
        materials_resp = (
            admin.table("course_materials")
            .select("*")
            .eq("course_id", course_id)
            .order("created_at", desc=True)
            .execute()
        )

        result = []
        for m in (materials_resp.data or []):
            result.append(CourseMaterialResponse(
                id=m["id"],
                course_id=m["course_id"],
                title=m["title"],
                description=m.get("description"),
                file_name=m["file_name"],
                file_url=m["file_url"],
                file_size=m.get("file_size", 0),
                uploaded_by=m.get("uploaded_by"),
                created_at=m.get("created_at"),
            ))
        return result

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch materials: {str(e)}",
        )

