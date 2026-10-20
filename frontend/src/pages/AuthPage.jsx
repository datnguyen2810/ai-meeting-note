import { useState, useEffect } from "react";
import { api } from "../services/api";
import "../styles/AuthPage.css";

export default function AuthPage({ onLoginSuccess, onBack, initialMode = "login" }) {
  const [isRegister, setIsRegister] = useState(initialMode === "register");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setIsRegister(initialMode === "register");
    setError("");
  }, [initialMode]);

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

  return (
    <div className="ap-root">
      {/* Back to landing */}
      <button className="ap-back-btn" onClick={onBack}>
        ← Quay về trang chủ
      </button>

      <div className="ap-center">
        {/* Left panel — branding */}
        <div className="ap-left">
          <div className="ap-brand">
            <span className="ap-brand-name">AI Meeting Note</span>
          </div>
          <h1 className="ap-left-title">
            Quản lý và tóm tắt cuộc họp hiệu quả
          </h1>
          <p className="ap-left-desc">
            Đăng nhập để sử dụng các tính năng ghi âm trực tiếp, tải file âm thanh và xem lại biên bản tóm tắt cuộc họp.
          </p>
          <div className="ap-left-features">
            {[
              "Phiên âm giọng nói trực tiếp trong cuộc họp",
              "Tải lên tệp ghi âm sẵn có để phân tích",
              "Tự động trích xuất các ý chính và hành động",
              "Lưu trữ và tra cứu lịch sử các phiên họp",
            ].map((f, i) => (
              <div key={i} className="ap-left-feature-item">
                <span className="ap-left-feature-check">✓</span>
                <span>{f}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Right panel — form */}
        <div className="ap-right">
          <div className="ap-card">
            {/* Tab switcher */}
            <div className="ap-tabs">
              <button
                type="button"
                className={`ap-tab ${!isRegister ? "ap-tab--active" : ""}`}
                onClick={() => { setIsRegister(false); setError(""); }}
              >
                Đăng nhập
              </button>
              <button
                type="button"
                className={`ap-tab ${isRegister ? "ap-tab--active" : ""}`}
                onClick={() => { setIsRegister(true); setError(""); }}
              >
                Đăng ký
              </button>
            </div>

            <div className="ap-card-body">
              <h2 className="ap-form-title">
                {isRegister ? "Tạo tài khoản mới" : "Chào mừng trở lại"}
              </h2>
              <p className="ap-form-sub">
                {isRegister
                  ? "Điền thông tin để bắt đầu sử dụng hệ thống"
                  : "Đăng nhập để tiếp tục làm việc"}
              </p>

              {error && <div className="ap-error">{error}</div>}

              <form onSubmit={handleSubmit} className="ap-form">
                <div className="ap-field">
                  <label className="ap-label">Tên đăng nhập</label>
                  <input
                    type="text"
                    className="ap-input"
                    placeholder="Nhập tên đăng nhập"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    disabled={loading}
                    autoFocus
                    required
                  />
                </div>

                {isRegister && (
                  <>
                    <div className="ap-field">
                      <label className="ap-label">Họ và tên</label>
                      <input
                        type="text"
                        className="ap-input"
                        placeholder="Nhập họ và tên đầy đủ"
                        value={fullName}
                        onChange={(e) => setFullName(e.target.value)}
                        disabled={loading}
                        required
                      />
                    </div>
                    <div className="ap-field">
                      <label className="ap-label">Email</label>
                      <input
                        type="email"
                        className="ap-input"
                        placeholder="email@example.com"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        disabled={loading}
                        required
                      />
                    </div>
                  </>
                )}

                <div className="ap-field">
                  <label className="ap-label">Mật khẩu</label>
                  <input
                    type="password"
                    className="ap-input"
                    placeholder="••••••••"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    disabled={loading}
                    required
                  />
                </div>

                <button
                  type="submit"
                  className="ap-submit-btn"
                  disabled={loading}
                >
                  {loading
                    ? <><span className="ap-spinner" /> Đang xử lý...</>
                    : isRegister
                      ? "Tạo tài khoản"
                      : "Đăng nhập"}
                </button>
              </form>

              <p className="ap-switch-mode">
                {isRegister ? "Đã có tài khoản?" : "Chưa có tài khoản?"}
                {" "}
                <button
                  type="button"
                  className="ap-switch-link"
                  onClick={() => { setIsRegister(!isRegister); setError(""); }}
                >
                  {isRegister ? "Đăng nhập ngay" : "Đăng ký tài khoản"}
                </button>
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
