import { useState, useRef } from "react";
import "./MeetingNote.css";

export default function SpeechToTextDemo() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [transcript, setTranscript]     = useState("");
  const [summary, setSummary]           = useState("");
  const [isLoading, setIsLoading]       = useState(false);
  const [error, setError]               = useState("");
  const inputRef = useRef(null);

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    setSelectedFile(file || null);
    setTranscript("");
    setSummary("");
    setError("");
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setError("Vui lòng chọn một file âm thanh trước khi nhận diện.");
      return;
    }
    setIsLoading(true);
    setError("");
    setTranscript("");
    setSummary("");
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      const response = await fetch("http://localhost:8000/api/transcribe", {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        let errMsg = `Lỗi từ server: ${response.status} ${response.statusText}`;
        try {
          const errData = await response.json();
          if (errData?.detail) errMsg = errData.detail;
        } catch (_) {}
        throw new Error(errMsg);
      }
      const data = await response.json();
      if (data?.status === "success" && data?.transcript !== undefined) {
        setTranscript(data.transcript);
        setSummary(data.summary || "");
      } else {
        throw new Error("Phản hồi không hợp lệ từ API.");
      }
    } catch (err) {
      if (err.name === "TypeError") {
        setError("Không thể kết nối tới server. Kiểm tra API tại http://localhost:8000.");
      } else {
        setError(err.message);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const isButtonDisabled = isLoading || !selectedFile;

  return (
    <main className="mn-layout">
      <div className="mn-card">

        {/* Header */}
        <header className="mn-header">
          <h1 className="mn-title">Meeting Notes</h1>
          <p className="mn-desc">
            Tải lên file ghi âm cuộc họp để nhận bản phiên âm và tóm tắt nội dung.
          </p>
        </header>

        {/* File upload */}
        <section className="mn-section">
          <label className="mn-label" htmlFor="audio-input">File âm thanh</label>
          <div
            className={`mn-dropzone${selectedFile ? " mn-dropzone--has-file" : ""}`}
            onClick={() => inputRef.current?.click()}
          >
            <input
              ref={inputRef}
              id="audio-input"
              type="file"
              accept=".wav,.mp3,.m4a,audio/*"
              onChange={handleFileChange}
              disabled={isLoading}
              className="mn-file-input"
            />
            {selectedFile ? (
              <span className="mn-file-name">{selectedFile.name}</span>
            ) : (
              <span className="mn-file-placeholder">
                Nhấn để chọn file <span className="mn-file-hint">(.wav, .mp3, .m4a)</span>
              </span>
            )}
          </div>
        </section>

        {/* Submit */}
        <button
          className={`mn-btn${isButtonDisabled ? " mn-btn--disabled" : ""}`}
          onClick={handleUpload}
          disabled={isButtonDisabled}
        >
          {isLoading ? <span className="mn-spinner" /> : null}
          {isLoading ? "Đang xử lý..." : "Bắt đầu nhận diện"}
        </button>

        {/* Error */}
        {error && <p className="mn-error">{error}</p>}

        {/* Results */}
        {(transcript || isLoading) && (
          <div className="mn-results">
            <div className="mn-result-block">
              <p className="mn-result-label">Phiên âm</p>
              <div className="mn-result-content">
                {transcript
                  ? <p className="mn-result-text">{transcript}</p>
                  : <p className="mn-result-empty">Đang phân tích âm thanh...</p>
                }
              </div>
            </div>

            <div className="mn-result-block mn-result-block--summary">
              <p className="mn-result-label">Tóm tắt</p>
              <div className="mn-result-content">
                {summary
                  ? <p className="mn-result-text">{summary}</p>
                  : <p className="mn-result-empty">Đang tổng hợp nội dung...</p>
                }
              </div>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
