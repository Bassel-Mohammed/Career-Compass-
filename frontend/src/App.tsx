import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthProvider';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { useAuth } from './auth/useAuth';
import { homeFor } from './auth/roles';
import { LoginPage } from './pages/LoginPage';
import { SignupPage } from './pages/SignupPage';
import { PlaceholderHome } from './pages/PlaceholderHome';
import { NotFoundPage } from './pages/NotFoundPage';
import { SetupPage } from './pages/student/SetupPage';
import { TranscriptPage } from './pages/student/TranscriptPage';
import { DashboardPage } from './pages/student/DashboardPage';
import { CoursesPage } from './pages/student/CoursesPage';
import { QuizzesPage } from './pages/student/QuizzesPage';
import { MentorsPage } from './pages/student/MentorsPage';
import { JobsPage } from './pages/student/JobsPage';
import { ProfilePage } from './pages/student/ProfilePage';
import { StudyFieldPage } from './pages/content/StudyFieldPage';
import { LearningOutcomesPage } from './pages/content/LearningOutcomesPage';
import { EmployerJobsPage } from './pages/employer/EmployerJobsPage';
import { JobFormPage } from './pages/employer/JobFormPage';
import { CandidatesPage } from './pages/employer/CandidatesPage';
import { CompanyProfilePage } from './pages/employer/CompanyProfilePage';
import type { ReactNode } from 'react';

/** Every student route carries the same guard; naming it once keeps the table readable. */
function Student({ children }: { children: ReactNode }) {
  return <ProtectedRoute allow={['JOB_SEEKER']}>{children}</ProtectedRoute>;
}

function Employer({ children }: { children: ReactNode }) {
  return <ProtectedRoute allow={['EMPLOYER']}>{children}</ProtectedRoute>;
}

/** "/" is not a page of its own yet — it forwards to wherever the visitor belongs. */
function RootRedirect() {
  const { session } = useAuth();
  return <Navigate to={session ? homeFor(session.role) : '/login'} replace />;
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />

          {/*
            One home per actor. Each is guarded by role, not merely by being signed in:
            the Java API enforces the same split at /api/<actor>/**, so a route that let
            the wrong role in would only render a screen full of 403s.
          */}
          {/* --- Student (FR-JS-*) ------------------------------------- */}
          <Route path="/dashboard" element={<Student><DashboardPage /></Student>} />
          <Route path="/setup" element={<Student><SetupPage /></Student>} />
          <Route path="/transcript" element={<Student><TranscriptPage /></Student>} />
          <Route path="/courses" element={<Student><CoursesPage /></Student>} />
          <Route path="/quizzes" element={<Student><QuizzesPage /></Student>} />
          <Route path="/mentors" element={<Student><MentorsPage /></Student>} />
          <Route path="/jobs" element={<Student><JobsPage /></Student>} />
          <Route path="/profile" element={<Student><ProfilePage /></Student>} />
          {/* --- Employer (FR-EMP-*) ------------------------------------- */}
          <Route path="/employer" element={<Employer><EmployerJobsPage /></Employer>} />
          <Route path="/employer/jobs/new" element={<Employer><JobFormPage /></Employer>} />
          <Route path="/employer/jobs/:jobId/edit" element={<Employer><JobFormPage /></Employer>} />
          <Route
            path="/employer/jobs/:jobId/candidates"
            element={<Employer><CandidatesPage /></Employer>}
          />
          <Route
            path="/employer/profile"
            element={<Employer><CompanyProfilePage /></Employer>}
          />
          <Route
            path="/expert"
            element={
              <ProtectedRoute allow={['EXPERT']}>
                <PlaceholderHome />
              </ProtectedRoute>
            }
          />
          {/* --- Content manager (FR-CM-*) ----------------------------- */}
          <Route
            path="/content"
            element={
              <ProtectedRoute allow={['CONTENT_MANAGER']}>
                <LearningOutcomesPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/content/profile"
            element={
              <ProtectedRoute allow={['CONTENT_MANAGER']}>
                <StudyFieldPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin"
            element={
              <ProtectedRoute allow={['ADMIN']}>
                <PlaceholderHome />
              </ProtectedRoute>
            }
          />

          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
