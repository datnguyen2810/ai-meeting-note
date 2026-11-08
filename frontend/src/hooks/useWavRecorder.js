import { useCallback, useEffect, useRef } from "react";
import { encodeWav } from "../utils/encodeWav";
import { flushCapture } from "../utils/flushCapture";

/**
 * Ghi âm micro thành WAV PCM 16-bit mono 16 kHz, không cần WebSocket.
 *
 * Dùng lại AudioWorklet `capture-processor` của luồng ghi âm trực tiếp. Không dùng
 * MediaRecorder vì Chrome tạo WebM/Opus, mà AI service không giải mã được WebM nếu
 * máy chưa cài FFmpeg.
 *
 * start(): xin quyền micro và bắt đầu thu.
 * stop():  đợi worklet gửi hết phần đệm cuối rồi trả về Blob WAV (null nếu chưa thu).
 */
export function useWavRecorder() {
  const ctxRef = useRef(null);
  const streamRef = useRef(null);
  const nodeRef = useRef(null);
  const chunksRef = useRef([]);

  const release = useCallback(() => {
    try {
      nodeRef.current?.disconnect();
    } catch {
      // node đã ngắt
    }
    streamRef.current?.getTracks().forEach((track) => track.stop());
    if (ctxRef.current && ctxRef.current.state !== "closed") {
      ctxRef.current.close().catch(() => {});
    }
    nodeRef.current = null;
    streamRef.current = null;
    ctxRef.current = null;
  }, []);

  const start = useCallback(async () => {
    release();
    chunksRef.current = [];

    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    const ctx = new AudioContextClass({ sampleRate: 16000 });
    ctxRef.current = ctx;
    try {
      try {
        await ctx.audioWorklet.addModule("/capture.worklet.js");
      } catch {
        await ctx.audioWorklet.addModule(new URL("../audio/capture.worklet.js", import.meta.url));
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
      });
      streamRef.current = stream;

      const source = ctx.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(ctx, "capture-processor");
      nodeRef.current = node;
      node.port.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) chunksRef.current.push(new Int16Array(event.data));
      };

      // Nối qua gain 0 để worklet chạy mà không phát tiếng ra loa
      const mute = ctx.createGain();
      mute.gain.value = 0;
      source.connect(node);
      node.connect(mute);
      mute.connect(ctx.destination);
    } catch (err) {
      release();
      throw err;
    }
  }, [release]);

  const stop = useCallback(async () => {
    if (!nodeRef.current) return null;
    const flushed = await flushCapture(nodeRef.current);
    if (!flushed) console.warn("[Audio] Không nhận được xác nhận gửi hết bộ đệm âm thanh.");
    release();
    const chunks = chunksRef.current;
    chunksRef.current = [];
    return chunks.length ? encodeWav(chunks, 16000) : null;
  }, [release]);

  useEffect(() => release, [release]);

  return { start, stop };
}
