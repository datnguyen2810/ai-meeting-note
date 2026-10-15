import { useState, useRef, useCallback, useEffect } from "react";
import { encodeWav } from "../utils/encodeWav";

const WS_URL = "ws://localhost:8000/ws/live-stream";

/**
 * Custom hook quản lý Live Stream ASR qua WebSocket và AudioWorklet
 */
export function useLiveTranscription() {
  const [status, setStatus] = useState("idle"); // 'idle' | 'connecting' | 'recording' | 'stopping' | 'error'
  const [captions, setCaptions] = useState([]);
  const [duration, setDuration] = useState(0);
  const [audioLevel, setAudioLevel] = useState(0);
  const [lagWarning, setLagWarning] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);

  const wsRef = useRef(null);
  const audioCtxRef = useRef(null);
  const streamRef = useRef(null);
  const workletNodeRef = useRef(null);
  const analyserRef = useRef(null);
  const animFrameRef = useRef(null);
  const timerRef = useRef(null);
  const chunksRef = useRef([]);
  const resolveStopRef = useRef(null);

  // Dọn dẹp tài nguyên âm thanh và kết nối
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
    if (workletNodeRef.current) {
      workletNodeRef.current.disconnect();
      workletNodeRef.current = null;
    }
    if (audioCtxRef.current && audioCtxRef.current.state !== "closed") {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    setAudioLevel(0);
  }, []);

  // Vòng lặp cập nhật mức âm thanh (Visualizer / Waveform)
  const updateAudioLevel = useCallback(() => {
    if (!analyserRef.current) return;
    const dataArray = new Uint8Array(analyserRef.current.frequencyBinCount);
    analyserRef.current.getByteFrequencyData(dataArray);

    let sum = 0;
    for (let i = 0; i < dataArray.length; i++) {
      sum += dataArray[i];
    }
    const avg = sum / dataArray.length;
    // Chuẩn hoá về thang 0 - 100
    setAudioLevel(Math.min(100, Math.round((avg / 128) * 100)));

    animFrameRef.current = requestAnimationFrame(updateAudioLevel);
  }, []);

  // Bắt đầu ghi âm và stream
  const startRecording = useCallback(async () => {
    setErrorMsg(null);
    setCaptions([]);
    setDuration(0);
    setLagWarning(false);
    chunksRef.current = [];
    setStatus("connecting");

    try {
      // 1. Tạo AudioContext
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      const ctx = new AudioContextClass({ sampleRate: 16000 });
      audioCtxRef.current = ctx;

      // 2. Nạp AudioWorklet
      try {
        await ctx.audioWorklet.addModule("/capture.worklet.js");
      } catch (workletErr) {
        console.warn("[Audio] Thử nạp worklet fallback:", workletErr);
        await ctx.audioWorklet.addModule(
          new URL("../audio/capture.worklet.js", import.meta.url)
        );
      }

      // 3. Xin quyền Microphone
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
      streamRef.current = stream;

      // 4. Tạo Audio Nodes
      const source = ctx.createMediaStreamSource(stream);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      analyserRef.current = analyser;

      const workletNode = new AudioWorkletNode(ctx, "capture-processor");
      workletNodeRef.current = workletNode;

      // Nối source -> analyser
      source.connect(analyser);

      // Nối source -> workletNode -> gain(0) -> destination (để kích hoạt process mà không gây echo)
      const silenceGain = ctx.createGain();
      silenceGain.gain.value = 0;
      source.connect(workletNode);
      workletNode.connect(silenceGain);
      silenceGain.connect(ctx.destination);

      // 5. Kết nối WebSocket
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log("[WS] Connected to", WS_URL);
        ws.send(JSON.stringify({ type: "start", sample_rate: 16000 }));
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);

          if (msg.type === "ready") {
            console.log("[WS] Server ready! Session:", msg.session_id);
            setStatus("recording");

            // Nối cổng worklet để gửi binary audio lên socket
            workletNode.port.onmessage = (e) => {
              if (ws.readyState === WebSocket.OPEN) {
                const chunkArray = new Int16Array(e.data);
                chunksRef.current.push(chunkArray);
                ws.send(e.data); // Gửi ArrayBuffer Int16 PCM
              }
            };

            // Bật đo waveform và đếm thời gian
            updateAudioLevel();
            timerRef.current = setInterval(() => {
              setDuration((prev) => prev + 1);
            }, 1000);
          } else if (msg.type === "interim") {
            // Cập nhật text tạm thời (mờ) theo seq
            setCaptions((prev) => {
              const idx = prev.findIndex((c) => c.seq === msg.seq);
              if (idx !== -1) {
                const updated = [...prev];
                updated[idx] = {
                  ...updated[idx],
                  text: msg.text,
                  isFinal: false,
                  inferMs: msg.infer_ms,
                };
                return updated;
              } else {
                return [
                  ...prev,
                  {
                    seq: msg.seq,
                    text: msg.text,
                    isFinal: false,
                    inferMs: msg.infer_ms,
                  },
                ];
              }
            });
          } else if (msg.type === "final") {
            // Thay thế interim cùng seq thành final (đậm)
            setCaptions((prev) => {
              const idx = prev.findIndex((c) => c.seq === msg.seq);
              const finalItem = {
                seq: msg.seq,
                text: msg.text,
                isFinal: true,
                tStart: msg.t_start,
                tEnd: msg.t_end,
                vadRatio: msg.vad_ratio,
                inferMs: msg.infer_ms,
              };
              if (idx !== -1) {
                const updated = [...prev];
                updated[idx] = finalItem;
                return updated;
              } else {
                return [...prev, finalItem];
              }
            });
          } else if (msg.type === "lag") {
            setLagWarning(true);
            setTimeout(() => setLagWarning(false), 3000);
          } else if (msg.type === "error") {
            console.error("[WS] Server error:", msg.message);
            setErrorMsg(msg.message);
          } else if (msg.type === "closed") {
            console.log("[WS] Session closed. Total segments:", msg.total_segments);
            // Đóng gói WAV từ toàn bộ chunks tích lũy
            const wavBlob = encodeWav(chunksRef.current, 16000);
            cleanupAudio();
            setStatus("idle");
            if (resolveStopRef.current) {
              resolveStopRef.current({
                wavBlob,
                captions: captions,
              });
              resolveStopRef.current = null;
            }
          }
        } catch (err) {
          console.error("[WS] Parse message error:", err);
        }
      };

      ws.onerror = (err) => {
        console.error("[WS] Error:", err);
        setErrorMsg("Lỗi kết nối WebSocket tới AI Service (Port 8000).");
        setStatus("error");
        cleanupAudio();
      };

      ws.onclose = () => {
        console.log("[WS] Connection closed.");
        cleanupAudio();
        setStatus("idle");
      };
    } catch (err) {
      console.error("[Live] Failed to start:", err);
      let msg = "Không thể truy cập Microphone hoặc khởi động âm thanh.";
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        msg = "Trình duyệt chưa được cấp quyền micro. Vui lòng bật quyền micro trong cài đặt.";
      }
      setErrorMsg(msg);
      setStatus("error");
      cleanupAudio();
    }
  }, [cleanupAudio, updateAudioLevel, captions]);

  // Kết thúc cuộc họp
  const stopRecording = useCallback(() => {
    return new Promise((resolve) => {
      setStatus("stopping");
      resolveStopRef.current = resolve;

      // Dừng mic ngay lập tức để tắt đèn micro
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((track) => track.stop());
      }

      // Gửi stop lên server
      if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "stop" }));
      } else {
        // Nếu socket đã đóng sẵn, đóng gói luôn
        const wavBlob = encodeWav(chunksRef.current, 16000);
        cleanupAudio();
        setStatus("idle");
        resolve({ wavBlob, captions });
      }
    });
  }, [cleanupAudio, captions]);

  // Cleanup khi component unmount
  useEffect(() => {
    return () => {
      cleanupAudio();
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [cleanupAudio]);

  return {
    status,
    isRecording: status === "recording",
    captions,
    duration,
    audioLevel,
    lagWarning,
    errorMsg,
    startRecording,
    stopRecording,
  };
}
