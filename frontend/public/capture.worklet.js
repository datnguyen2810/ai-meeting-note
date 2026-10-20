// capture.worklet.js
// Chạy trong AudioWorkletGlobalScope. Biến sampleRate là toàn cục do browser cấp.
class CaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / 16000; // = 1 nếu browser đã resample hộ về 16kHz
    this.prev = 0;                  // mẫu cuối của block trước (cho nội suy)
    this.phase = 0;                 // pha nội suy, luôn trong [0, 1)
    this.frame = new Int16Array(320); // 20ms @ 16kHz (320 mẫu)
    this.n = 0;
    this.accum = [];                // gom 10 frame = 200ms trước khi gửi
    this.stopped = false;
    this.port.onmessage = (event) => {
      if (event.data?.type !== "flush") return;
      this.stopped = true;
      const size = this.accum.length * 320 + this.n;
      if (size > 0) {
        const out = new Int16Array(size);
        this.accum.forEach((frame, index) => out.set(frame, index * 320));
        out.set(this.frame.subarray(0, this.n), this.accum.length * 320);
        this.port.postMessage(out.buffer, [out.buffer]);
      }
      this.accum = [];
      this.n = 0;
      this.port.postMessage({ type: "flushed" });
    };
  }

  flushFrame() {
    this.accum.push(this.frame.slice());
    if (this.accum.length === 10) {
      // 3.200 mẫu Int16 = 6.400 byte (200ms), không gửi từng frame nhỏ lẻ
      const out = new Int16Array(3200);
      this.accum.forEach((f, i) => out.set(f, i * 320));
      this.port.postMessage(out.buffer, [out.buffer]); // zero-copy transfer
      this.accum = [];
    }
    this.n = 0;
  }

  process(inputs) {
    if (this.stopped) return true;
    const input = inputs[0];
    if (!input || input.length === 0) return true; // mic im lặng hoặc chưa sẵn sàng

    // Mix mono: lấy trung bình các kênh đầu vào
    const chans = input;
    const len = chans[0].length;
    const mono = new Float32Array(len);
    for (let c = 0; c < chans.length; c++) {
      const ch = chans[c];
      for (let i = 0; i < len; i++) {
        mono[i] += ch[i] / chans.length;
      }
    }

    for (let i = 0; i < len; i++) {
      const cur = mono[i];
      if (this.ratio === 1) {
        // Đường thẳng — browser đã tự resample về 16kHz. Copy trực tiếp.
        const s = Math.max(-32768, Math.min(32767, Math.round(cur * 32767)));
        this.frame[this.n++] = s;
        if (this.n === 320) this.flushFrame();
      } else {
        // Nội suy tuyến tính: hạ mẫu từ sampleRate gốc về 16kHz
        while (this.phase < 1) {
          const v = this.prev + (cur - this.prev) * this.phase;
          const s = Math.max(-32768, Math.min(32767, Math.round(v * 32767)));
          this.frame[this.n++] = s;
          if (this.n === 320) this.flushFrame();
          this.phase += this.ratio;
        }
        this.phase -= 1;
      }
      this.prev = cur;
    }
    return true;
  }
}

registerProcessor("capture-processor", CaptureProcessor);
