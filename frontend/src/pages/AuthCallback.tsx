import { useEffect } from "react";
import { useNavigate, useLocation } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export default function AuthCallback() {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuth();
  useEffect(() => {
    const token = new URLSearchParams(location.hash.slice(1)).get("token")
      ?? new URLSearchParams(location.search).get("token");
    if (token) { void login(token).then(() => navigate("/", { replace: true })); }
    else navigate("/login", { replace: true });
  }, [location.hash, location.search, login, navigate]);
  return (
    <div className="flex h-screen items-center justify-center bg-[#0F1117]">
      <p className="text-gray-400">Completing sign in…</p>
    </div>
  );
}
