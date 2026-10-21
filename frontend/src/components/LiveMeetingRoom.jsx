import { useState, useRef, useEffect } from "react";
import { useLiveTranscription } from "../hooks/useLiveTranscription";
import { useWebSpeechTranscription } from "../hooks/useWebSpeechTranscription";
import SummaryContent from "./SummaryContent";
import "./LiveMeetingRoom.css";

export default function LiveMeetingRoom() {
  // Quản lý chế độ động cơ: 'server' (Wav2Vec2 + PhoWhisper) | 'webspeech' (Web Speech API)
  const [engineMode, setEngineMode] = useState(() => {
    return localStorage.getItem("preferred_engine_mode") || "server";
  });

  const handleSwitchEngine = (mode) => {
    setEngineMode(mode);
    localStorage.setItem("preferred_engine_mode", mode);
  };

  // Khởi tạo cả hai engine
  const serverTrans = useLiveTranscription();
  const webSpeechTrans = useWebSpeechTranscription();

  // Engine hiện đang được chọn
  const activeTrans = engineMode === "server" ? serverTrans : webSpeechTrans;
  const isAnyRecording = serverTrans.isRecording || webSpeechTrans.isRecording;

  const {
    status,
    isRecording,
    captions,
    duration,
    audioLevel,
    errorMsg,
  } = activeTrans;

  const lagWarning = engineMode === "server" ? serverTrans.lagWarning : false;

  const [isBatchLoading, setIsBatchLoading] = useState(false);
  const [batchTranscript, setBatchTranscript] = useState("");
  const [batchSummary, setBatchSummary] = useState("");
  const [batchError, setBatchError] = useState("");
  const [audioDownload, setAudioDownload] = useState(null);
  const [isUserScrolledUp, setIsUserScrolledUp] = useState(false);

  const scrollRef = useRef(null);

  useEffect(() => () => {
    if (audioDownload) URL.revokeObjectURL(audioDownload.url);
  }, [audioDownload]);

  // Định dạng thời gian mm:ss
  const formatTime = (secs) => {
    const m = Math.floor(secs / 60)
      .toString()
      .padStart(2, "0");
    const s = (secs % 60).toString().padStart(2, "0");
    return `${m}:${s}`;
  };

  // Tự động cuộn xuống cuối khi có caption mới
  useEffect(() => {
    if (!isUserScrolledUp && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [captions, isUserScrolledUp]);

  // Bắt sự kiện cuộn của user
  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    const isUp = scrollHeight - scrollTop - clientHeight > 40;
    setIsUserScrolledUp(isUp);
  };

  // Bắt đầu họp
  const handleStart = async () => {
    setBatchTranscript("");
    setBatchSummary("");
    setBatchError("");
    setAudioDownload(null);
    await activeTrans.startRecording();
  };

  // Kết thúc họp và kích hoạt xử lý gỡ băng + tóm tắt
  const handleStop = async () => {
    const result = await activeTrans.stopRecording();

    if (engineMode === "server") {
      // ── LUỒNG 1: Server AI (Wav2Vec2 realtime -> PhoWhisper batch + Qwen summary) ──
      if (!result?.wavBlob) return;
      setAudioDownload({
        url: URL.createObjectURL(result.wavBlob),
        filename: `meeting_${Date.now()}.wav`,
      });

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
          } catch { }
          throw new Error(errText);
        }

        const data = await res.json();
        setBatchTranscript(data.transcript || "");
        setBatchSummary(data.summary || "");
      } catch (err) {
        console.error("[Batch Error]:", err);
        setBatchError(err.message || "Gặp lỗi trong quá trình gỡ băng chính thức.");
      } finally {
        setIsBatchLoading(false);
      }
    } else {
      // ── LUỒNG 2: Web Speech API (nhận diện tại trình duyệt -> Qwen summary trực tiếp) ──
      if (result?.audioBlob) {
        const ext = result.audioBlob.type?.includes("wav") ? "wav" : "webm";
        setAudioDownload({
          url: URL.createObjectURL(result.audioBlob),
          filename: `meeting_webspeech_${Date.now()}.${ext}`,
        });
      }

      const fullText = result?.fullTranscript || "";
      setBatchTranscript(fullText);

      if (!fullText.trim()) {
        setBatchError("Không nhận diện được đoạn phát biểu nào để tóm tắt.");
        return;
      }

      setIsBatchLoading(true);
      setBatchError("");

      try {
        const res = await fetch("http://localhost:8000/api/summarize", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ transcript: fullText }),
        });

        if (!res.ok) {
          let errText = `Server trả về mã lỗi: ${res.status}`;
          try {
            const errData = await res.json();
            if (errData.detail) errText = errData.detail;
          } catch { }
          throw new Error(errText);
        }

        const data = await res.json();
        if (data?.status === "success") {
          setBatchSummary(data.summary || "");
        } else {
          throw new Error("Dữ liệu tóm tắt trả về không hợp lệ.");
        }
      } catch (err) {
        console.error("[WebSpeech Summarize Error]:", err);
        setBatchError(err.message || "Lỗi khi gọi AI tóm tắt (Qwen2.5).");
      } finally {
        setIsBatchLoading(false);
      }
    }
  };

  // Xuất file Markdown tổng hợp kết quả
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

    const engineName =
      engineMode === "server"
        ? "Mô hình AI Server (Wav2Vec2 + PhoWhisper)"
        : "Web Speech API (Chrome / Edge Engine)";

    const mdContent = `# BIÊN BẢN TỔNG KẾT CUỘC HỌP
*Thời gian lập:* ${now}
*Thời lượng họp:* ${formatTime(duration)}
*Động cơ nhận diện:* ${engineName}

---

## 1. TÓM TẮT & PHÂN CÔNG CÔNG VIỆC (Qwen2.5-1.5B)
${batchSummary || "_Chưa có bản tóm tắt._"}

---

## 2. BẢN GỠ BĂNG ĐẦY ĐỦ (${engineMode === "server" ? "PhoWhisper-small" : "Web Speech API"})
${batchTranscript || "_Chưa có bản gỡ băng đầy đủ._"}

---

## 3. NHẬT KÝ PHIÊN ÂM TRỰC TIẾP (${engineMode === "server" ? "Wav2Vec2 Realtime" : "Web Speech API Realtime"})
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
      {/* ── 0. CÔNG TẮC CHUYỂN ĐỔI ENGINE (AI Model vs Web Speech API) ── */}
      <div className="lmr-engine-switcher">
        <div className="lmr-engine-meta">
          <span className="lmr-engine-title">Mô hình STT:</span>
          <div className="lmr-engine-desc">
            {engineMode === "server" ? (
              <>

                <span>Wav2Vec2 (Realtime) + PhoWhisper (Batch)</span>
              </>
            ) : (
              <>

                <span>Web Speech API (Chrome/Edge Engine)</span>
              </>
            )}
          </div>
        </div>

        <div className="lmr-engine-tabs">
          <button
            type="button"
            className={`lmr-engine-tab ${engineMode === "server" ? "active" : ""}`}
            onClick={() => handleSwitchEngine("server")}
            disabled={isAnyRecording || isBatchLoading}
            title={isAnyRecording ? "Vui lòng dừng cuộc họp trước khi đổi mô hình" : "Chuyển sang mô hình AI máy chủ"}
          >

            <span>AI Model</span>
          </button>
          <button
            type="button"
            className={`lmr-engine-tab ${engineMode === "webspeech" ? "active" : ""}`}
            onClick={() => handleSwitchEngine("webspeech")}
            disabled={isAnyRecording || isBatchLoading}
            title={isAnyRecording ? "Vui lòng dừng cuộc họp trước khi đổi mô hình" : "Chuyển sang Web Speech API của trình duyệt"}
          >

            <span>Web Speech API</span>
          </button>
        </div>
      </div>

      {/* ── 1. Status Bar ──────────────────────────────────────── */}
      <div className="lmr-status-bar">
        <div className="lmr-status-indicator">
          <span
            className={`lmr-dot ${isRecording
              ? "lmr-dot--recording"
              : status === "connecting"
                ? "lmr-dot--connecting"
                : ""
              }`}
          />
          <span style={{ fontWeight: 500 }}>
            {status === "recording" && (
              engineMode === "server" ? "Đang trong cuộc họp (AI Server)" : "Đang trong cuộc họp (Web Speech)"
            )}
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

      {/* ── 2. Khung Live Captions (Realtime Streaming) ─────────── */}
      <div className="lmr-caption-box">
        <div className="lmr-caption-header">
          <span>
            Phụ đề trực tiếp ({engineMode === "server" ? "Wav2Vec2" : "Web Speech"})
          </span>
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
                {engineMode === "server"
                  ? "(Đang dùng mô hình AI: Wav2Vec2 chạy trực tiếp qua WebSocket)"
                  : "(Đang dùng Web Speech API: Chữ sẽ xuất hiện ngay lập tức khi bạn nói)"}
              </span>
            </div>
          ) : (
            captions.map((item) => (
              <div
                key={item.seq}
                className={`lmr-caption-item ${item.isFinal
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

      {/* ── 3. Controls ────────────────────────────────────────── */}
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
            Kết thúc họp & Gỡ băng
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

      {/* ── 4. Loading ─────────────────────────────────────────── */}
      {isBatchLoading && (
        <div className="lmr-batch-loading">
          <div className="mn-spinner" style={{ width: 24, height: 24, borderWidth: 3 }} />
          <div>
            <p style={{ fontWeight: 600, color: "var(--text-h)" }}>
              {engineMode === "server"
                ? "Đang gỡ băng chính thức (PhoWhisper) và tạo tóm tắt biên bản (Qwen2.5)..."
                : "Đang phân tích & tạo tóm tắt biên bản bằng AI (Qwen2.5)..."}
            </p>
            <p style={{ fontSize: 13, color: "var(--text)", marginTop: 4 }}>
              Vui lòng không tắt hoặc tải lại trang trong giây lát.
            </p>
          </div>
        </div>
      )}

      {/* ── 5. View Đối Chiếu 3 Cột ────────────────────────────── */}
      {(batchTranscript || batchSummary || audioDownload) && (
        <div className="lmr-results-panel">
          <div className="lmr-export-actions">
            <div>
              <strong>Kết quả đối chiếu cuộc họp</strong>
            </div>
            <button
              className="lmr-btn lmr-btn--secondary"
              onClick={handleExportMarkdown}
            >
              Xuất file .md
            </button>
            {audioDownload && (
              <a
                className="lmr-btn lmr-btn--secondary"
                href={audioDownload.url}
                download={audioDownload.filename}
                style={{ textDecoration: "none" }}
              >
                Tải bản ghi âm
              </a>
            )}
          </div>

          <div className="lmr-columns-grid">
            {/* Cột 1: Live Log */}
            <div className="lmr-column-card">
              <div className="lmr-col-header">
                <h3>1. Bản ghi trực tiếp</h3>
                <span className="lmr-col-badge">
                  {engineMode === "server" ? "Wav2Vec2 Realtime" : "Web Speech"}
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
                <h3>2. Bản gỡ băng đầy đủ</h3>
                <span className="lmr-col-badge">
                  {engineMode === "server" ? "PhoWhisper chuẩn hóa" : "Web Speech Transcript"}
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
                  Qwen2.5-1.5B
                </span>
              </div>
              <div className="lmr-col-body">
                {batchSummary ? <SummaryContent text={batchSummary} /> : "Chưa có nội dung tóm tắt."}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
