import { Toaster } from "sonner";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "@/lib/auth.jsx";
import Landing from "@/pages/Landing.jsx";
import Login from "@/pages/Login.jsx";
import DashboardLayout from "@/pages/DashboardLayout.jsx";
import Status from "@/pages/dashboard/Status.jsx";
import TelegramSetup from "@/pages/dashboard/TelegramSetup.jsx";
import Configuration from "@/pages/dashboard/Configuration.jsx";
import Activity from "@/pages/dashboard/Activity.jsx";
import Notifications from "@/pages/dashboard/Notifications.jsx";
import Pricing from "@/pages/dashboard/Pricing.jsx";
import Admin from "@/pages/dashboard/Admin.jsx";
import "@/App.css";

function Protected({ children, adminOnly = false }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen bg-[#05050A]" />;
  if (!user) return <Navigate to="/login" replace />;
  if (adminOnly && user.role !== "admin") return <Navigate to="/dashboard" replace />;
  return children;
}

function App() {
  return (
    <AuthProvider>
      <Toaster
        theme="dark"
        position="bottom-right"
        toastOptions={{
          style: {
            background: "#0F0F16",
            border: "1px solid rgba(255,255,255,0.1)",
            color: "#F8FAFC",
            fontFamily: "Outfit, sans-serif",
          },
        }}
      />
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />

          <Route
            path="/dashboard"
            element={
              <Protected>
                <DashboardLayout />
              </Protected>
            }
          >
            <Route index element={<Status />} />
            <Route path="telegram" element={<TelegramSetup />} />
            <Route path="config" element={<Configuration />} />
            <Route path="activity" element={<Activity />} />
            <Route path="notifications" element={<Notifications />} />
            <Route path="pricing" element={<Pricing />} />
            <Route
              path="admin"
              element={
                <Protected adminOnly>
                  <Admin />
                </Protected>
              }
            />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}

export default App;
