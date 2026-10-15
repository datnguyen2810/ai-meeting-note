/**
 * Đóng gói mảng các Int16Array thành Blob file .WAV chuẩn PCM mono 16-bit 16kHz
 * Tham khảo Phụ lục A.3 trong PLAN_REALTIME_HYBRID_ASR.md
 * @param {Int16Array[]} int16Chunks - Mảng các chunk Int16 mẫu âm thanh
 * @param {number} sampleRate - Tần số lấy mẫu (mặc định 16000)
 * @returns {Blob}
 */
export function encodeWav(int16Chunks, sampleRate = 16000) {
  const dataLen = int16Chunks.reduce((s, c) => s + c.length, 0);
  const buf = new ArrayBuffer(44 + dataLen * 2);
  const view = new DataView(buf);

  const writeStr = (off, s) => {
    for (let i = 0; i < s.length; i++) view.setUint8(off + i, s.charCodeAt(i));
  };

  writeStr(0, "RIFF");
  view.setUint32(4, 36 + dataLen * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true); // Kích thước chunk fmt (16 cho PCM)
  view.setUint16(20, 1, true); // PCM format = 1
  view.setUint16(22, 1, true); // Kênh: Mono = 1
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // Byte rate (SampleRate * Channels * BitsPerSample / 8)
  view.setUint16(32, 2, true); // Block align (Channels * BitsPerSample / 8)
  view.setUint16(34, 16, true); // Bits per sample = 16
  writeStr(36, "data");
  view.setUint32(40, dataLen * 2, true);

  let off = 44;
  for (const c of int16Chunks) {
    for (let i = 0; i < c.length; i++, off += 2) {
      view.setInt16(off, c[i], true);
    }
  }
  return new Blob([buf], { type: "audio/wav" });
}
