import { useState, useRef, useEffect } from "react";
import { useLiveTranscription } from "../hooks/useLiveTranscription";
import { api } from "../services/api";
import "./LiveMeetingRoom.css";

export default function LiveMeetingRoom({ onMeetingSaved }) {
  const {
    status,
    isRecording,
    captions,
    duration,
    audioLevel,
    lagWarning,
    errorMsg,
    startRecording,
    stopRecording,
  } = useLiveTranscription();

  const [isBatchLoading, setIsBatchLoading] = useState(false);
  const [batchTranscript, setBatchTranscript] = useState("");
  const [batchSummary, setBatchSummary] = useState("");
  const [batchError, setBatchError] = useState("");
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);
  const [saveStatus, setSaveStatus] = useState(""); // "", "saving", "saved", "error"
  const [savedMeetingInfo, setSavedMeetingInfo] = useState(null);

  const scrollRef = useRef(null);

  // Định dạng thời gian mm:ss
  const formatTime = (secs) => {
    const m = Math.floor(secs / 60)
      .toString()
      .padStart(2, "0");
    const s = (secs % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  };

  // Tự động cuộn xuống cuối khi có caption mới (chỉ cuộn nếu user không cuộn ngược lên)
  useEffect(() => {
    if (!isUserScrolledUp && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [captions, isUserScrolledUp]);

  // Bắt sự kiện cuộn của user
  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    // Nếu khoảng cách tới đáy > 40px thì coi là user đang xem lại phía trên
    const isUp = scrollHeight - scrollTop - clientHeight > 40;
    setIsUserScrolledUp(isUp);
  };

  // Bắt đầu họp
  const handleStart = async () => {
    setBatchTranscript("");
    setBatchSummary("");
    setBatchError("");
    setSaveStatus("");
    setSavedMeetingInfo(null);
    await startRecording();
  };

  // Kết thúc họp và kích hoạt Engine 2 (Batch PhoWhisper) + Engine 3 (Qwen Summary)
  const handleStop = async () => {
    const result = await stopRecording();
    if (!result?.wavBlob) return;

    setIsBatchLoading(true);
    setBatchError("");

    try {
      const formData = new FormData();
      formData.append("file", result.wavBlob, `meeting_${Date.now()}.wav`);

      const res = await fetch("http://localhost:8000/api/transcribe", {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        let errText = `Server trả về mã lỗi: ${res.status}`;
        try {
          const errData = await res.json();
          if (errData.detail) errText = errData.detail;
        } catch (_) {}
        throw new Error(errText);
      }

      const data = await res.json();
      const finalTranscript = data.transcript || "";
      const finalSummary = data.summary || "";
      setBatchTranscript(finalTranscript);
      setBatchSummary(finalSummary);

      // Tự động lưu cuộc họp và tóm tắt vào database qua Spring Boot backend
      try {
        setSaveStatus("saving");
        const meetingTitle = `Cuộc họp trực tiếp - ${new Date().toLocaleString("vi-VN", {
          hour: "2-digit",
          minute: "2-digit",
          day: "2-digit",
          month: "2-digit",
          year: "numeric",
        })}`;

        const audioFile = new File([result.wavBlob], `meeting_${Date.now()}.wav`, {
          type: "audio/wav",
        });

        const saved = await api.saveMeetingSession({
          title: meetingTitle,
          transcript: finalTranscript,
          summary: finalSummary,
          durationSeconds: duration,
          file: audioFile,
        });

        setSaveStatus("saved");
        setSavedMeetingInfo(saved);
        if (typeof onMeetingSaved === "function") {
          onMeetingSaved();
        }
      } catch (saveErr) {
        console.error("[Save Session Error]:", saveErr);
        setSaveStatus("error");
      }
    } catch (err) {
      console.error("[Batch Error]:", err);
      setBatchError(err.message || "Gặp lỗi trong quá trình tổng hợp và tóm tắt cuộc họp.");
    } finally {
      setIsBatchLoading(false);
    }
  };

  const handleManualSave = async () => {
    if (!batchTranscript && !batchSummary) return;
    try {
      setSaveStatus("saving");
      const meetingTitle = `Cuộc họp trực tiếp - ${new Date().toLocaleString("vi-VN", {
        hour: "2-digit",
        minute: "2-digit",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
      })}`;

      const saved = await api.saveMeetingSession({
        title: meetingTitle,
        transcript: batchTranscript,
        summary: batchSummary,
        durationSeconds: duration,
      });

      setSaveStatus("saved");
      setSavedMeetingInfo(saved);
      if (typeof onMeetingSaved === "function") {
        onMeetingSaved();
      }
    } catch (saveErr) {
      console.error("[Manual Save Error]:", saveErr);
      setSaveStatus("error");
    }
  };

  // Xuất file Markdown tổng hợp kết quả (chống mất dữ liệu khi F5)
  const handleExportMarkdown = () => {
    const now = new Date().toLocaleString("vi-VN");
    let liveLogText = "";
    captions
      .filter((c) => c.isFinal)
      .forEach((c) => {
        const timeStr =
          c.tStart !== undefined ? `[${c.tStart}s - ${c.tEnd}s] ` : "";
        liveLogText += `- ${timeStr}${c.text}\n`;
      });

    const mdContent = `# BIÊN BẢN TỔNG KẾT CUỘC HỌP
*Thời gian lập:* ${now}
*Thời lượng họp:* ${formatTime(duration)}

---

## 1. TÓM TẮT & PHÂN CÔNG CÔNG VIỆC (Qwen2.5-1.5B)
${batchSummary || "_Chưa có bản tóm tắt._"}

---

## 2. NỘI DUNG CUỘC HỌP ĐẦY ĐỦ (PhoWhisper-small)
${batchTranscript || "_Chưa có nội dung cuộc họp chi tiết._"}

---

## 3. NHẬT KÝ PHIÊN ÂM TRỰC TIẾP (Wav2Vec2 Realtime)
${liveLogText || "_Không có nhật ký phát ngôn._"}
`;

    const blob = new Blob([mdContent], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `Bien_ban_cuoc_hop_${Date.now()}.md`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Chuẩn bị các thanh Visualizer
  const visualizerBars = Array.from({ length: 16 }).map((_, i) => {
    const factor = Math.sin((i / 15) * Math.PI);
    const height = Math.max(4, Math.round(audioLevel * 0.32 * factor + 4));
    return height;
  });

  return (
    <div className="lmr-container">
      {/* ── Status Bar ──────────────────────────────────────── */}
      <div className="lmr-status-bar">
        <div className="lmr-status-indicator">
          <span
            className={`lmr-dot ${
              isRecording
                ? "lmr-dot--recording"
                : status === "connecting"
                ? "lmr-dot--connecting"
                : ""
            }`}
          />
          <span style={{ fontWeight: 500 }}>
            {status === "recording" && "Đang trong cuộc họp"}
            {status === "connecting" && "Đang kết nối..."}
            {status === "stopping" && "Đang kết thúc phiên họp..."}
            {status === "idle" && "Sẵn sàng bắt đầu"}
            {status === "error" && "Gặp sự cố kết nối"}
          </span>
          {lagWarning && (
            <span className="lmr-badge lmr-badge--active">
              Server đang xử lý chậm
            </span>
          )}
        </div>

        <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
          {isRecording && (
            <div className="lmr-visualizer">
              {visualizerBars.map((h, i) => (
                <div key={i} className="lmr-bar" style={{ height: `${h}px` }} />
              ))}
            </div>
          )}
          <div className="lmr-timer">{formatTime(duration)}</div>
        </div>
      </div>

      {/* Thông báo lỗi nếu có */}
      {(errorMsg || batchError) && (
        <div className="mn-error">
          {errorMsg || batchError}
        </div>
      )}

      {/* ── Khung Live Captions (Realtime Streaming) ─────────── */}
      <div className="lmr-caption-box">
        <div className="lmr-caption-header">
          <span>Phụ đề trực tiếp</span>
          <span>
            {captions.filter((c) => c.isFinal).length} cụm từ đã nhận diện
          </span>
        </div>

        <div
          ref={scrollRef}
          className="lmr-caption-scroll"
          onScroll={handleScroll}
        >
          {captions.length === 0 ? (
            <div className="lmr-caption-empty">
              <span>Nhấn &quot;Bắt đầu cuộc họp&quot; và nói vào micro để thấy phụ đề.</span>
              <span style={{ fontSize: 12, opacity: 0.8 }}>
                (Nội dung phát biểu sẽ hiển thị theo thời gian thực)
              </span>
            </div>
          ) : (
            captions.map((item) => (
              <div
                key={item.seq}
                className={`lmr-caption-item ${
                  item.isFinal
                    ? "lmr-caption-item--final"
                    : "lmr-caption-item--interim"
                }`}
              >
                <div className="lmr-caption-meta">
                  {item.isFinal ? (
                    <>
                      <span>Chính thức</span>
                      {item.tStart !== undefined && (
                        <span>
                          [{item.tStart}s - {item.tEnd}s]
                        </span>
                      )}
                      {item.inferMs !== undefined && (
                        <span>({item.inferMs}ms)</span>
                      )}
                    </>
                  ) : (
                    <>
                      <span>Đang nói...</span>
                      {item.inferMs !== undefined && (
                        <span>({item.inferMs}ms)</span>
                      )}
                    </>
                  )}
                </div>
                <div className="lmr-caption-text">{item.text}</div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* ── Controls ────────────────────────────────────────── */}
      <div className="lmr-controls">
        {!isRecording ? (
          <button
            className="lmr-btn lmr-btn--start"
            onClick={handleStart}
            disabled={status === "connecting" || status === "stopping" || isBatchLoading}
          >
            Bắt đầu cuộc họp
          </button>
        ) : (
          <button className="lmr-btn lmr-btn--stop" onClick={handleStop}>
            Kết thúc cuộc họp
          </button>
        )}

        {(batchTranscript || batchSummary || captions.length > 0) && (
          <button
            className="lmr-btn lmr-btn--secondary"
            onClick={handleExportMarkdown}
            title="Lưu biên bản dạng Markdown"
          >
            Tải biên bản (.md)
          </button>
        )}
      </div>

      {/* ── Loading ─────────────────────────────────────────── */}
      {isBatchLoading && (
        <div className="lmr-batch-loading">
          <div className="mn-spinner" style={{ width: 24, height: 24, borderWidth: 3 }} />
          <div>
            <p style={{ fontWeight: 600, color: "var(--text-h)" }}>
              Đang tổng hợp và tóm tắt cuộc họp...
            </p>
            <p style={{ fontSize: 13, color: "var(--text)", marginTop: 4 }}>
              Vui lòng không tắt hoặc tải lại trang trong giây lát.
            </p>
          </div>
        </div>
      )}

      {/* ── View Đối Chiếu 3 Cột ────────────────────────────── */}
      {(batchTranscript || batchSummary) && (
        <div className="lmr-results-panel">
          <div className="lmr-export-actions">
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <strong>Kết quả đối chiếu cuộc họp</strong>
              {saveStatus === "saving" && (
                <span className="lmr-col-badge" style={{ background: "#e0f2fe", color: "#0284c7" }}>
                  Đang lưu vào lịch sử...
                </span>
              )}
              {saveStatus === "saved" && (
                <span className="lmr-col-badge" style={{ background: "#dcfce7", color: "#166534" }}>
                  ✓ Đã lưu vào lịch sử cuộc họp{savedMeetingInfo?.id ? ` (#${savedMeetingInfo.id})` : ""}
                </span>
              )}
              {saveStatus === "error" && (
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <span className="lmr-col-badge" style={{ background: "#fee2e2", color: "#b91c1c" }}>
                    Chưa lưu vào DB
                  </span>
                  <button
                    type="button"
                    className="lmr-btn lmr-btn--secondary"
                    style={{ padding: "3px 10px", fontSize: 12, height: "auto" }}
                    onClick={handleManualSave}
                  >
                    Thử lưu lại
                  </button>
                </div>
              )}
            </div>
            <button
              className="lmr-btn lmr-btn--secondary"
              onClick={handleExportMarkdown}
            >
              Xuất file .md
            </button>
          </div>

          <div className="lmr-columns-grid">
            {/* Cột 1: Live Log */}
            <div className="lmr-column-card">
              <div className="lmr-col-header">
                <h3>1. Bản ghi trực tiếp</h3>
                <span className="lmr-col-badge">
                  Thời gian thực
                </span>
              </div>
              <div className="lmr-col-body">
                {captions.filter((c) => c.isFinal).length === 0 ? (
                  <span style={{ color: "#94a3b8", fontStyle: "italic" }}>
                    Không có bản ghi trực tiếp.
                  </span>
                ) : (
                  captions
                    .filter((c) => c.isFinal)
                    .map((c) => (
                      <div key={c.seq} style={{ marginBottom: 8 }}>
                        <span style={{ fontSize: 11, color: "#94a3b8" }}>
                          [{c.tStart}s - {c.tEnd}s]{" "}
                        </span>
                        <span>{c.text}</span>
                      </div>
                    ))
                )}
              </div>
            </div>

            {/* Cột 2: Full transcript */}
            <div className="lmr-column-card">
              <div className="lmr-col-header">
                <h3>2. Nội dung cuộc họp chi tiết</h3>
                <span className="lmr-col-badge">
                  Đầy đủ & chuẩn hóa
                </span>
              </div>
              <div className="lmr-col-body">
                {batchTranscript || "Chưa có nội dung."}
              </div>
            </div>

            {/* Cột 3: Summary */}
            <div className="lmr-column-card lmr-col-summary">
              <div className="lmr-col-header">
                <h3 style={{ color: "var(--accent, #3b82f6)" }}>
                  3. Tóm tắt & Phân công
                </h3>
                <span className="lmr-col-badge">
                  Biên bản tóm tắt
                </span>
              </div>
              <div className="lmr-col-body">
                {batchSummary || "Chưa có nội dung tóm tắt."}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
