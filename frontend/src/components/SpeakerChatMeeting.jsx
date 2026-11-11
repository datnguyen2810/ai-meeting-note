import { useState, useRef, useEffect } from "react";
import { api } from "../services/api";
import SummaryContent from "./SummaryContent";
import { useWavRecorder } from "../hooks/useWavRecorder";
import {
  appendChat,
  getStoredMeetingId,
  loadChat,
  removeChat,
  saveChat,
  storeMeetingId,
} from "../utils/meetingViewStorage";
import "./SpeakerChatMeeting.css";

// Mã bộ phân người do AI service trả về (meeting_processing/diarize.py)
const PYANNOTE_ENGINE = "pyannote/speaker-diarization-community-1";
const DIARIZATION_LABELS = {
  [PYANNOTE_ENGINE]: "pyannote (speaker-diarization-community-1)",
  "acoustic-pitch-mfcc": "phân cụm cao độ + MFCC (bộ dự phòng, chưa dùng pyannote)",
  none: "không phân được người nói",
};

function diarizationLabel(engine, hasMeeting) {
  if (engine) return DIARIZATION_LABELS[engine] || engine;
  return hasMeeting ? "không ghi nhận (xử lý trước khi lưu thông tin này)" : "hiển thị sau khi xử lý";
}

// "vinai/PhoWhisper-small" -> "PhoWhisper-small"; tên lấy từ backend, không viết cứng
function modelName(id) {
  return id ? String(id).split("/").pop() : null;
}

// Bộ phân người dùng gần nhất, để biết có nên hiện mẹo chọn số người trước khi xử lý
const LAST_ENGINE_KEY = "speaker_view:last_engine";
function readLastEngine() {
  try {
    return localStorage.getItem(LAST_ENGINE_KEY);
  } catch {
    return null;
  }
}
function writeLastEngine(engine) {
  try {
    if (engine) localStorage.setItem(LAST_ENGINE_KEY, engine);
  } catch {
    // storage bị chặn: chỉ mất tiện ích này
  }
}

// Màu theo người nói (Người 1, 2...): nhìn lướt biết ai đang nói
const SPEAKER_COLORS = [
  { fg: "#1d4ed8", bg: "#eff6ff", border: "#93c5fd" },
  { fg: "#047857", bg: "#ecfdf5", border: "#6ee7b7" },
  { fg: "#b45309", bg: "#fffbeb", border: "#fcd34d" },
  { fg: "#7c3aed", bg: "#f5f3ff", border: "#c4b5fd" },
  { fg: "#be123c", bg: "#fff1f2", border: "#fda4af" },
  { fg: "#0e7490", bg: "#ecfeff", border: "#67e8f9" },
];
const UNKNOWN_SPEAKER_COLOR = { fg: "#475569", bg: "#f8fafc", border: "#cbd5e1" };

function speakerColor(speakerId) {
  const n = Number(String(speakerId || "").match(/(\d+)$/)?.[1]);
  return Number.isFinite(n) && n > 0 ? SPEAKER_COLORS[(n - 1) % SPEAKER_COLORS.length] : UNKNOWN_SPEAKER_COLOR;
}

const MAX_QUOTE_CHARS = 120;

function shortenQuote(quote) {
  const text = String(quote || "");
  if (text.length <= MAX_QUOTE_CHARS) return text;
  const cut = text.slice(0, MAX_QUOTE_CHARS);
  return cut.slice(0, cut.lastIndexOf(" ") > 60 ? cut.lastIndexOf(" ") : MAX_QUOTE_CHARS) + "…";
}

// Định dạng AI service đọc được khi chưa có FFmpeg (M4A/WebM cần FFmpeg)
const SUPPORTED_AUDIO = [".wav", ".mp3", ".flac", ".ogg"];

// Câu hỏi gợi ý trong khung chat; các câu này được trả lời bằng quy tắc, nhanh và bám biên bản
const SUGGESTED_QUESTIONS = ["Mục tiêu cuộc họp là gì?", "Có những vấn đề gì?", "Nhóm đã quyết định gì?",
  "Cuộc họp có mấy người?"];

const WELCOME_MESSAGE = {
  role: "assistant",
  content: "Tôi đã sẵn sàng trả lời các câu hỏi liên quan đến nội dung cuộc họp này.",
  citations: [],
};

/**
 * openRequest: { id, nonce } do App gửi khi người dùng bấm "Mở và hỏi đáp" trong
 * lịch sử. nonce đổi mỗi lần bấm để mở lại được cùng một cuộc họp.
 */
export default function SpeakerChatMeeting({ onMeetingSaved, openRequest, onOpenHandled, onBusyChange }) {
  const [isRecording, setIsRecording] = useState(false);
  const [duration, setDuration] = useState(0);
  const [audioBlob, setAudioBlob] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [meetingTitle, setMeetingTitle] = useState("");
  // "" = để AI tự đoán số người; giá trị số = người dùng biết chính xác
  const [numSpeakers, setNumSpeakers] = useState("");
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

  // Thông tin cuộc họp đang xem (tiêu đề, ngày tạo, transcript thường cho cuộc họp cũ)
  const [meetingInfo, setMeetingInfo] = useState(null);
  const [isLoadingMeeting, setIsLoadingMeeting] = useState(false);
  // Bộ phân người thực sự đã dùng cho cuộc họp đang xem (null = chưa biết)
  const [diarizationEngine, setDiarizationEngineState] = useState(null);
  // Bộ phân người gần nhất từng thấy (kể cả cuộc họp trước), quyết định có hiện mẹo
  const [lastEngine, setLastEngine] = useState(readLastEngine);
  // Model phiên âm/tóm tắt do backend trả (không viết cứng tên model trên giao diện)
  const [models, setModels] = useState({});
  // Vị trí đang phát, để tô sáng đoạn biên bản tương ứng
  const [playback, setPlayback] = useState({ time: 0, playing: false });

  // Hỏi đáp cần một cuộc họp có các đoạn theo người nói
  const chatAvailable = currentMeetingId != null && segments.length > 0;

  const setDiarizationEngine = (engine) => {
    setDiarizationEngineState(engine);
    if (engine && engine !== "none") {
      setLastEngine(engine);
      writeLastEngine(engine);
    }
  };

  // Bản ghi/tệp đã xử lý thành công: bấm lại không tạo cuộc họp trùng
  const [processedBlob, setProcessedBlob] = useState(null);

  const timerRef = useRef(null);
  const wavRecorder = useWavRecorder();
  const audioPlayerRef = useRef(null);
  const chatMessagesEndRef = useRef(null);
  // Cuộc họp đang hiển thị, đọc được ngay trong callback bất đồng bộ
  const currentMeetingIdRef = useRef(null);
  // Tăng mỗi lần đổi cuộc họp; phản hồi mang token cũ thì bỏ qua
  const viewTokenRef = useRef(0);

  const showMeeting = (meetingId) => {
    currentMeetingIdRef.current = meetingId;
    viewTokenRef.current += 1;
    setCurrentMeetingId(meetingId);
    storeMeetingId(meetingId);
    setIsChatLoading(false);
    setChatInput("");
    setActiveSpeakerFilter("");
    return viewTokenRef.current;
  };

  const clearLocalAudio = () => {
    // Bản ghi cục bộ không thuộc cuộc họp mở từ lịch sử; bỏ để không xử lý nhầm
    setAudioBlob(null);
    setAudioUrl(null);
    setDuration(0);
  };

  const loadMeeting = async (meetingId) => {
    const token = showMeeting(meetingId);
    clearLocalAudio();
    setIsLoadingMeeting(true);
    setStatusMessage("Đang mở cuộc họp...");
    setSpeakers([]);
    setSegments([]);
    setSummary("");
    setMeetingInfo(null);
    setDiarizationEngine(null);
    setModels({});
    setChatMessages(loadChat(meetingId) || [WELCOME_MESSAGE]);

    try {
      const [meeting, speakersRes, segmentsRes, processing] = await Promise.all([
        api.getMeeting(meetingId),
        api.getSpeakers(meetingId),
        api.getSegments(meetingId),
        // Không có thông tin xử lý (backend cũ) thì vẫn mở được cuộc họp
        api.getProcessingInfo(meetingId).catch(() => ({})),
      ]);
      if (token !== viewTokenRef.current) return; // người dùng đã mở cuộc họp khác
      setMeetingInfo(meeting || null);
      setDiarizationEngine(processing?.diarizationEngine || null);
      setModels({ asr: processing?.asrModel || null });
      setSummary(meeting?.summary || "");
      setSpeakers(speakersRes || []);
      setSegments(segmentsRes || []);
      setStatusMessage(
        (segmentsRes || []).length
          ? ""
          : "Cuộc họp này chưa có phiên âm theo người nói nên trợ lý AI chưa trả lời được; chỉ xem được bản phiên âm thường."
      );
      // Tải audio để nghe lại và bấm đoạn/trích dẫn để tua; không có thì vẫn xem được
      api
        .getMeetingAudio(meetingId)
        .then((blob) => {
          if (blob && token === viewTokenRef.current) setAudioUrl(URL.createObjectURL(blob));
        })
        .catch(() => { });
    } catch (err) {
      if (token !== viewTokenRef.current) return;
      showMeeting(null);
      setChatMessages([]);
      setStatusMessage("Không mở được cuộc họp: " + err.message);
    } finally {
      if (token === viewTokenRef.current) setIsLoadingMeeting(false);
    }
  };

  // Bỏ cuộc họp đang xem (biên bản, tóm tắt, chat); không đụng audio cục bộ
  const clearMeetingView = () => {
    showMeeting(null);
    setSpeakers([]);
    setSegments([]);
    setSummary("");
    setMeetingInfo(null);
    setDiarizationEngineState(null);
    setModels({});
    setChatMessages([]);
    setIsLoadingMeeting(false);
  };

  const startNewMeeting = () => {
    clearMeetingView();
    clearLocalAudio();
    setMeetingTitle("");
    setStatusMessage("");
  };

  // Ghi âm/chọn tệp mới khi đang xem cuộc họp cũ: chuyển sang cuộc họp mới để không
  // nhầm rằng bấm "Xử lý" sẽ ghi đè cuộc họp đang xem
  const leaveViewedMeeting = () => {
    if (currentMeetingIdRef.current == null) return;
    clearMeetingView();
    setMeetingTitle("");
  };

  // Mở lại cuộc họp đang xem trước khi tải lại trang (một lần khi gắn component)
  useEffect(() => {
    if (openRequest?.id) return; // App đang yêu cầu mở cuộc họp khác
    const storedId = getStoredMeetingId();
    if (storedId) loadMeeting(storedId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Mở cuộc họp được chọn từ lịch sử. Báo App xóa yêu cầu sau khi nhận, để lần
  // gắn lại sau (đổi tab) khôi phục cuộc họp xem gần nhất thay vì yêu cầu cũ.
  useEffect(() => {
    if (!openRequest?.id) return;
    loadMeeting(openRequest.id);
    onOpenHandled?.();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [openRequest?.nonce]);

  // Cuộc họp bị xóa trong lịch sử: đóng nếu đang xem, xóa lịch sử chat của nó
  useEffect(() => {
    const onDeleted = (event) => {
      const id = event.detail?.id;
      removeChat(id);
      if (id != null && id === currentMeetingIdRef.current) startNewMeeting();
    };
    window.addEventListener("meeting_deleted", onDeleted);
    return () => window.removeEventListener("meeting_deleted", onDeleted);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Lưu lịch sử chat theo cuộc họp đang xem
  useEffect(() => {
    if (currentMeetingId != null && chatMessages.length) saveChat(currentMeetingId, chatMessages);
  }, [currentMeetingId, chatMessages]);

  // Thu hồi object URL cũ khi đổi audio. Bộ đếm giờ dọn riêng lúc unmount: trước đây
  // nằm chung effect này nên chọn tệp khi đang ghi làm đồng hồ dừng giữa chừng.
  useEffect(() => {
    return () => {
      if (audioUrl) URL.revokeObjectURL(audioUrl);
    };
  }, [audioUrl]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  // Báo App để hiện trạng thái trên nút tab khi người dùng đang ở tab khác
  const busyState = isRecording ? "recording" : isLoading ? "processing" : null;
  useEffect(() => {
    onBusyChange?.(busyState);
  }, [busyState, onBusyChange]);

  // Cảnh báo khi đóng/tải lại trang lúc đang ghi âm hoặc đang xử lý
  useEffect(() => {
    if (!busyState) return undefined;
    const onBeforeUnload = (event) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [busyState]);

  // Tự động cuộn xuống cuối khi có tin nhắn mới trong khung chat
  useEffect(() => {
    if (isChatOpen && chatMessagesEndRef.current) {
      chatMessagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [chatMessages, isChatOpen]);

  const startRecording = async () => {
    try {
      // Ghi WAV thật (PCM 16 kHz); MediaRecorder tạo WebM mà AI không đọc được
      await wavRecorder.start();
      if (currentMeetingIdRef.current != null) {
        leaveViewedMeeting();
        clearLocalAudio(); // audio của cuộc họp cũ
      }
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

  const stopRecording = async () => {
    if (!isRecording) return;
    setIsRecording(false);
    if (timerRef.current) clearInterval(timerRef.current);
    const blob = await wavRecorder.stop();
    if (!blob) {
      setStatusMessage("Không thu được âm thanh. Hãy kiểm tra micro và ghi lại.");
      return;
    }
    setAudioBlob(blob);
    setAudioUrl(URL.createObjectURL(blob));
    setStatusMessage("Ghi âm hoàn tất. Sẵn sàng xử lý.");
  };

  const handleFileUpload = (event) => {
    const input = event.target;
    const file = input.files?.[0];
    // Reset để chọn lại đúng tệp vừa chọn vẫn kích hoạt onChange
    input.value = "";
    if (!file || isRecording || isLoading) return;

    const ext = (file.name.match(/\.[^/.]+$/)?.[0] || "").toLowerCase();
    if (!SUPPORTED_AUDIO.includes(ext)) {
      setStatusMessage(
        `Không hỗ trợ tệp ${ext || "không có đuôi"}. Hãy dùng ${SUPPORTED_AUDIO.join(", ")} ` +
        "(M4A/WebM cần cài FFmpeg trên máy chạy AI)."
      );
      return;
    }

    leaveViewedMeeting();
    setAudioBlob(file);
    setAudioUrl(URL.createObjectURL(file));
    setDuration(0); // cập nhật khi trình phát đọc xong thời lượng
    setMeetingTitle(file.name.replace(/\.[^/.]+$/, ""));
    setStatusMessage(`Đã chọn tệp: ${file.name}`);
  };

  // Thời lượng thật của tệp hoặc bản ghi (bộ đếm giây chỉ dùng trong lúc ghi)
  const handleAudioMetadata = (event) => {
    const seconds = event.currentTarget.duration;
    if (!isRecording && Number.isFinite(seconds)) setDuration(Math.round(seconds));
  };

  const handleProcessMeeting = async () => {
    if (!audioBlob) {
      alert("Vui lòng ghi âm hoặc chọn tệp âm thanh trước khi xử lý.");
      return;
    }
    if (audioBlob === processedBlob) return; // đã xử lý, tránh tạo cuộc họp trùng

    // Người dùng có thể mở cuộc họp khác từ lịch sử trong lúc chờ (vài phút)
    const startToken = viewTokenRef.current;
    const blobToProcess = audioBlob;
    setIsLoading(true);
    setStatusMessage("Hệ thống đang phân đoạn người nói, nhận dạng giọng nói và tạo tóm tắt...");

    try {
      const fileToUpload =
        audioBlob instanceof File
          ? audioBlob
          : new File([audioBlob], "recording.wav", { type: "audio/wav" });

      const res = await api.processAudio(
        fileToUpload,
        meetingTitle,
        undefined,
        4,
        numSpeakers ? Number(numSpeakers) : undefined
      );
      // Backend trả HTTP 200 kèm status "failed" khi AI lỗi; không báo thành công giả
      if (res?.status === "failed") {
        throw new Error(res.error || "AI xử lý thất bại");
      }
      const meetingId = res.meetingId;
      setProcessedBlob(blobToProcess);
      onMeetingSaved?.();

      if (startToken !== viewTokenRef.current) {
        // Đã mở cuộc họp khác: không kéo màn hình về cuộc họp vừa xử lý
        setStatusMessage(
          `Đã xử lý xong "${meetingTitle || `Cuộc họp #${meetingId}`}". Mở từ lịch sử để xem và hỏi đáp.`
        );
        return;
      }
      const token = showMeeting(meetingId);
      setMeetingInfo({ id: meetingId, title: meetingTitle || null, createdAt: new Date().toISOString() });

      const aiData = res.data || {};
      setSummary(aiData.summary || "");
      setDiarizationEngine(aiData.models?.diarization || null);
      setModels({ asr: aiData.models?.asr || null, summary: aiData.models?.summary || null });
      setChatMessages([WELCOME_MESSAGE]);

      const [speakersRes, segmentsRes] = await Promise.all([
        api.getSpeakers(meetingId),
        api.getSegments(meetingId),
      ]);
      if (token !== viewTokenRef.current) return; // đã mở cuộc họp khác trong lúc chờ
      setSpeakers(speakersRes || []);
      setSegments(segmentsRes || []);

      const warnings = Array.isArray(aiData.warnings) ? aiData.warnings : [];
      setStatusMessage(["Xử lý cuộc họp thành công!", ...warnings].join(" "));
    } catch (err) {
      // Chỉ hiện lỗi khi người dùng vẫn đang ở màn hình xử lý
      if (startToken === viewTokenRef.current) setStatusMessage("Lỗi khi xử lý: " + err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendMessage = (e) => {
    e.preventDefault();
    askQuestion(chatInput);
  };

  const askQuestion = async (question) => {
    if (!question.trim() || !currentMeetingId || isChatLoading) return;

    const userQuestion = question.trim();
    // Ghi nhớ cuộc họp lúc gửi: người dùng có thể mở cuộc họp khác khi đang chờ
    const meetingId = currentMeetingId;
    setChatInput("");
    setChatMessages((prev) => [...prev, { role: "user", content: userQuestion }]);
    setIsChatLoading(true);

    let reply;
    try {
      const res = await api.chatMeeting(meetingId, userQuestion, activeSpeakerFilter);
      reply = { role: "assistant", content: res.answer, citations: res.citations || [] };
    } catch (err) {
      reply = { role: "assistant", content: "Lỗi khi hỏi đáp: " + err.message, citations: [] };
    }

    if (meetingId === currentMeetingIdRef.current) {
      setChatMessages((prev) => [...prev, reply]);
      setIsChatLoading(false);
    } else {
      // Đã đổi cuộc họp: không chen câu trả lời vào cuộc họp mới, lưu về đúng cuộc họp cũ
      appendChat(meetingId, reply);
    }
  };

  const handleSeekAudio = (seconds) => {
    if (audioPlayerRef.current && seconds != null) {
      audioPlayerRef.current.currentTime = Number(seconds);
      audioPlayerRef.current.play().catch(() => { });
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
      {/* ── Bố cục 2 phần: Trái (Điều khiển ghi âm & xử lý) - Phải (Biên bản & Tóm tắt) ── */}
      <div className="smc-main-layout">
        {/* Cột trái: Thẻ Điều khiển & Xử lý cuộc họp */}
        <div className="smc-left-col">
          <div className="meeting-header-card">
            <div className="panel-title-wrap">
              <h2 className="smc-card-title">Điều khiển & Xử lý cuộc họp</h2>
              <div className="panel-subtitle">Ghi âm trực tiếp hoặc chọn tệp âm thanh để bắt đầu</div>
            </div>

            {currentMeetingId != null && (
              <div className="viewing-meeting-bar">
                <span className="viewing-meeting-text">
                  {isLoadingMeeting ? "Đang mở cuộc họp" : "Đang xem"}:{" "}
                  <strong>{meetingInfo?.title || `Cuộc họp #${currentMeetingId}`}</strong>
                  {meetingInfo?.createdAt && (
                    <span className="viewing-meeting-date">
                      {" · "}
                      {new Date(meetingInfo.createdAt).toLocaleString("vi-VN")}
                    </span>
                  )}
                </span>
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={startNewMeeting}
                  disabled={isLoading}
                >
                  Cuộc họp mới
                </button>
              </div>
            )}

            <div className="smc-steps smc-steps-vertical">
              {/* Bước 1: chọn nguồn âm thanh */}
              <div className="smc-step">
                <div className="smc-step-title">1. Âm thanh cuộc họp</div>
                <div className="smc-audio-btn-grid">
                  {!isRecording ? (
                    <button type="button" className="smc-btn smc-btn-record" onClick={startRecording} disabled={isLoading}>
                      Ghi âm
                    </button>
                  ) : (
                    <button type="button" className="smc-btn smc-btn-stop" onClick={stopRecording}>
                      Kết thúc ghi âm
                    </button>
                  )}
                  <label
                    className={`smc-btn smc-btn-outline ${isRecording || isLoading ? "is-disabled" : ""}`}
                    title={isRecording ? "Hãy kết thúc ghi âm trước khi chọn tệp" : "WAV, MP3, FLAC hoặc OGG"}
                  >
                    Chọn tệp âm thanh
                    <input
                      type="file"
                      accept={[...SUPPORTED_AUDIO, "audio/wav", "audio/mpeg", "audio/flac", "audio/ogg"].join(",")}
                      onChange={handleFileUpload}
                      disabled={isRecording || isLoading}
                      style={{ display: "none" }}
                    />
                  </label>
                </div>
                <div
                  className={`smc-duration ${isRecording ? "is-recording" : ""} ${!isRecording && !audioUrl ? "is-empty" : ""}`}
                  title={audioBlob?.name || undefined}
                >
                  {isRecording
                    ? `Đang ghi âm: ${formatSeconds(duration)}`
                    : !audioUrl
                      ? "Chưa có âm thanh"
                      : `${audioBlob?.name || (audioBlob ? "Bản ghi âm" : "Âm thanh cuộc họp")} · ${formatSeconds(duration)}`}
                </div>
              </div>

              {/* Bước 2: tham số và xử lý */}
              <div className="smc-step">
                <div className="smc-step-title">2. Xử lý cuộc họp</div>
                <div className="smc-step-fields">
                  <input
                    type="text"
                    placeholder="Tiêu đề cuộc họp (tùy chọn)"
                    value={meetingTitle}
                    onChange={(e) => setMeetingTitle(e.target.value)}
                    className="meeting-title-input"
                  />
                  <div className="smc-process-action-row">
                    <label className="speaker-count-field" title="Nhập đúng số người giúp phân biệt người nói chính xác hơn">
                      Số người
                      <select
                        value={numSpeakers}
                        onChange={(e) => setNumSpeakers(e.target.value)}
                        disabled={isLoading}
                        className="speaker-count-select"
                      >
                        <option value="">Tự động</option>
                        {[1, 2, 3, 4, 5, 6].map((n) => (
                          <option key={n} value={n}>
                            {n}
                          </option>
                        ))}
                      </select>
                    </label>
                    {(() => {
                      const alreadyProcessed = audioBlob != null && audioBlob === processedBlob;
                      const disabled = isLoading || isRecording || !audioBlob || alreadyProcessed;
                      return (
                        <button
                          type="button"
                          className={`smc-btn smc-btn-primary smc-btn-process ${alreadyProcessed ? "is-processed" : ""}`}
                          onClick={handleProcessMeeting}
                          disabled={disabled}
                          title={
                            alreadyProcessed
                              ? "Bản ghi này đã được xử lý; ghi âm hoặc chọn tệp mới để xử lý tiếp"
                              : !audioBlob
                                ? "Ghi âm hoặc chọn tệp âm thanh trước"
                                : undefined
                          }
                        >
                          {isLoading ? "Đang xử lý..." : alreadyProcessed ? "Đã xử lý xong" : "Xử lý cuộc họp"}
                        </button>
                      );
                    })()}
                  </div>
                </div>
                {!audioBlob && !isLoading && !isRecording && (
                  <div className="smc-step-note">
                    {currentMeetingId
                      ? "Đang xem cuộc họp đã xử lý. Ghi âm hoặc chọn tệp mới để xử lý cuộc họp khác."
                      : "Ghi âm hoặc chọn tệp âm thanh ở bước 1 để bật nút xử lý."}
                  </div>
                )}
                {/* Chỉ bộ pitch/MFCC mới hay tự đoán thiếu người; pyannote tự đoán được */}
                {!numSpeakers && lastEngine !== PYANNOTE_ENGINE && audioBlob && audioBlob !== processedBlob && !isLoading && (
                  <div className="smc-hint">
                    Mẹo: chế độ "Tự động" có thể tách thiếu người khi giọng giống nhau; biết số người thì nên chọn ở ô "Số người".
                  </div>
                )}
              </div>
            </div>

            {statusMessage && <div className="meeting-status-msg">{statusMessage}</div>}

            {audioUrl && (
              <div className="audio-player-box">
                <audio
                  ref={audioPlayerRef}
                  controls
                  src={audioUrl}
                  onLoadedMetadata={handleAudioMetadata}
                  onTimeUpdate={(e) => setPlayback({ time: e.currentTarget.currentTime, playing: !e.currentTarget.paused })}
                  onPlay={(e) => setPlayback({ time: e.currentTarget.currentTime, playing: true })}
                  onPause={(e) => setPlayback({ time: e.currentTarget.currentTime, playing: false })}
                  style={{ width: "100%" }}
                />
              </div>
            )}
          </div>
        </div>

        {/* Cột phải: Biên bản theo người nói và Tóm tắt nội dung cuộc họp */}
        <div className="smc-right-col">
          {/* Thẻ: Biên bản theo người nói */}
          <div className="panel-card">
            <div className="panel-title-wrap">
              <div className="panel-title">Biên bản theo người nói</div>
              <div className="panel-subtitle">Nhấp vào câu thoại để nghe lại đoạn âm thanh tương ứng</div>
            </div>

            {speakers.length > 0 && (
              <div className="speaker-filter-bar">
                <button
                  className={`filter-chip ${activeSpeakerFilter === "" ? "active" : ""}`}
                  onClick={() => setActiveSpeakerFilter("")}
                >
                  Tất cả
                </button>
                {speakers.map((spk) => {
                  const color = speakerColor(spk.speakerId);
                  const active = activeSpeakerFilter === spk.speakerId;
                  return (
                    <button
                      key={spk.speakerId}
                      className={`filter-chip ${active ? "active" : ""}`}
                      style={
                        active
                          ? { background: color.fg, borderColor: color.fg, color: "#ffffff" }
                          : { background: color.bg, borderColor: color.border, color: color.fg }
                      }
                      onClick={() => setActiveSpeakerFilter(spk.speakerId)}
                    >
                      {spk.label}
                    </button>
                  );
                })}
              </div>
            )}

            <div className="segments-scroll-list">
              {filteredSegments.length === 0 && segments.length === 0 && meetingInfo?.transcript ? (
                // Cuộc họp tạo trước khi có phân người nói: chỉ có bản phiên âm thường
                <div className="legacy-transcript">
                  <div className="legacy-transcript-note">
                    Cuộc họp này chưa có phiên âm theo người nói; hiển thị bản phiên âm thường.
                  </div>
                  <div className="legacy-transcript-text">{meetingInfo.transcript}</div>
                </div>
              ) : filteredSegments.length === 0 ? (
                <div className="empty-panel-msg">
                  {isLoadingMeeting
                    ? "Đang tải phiên âm..."
                    : "Chưa có dữ liệu phiên âm. Hãy ghi âm hoặc tải tệp âm thanh lên rồi bấm \"Xử lý cuộc họp\"."}
                </div>
              ) : (
                filteredSegments.map((seg) => {
                  const color = speakerColor(seg.speakerId);
                  const playing =
                    playback.playing &&
                    playback.time >= Number(seg.startSeconds) &&
                    playback.time < Number(seg.endSeconds);
                  return (
                    <div
                      key={seg.segmentId || `${seg.startSeconds}-${seg.speakerId}`}
                      className={`segment-item ${playing ? "playing" : ""}`}
                      style={{ borderLeftColor: color.border, ...(playing ? { background: color.bg } : {}) }}
                      onClick={() => handleSeekAudio(seg.startSeconds)}
                      title={audioUrl ? "Bấm để nghe đoạn này" : "Không có audio của cuộc họp này trên máy"}
                    >
                      <div className="segment-header">
                        <span className="speaker-tag" style={{ color: color.fg }}>
                          {seg.speakerLabel || seg.speakerId || "Chưa rõ người nói"}
                          {playing && <span className="playing-badge"> (đang phát)</span>}
                        </span>
                        <span className="time-tag">{formatRange(seg.startSeconds, seg.endSeconds)}</span>
                      </div>
                      <div className="segment-text">{seg.text}</div>
                    </div>
                  );
                })
              )}
            </div>
          </div>

          {/* Thẻ: Tóm tắt nội dung cuộc họp */}
          <div className="panel-card">
            <div className="panel-title-wrap">
              <div className="panel-title">Tóm tắt nội dung cuộc họp</div>
              <div className="panel-subtitle">Tự động trích xuất các ý chính theo cấu trúc nội dung</div>
            </div>

            <div className="summary-scroll-content">
              {summary ? (
                <SummaryContent text={summary} />
              ) : (
                <div className="empty-panel-msg">
                  Chưa có nội dung tóm tắt. Sau khi xử lý cuộc họp, bản tóm tắt nội dung có cấu trúc (mục tiêu, kết quả, vấn đề, quyết định, phân công) sẽ tự động hiển thị tại đây.
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Footer: Thông tin các mô hình AI bé bé ── */}
      {/* Chỉ hiện model thực sự đã dùng (backend trả); chưa biết thì không đoán */}
      <footer className="smc-models-footer">
        {(() => {
          const items = [
            models.asr && `Phiên âm: ${modelName(models.asr)}`,
            models.summary && `Tóm tắt: ${modelName(models.summary)}`,
            diarizationEngine && `Phân người nói: ${diarizationLabel(diarizationEngine, true)}`,
          ].filter(Boolean);
          if (!items.length) {
            return <span>{currentMeetingId ? "Không có thông tin mô hình cho cuộc họp này" : "Tên các mô hình AI sẽ hiện sau khi xử lý cuộc họp"}</span>;
          }
          return items.map((text, i) => (
            <span key={text}>
              {i > 0 && <span className="smc-footer-sep">· </span>}
              {text}
            </span>
          ));
        })()}
      </footer>

      {/* ── Biểu tượng Bot ở góc dưới bên phải màn hình ── */}
      <button
        type="button"
        className={`bot-fab-btn ${isChatOpen && chatAvailable ? "active" : ""}`}
        onClick={() => setIsChatOpen((prev) => !prev)}
        disabled={!chatAvailable}
        title={
          !chatAvailable
            ? currentMeetingId
              ? "Cuộc họp này chưa có phiên âm theo người nói nên chưa hỏi đáp được"
              : "Xử lý hoặc mở một cuộc họp trước khi hỏi đáp"
            : isChatOpen
              ? "Thu nhỏ trợ lý AI"
              : "Mở trợ lý hỏi đáp AI"
        }
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
        <span className="bot-fab-label">Hỏi đáp</span>
      </button>

      {/* ── Cửa sổ Chat AI bật lên khi ấn vào biểu tượng Bot ── */}
      {isChatOpen && chatAvailable && (
        <div className="bot-chat-window">
          <div className="bot-chat-header">
            <div className="bot-header-info">
              <div className="bot-header-title">Trợ lý hỏi đáp cuộc họp</div>
              <div className="bot-header-sub">Trả lời theo biên bản, kèm mốc thời gian để nghe lại</div>
            </div>
            <button
              type="button"
              className="bot-close-btn"
              onClick={() => setIsChatOpen(false)}
              title="Đóng trợ lý"
            >
              X
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
                <p>
                  Sau khi xử lý xong cuộc họp, hoặc mở một cuộc họp từ lịch sử, bạn có thể đặt câu hỏi tại đây.
                </p>
                <p className="chat-empty-hint">
                  Ví dụ: &quot;Mục tiêu cuộc họp là gì?&quot;, &quot;Người 1 nói gì?&quot;, &quot;Có vấn đề gì cần xử lý?&quot;
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
                            {c.quote && (
                              // Rút gọn để câu trả lời không bị lặp nguyên văn quá dài; rê chuột xem đủ
                              <div className="citation-quote" title={c.quote}>
                                &quot;{shortenQuote(c.quote)}&quot;
                              </div>
                            )}
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

          {currentMeetingId != null && segments.length > 0 && (
            <div className="chat-suggestions">
              {[...SUGGESTED_QUESTIONS, ...speakers.slice(0, 3).map((s) => `${s.label} nói gì?`)].map((q) => (
                <button
                  key={q}
                  type="button"
                  className="chat-suggestion-chip"
                  onClick={() => askQuestion(q)}
                  disabled={isChatLoading}
                >
                  {q}
                </button>
              ))}
            </div>
          )}

          <form onSubmit={handleSendMessage} className="chat-input-row">
            <input
              type="text"
              className="chat-input"
              placeholder="Hỏi về cuộc họp..."
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
