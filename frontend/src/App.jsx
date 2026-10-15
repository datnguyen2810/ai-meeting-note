import { useState, useEffect } from "react";
import { api, getStoredUser, getStoredToken } from "./services/api";
import LandingPage from "./pages/LandingPage";
import AuthPage from "./pages/AuthPage";
import LiveMeetingRoom from "./components/LiveMeetingRoom";
import SpeechToTextDemo from "./components/SpeechToTextDemo";
import "./App.css";

function getUserInitials(user) {
  const name = user?.fullName || user?.username || "U";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

export default function App() {
  const [page, setPage] = useState("landing");
  const [user, setUser] = useState(getStoredUser());
  const [activeTab, setActiveTab] = useState("live");
  const [meetings, setMeetings] = useState([]);
  const [searchMeeting, setSearchMeeting] = useState("");
  const [selectedMeeting, setSelectedMeeting] = useState(null);
  const [showUserModal, setShowUserModal] = useState(false);
  const [authMode, setAuthMode] = useState("login");

  // If already logged in, go straight to dashboard
  useEffect(() => {
    if (user) {
      setPage("dashboard");
      loadMeetings();
    }
  }, []);

  // Listen for auth_logout events (from API module)
  useEffect(() => {
    const handleLogoutListener = () => {
      setUser(null);
      setPage("landing");
    };
    window.addEventListener("auth_logout", handleLogoutListener);
    return () => window.removeEventListener("auth_logout", handleLogoutListener);
  }, []);

  const loadMeetings = async () => {
    if (!getStoredToken()) return;
    try {
      const data = await api.getMeetings();
      setMeetings(data || []);
    } catch (err) {
      console.warn("Could not load meetings:", err.message);
    }
  };

  const handleLoginSuccess = (userData) => {
    setUser(userData);
    setPage("dashboard");
    loadMeetings();
  };

  const handleLogout = () => {
    api.logout();
    setUser(null);
    setPage("landing");
  };

  // ── Landing Page ──────────────────────────────────────────────
  if (page === "landing") {
    return (
      <LandingPage
        onLogin={() => {
          setAuthMode("login");
          setPage("auth");
        }}
        onRegister={() => {
          setAuthMode("register");
          setPage("auth");
        }}
      />
    );
  }

  // ── Auth Page ─────────────────────────────────────────────────
  if (page === "auth") {
    return (
      <AuthPage
        initialMode={authMode}
        onLoginSuccess={handleLoginSuccess}
        onBack={() => setPage("landing")}
      />
    );
  }

  // Filter meetings by search query
  const filteredMeetings = meetings.filter((m) =>
    (m.title || `Cuộc họp #${m.id}`)
      .toLowerCase()
      .includes(searchMeeting.toLowerCase())
  );

  // ── Dashboard ─────────────────────────────────────────────────
  return (
    <div className="db-app-root">
      {/* ── Top Navbar ──────────────────────────────────────── */}
      <header className="db-navbar">
        <div className="db-brand">
          <div className="db-brand-info">
            <span className="db-brand-title">AI Meeting Note</span>
            <span className="db-brand-sub">Tóm tắt và lưu trữ cuộc họp</span>
          </div>
        </div>

        {/* Tab chuyển đổi 2 chức năng */}
        <div className="db-tabs">
          <button
            type="button"
            className={`db-tab-btn ${activeTab === "live" ? "active" : ""}`}
            onClick={() => setActiveTab("live")}
          >
            Cuộc họp trực tiếp
          </button>
          <button
            type="button"
            className={`db-tab-btn ${activeTab === "upload" ? "active" : ""}`}
            onClick={() => setActiveTab("upload")}
          >
            Tải file & Phân tích
          </button>
        </div>

        {/* Nút đăng xuất to và có màu nổi bật */}
        <div className="db-nav-actions">
          <button
            type="button"
            className="db-logout-btn"
            onClick={handleLogout}
            title="Đăng xuất khỏi hệ thống"
          >
            Đăng xuất
          </button>
        </div>
      </header>

      {/* ── Dashboard Body (2 Cột) ───────────────────────────── */}
      <div className="db-body">
        {/* Cột trái: Lịch sử cuộc họp + Taskbar thông tin người học */}
        <aside className="db-sidebar">
          <div className="db-sidebar-header">
            <div className="db-sidebar-title-wrap">
              <h2 className="db-sidebar-title">Lịch sử cuộc họp</h2>
              <span className="db-sidebar-badge">{meetings.length}</span>
            </div>
            <button
              type="button"
              className="db-refresh-btn"
              onClick={loadMeetings}
              title="Làm mới danh sách"
            >
              Làm mới
            </button>
          </div>

          <div className="db-search-box">
            <input
              type="text"
              className="db-search-input"
              placeholder="Tìm kiếm cuộc họp..."
              value={searchMeeting}
              onChange={(e) => setSearchMeeting(e.target.value)}
            />
          </div>

          <div className="db-history-list">
            {filteredMeetings.length === 0 ? (
              <div className="db-history-empty">
                <div className="db-empty-title">Chưa có cuộc họp nào</div>
                <div className="db-empty-desc">
                  Các phiên họp sau khi tiến hành hoặc phân tích file sẽ được lưu tự động tại đây.
                </div>
              </div>
            ) : (
              filteredMeetings.map((m) => (
                <div
                  key={m.id}
                  className={`db-history-card ${selectedMeeting?.id === m.id ? "active" : ""}`}
                  onClick={() => setSelectedMeeting(m)}
                >
                  <div className="db-card-header">
                    <span className="db-card-title">{m.title || `Cuộc họp #${m.id}`}</span>
                    <span className="db-card-status">{m.status || "ĐÃ LƯU"}</span>
                  </div>
                  <div className="db-card-meta">
                    <span>
                      {m.createdAt
                        ? new Date(m.createdAt).toLocaleDateString("vi-VN", {
                            day: "2-digit",
                            month: "2-digit",
                            year: "numeric",
                            hour: "2-digit",
                            minute: "2-digit",
                          })
                        : "Vừa xong"}
                    </span>
                    {m.audioCount > 0 && <span>• {m.audioCount} tệp ghi âm</span>}
                  </div>
                  {m.description && (
                    <div className="db-card-desc">{m.description}</div>
                  )}
                </div>
              ))
            )}
          </div>

          {/* Taskbar trái: Tài khoản người học */}
          <div
            className="db-sidebar-user"
            onClick={() => setShowUserModal(true)}
            title="Xem thông tin người dùng"
          >
            <div className="db-user-avatar">
              {getUserInitials(user)}
            </div>
            <div className="db-user-details">
              <span className="db-user-fullname">
                {user?.fullName || user?.username || "Học viên"}
              </span>
              <span className="db-user-role">Xem thông tin tài khoản</span>
            </div>
          </div>
        </aside>

        {/* Cột phải: Khu vực làm việc chính (2 chức năng) */}
        <main className="db-main-content">
          <div className="db-workspace-card">
            {activeTab === "live" && <LiveMeetingRoom />}
            {activeTab === "upload" && <SpeechToTextDemo />}
          </div>
        </main>
      </div>

      {/* ── Modal: Thông tin người học / tài khoản ───────────── */}
      {showUserModal && (
        <div className="db-modal-overlay" onClick={() => setShowUserModal(false)}>
          <div className="db-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="db-modal-header">
              <h3 className="db-modal-title">Thông tin người học</h3>
              <button
                type="button"
                className="db-modal-close"
                onClick={() => setShowUserModal(false)}
              >
                ✕
              </button>
            </div>

            <div className="db-modal-profile">
              <div className="db-modal-avatar">
                {getUserInitials(user)}
              </div>
              <h4 className="db-modal-name">
                {user?.fullName || user?.username || "Chưa cập nhật"}
              </h4>
              <span className="db-modal-badge">Tài khoản học viên</span>
            </div>

            <div className="db-modal-fields">
              <div className="db-modal-field">
                <span className="db-modal-label">Họ và tên</span>
                <span className="db-modal-val">{user?.fullName || "Chưa cập nhật"}</span>
              </div>
              <div className="db-modal-field">
                <span className="db-modal-label">Tên đăng nhập</span>
                <span className="db-modal-val">@{user?.username || "—"}</span>
              </div>
              <div className="db-modal-field">
                <span className="db-modal-label">Email</span>
                <span className="db-modal-val">{user?.email || "Chưa cập nhật"}</span>
              </div>
              <div className="db-modal-field">
                <span className="db-modal-label">Mã tài khoản</span>
                <span className="db-modal-val">#{user?.id || 1}</span>
              </div>
              <div className="db-modal-field">
                <span className="db-modal-label">Trạng thái</span>
                <span className="db-modal-val db-modal-val--online">Đang hoạt động</span>
              </div>
            </div>

            <div className="db-modal-actions">
              <button
                type="button"
                className="db-modal-btn"
                onClick={() => setShowUserModal(false)}
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: Chi tiết cuộc họp khi click item lịch sử ─── */}
      {selectedMeeting && (
        <div className="db-modal-overlay" onClick={() => setSelectedMeeting(null)}>
          <div className="db-modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="db-modal-header">
              <h3 className="db-modal-title">Chi tiết cuộc họp</h3>
              <button
                type="button"
                className="db-modal-close"
                onClick={() => setSelectedMeeting(null)}
              >
                ✕
              </button>
            </div>

            <div className="db-modal-fields">
              <div className="db-modal-field">
                <span className="db-modal-label">Tiêu đề cuộc họp</span>
                <span className="db-modal-val" style={{ fontWeight: 700 }}>
                  {selectedMeeting.title || `Cuộc họp #${selectedMeeting.id}`}
                </span>
              </div>
              <div className="db-modal-field">
                <span className="db-modal-label">Mã cuộc họp</span>
                <span className="db-modal-val">#{selectedMeeting.id}</span>
              </div>
              <div className="db-modal-field">
                <span className="db-modal-label">Người tạo</span>
                <span className="db-modal-val">
                  {selectedMeeting.organizerName || user?.fullName || "Bạn"}
                </span>
              </div>
              <div className="db-modal-field">
                <span className="db-modal-label">Thời gian tạo</span>
                <span className="db-modal-val">
                  {selectedMeeting.createdAt
                    ? new Date(selectedMeeting.createdAt).toLocaleString("vi-VN")
                    : "—"}
                </span>
              </div>
              <div className="db-modal-field">
                <span className="db-modal-label">Số file ghi âm</span>
                <span className="db-modal-val">{selectedMeeting.audioCount || 0} tệp</span>
              </div>
              <div className="db-modal-field">
                <span className="db-modal-label">Trạng thái</span>
                <span className="db-modal-val">{selectedMeeting.status || "SCHEDULED"}</span>
              </div>
              {selectedMeeting.description && (
                <div className="db-modal-field" style={{ flexDirection: "column", gap: 4 }}>
                  <span className="db-modal-label">Mô tả cuộc họp</span>
                  <p className="db-modal-val" style={{ margin: 0, color: "#475569" }}>
                    {selectedMeeting.description}
                  </p>
                </div>
              )}
            </div>

            <div className="db-modal-actions">
              <button
                type="button"
                className="db-modal-btn"
                onClick={() => setSelectedMeeting(null)}
              >
                Đóng
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
