-- ============================================================
-- GradeFlow LMS – Migration: Materials, Enhanced Assignments & Submissions
-- Run this in Supabase SQL Editor (Dashboard > SQL Editor > New Query)
-- ============================================================

-- 1. Course Materials table
CREATE TABLE IF NOT EXISTS course_materials (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  course_id UUID NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  description TEXT,
  file_name TEXT NOT NULL,
  file_url TEXT NOT NULL,
  file_size BIGINT DEFAULT 0,
  uploaded_by UUID NOT NULL REFERENCES profiles(id),
  created_at TIMESTAMPTZ DEFAULT now()
);

-- 2. Enhance assignments table
ALTER TABLE assignments ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE assignments ADD COLUMN IF NOT EXISTS instructions TEXT;
ALTER TABLE assignments ADD COLUMN IF NOT EXISTS max_marks INT DEFAULT 100;

-- 3. Enhance submissions table
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS file_url TEXT;
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS file_name TEXT;
ALTER TABLE submissions ADD COLUMN IF NOT EXISTS notes TEXT;

-- ============================================================
-- Row Level Security for course_materials
-- ============================================================

ALTER TABLE course_materials ENABLE ROW LEVEL SECURITY;

-- Instructors can manage materials for their own courses
CREATE POLICY "Instructors manage their course materials" ON course_materials
  FOR ALL USING (
    EXISTS (
      SELECT 1 FROM courses
      WHERE courses.id = course_materials.course_id
        AND courses.instructor_id = auth.uid()
    )
  );

-- Students can view materials for courses they are enrolled in
CREATE POLICY "Students view materials for enrolled courses" ON course_materials
  FOR SELECT USING (
    EXISTS (
      SELECT 1 FROM enrollments
      WHERE enrollments.course_id = course_materials.course_id
        AND enrollments.student_id = auth.uid()
    )
  );

-- ============================================================
-- Enrollment: allow students to enroll themselves
-- ============================================================

-- Check if policy exists first (safe to re-run)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE policyname = 'Students can enroll themselves' AND tablename = 'enrollments'
  ) THEN
    EXECUTE 'CREATE POLICY "Students can enroll themselves" ON enrollments FOR INSERT WITH CHECK (auth.uid() = student_id)';
  END IF;
END $$;

-- Allow service role full access to course_materials (for backend admin operations)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE policyname = 'Service role full access to materials' AND tablename = 'course_materials'
  ) THEN
    EXECUTE 'CREATE POLICY "Service role full access to materials" ON course_materials FOR ALL USING (true) WITH CHECK (true)';
  END IF;
END $$;
