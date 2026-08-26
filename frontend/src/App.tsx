import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './auth/AuthProvider';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { useAuth } from './auth/useAuth';
import { homeFor } from './auth/roles';
import { LoginPage } from './pages/LoginPage';
import { SignupPage } from './pages/SignupPage';
import { NotFoundPage } from './pages/NotFoundPage';

import { SetupPage } from './pages/student/SetupPage';
import { TranscriptPage } from './pages/student/TranscriptPage';
import { DashboardPage } from './pages/student/DashboardPage';
import { CoursesPage } from './pages/student/CoursesPage';
import { QuizzesPage } from './pages/student/QuizzesPage';
import { MentorsPage } from './pages/student/MentorsPage';
import { JobsPage } from './pages/student/JobsPage';
import { ProfilePage } from './pages/student/ProfilePage';

import { EmployerJobsPage } from './pages/employer/EmployerJobsPage';
import { JobFormPage } from './pages/employer/JobFormPage';
import { CandidatesPage } from './pages/employer/CandidatesPage';
import { CompanyProfilePage } from './pages/employer/CompanyProfilePage';

import { ExpertSessionsPage } from './pages/expert/ExpertSessionsPage';
import { ExpertAvailabilityPage } from './pages/expert/ExpertAvailabilityPage';
import { ExpertProfilePage } from './pages/expert/ExpertProfilePage';

import { LearningOutcomesPage } from './pages/content/LearningOutcomesPage';
import { LearningOutcomeReviewPage } from './pages/content/LearningOutcomeReviewPage';

import { AdminContentManagersPage } from './pages/admin/AdminContentManagersPage';
import { AdminMentorsPage } from './pages/admin/AdminMentorsPage';
import { AdminReferencePage } from './pages/admin/AdminReferencePage';

import type { ReactNode } from 'react';

/** Every student route carries the same guard; naming it once keeps the table readable. */
function Student({ children }: { children: ReactNode }) {
  return <ProtectedRoute allow={['JOB_SEEKER']}>{children}</ProtectedRoute>;
}

function Employer({ children }: { children: ReactNode }) {
  return <ProtectedRoute allow={['EMPLOYER']}>{children}</ProtectedRoute>;
}

function Expert({ children }: { children: ReactNode }) {
  return <ProtectedRoute allow={['EXPERT']}>{children}</ProtectedRoute>;
}

function ContentManager({ children }: { children: ReactNode }) {
  return <ProtectedRoute allow={['CONTENT_MANAGER']}>{children}</ProtectedRoute>;
}

function Admin({ children }: { children: ReactNode }) {
  return <ProtectedRoute allow={['ADMIN']}>{children}</ProtectedRoute>;
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
          <Route path="/employer/jobs/:jobId/candidates" element={<Employer><CandidatesPage /></Employer>} />
          <Route path="/employer/profile" element={<Employer><CompanyProfilePage /></Employer>} />

          {/* --- Expert (FR-EX-*) -------------------------------------- */}
          <Route path="/expert" element={<Expert><ExpertSessionsPage /></Expert>} />
          <Route path="/expert/availability" element={<Expert><ExpertAvailabilityPage /></Expert>} />
          <Route path="/expert/profile" element={<Expert><ExpertProfilePage /></Expert>} />

          {/* --- Content manager (FR-CM-*) ----------------------------- */}
          <Route path="/content" element={<ContentManager><LearningOutcomesPage /></ContentManager>} />
          <Route path="/content/learning-outcomes/:outcomeId/review" element={<ContentManager><LearningOutcomeReviewPage /></ContentManager>} />

          {/* --- Admin (FR-SA-*) --------------------------------------- */}
          <Route path="/admin" element={<Admin><AdminContentManagersPage /></Admin>} />
          <Route path="/admin/mentors" element={<Admin><AdminMentorsPage /></Admin>} />
          <Route path="/admin/reference" element={<Admin><AdminReferencePage /></Admin>} />

          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
