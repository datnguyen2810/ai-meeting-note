import { useState, useRef, useEffect } from "react";
import { api } from "../services/api";
import SummaryContent from "./SummaryContent";
import "./SpeakerChatMeeting.css";

export default function SpeakerChatMeeting({ onMeetingSaved }) {
  const [isRecording, setIsRecording] = useState(false);
  const [duration, setDuration] = useState(0);
  const [audioBlob, setAudioBlob] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [meetingTitle, setMeetingTitle] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");

  const [currentMeetingId, setCurrentMeetingId] = useState(null);
  const [speakers, setSpeakers] = useState([]);
  const [segments, setSegments] = useState([]);
  const [summary, setSummary] = useState("");
  const [activeSpeakerFilter, setActiveSpeakerFilter] = useState("");

  // Trạng thái cửa sổ chat AI dạng Bot nổi (floating widget)
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [chatMessages, setChatMessages] = useState([]);
  const [chatInput, setChatInput] = useState("");
  const [isChatLoading, setIsChatLoading] = useState(false);

  const timerRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioPlayerRef = useRef(null);
  const chatMessagesEndRef = useRef(null);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  // Tự động cuộn xuống cuối khi có tin nhắn mới trong khung chat
  useEffect(() => {
    if (isChatOpen && chatMessagesEndRef.current) {
      chatMessagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [chatMessages, isChatOpen]);

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data && event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const blob = new Blob(audioChunksRef.current, { type: "audio/wav" });
        setAudioBlob(blob);
        const url = URL.createObjectURL(blob);
        setAudioUrl(url);
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorder.start(250);
      setIsRecording(true);
      setDuration(0);
      setStatusMessage("Đang ghi âm cuộc họp...");

      timerRef.current = setInterval(() => {
        setDuration((prev) => prev + 1);
      }, 1000);
    } catch (err) {
      alert("Không thể truy cập microphone: " + err.message);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerRef.current) clearInterval(timerRef.current);
      setStatusMessage("Ghi âm hoàn tất. Sẵn sàng xử lý.");
    }
  };

  const handleFileUpload = (event) => {
    const file = event.target.files?.[0];
    if (file) {
      setAudioBlob(file);
      const url = URL.createObjectURL(file);
      setAudioUrl(url);
      setMeetingTitle(file.name.replace(/\.[^/.]+$/, ""));
      setStatusMessage(`Đã chọn tệp: ${file.name}`);
    }
  };

  const handleProcessMeeting = async () => {
    if (!audioBlob) {
      alert("Vui lòng ghi âm hoặc chọn tệp âm thanh trước khi xử lý.");
      return;
    }

    setIsLoading(true);
    setStatusMessage("Hệ thống đang phân đoạn người nói, nhận dạng giọng nói và tạo tóm tắt...");

    try {
      const fileToUpload =
        audioBlob instanceof File
          ? audioBlob
          : new File([audioBlob], "recording.wav", { type: "audio/wav" });

      const res = await api.processAudio(fileToUpload, meetingTitle);
      const meetingId = res.meetingId;
      setCurrentMeetingId(meetingId);

      const aiData = res.data || {};
      setSummary(aiData.summary || "");

      const speakersRes = await api.getSpeakers(meetingId);
      setSpeakers(speakersRes || []);

      const segmentsRes = await api.getSegments(meetingId);
      setSegments(segmentsRes || []);

      setStatusMessage("Xử lý cuộc họp thành công!");
      setChatMessages([
        {
          role: "assistant",
          content: "Tôi đã sẵn sàng trả lời các câu hỏi liên quan đến nội dung cuộc họp này.",
          citations: [],
        },
      ]);

      if (onMeetingSaved) {
        onMeetingSaved();
      }
    } catch (err) {
      setStatusMessage("Lỗi khi xử lý: " + err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendMessage = async (e) => {
    e.preventDefault();
    if (!chatInput.trim() || !currentMeetingId || isChatLoading) return;

    const userQuestion = chatInput.trim();
    setChatInput("");
    setChatMessages((prev) => [...prev, { role: "user", content: userQuestion }]);
    setIsChatLoading(true);

    try {
      const res = await api.chatMeeting(currentMeetingId, userQuestion, activeSpeakerFilter);
      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: res.answer,
          citations: res.citations || [],
        },
      ]);
    } catch (err) {
      setChatMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Lỗi khi hỏi đáp: " + err.message,
          citations: [],
        },
      ]);
    } finally {
      setIsChatLoading(false);
    }
  };

  const handleSeekAudio = (seconds) => {
    if (audioPlayerRef.current && seconds != null) {
      audioPlayerRef.current.currentTime = Number(seconds);
      audioPlayerRef.current.play();
    }
  };

  const formatSeconds = (sec) => {
    if (sec == null || isNaN(sec)) return "00:00";
    const totalSec = Math.max(0, Math.floor(Number(sec)));
    const m = Math.floor(totalSec / 60)
      .toString()
      .padStart(2, "0");
    const s = Math.floor(totalSec % 60)
      .toString()
      .padStart(2, "0");
    return `${m}:${s}`;
  };

  const formatRange = (start, end) => {
    const s = formatSeconds(start);
    let e = formatSeconds(end);
    if (s === e && Number(end) > Number(start)) {
      e = formatSeconds(Math.ceil(Number(end)));
    }
    return `${s} - ${e}`;
  };

  const filteredSegments = activeSpeakerFilter
    ? segments.filter((s) => s.speakerId === activeSpeakerFilter)
    : segments;

  return (
    <div className="speaker-meeting-container">
      {/* ── Header Card: Điều khiển ghi âm & xử lý ── */}
      <div className="meeting-header-card">
        <h2>Phiên âm theo người nói và Tóm tắt cuộc họp</h2>
        <p className="meeting-header-desc">
          Mô hình kết hợp: Pyannote Diarization + PhoWhisper ASR + Qwen2.5 Summarizer &amp; QA Chat
        </p>

        <div className="meeting-controls-row">
          <input
            type="text"
            placeholder="Tiêu đề cuộc họp (tùy chọn)..."
            value={meetingTitle}
            onChange={(e) => setMeetingTitle(e.target.value)}
            className="meeting-title-input"
          />

          {!isRecording ? (
            <button className="btn-primary" onClick={startRecording}>
              Bắt đầu ghi âm
            </button>
          ) : (
            <button className="btn-danger" onClick={stopRecording}>
              Kết thúc ghi âm
            </button>
          )}

          <label className="btn-secondary file-upload-label">
            Chọn tệp âm thanh
            <input type="file" accept="audio/*" onChange={handleFileUpload} style={{ display: "none" }} />
          </label>

          <span className="timer-badge">
            Thời lượng: {formatSeconds(duration)}
          </span>

          <button
            className="btn-primary"
            onClick={handleProcessMeeting}
            disabled={isLoading || isRecording || !audioBlob}
            style={{ opacity: isLoading || !audioBlob ? 0.6 : 1 }}
          >
            {isLoading ? "Đang xử lý..." : "Xử lý cuộc họp"}
          </button>
        </div>

        {statusMessage && (
          <div className="meeting-status-msg">
            {statusMessage}
          </div>
        )}

        {audioUrl && (
          <div className="audio-player-box">
            <audio ref={audioPlayerRef} controls src={audioUrl} style={{ width: "100%" }} />
          </div>
        )}
      </div>

      {/* ── Thẻ Biên bản người nói & Tóm tắt nội dung ngang hàng nhau ── */}
      <div className="meeting-content-grid">
        {/* Cột trái: Biên bản theo người nói */}
        <div className="panel-card">
          <div className="panel-title">Biên bản theo người nói</div>

          {speakers.length > 0 && (
            <div className="speaker-filter-bar">
              <button
                className={`filter-chip ${activeSpeakerFilter === "" ? "active" : ""}`}
                onClick={() => setActiveSpeakerFilter("")}
              >
                Tất cả
              </button>
              {speakers.map((spk) => (
                <button
                  key={spk.speakerId}
                  className={`filter-chip ${activeSpeakerFilter === spk.speakerId ? "active" : ""}`}
                  onClick={() => setActiveSpeakerFilter(spk.speakerId)}
                >
                  {spk.label}
                </button>
              ))}
            </div>
          )}

          <div className="segments-scroll-list">
            {filteredSegments.length === 0 ? (
              <div className="empty-panel-msg">
                Chưa có dữ liệu phiên âm. Hãy ghi âm hoặc tải tệp âm thanh lên rồi bấm &quot;Xử lý cuộc họp&quot;.
              </div>
            ) : (
              filteredSegments.map((seg, idx) => (
                <div
                  key={idx}
                  className="segment-item"
                  onClick={() => handleSeekAudio(seg.startSeconds)}
                  title="Bấm để nghe đoạn này"
                >
                  <div className="segment-header">
                    <span className="speaker-tag">{seg.speakerLabel || seg.speakerId}</span>
                    <span className="time-tag">
                      {formatRange(seg.startSeconds, seg.endSeconds)}
                    </span>
                  </div>
                  <div className="segment-text">{seg.text}</div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Cột phải: Tóm tắt nội dung cuộc họp (ngang hàng) */}
        <div className="panel-card">
          <div className="panel-title">Tóm tắt nội dung cuộc họp</div>

          <div className="summary-scroll-content">
            {summary ? (
              <SummaryContent text={summary} />
            ) : (
              <div className="empty-panel-msg">
                Chưa có nội dung tóm tắt. Sau khi xử lý cuộc họp, bản tóm tắt nội dung có cấu trúc (mục tiêu, kết quả, kế hoạch, vấn đề) sẽ tự động hiển thị tại đây.
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Biểu tượng Bot ở góc dưới bên phải màn hình ── */}
      <button
        type="button"
        className={`bot-fab-btn ${isChatOpen ? "active" : ""}`}
        onClick={() => setIsChatOpen((prev) => !prev)}
        title={isChatOpen ? "Thu nhỏ trợ lý AI" : "Mở trợ lý hỏi đáp AI"}
      >
        <svg
          width="24"
          height="24"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M12 8V4H8" />
          <rect width="16" height="12" x="4" y="8" rx="2" />
          <path d="M2 14h2" />
          <path d="M20 14h2" />
          <path d="M15 13v2" />
          <path d="M9 13v2" />
        </svg>
        <span className="bot-fab-label">Trợ lý AI</span>
      </button>

      {/* ── Cửa sổ Chat AI bật lên khi ấn vào biểu tượng Bot ── */}
      {isChatOpen && (
        <div className="bot-chat-window">
          <div className="bot-chat-header">
            <div className="bot-header-info">
              <div className="bot-header-title">Trợ lý hỏi đáp cuộc họp</div>
              <div className="bot-header-sub">
                Mô hình Qwen2.5 QA Chat | Trích dẫn nguồn theo mốc thời gian
              </div>
            </div>
            <button
              type="button"
              className="bot-close-btn"
              onClick={() => setIsChatOpen(false)}
              title="Đóng trợ lý"
            >
              Đóng
            </button>
          </div>

          {speakers.length > 0 && (
            <div className="bot-speaker-filter">
              <span className="bot-filter-label">Người nói:</span>
              <select
                value={activeSpeakerFilter}
                onChange={(e) => setActiveSpeakerFilter(e.target.value)}
                className="bot-speaker-select"
              >
                <option value="">Tất cả người nói</option>
                {speakers.map((spk) => (
                  <option key={spk.speakerId} value={spk.speakerId}>
                    {spk.label}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div className="chat-messages-container">
            {chatMessages.length === 0 ? (
              <div className="chat-empty-state">
                <p>Sau khi xử lý xong cuộc họp, bạn có thể đặt câu hỏi tại đây.</p>
                <p className="chat-empty-hint">
                  Ví dụ: &quot;Kế hoạch tuần tới là gì?&quot;, &quot;Tiến độ công việc ra sao?&quot;, &quot;Có vấn đề gì cần xử lý?&quot;
                </p>
              </div>
            ) : (
              chatMessages.map((msg, i) => (
                <div key={i} className={`chat-bubble ${msg.role}`}>
                  <div className="chat-bubble-content">{msg.content}</div>
                  {msg.citations && msg.citations.length > 0 && (
                    <div className="citations-block">
                      <div className="citations-header">Trích dẫn nguồn:</div>
                      {msg.citations.map((c, ci) => {
                        const start = c.startSeconds ?? c.start_seconds ?? 0;
                        const end = c.endSeconds ?? c.end_seconds ?? 0;
                        const spkName =
                          c.speakerLabel || c.speaker_label || c.speakerId || c.speaker_id || "Người nói";
                        return (
                          <div
                            key={ci}
                            className="citation-card"
                            onClick={() => handleSeekAudio(start)}
                            title="Bấm để nghe đúng đoạn này"
                          >
                            <div className="citation-speaker">
                              <strong>{spkName}</strong> ({formatRange(start, end)})
                            </div>
                            {c.quote && <div className="citation-quote">&quot;{c.quote}&quot;</div>}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              ))
            )}
            {isChatLoading && (
              <div className="chat-bubble assistant loading-bubble">
                Đang suy nghĩ và tra cứu nội dung cuộc họp...
              </div>
            )}
            <div ref={chatMessagesEndRef} />
          </div>

          <form onSubmit={handleSendMessage} className="chat-input-row">
            <input
              type="text"
              className="chat-input"
              placeholder="Hỏi về cuộc họp (VD: Kế hoạch tuần tới là gì?)..."
              value={chatInput}
              onChange={(e) => setChatInput(e.target.value)}
              disabled={isChatLoading || !currentMeetingId}
            />
            <button
              type="submit"
              className="btn-primary"
              disabled={isChatLoading || !chatInput.trim() || !currentMeetingId}
            >
              Gửi
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
