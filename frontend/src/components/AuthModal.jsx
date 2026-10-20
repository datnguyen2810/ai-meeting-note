import { useState } from "react";
import { api } from "../services/api";

export default function AuthModal({ onLoginSuccess, onClose }) {
  const [isRegister, setIsRegister] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      if (isRegister) {
        if (!username || !password || !email || !fullName) {
          throw new Error("Vui lòng điền đầy đủ tất cả các trường.");
        }
        const data = await api.register(username, email, password, fullName);
        onLoginSuccess(data);
      } else {
        if (!username || !password) {
          throw new Error("Vui lòng nhập tên đăng nhập và mật khẩu.");
        }
        const data = await api.login(username, password);
        onLoginSuccess(data);
      }
    } catch (err) {
      setError(err.message || "Đã có lỗi xảy ra. Vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  };

  const handleQuickDemo = async () => {
    setError("");
    setLoading(true);
    try {
      // Try login with admin
      const data = await api.login("admin", "password123");
      onLoginSuccess(data);
    } catch {
      try {
        // If not registered yet, register admin
        const regData = await api.register("admin", "admin@meeting.local", "password123", "Quản Trị Viên Demo");
        onLoginSuccess(regData);
      } catch (regErr) {
        setError(regErr.message || "Không thể đăng nhập mẫu");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-overlay">
      <div className="auth-card">
        {onClose && (
          <button
            type="button"
            className="auth-close-btn"
            onClick={onClose}
            title="Đóng"
          >
            ✕
          </button>
        )}
        <div className="auth-header">
          <div className="auth-badge">Hệ Thống Thông Minh</div>
          <h2 className="auth-title">
            {isRegister ? "Đăng ký tài khoản" : "Đăng nhập hệ thống"}
          </h2>
          <p className="auth-subtitle">
            AI Meeting Notes — Tóm tắt cuộc họp và nhận diện giọng nói
          </p>
        </div>

        <div className="auth-tabs">
          <button
            type="button"
            className={`auth-tab ${!isRegister ? "auth-tab--active" : ""}`}
            onClick={() => { setIsRegister(false); setError(""); }}
          >
            Đăng nhập
          </button>
          <button
            type="button"
            className={`auth-tab ${isRegister ? "auth-tab--active" : ""}`}
            onClick={() => { setIsRegister(true); setError(""); }}
          >
            Đăng ký
          </button>
        </div>

        <form onSubmit={handleSubmit} className="auth-form">
          {error && <div className="auth-alert">{error}</div>}

          <div className="auth-field">
            <label className="auth-label">Tên đăng nhập (Username)</label>
            <input
              type="text"
              className="auth-input"
              placeholder="VD: admin hoặc nguyenvana"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          {isRegister && (
            <>
              <div className="auth-field">
                <label className="auth-label">Họ và tên</label>
                <input
                  type="text"
                  className="auth-input"
                  placeholder="VD: Nguyễn Văn A"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  disabled={loading}
                  required
                />
              </div>

              <div className="auth-field">
                <label className="auth-label">Email</label>
                <input
                  type="email"
                  className="auth-input"
                  placeholder="VD: vana@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={loading}
                  required
                />
              </div>
            </>
          )}

          <div className="auth-field">
            <label className="auth-label">Mật khẩu</label>
            <input
              type="password"
              className="auth-input"
              placeholder="••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={loading}
              required
            />
          </div>

          <button
            type="submit"
            className="auth-submit-btn"
            disabled={loading}
          >
            {loading ? "Đang xử lý..." : isRegister ? "Tạo tài khoản" : "Đăng nhập ngay"}
          </button>

          <button
            type="button"
            className="auth-demo-btn"
            onClick={handleQuickDemo}
            disabled={loading}
          >
            ⚡ Đăng nhập nhanh tài khoản mẫu (Demo 1-Click)
          </button>
        </form>
      </div>
    </div>
  );
}
