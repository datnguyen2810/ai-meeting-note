import codecs

jsx = u"""import { useState } from "react";

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
      setError("\u26a0\ufe0f Vui l\u00f2ng ch\u1ecdn m\u1ed9t file \u00e2m thanh tr\u01b0\u1edbc khi nh\u1eadn di\u1ec7n.");
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
        let errMsg = "L\u1ed7i t\u1eeb server: " + response.status + " " + response.statusText;
        try {
          const errData = await response.json();
          if (errData?.detail) errMsg = "L\u1ed7i: " + errData.detail;
        } catch (_) {}
        throw new Error(errMsg);
      }
      const data = await response.json();
      if (data?.status === "success" && data?.transcript !== undefined) {
        setTranscript(data.transcript);
      } else {
        throw new Error("Ph\u1ea3n h\u1ed3i kh\u00f4ng h\u1ee3p l\u1ec7 t\u1eeb API.");
      }
    } catch (err) {
      if (err.name === "TypeError") {
        setError("\u274c Kh\u00f4ng th\u1ec3 k\u1ebft n\u1ed1i t\u1edbi server. Ki\u1ec3m tra API t\u1ea1i http://localhost:8000.");
      } else {
        setError("\u274c " + err.message);
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
        <h1 style={styles.title}>\U0001f3a4 Nh\u1eadn Di\u1ec7n Gi\u1ecdng N\u00f3i</h1>
        <p style={styles.subtitle}>T\u1ea3i l\u00ean file \u00e2m thanh \u0111\u1ec3 chuy\u1ec3n \u0111\u1ed5i th\u00e0nh v\u0103n b\u1ea3n t\u1ef1 \u0111\u1ed9ng</p>

        <div style={styles.fileInputWrapper}>
          <label style={styles.label} htmlFor="audio-input">Ch\u1ecdn file \u00e2m thanh</label>
          <input
            id="audio-input"
            type="file"
            accept="audio/*"
            onChange={handleFileChange}
            style={styles.fileInput}
            disabled={isLoading}
          />
          {selectedFile && (
            <p style={styles.fileName}>\u2705 \u0110\u00e3 ch\u1ecdn: {selectedFile.name}</p>
          )}
        </div>

        <button
          onClick={handleUpload}
          disabled={isButtonDisabled}
          style={{ ...styles.button, ...(isButtonDisabled ? styles.buttonDisabled : {}) }}
        >
          {isLoading ? "\u23f3 \u0110ang x\u1eed l\u00fd..." : "\U0001f680 B\u1eaft \u0111\u1ea7u nh\u1eadn di\u1ec7n"}
        </button>

        <div style={styles.resultBox}>
          <p style={styles.resultLabel}>\U0001f4dd Transcript</p>
          {error ? (
            <p style={styles.errorText}>{error}</p>
          ) : transcript ? (
            <p style={styles.resultText}>{transcript}</p>
          ) : (
            <p style={styles.placeholder}>
              {isLoading ? "\u0110ang ph\u00e2n t\u00edch \u00e2m thanh, vui l\u00f2ng ch\u1edd..." : "K\u1ebft qu\u1ea3 nh\u1eadn di\u1ec7n s\u1ebd hi\u1ec3n th\u1ecb t\u1ea1i \u0111\u00e2y."}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
"""

with open(r"d:\Code\PTIT\HTTM\AI_Meeting_Note\frontend\src\components\SpeechToTextDemo.jsx", "w", encoding="utf-8") as f:
    f.write(jsx)
print("Done")
