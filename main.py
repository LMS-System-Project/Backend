from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import auth, courses, dashboard, analytics, students, grading, settings

app = FastAPI(
    title="GradeFlow API",
    description="Backend API for the GradeFlow LMS – Instructor Module",
    version="1.0.0",
)

# CORS – allow the Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(dashboard.router)
app.include_router(analytics.router)
app.include_router(students.router)
app.include_router(grading.router)
app.include_router(settings.router)


@app.get("/")
def root():
    return {"message": "GradeFlow API is running 🚀"}
