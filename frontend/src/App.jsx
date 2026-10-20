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
  const [loadingDetail, setLoadingDetail] = useState(false);

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

  const handleSelectMeeting = async (m) => {
    setSelectedMeeting(m);
    setLoadingDetail(true);
    try {
      const full = await api.getMeeting(m.id);
      if (full) {
        setSelectedMeeting(full);
      }
    } catch (err) {
      console.warn("Could not load meeting detail:", err);
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleDeleteMeeting = async (id) => {
    if (!window.confirm("Bạn có chắc chắn muốn xóa cuộc họp này khỏi lịch sử không?")) {
      return;
    }
    try {
      await api.deleteMeeting(id);
      setSelectedMeeting(null);
      loadMeetings();
    } catch (err) {
      alert("Lỗi khi xóa cuộc họp: " + err.message);
    }
  };

  const handleDownloadMeetingMd = (m) => {
    const title = m.title || `Cuoc_hop_${m.id}`;
    const time = m.createdAt ? new Date(m.createdAt).toLocaleString("vi-VN") : "";
    const content = `# ${m.title || `CUỘC HỌP #${m.id}`}
*Thời gian:* ${time}
*Mã cuộc họp:* #${m.id}
*Người tạo:* ${m.organizerName || user?.fullName || "Bạn"}

---

## 1. TÓM TẮT & PHÂN CÔNG CÔNG VIỆC
${m.summary || "_Chưa có nội dung tóm tắt._"}

---

## 2. NỘI DUNG CUỘC HỌP ĐẦY ĐỦ
${m.transcript || "_Chưa có nội dung cuộc họp chi tiết._"}
`;
    const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${title.replace(/[^a-zA-Z0-9_\u00C0-\u024F\u1EA0-\u1EF9]/g, "_")}.md`;
    a.click();
    URL.revokeObjectURL(url);
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
                  onClick={() => handleSelectMeeting(m)}
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
            {activeTab === "live" && <LiveMeetingRoom onMeetingSaved={loadMeetings} />}
            {activeTab === "upload" && <SpeechToTextDemo onMeetingSaved={loadMeetings} />}
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
          <div
            className="db-modal-card db-modal-card--lg"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: 880, maxHeight: "90vh", display: "flex", flexDirection: "column" }}
          >
            <div className="db-modal-header" style={{ marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                <h3 className="db-modal-title" style={{ fontSize: 19 }}>
                  {selectedMeeting.title || `Cuộc họp #${selectedMeeting.id}`}
                </h3>
                <span className="lmr-col-badge" style={{ background: "#dcfce7", color: "#166534" }}>
                  {selectedMeeting.status || "COMPLETED"}
                </span>
              </div>
              <button
                type="button"
                className="db-modal-close"
                onClick={() => setSelectedMeeting(null)}
              >
                ✕
              </button>
            </div>

            {/* Sub-bar thông tin và các nút xuất / xóa */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                background: "#f8fafc",
                padding: "8px 12px",
                borderRadius: 8,
                marginBottom: 14,
                fontSize: 13,
                color: "#64748b",
                flexWrap: "wrap",
                gap: 8,
              }}
            >
              <div style={{ display: "flex", gap: 14, flexWrap: "wrap" }}>
                <span>
                  <strong>Thời gian:</strong>{" "}
                  {selectedMeeting.createdAt
                    ? new Date(selectedMeeting.createdAt).toLocaleString("vi-VN")
                    : "—"}
                </span>
                <span>
                  <strong>Người tạo:</strong> {selectedMeeting.organizerName || user?.fullName || "Bạn"}
                </span>
                <span>
                  <strong>Mã:</strong> #{selectedMeeting.id}
                </span>
              </div>

              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  onClick={() => handleDownloadMeetingMd(selectedMeeting)}
                  style={{
                    padding: "5px 12px",
                    fontSize: 12.5,
                    fontWeight: 600,
                    background: "#ffffff",
                    color: "#3b82f6",
                    border: "1px solid #bfdbfe",
                    borderRadius: 6,
                    cursor: "pointer",
                  }}
                >
                  Tải biên bản (.md)
                </button>
                <button
                  type="button"
                  onClick={() => handleDeleteMeeting(selectedMeeting.id)}
                  style={{
                    padding: "5px 12px",
                    fontSize: 12.5,
                    fontWeight: 600,
                    background: "#ffffff",
                    color: "#ef4444",
                    border: "1px solid #fecaca",
                    borderRadius: 6,
                    cursor: "pointer",
                  }}
                >
                  Xóa
                </button>
              </div>
            </div>

            {/* Nội dung chi tiết: 2 Cột (Tóm tắt & Phiên âm) */}
            <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 14 }}>
              {loadingDetail ? (
                <div style={{ textAlign: "center", padding: 30, color: "#64748b" }}>
                  <div className="mn-spinner" style={{ margin: "0 auto 10px", width: 22, height: 22 }} />
                  Đang tải nội dung tóm tắt cuộc họp...
                </div>
              ) : (
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14, minHeight: 280 }}>
                  {/* Cột Tóm tắt */}
                  <div
                    style={{
                      border: "1px solid #f3e8ff",
                      borderRadius: 10,
                      padding: 14,
                      background: "#faf5ff",
                      display: "flex",
                      flexDirection: "column",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, borderBottom: "1px solid #f3e8ff", paddingBottom: 6 }}>
                      <strong style={{ color: "#7c3aed", fontSize: 14.5 }}>
                        Tóm tắt & Phân công công việc
                      </strong>
                      <span style={{ fontSize: 11, background: "#f3e8ff", color: "#6b21a8", padding: "2px 8px", borderRadius: 4, fontWeight: 600 }}>
                        AI Qwen2.5
                      </span>
                    </div>
                    <div style={{ flex: 1, overflowY: "auto", fontSize: 13, lineHeight: 1.6, color: "#1e293b", whiteSpace: "pre-wrap", maxHeight: 380 }}>
                      {selectedMeeting.summary || (
                        <span style={{ color: "#94a3b8", fontStyle: "italic" }}>
                          Chưa có bản tóm tắt cho cuộc họp này.
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Cột Nội dung chi tiết */}
                  <div
                    style={{
                      border: "1px solid #e2e8f0",
                      borderRadius: 10,
                      padding: 14,
                      background: "#f8fafc",
                      display: "flex",
                      flexDirection: "column",
                    }}
                  >
                    <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, borderBottom: "1px solid #e2e8f0", paddingBottom: 6 }}>
                      <strong style={{ color: "#0f172a", fontSize: 14.5 }}>
                        Nội dung cuộc họp chi tiết (Transcript)
                      </strong>
                      <span style={{ fontSize: 11, background: "#e2e8f0", color: "#475569", padding: "2px 8px", borderRadius: 4, fontWeight: 600 }}>
                        PhoWhisper
                      </span>
                    </div>
                    <div style={{ flex: 1, overflowY: "auto", fontSize: 13, lineHeight: 1.6, color: "#334155", whiteSpace: "pre-wrap", maxHeight: 380 }}>
                      {selectedMeeting.transcript || (
                        <span style={{ color: "#94a3b8", fontStyle: "italic" }}>
                          Chưa có nội dung phiên âm cho cuộc họp này.
                        </span>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div className="db-modal-actions" style={{ marginTop: 14, borderTop: "1px solid #f1f5f9", paddingTop: 12 }}>
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
