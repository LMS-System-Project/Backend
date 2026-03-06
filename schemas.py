from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import datetime


# ── Auth Schemas ──────────────────────────────────────────────

class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: str = "instructor"  # default for now
    department: Optional[str] = None


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str
    role: str
    department: Optional[str] = None


class AuthResponse(BaseModel):
    user: UserResponse
    access_token: str
    token_type: str = "bearer"


# ── Course Schemas ────────────────────────────────────────────

class CourseCreate(BaseModel):
    code: str
    title: str
    description: Optional[str] = None
    status: str = "active"


class CourseUpdate(BaseModel):
    code: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class CourseResponse(BaseModel):
    id: str
    instructor_id: str
    code: str
    title: str
    description: Optional[str] = None
    status: str
    student_count: int = 0
    created_at: Optional[str] = None


# ── Dashboard Schemas ─────────────────────────────────────────

class DashboardStats(BaseModel):
    active_courses: int
    total_students: int
    pending_reviews: int
    class_average: str
    avg_attendance: str = "N/A"


# ── Analytics Schemas ─────────────────────────────────────────

class EngagementDataPoint(BaseModel):
    label: str
    active_users: int
    course_views: int


class AnalyticsStat(BaseModel):
    label: str
    value: int
    sub: str
    color: str


class AnalyticsResponse(BaseModel):
    engagement: List[EngagementDataPoint]
    stats: List[AnalyticsStat]


# ── Student Schemas ───────────────────────────────────────────

class StudentResponse(BaseModel):
    id: str
    full_name: str
    email: Optional[str] = None
    department: Optional[str] = None
    course_id: str
    course_code: str
    course_title: str
    enrolled_at: Optional[str] = None


# ── Assignment Schemas ────────────────────────────────────────

class AssignmentCreate(BaseModel):
    course_id: str
    title: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    max_marks: int = 100
    due_date: Optional[str] = None


class AssignmentResponse(BaseModel):
    id: str
    course_id: str
    course_code: Optional[str] = None
    course_title: Optional[str] = None
    title: str
    description: Optional[str] = None
    instructions: Optional[str] = None
    max_marks: int = 100
    due_date: Optional[str] = None
    created_at: Optional[str] = None


# ── Submission / Grading Schemas ──────────────────────────────

class SubmissionResponse(BaseModel):
    id: str
    assignment_id: str
    assignment_title: Optional[str] = None
    course_code: Optional[str] = None
    student_id: str
    student_name: Optional[str] = None
    status: str
    grade: Optional[str] = None
    file_url: Optional[str] = None
    file_name: Optional[str] = None
    notes: Optional[str] = None
    submitted_at: Optional[str] = None


class GradeSubmission(BaseModel):
    grade: str
    status: str = "graded"


# ── Profile / Settings Schemas ────────────────────────────────

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    department: Optional[str] = None


class ProfileResponse(BaseModel):
    id: str
    full_name: str
    email: Optional[str] = None
    role: str
    department: Optional[str] = None
    created_at: Optional[str] = None


# ── Student-specific Schemas ──────────────────────────────────

class StudentDashboardStats(BaseModel):
    enrolled_courses: int
    pending_assignments: int
    submitted_assignments: int
    graded_assignments: int
    average_grade: str


class StudentCourseResponse(BaseModel):
    id: str
    code: str
    title: str
    description: Optional[str] = None
    status: str
    instructor_name: Optional[str] = None
    total_assignments: int = 0
    submitted_assignments: int = 0
    progress: int = 0
    enrolled_at: Optional[str] = None


class StudentAssignmentResponse(BaseModel):
    id: str
    course_id: str
    course_code: Optional[str] = None
    course_title: Optional[str] = None
    title: str
    due_date: Optional[str] = None
    created_at: Optional[str] = None
    submission_status: str = "not_submitted"
    grade: Optional[str] = None
    submitted_at: Optional[str] = None
    submission_id: Optional[str] = None


class StudentSubmitRequest(BaseModel):
    notes: Optional[str] = None  # optional submission note


class StudentSubmissionResponse(BaseModel):
    id: str
    assignment_id: str
    assignment_title: Optional[str] = None
    student_id: str
    status: str
    grade: Optional[str] = None
    submitted_at: Optional[str] = None


# ── AI Chat Schemas ───────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    response: str


# ── Career Hub Schemas ────────────────────────────────────────

class ResumeRequest(BaseModel):
    include_skills: bool = True
    include_courses: bool = True
    target_role: Optional[str] = None


class ResumeResponse(BaseModel):
    resume_markdown: str
    skills: List[str]
    courses: List[str]


class JobListing(BaseModel):
    id: str
    title: str
    company: str
    location: str
    type: str  # internship, full-time, part-time
    skills: List[str]
    description: str
    apply_url: str


# ── CollabMesh Schemas ────────────────────────────────────────

class StudyGroup(BaseModel):
    id: str
    course_id: str
    course_title: str
    course_code: str
    member_count: int
    members: List[dict]


class StudyPartner(BaseModel):
    id: str
    full_name: str
    shared_courses: List[str]
    match_score: int  # Number of shared courses


# ── Course Catalog & Materials Schemas ────────────────────────

class CatalogCourseResponse(BaseModel):
    id: str
    code: str
    title: str
    description: Optional[str] = None
    status: str
    instructor_name: Optional[str] = None
    student_count: int = 0
    is_enrolled: bool = False
    created_at: Optional[str] = None


class CourseMaterialResponse(BaseModel):
    id: str
    course_id: str
    title: str
    description: Optional[str] = None
    file_name: str
    file_url: str
    file_size: int = 0
    uploaded_by: Optional[str] = None
    created_at: Optional[str] = None


class EnrollmentResponse(BaseModel):
    id: str
    course_id: str
    student_id: str
    enrolled_at: Optional[str] = None


