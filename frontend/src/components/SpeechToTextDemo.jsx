import { useState } from "react";

const styles = {
  wrapper: {
    minHeight: "100vh", display: "flex", alignItems: "center",
    justifyContent: "center", backgroundColor: "#f0f4f8",
    fontFamily: "'Segoe UI', Tahoma, Geneva, Verdana, sans-serif",
  },
  card: {
    backgroundColor: "#ffffff", borderRadius: "16px",
    boxShadow: "0 8px 30px rgba(0, 0, 0, 0.12)",
    padding: "40px", width: "100%", maxWidth: "600px",
  },
  title: { textAlign: "center", fontSize: "24px", fontWeight: "700", color: "#1a202c", marginBottom: "8px" },
  subtitle: { textAlign: "center", fontSize: "14px", color: "#718096", marginBottom: "32px" },
  label: { display: "block", fontSize: "14px", fontWeight: "600", color: "#4a5568", marginBottom: "8px" },
  fileInputWrapper: { position: "relative", marginBottom: "20px" },
  fileInput: {
    display: "block", width: "100%", padding: "12px",
    border: "2px dashed #cbd5e0", borderRadius: "10px",
    backgroundColor: "#f7fafc", fontSize: "14px",
    color: "#4a5568", cursor: "pointer",
    boxSizing: "border-box", transition: "border-color 0.2s",
  },
  fileName: { marginTop: "8px", fontSize: "13px", color: "#38a169", fontStyle: "italic" },
  button: {
    width: "100%", padding: "14px", backgroundColor: "#4f46e5",
    color: "#ffffff", border: "none", borderRadius: "10px",
    fontSize: "16px", fontWeight: "600", cursor: "pointer",
    transition: "background-color 0.2s, opacity 0.2s", marginBottom: "28px",
  },
  buttonDisabled: { backgroundColor: "#a5b4fc", cursor: "not-allowed" },
  resultBox: {
    backgroundColor: "#f7fafc", border: "1px solid #e2e8f0",
    borderRadius: "10px", padding: "20px", minHeight: "120px",
  },
  resultLabel: { fontSize: "13px", fontWeight: "600", color: "#718096", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: "10px" },
  resultText: { fontSize: "15px", color: "#2d3748", lineHeight: "1.7", whiteSpace: "pre-wrap", wordBreak: "break-word" },
  placeholder: { color: "#a0aec0", fontStyle: "italic", fontSize: "14px" },
  errorText: { color: "#e53e3e", fontSize: "14px" },
};

export default function SpeechToTextDemo() {
  const [selectedFile, setSelectedFile] = useState(null);
  const [transcript, setTranscript]     = useState("");
  const [isLoading, setIsLoading]       = useState(false);
  const [error, setError]               = useState("");

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    setSelectedFile(file || null);
    setTranscript("");
    setError("");
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setError("⚠️ Vui lòng chọn một file âm thanh trước khi nhận diện.");
      return;
    }
    setIsLoading(true);
    setError("");
    setTranscript("");
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      const response = await fetch("http://localhost:8000/api/transcribe", {
        method: "POST",
        body: formData,
      });
      if (!response.ok) {
        let errMsg = "Lỗi từ server: " + response.status + " " + response.statusText;
        try {
          const errData = await response.json();
          if (errData?.detail) errMsg = "Lỗi: " + errData.detail;
        } catch (_) {}
        throw new Error(errMsg);
      }
      const data = await response.json();
      if (data?.status === "success" && data?.transcript !== undefined) {
        setTranscript(data.transcript);
      } else {
        throw new Error("Phản hồi không hợp lệ từ API.");
      }
    } catch (err) {
      if (err.name === "TypeError") {
        setError("❌ Không thể kết nối tới server. Kiểm tra API tại http://localhost:8000.");
      } else {
        setError("❌ " + err.message);
      }
    } finally {
      setIsLoading(false);
    }
  };

  const isButtonDisabled = isLoading || !selectedFile;

  return (
    <div style={styles.wrapper}>
      <style>{"@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }"}</style>
      <div style={styles.card}>
        <h1 style={styles.title}>🎤 Nhận Diện Giọng Nói</h1>
        <p style={styles.subtitle}>Tải lên file âm thanh để chuyển đổi thành văn bản tự động</p>

        <div style={styles.fileInputWrapper}>
          <label style={styles.label} htmlFor="audio-input">Chọn file âm thanh</label>
          <input
            id="audio-input"
            type="file"
            accept="audio/*"
            onChange={handleFileChange}
            style={styles.fileInput}
            disabled={isLoading}
          />
          {selectedFile && (
            <p style={styles.fileName}>✅ Đã chọn: {selectedFile.name}</p>
          )}
        </div>

        <button
          onClick={handleUpload}
          disabled={isButtonDisabled}
          style={{ ...styles.button, ...(isButtonDisabled ? styles.buttonDisabled : {}) }}
        >
          {isLoading ? "⏳ Đang xử lý..." : "🚀 Bắt đầu nhận diện"}
        </button>

        <div style={styles.resultBox}>
          <p style={styles.resultLabel}>📝 Transcript</p>
          {error ? (
            <p style={styles.errorText}>{error}</p>
          ) : transcript ? (
            <p style={styles.resultText}>{transcript}</p>
          ) : (
            <p style={styles.placeholder}>
              {isLoading ? "Đang phân tích âm thanh, vui lòng chờ..." : "Kết quả nhận diện sẽ hiển thị tại đây."}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
