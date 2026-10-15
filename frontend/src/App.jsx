import { useState, useEffect, useRef } from "react";
import { api, getStoredUser, getStoredToken } from "./services/api";
import AuthModal from "./components/AuthModal";
import LiveMeetingRoom from "./components/LiveMeetingRoom";
import SpeechToTextDemo from "./components/SpeechToTextDemo";
import "./App.css";

export default function App() {
  const [user, setUser] = useState(getStoredUser());
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [activeTab, setActiveTab] = useState("live"); // 'live' | 'backend-transcribe' | 'history' | 'fastapi-demo'

  // Meeting & Upload State (for Backend tab)
  const [meetings, setMeetings] = useState([]);
  const [selectedMeetingId, setSelectedMeetingId] = useState("new");
  const [newTitle, setNewTitle] = useState("Cuộc họp thảo luận đồ án");
  const [newDesc, setNewDesc] = useState("Bàn về kiến trúc AI và Backend Spring Boot");
  const [audioFile, setAudioFile] = useState(null);

  // Processing State
  const [isProcessing, setIsProcessing] = useState(false);
  const [stepMsg, setStepMsg] = useState("");
  const [errorMsg, setErrorMsg] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  // AI Output Results
  const [transcript, setTranscript] = useState("");
  const [summary, setSummary] = useState("");

  const fileInputRef = useRef(null);

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

  const handleFileChange = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setAudioFile(file);
      setErrorMsg("");
      setSuccessMsg("");
    }
  };

  const handleStartProcess = async () => {
    if (!audioFile) {
      setErrorMsg("Vui lòng chọn hoặc kéo thả một file âm thanh (.wav, .mp3, .m4a).");
      return;
    }

    setIsProcessing(true);
    setErrorMsg("");
    setSuccessMsg("");
    setTranscript("");
    setSummary("");

    try {
      let meetingId = selectedMeetingId;

      // 1. Tạo meeting nếu chọn tạo mới
      if (meetingId === "new") {
        setStepMsg("1/4: Đang tạo cuộc họp mới trên Backend Spring Boot...");
        const created = await api.createMeeting(
          newTitle || "Cuộc họp mới",
          newDesc || "Tạo từ giao diện web"
        );
        meetingId = created.id;
        loadMeetings();
      }

      // 2. Upload file audio lên backend
      setStepMsg(`2/4: Đang tải file "${audioFile.name}" lên Backend...`);
      const audioRes = await api.uploadAudio(meetingId, audioFile);
      const audioId = audioRes.id;

      // 3. Gọi Speech-To-Text (PhoWhisper)
      setStepMsg("3/4: Đang nhận diện giọng nói tiếng Việt (AI STT PhoWhisper)...");
      let transcriptText = "";
      let transcriptId = null;
      try {
        const transcriptRes = await api.transcribeAudio(audioId);
        transcriptText = transcriptRes.fullText || transcriptRes.text || "";
        transcriptId = transcriptRes.id;
        setTranscript(transcriptText);
      } catch (sttErr) {
        throw new Error(
          `Lỗi STT: ${sttErr.message}. (Lưu ý: Hãy chắc chắn server Python FastAPI đang chạy ở cổng 8000).`
        );
      }

      // 4. Gọi LLM Tóm tắt nội dung
      if (transcriptId) {
        setStepMsg("4/4: Đang tóm tắt cuộc họp và trích xuất hành động (LLM)...");
        try {
          const noteRes = await api.generateNote(transcriptId);
          setSummary(noteRes.summary || noteRes.content || "Đã tạo biên bản cuộc họp.");
        } catch (llmErr) {
          console.warn("LLM summary error:", llmErr.message);
          setSummary("Đã có bản phiên âm thành công. (Mô hình tóm tắt cần server AI chạy trên cổng 8000).");
        }
      }

      setSuccessMsg("Xử lý thành công! Bản phiên âm và tóm tắt cuộc họp đã được lưu.");
      loadMeetings();
    } catch (err) {
      setErrorMsg(err.message || "Đã xảy ra lỗi trong quá trình xử lý.");
    } finally {
      setIsProcessing(false);
      setStepMsg("");
    }
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
            className={`nav-tab-btn ${activeTab === "backend-transcribe" ? "active" : ""}`}
            onClick={() => setActiveTab("backend-transcribe")}
          >
            ⚡ Ghi âm & Tóm tắt AI (Backend)
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
          <button
            className={`nav-tab-btn ${activeTab === "fastapi-demo" ? "active" : ""}`}
            onClick={() => setActiveTab("fastapi-demo")}
          >
            🧪 Tải file trực tiếp (FastAPI Demo)
          </button>
        </div>

        {/* User / Auth Info */}
        <div className="nav-user">
          <div className="status-badge" title="Backend Spring Boot & AI Service Status">
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
              title="Đăng nhập để lưu cuộc họp"
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

        {/* Tab 2: Ghi âm & Tóm tắt AI (Backend Spring Boot pipeline) */}
        {activeTab === "backend-transcribe" && (
          <div>
            {!user ? (
              <div className="glass-card" style={{ textAlign: "center", padding: "48px 24px" }}>
                <p style={{ fontSize: 36, margin: 0 }}>🔐</p>
                <h3 style={{ fontSize: 20, margin: "12px 0 6px" }}>Yêu cầu đăng nhập tài khoản</h3>
                <p style={{ color: "var(--text-muted)", maxWidth: 480, margin: "0 auto 20px" }}>
                  Tính năng ghi âm liên kết với Backend Spring Boot yêu cầu bạn đăng nhập để lưu trữ thông tin cuộc họp, file âm thanh và tóm tắt vào cơ sở dữ liệu.
                </p>
                <button className="btn-primary" style={{ maxWidth: 220 }} onClick={() => setShowAuthModal(true)}>
                  Đăng nhập ngay
                </button>
              </div>
            ) : (
              <div>
                {/* Step 1: Chọn / Tạo cuộc họp */}
                <div className="glass-card">
                  <h3 className="card-title">1. Thiết lập cuộc họp</h3>
                  <p className="card-desc">
                    Liên kết bản ghi âm này với một cuộc họp trên hệ thống Backend.
                  </p>

                  <div className="form-grid">
                    <div className="form-group">
                      <label className="form-label">Chọn cuộc họp</label>
                      <select
                        className="form-select"
                        value={selectedMeetingId}
                        onChange={(e) => setSelectedMeetingId(e.target.value)}
                        disabled={isProcessing}
                      >
                        <option value="new">+ Tạo cuộc họp mới ngay bây giờ</option>
                        {meetings.map((m) => (
                          <option key={m.id} value={m.id}>
                            [#{m.id}] {m.title} ({new Date(m.createdAt).toLocaleDateString("vi-VN")})
                          </option>
                        ))}
                      </select>
                    </div>

                    {selectedMeetingId === "new" && (
                      <div className="form-group">
                        <label className="form-label">Tiêu đề cuộc họp</label>
                        <input
                          type="text"
                          className="form-input"
                          placeholder="VD: Họp định kỳ tuần 4"
                          value={newTitle}
                          onChange={(e) => setNewTitle(e.target.value)}
                          disabled={isProcessing}
                        />
                      </div>
                    )}
                  </div>

                  {selectedMeetingId === "new" && (
                    <div className="form-group">
                      <label className="form-label">Mô tả ngắn cuộc họp</label>
                      <input
                        type="text"
                        className="form-input"
                        placeholder="VD: Bàn về tiến độ đồ án và phân công nhiệm vụ"
                        value={newDesc}
                        onChange={(e) => setNewDesc(e.target.value)}
                        disabled={isProcessing}
                      />
                    </div>
                  )}
                </div>

                {/* Step 2: Tải lên file âm thanh */}
                <div className="glass-card">
                  <h3 className="card-title">2. Tải lên file ghi âm cuộc họp</h3>
                  <p className="card-desc">
                    Hỗ trợ định dạng .wav, .mp3, .m4a. Tối đa 100MB mỗi file.
                  </p>

                  <div
                    className={`upload-dropzone ${audioFile ? "has-file" : ""}`}
                    onClick={() => fileInputRef.current?.click()}
                  >
                    <input
                      ref={fileInputRef}
                      type="file"
                      accept=".wav,.mp3,.m4a,audio/*"
                      onChange={handleFileChange}
                      style={{ display: "none" }}
                      disabled={isProcessing}
                    />
                    <div className="dropzone-icon">
                      {audioFile ? "🎵" : "☁️"}
                    </div>
                    <div className="dropzone-text">
                      {audioFile ? audioFile.name : "Nhấn để chọn file hoặc kéo thả file âm thanh vào đây"}
                    </div>
                    <div className="dropzone-hint">
                      {audioFile
                        ? `Kích thước: ${(audioFile.size / (1024 * 1024)).toFixed(2)} MB — Nhấn để đổi file khác`
                        : "Hỗ trợ WAV, MP3, M4A"}
                    </div>
                  </div>

                  <div style={{ marginTop: 20 }}>
                    <button
                      className="btn-primary"
                      onClick={handleStartProcess}
                      disabled={isProcessing || !audioFile}
                    >
                      {isProcessing ? (
                        <>
                          <span className="spinner"></span> {stepMsg || "Đang xử lý..."}
                        </>
                      ) : (
                        "🚀 Bắt đầu Tải lên & Nhận diện AI"
                      )}
                    </button>
                  </div>

                  {/* Status messages */}
                  {errorMsg && (
                    <div className="alert-box error" style={{ marginTop: 16 }}>
                      ⚠️ {errorMsg}
                    </div>
                  )}
                  {successMsg && (
                    <div className="alert-box success" style={{ marginTop: 16 }}>
                      ✅ {successMsg}
                    </div>
                  )}
                </div>

                {/* Step 3: Kết quả phiên âm & tóm tắt */}
                {(transcript || summary || isProcessing) && (
                  <div className="results-grid">
                    <div className="result-box">
                      <div className="result-box-header">
                        <span className="result-box-title">📝 Bản phiên âm (Speech-to-Text)</span>
                        {transcript && (
                          <button
                            className="btn-secondary"
                            onClick={() => navigator.clipboard.writeText(transcript)}
                          >
                            Sao chép
                          </button>
                        )}
                      </div>
                      <div className="result-box-content">
                        {transcript ? (
                          transcript
                        ) : (
                          <span style={{ color: "var(--text-dim)" }}>
                            {isProcessing ? "Đang xử lý nhận dạng âm thanh qua PhoWhisper..." : "Chưa có nội dung phiên âm."}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="result-box result-box--summary">
                      <div className="result-box-header">
                        <span className="result-box-title">🤖 Tóm tắt & Ghi chú cuộc họp (AI Note)</span>
                        {summary && (
                          <button
                            className="btn-secondary"
                            onClick={() => navigator.clipboard.writeText(summary)}
                          >
                            Sao chép
                          </button>
                        )}
                      </div>
                      <div className="result-box-content">
                        {summary ? (
                          summary
                        ) : (
                          <span style={{ color: "var(--text-dim)" }}>
                            {isProcessing ? "Đang tổng hợp nội dung bằng mô hình ngôn ngữ lớn..." : "Chưa có bản tóm tắt."}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
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
                    <p style={{ fontSize: 14 }}>Hãy chuyển sang tab "Ghi âm & Tóm tắt AI" để tạo cuộc họp đầu tiên!</p>
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

        {/* Tab 4: Tải file trực tiếp (FastAPI Demo không cần backend Spring Boot) */}
        {activeTab === "fastapi-demo" && (
          <section>
            <SpeechToTextDemo />
          </section>
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
