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
    due_date: Optional[str] = None


class AssignmentResponse(BaseModel):
    id: str
    course_id: str
    course_code: Optional[str] = None
    course_title: Optional[str] = None
    title: str
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

