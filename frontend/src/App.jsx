import { useState } from "react";
import SpeechToTextDemo from "./components/SpeechToTextDemo";
import LiveMeetingRoom from "./components/LiveMeetingRoom";
import "./App.css";

function App() {
  const [activeTab, setActiveTab] = useState("live"); // "live" | "upload"

  return (
    <div className="app-container">
      {/* Navbar / Header Navigation */}
      <header className="app-nav">
        <div className="app-brand">
          <span className="app-logo">🎙️</span>
          <div>
            <h1 className="app-brand-title">AI Meeting Note</h1>
            <span className="app-brand-sub">Hệ thống ghi chép & Tóm tắt cuộc họp thông minh</span>
          </div>
        </div>

        <nav className="app-tabs">
          <button
            className={`app-tab-btn ${activeTab === "live" ? "app-tab-btn--active" : ""}`}
            onClick={() => setActiveTab("live")}
          >
            🔴 Cuộc họp trực tiếp (Live ASR)
          </button>
          <button
            className={`app-tab-btn ${activeTab === "upload" ? "app-tab-btn--active" : ""}`}
            onClick={() => setActiveTab("upload")}
          >
            📁 Tải file âm thanh (Offline Batch)
          </button>
        </nav>
      </header>

      {/* Main Content Area */}
      <main className="app-main">
        {activeTab === "live" ? (
          <section className="app-section">
            <LiveMeetingRoom />
          </section>
        ) : (
          <section className="app-section">
            <SpeechToTextDemo />
          </section>
        )}
      </main>
    </div>
  );
}

export default App;
