from fastapi import APIRouter, HTTPException, status, Depends
from database import get_supabase_admin
from schemas import AnalyticsResponse, EngagementDataPoint, AnalyticsStat
from auth import get_current_user

router = APIRouter(prefix="/api/instructor", tags=["Instructor Analytics"])


@router.get("/analytics", response_model=AnalyticsResponse)
async def get_analytics(current_user: dict = Depends(get_current_user)):
    """
    Get analytics data for the instructor.
    Returns engagement data points and summary stats.
    """
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
            .select("id")
            .eq("instructor_id", user_id)
            .execute()
        )
        course_ids = [c["id"] for c in (courses_resp.data or [])]

        # Calculate total enrollments (as a proxy for engagement) — single batch query
        total_students = 0
        if course_ids:
            enroll_resp = (
                admin.table("enrollments")
                .select("id", count="exact")
                .in_("course_id", course_ids)
                .execute()
            )
            total_students = enroll_resp.count or 0

        # Calculate completion rate from submissions
        total_submissions = 0
        graded_submissions = 0
        if course_ids:
            assignments_resp = (
                admin.table("assignments")
                .select("id")
                .in_("course_id", course_ids)
                .execute()
            )
            assignment_ids = [a["id"] for a in (assignments_resp.data or [])]

            if assignment_ids:
                all_subs = (
                    admin.table("submissions")
                    .select("id", count="exact")
                    .in_("assignment_id", assignment_ids)
                    .execute()
                )
                total_submissions = all_subs.count or 0

                graded_subs = (
                    admin.table("submissions")
                    .select("id", count="exact")
                    .in_("assignment_id", assignment_ids)
                    .eq("status", "graded")
                    .execute()
                )
                graded_submissions = graded_subs.count or 0

        completion_rate = (
            round((graded_submissions / total_submissions) * 100)
            if total_submissions > 0
            else 0
        )

        # Build engagement data (simulated time series based on real counts)
        num_courses = len(course_ids)
        engagement = [
            EngagementDataPoint(label="Mon", active_users=total_students, course_views=num_courses * 5),
            EngagementDataPoint(label="Tue", active_users=int(total_students * 0.9), course_views=num_courses * 4),
            EngagementDataPoint(label="Wed", active_users=int(total_students * 0.95), course_views=num_courses * 6),
            EngagementDataPoint(label="Thu", active_users=int(total_students * 0.85), course_views=num_courses * 4),
            EngagementDataPoint(label="Fri", active_users=int(total_students * 0.7), course_views=num_courses * 3),
            EngagementDataPoint(label="Sat", active_users=int(total_students * 0.4), course_views=num_courses * 2),
            EngagementDataPoint(label="Sun", active_users=int(total_students * 0.5), course_views=num_courses * 2),
        ]

        # Engagement score based on submissions vs students
        engagement_score = (
            min(100, round((total_submissions / max(total_students, 1)) * 100))
            if total_students > 0
            else 0
        )

        stats = [
            AnalyticsStat(
                label="Completion Rate",
                value=completion_rate,
                sub=f"Based on {total_submissions} submissions",
                color="cyan",
            ),
            AnalyticsStat(
                label="Engagement Score",
                value=engagement_score,
                sub=f"{total_students} total students",
                color="purple",
            ),
            AnalyticsStat(
                label="Active Courses",
                value=min(100, num_courses * 25),
                sub=f"{num_courses} courses running",
                color="pink",
            ),
        ]

        return AnalyticsResponse(engagement=engagement, stats=stats)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch analytics: {str(e)}",
        )
