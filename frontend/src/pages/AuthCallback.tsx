import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

export default function AuthCallback() {
  const navigate = useNavigate();
  const { login } = useAuth();
  useEffect(() => {
    void login().then(() => navigate("/", { replace: true }));
  }, [login, navigate]);
  return (
    <div className="flex h-screen items-center justify-center bg-[#0F1117]">
      <p className="text-gray-400">Completing sign in…</p>
    </div>
  );
}
