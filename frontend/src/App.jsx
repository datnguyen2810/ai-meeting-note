import { useState, useEffect } from "react";
import { api, getStoredUser, getStoredToken } from "./services/api";
import AuthModal from "./components/AuthModal";
import LiveMeetingRoom from "./components/LiveMeetingRoom";
import SpeechToTextDemo from "./components/SpeechToTextDemo";
import "./App.css";

export default function App() {
  const [user, setUser] = useState(getStoredUser());
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [activeTab, setActiveTab] = useState("live"); // 'live' | 'upload' | 'history'

  // Meeting History State
  const [meetings, setMeetings] = useState([]);

  // Sync auth state
  useEffect(() => {
    const handleLogout = () => {
      setUser(null);
    };
    window.addEventListener("auth_logout", handleLogout);
    return () => window.removeEventListener("auth_logout", handleLogout);
  }, []);

  // Fetch meetings when logged in
  const loadMeetings = async () => {
    if (!getStoredToken()) return;
    try {
      const data = await api.getMeetings();
      setMeetings(data || []);
    } catch (err) {
      console.warn("Could not load meetings:", err.message);
    }
  };

  useEffect(() => {
    if (user) {
      loadMeetings();
    }
  }, [user]);

  const handleLogout = () => {
    api.logout();
    setUser(null);
  };

  return (
    <div className="app-container">
      {/* Navbar */}
      <nav className="navbar">
        <div className="nav-brand">
          <div className="brand-icon">🎙️</div>
          <div>
            <div className="brand-title">AI Meeting Note</div>
            <div className="brand-sub">Hệ Thống Tóm Tắt & Ghi Chép Cuộc Họp Thông Minh</div>
          </div>
        </div>

        {/* Tab Switcher */}
        <div className="nav-tabs">
          <button
            className={`nav-tab-btn ${activeTab === "live" ? "active" : ""}`}
            onClick={() => setActiveTab("live")}
          >
            🔴 Cuộc họp trực tiếp (Live ASR)
          </button>
          <button
            className={`nav-tab-btn ${activeTab === "upload" ? "active" : ""}`}
            onClick={() => setActiveTab("upload")}
          >
            📁 Tải file trực tiếp (Offline Batch)
          </button>
          <button
            className={`nav-tab-btn ${activeTab === "history" ? "active" : ""}`}
            onClick={() => {
              setActiveTab("history");
              if (user) loadMeetings();
            }}
          >
            📋 Lịch sử cuộc họp {user ? `(${meetings.length})` : ""}
          </button>
        </div>

        {/* User / Auth Info */}
        <div className="nav-user">
          <div className="status-badge" title="AI Service & Backend Status">
            <span className="status-dot"></span>
            Online
          </div>

          {user ? (
            <>
              <div className="user-profile">
                👤 <span>{user.fullName || user.username}</span>
              </div>
              <button className="logout-btn" onClick={handleLogout} title="Đăng xuất">
                Đăng xuất
              </button>
            </>
          ) : (
            <button
              className="login-nav-btn"
              onClick={() => setShowAuthModal(true)}
              title="Đăng nhập để xem lịch sử cuộc họp"
            >
              🔐 Đăng nhập
            </button>
          )}
        </div>
      </nav>

      {/* Main Content Body */}
      <main className="main-content">
        {/* Tab 1: Cuộc họp trực tiếp (Live ASR Realtime) */}
        {activeTab === "live" && (
          <section>
            <LiveMeetingRoom />
          </section>
        )}

        {/* Tab 2: Tải file trực tiếp (FastAPI Offline STT & LLM) */}
        {activeTab === "upload" && (
          <section>
            <SpeechToTextDemo />
          </section>
        )}

        {/* Tab 3: Lịch sử cuộc họp (Backend History) */}
        {activeTab === "history" && (
          <div className="glass-card">
            {!user ? (
              <div style={{ textAlign: "center", padding: "48px 24px" }}>
                <p style={{ fontSize: 36, margin: 0 }}>🔐</p>
                <h3 style={{ fontSize: 20, margin: "12px 0 6px" }}>Yêu cầu đăng nhập tài khoản</h3>
                <p style={{ color: "var(--text-muted)", maxWidth: 480, margin: "0 auto 20px" }}>
                  Hãy đăng nhập để xem lịch sử danh sách cuộc họp được lưu trên hệ thống Backend.
                </p>
                <button className="btn-primary" style={{ maxWidth: 220 }} onClick={() => setShowAuthModal(true)}>
                  Đăng nhập ngay
                </button>
              </div>
            ) : (
              <div>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
                  <div>
                    <h3 className="card-title" style={{ margin: 0 }}>📋 Danh sách cuộc họp của bạn</h3>
                    <p className="card-desc" style={{ margin: 0, marginTop: 4 }}>
                      Dữ liệu được lưu trữ trực tiếp trên Spring Boot Backend.
                    </p>
                  </div>
                  <button className="btn-secondary" onClick={loadMeetings}>
                    🔄 Làm mới
                  </button>
                </div>

                {meetings.length === 0 ? (
                  <div style={{ textAlign: "center", padding: "48px 0", color: "var(--text-muted)" }}>
                    <p style={{ fontSize: 32, margin: 0 }}>📂</p>
                    <p style={{ fontSize: 16, fontWeight: 600 }}>Chưa có cuộc họp nào được lưu</p>
                    <p style={{ fontSize: 14 }}>Các phiên họp từ hệ thống sẽ xuất hiện tại đây.</p>
                  </div>
                ) : (
                  <div className="meetings-table-container">
                    <table className="meetings-table">
                      <thead>
                        <tr>
                          <th>ID</th>
                          <th>Tiêu đề cuộc họp</th>
                          <th>Mô tả</th>
                          <th>Người tạo</th>
                          <th>Số file ghi âm</th>
                          <th>Thời gian tạo</th>
                          <th>Trạng thái</th>
                        </tr>
                      </thead>
                      <tbody>
                        {meetings.map((m) => (
                          <tr key={m.id}>
                            <td><strong>#{m.id}</strong></td>
                            <td style={{ fontWeight: 600 }}>{m.title}</td>
                            <td style={{ color: "var(--text-muted)" }}>{m.description || "—"}</td>
                            <td>{m.organizerName || "Bạn"}</td>
                            <td>{m.audioCount || 0} file</td>
                            <td>
                              {m.createdAt ? new Date(m.createdAt).toLocaleString("vi-VN") : "—"}
                            </td>
                            <td>
                              <span className={`status-chip ${m.status || "SCHEDULED"}`}>
                                {m.status || "SCHEDULED"}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>

      {/* Auth Modal Overlay */}
      {showAuthModal && (
        <AuthModal
          onLoginSuccess={(userData) => {
            setUser(userData);
            setShowAuthModal(false);
          }}
          onClose={() => setShowAuthModal(false)}
        />
      )}
    </div>
  );
}
