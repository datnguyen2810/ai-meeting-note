import { useState, useRef, useCallback, useEffect } from "react";

/**
 * Custom hook quản lý nhận diện giọng nói trực tiếp qua Web Speech API (trình duyệt Chromium)
 * Tích hợp AudioContext Analyser (visualizer) và MediaRecorder (lưu file âm thanh)
 */
export function useWebSpeechTranscription() {
  const [status, setStatus] = useState("idle"); // 'idle' | 'connecting' | 'recording' | 'stopping' | 'error'
  const [captions, setCaptions] = useState([]);
  const [duration, setDuration] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const [errorMsg, setErrorMsg] = useState(null);

  const recognitionRef = useRef(null);
  const shouldListenRef = useRef(false);
  const timerRef = useRef(null);
  const durationRef = useRef(0);
  const seqRef = useRef(1);
  const finalCaptionsRef = useRef([]);

  // Audio Context & MediaRecorder
  const audioCtxRef = useRef(null);
  const streamRef = useRef(null);
  const analyserRef = useRef(null);
  const animFrameRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const recordedBlobsRef = useRef([]);

  // Dọn dẹp tài nguyên âm thanh
  const cleanupAudio = useCallback(() => {
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current);
      animFrameRef.current = null;
    }
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }
    if (audioCtxRef.current && audioCtxRef.current.state !== "closed") {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    setAudioLevel(0);
  }, []);

  // Visualizer loop (sử dụng named function expression)
  const updateAudioLevel = useCallback(function tick() {
    if (!analyserRef.current) return;
    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteFrequencyData(dataArray);

    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i];
    }
    const avg = sum / dataArray.length;
    setAudioLevel(Math.min(100, Math.round((avg / 128) * 100)));

    animFrameRef.current = requestAnimationFrame(tick);
  }, []);

  // Bắt đầu nhận diện Web Speech
  const startRecording = useCallback(async () => {
    setErrorMsg(null);
    setCaptions([]);
    setDuration(0);
    durationRef.current = 0;
    seqRef.current = 1;
    finalCaptionsRef.current = [];
    recordedBlobsRef.current = [];
    setStatus("connecting");

    const SpeechRecognition =
      window.SpeechRecognition || window.webkitSpeechRecognition;

    if (!SpeechRecognition) {
      setErrorMsg(
        "Trình duyệt của bạn không hỗ trợ Web Speech API. Vui lòng sử dụng Google Chrome hoặc Microsoft Edge."
      );
      setStatus("error");
      return;
    }

    try {
      // 1. Microphone & AudioContext cho visualizer và MediaRecorder
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      const AudioContextClass =
        window.AudioContext || window.webkitAudioContext;
      const ctx = new AudioContextClass();
      audioCtxRef.current = ctx;

      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;
      source.connect(analyser);

      // MediaRecorder để lưu file âm thanh
      try {
        const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
          ? "audio/webm;codecs=opus"
          : "audio/webm";
        const recorder = new MediaRecorder(stream, { mimeType });
        recorder.ondataavailable = (e) => {
          if (e.data && e.data.size > 0) {
            recordedBlobsRef.current.push(e.data);
          }
        };
        recorder.start(1000); // Lưu chunk mỗi 1s
        mediaRecorderRef.current = recorder;
      } catch (recErr) {
        console.warn("[WebSpeech] Không thể khởi động MediaRecorder:", recErr);
      }

      // Kích hoạt Visualizer
      updateAudioLevel();

      // Timer
      timerRef.current = setInterval(() => {
        setDuration((prev) => {
          durationRef.current = prev + 1;
          return prev + 1;
        });
      }, 1000);

      // 2. Khởi tạo SpeechRecognition
      const recognition = new SpeechRecognition();
      recognition.continuous = true;
      recognition.interimResults = true;
      recognition.lang = "vi-VN";
      recognition.maxAlternatives = 1;

      shouldListenRef.current = true;

      recognition.onstart = () => {
        setStatus("recording");
      };

      recognition.onresult = (event) => {
        let finalChunk = "";
        let interimChunk = "";

        for (let i = event.resultIndex; i < event.results.length; ++i) {
          const res = event.results[i];
          if (res.isFinal) {
            finalChunk += res[0].transcript + " ";
          } else {
            interimChunk += res[0].transcript;
          }
        }

        if (finalChunk.trim()) {
          const curTime = durationRef.current;
          const newSeq = seqRef.current++;
          finalCaptionsRef.current.push({
            seq: newSeq,
            text: finalChunk.trim(),
            isFinal: true,
            tStart: Math.max(0, curTime - 2),
            tEnd: curTime,
            inferMs: 35,
          });
        }

        // Tạo danh sách hiển thị
        const displayList = [...finalCaptionsRef.current];
        if (interimChunk.trim()) {
          displayList.push({
            seq: 999999,
            text: interimChunk.trim(),
            isFinal: false,
            inferMs: 15,
          });
        }
        setCaptions(displayList);
      };

      recognition.onerror = (event) => {
        console.warn("[WebSpeech error]:", event.error);
        if (event.error === "no-speech") {
          // Im lặng tạm thời, không phải lỗi nghiêm trọng
          return;
        }
        if (event.error === "not-allowed") {
          setErrorMsg("Bạn đã từ chối quyền truy cập Micro.");
          setStatus("error");
          shouldListenRef.current = false;
        }
      };

      recognition.onend = () => {
        // Tự động kết nối lại nếu người dùng chưa bấm dừng
        if (shouldListenRef.current) {
          try {
            recognition.start();
          } catch {}
        } else {
          setStatus("idle");
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err) {
      console.error("[WebSpeech init error]:", err);
      cleanupAudio();
      setErrorMsg(err.message || "Không thể cấp quyền Micro cho Web Speech API.");
      setStatus("error");
    }
  }, [cleanupAudio, updateAudioLevel]);

  // Kết thúc nhận diện Web Speech
  const stopRecording = useCallback(async () => {
    setStatus("stopping");
    shouldListenRef.current = false;

    // Dừng recognition
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {}
      recognitionRef.current = null;
    }

    // Dừng MediaRecorder và thu thập audio blob
    let audioBlob = null;
    if (
      mediaRecorderRef.current &&
      mediaRecorderRef.current.state !== "inactive"
    ) {
      await new Promise((resolve) => {
        mediaRecorderRef.current.onstop = () => {
          if (recordedBlobsRef.current.length > 0) {
            const mime =
              recordedBlobsRef.current[0].type || "audio/webm";
            audioBlob = new Blob(recordedBlobsRef.current, { type: mime });
          }
          resolve();
        };
        try {
          mediaRecorderRef.current.stop();
        } catch {
          resolve();
        }
      });
    }

    cleanupAudio();
    setStatus("idle");

    // Ghép toàn bộ nội dung đã nhận diện được
    const fullTranscript = finalCaptionsRef.current
      .map((c) => c.text)
      .join(" ")
      .trim();

    return {
      audioBlob,
      fullTranscript,
      captions: [...finalCaptionsRef.current],
    };
  }, [cleanupAudio]);

  // Dọn dẹp khi unmount
  useEffect(() => {
    return () => {
      shouldListenRef.current = false;
      if (recognitionRef.current) {
        try {
          recognitionRef.current.stop();
        } catch {}
      }
      cleanupAudio();
    };
  }, [cleanupAudio]);

  return {
    status,
    isRecording: status === "recording",
    captions,
    duration,
    audioLevel,
    errorMsg,
    startRecording,
    stopRecording,
  };
}
