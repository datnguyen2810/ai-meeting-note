"""
VAD gate + gom cụm từ cho streaming ASR.

Module này được dùng chung bởi HAI nơi:
  - models_testing/benchmark_chunking.py   (Phase 0 — đo WER & độ trễ)
  - ai-service/main.py                     (Phase 1 — WebSocket live stream)

Cố ý đặt ở ai-service/ và import từ benchmark, KHÔNG copy sang models_testing/.
Lý do: nếu benchmark và production dùng hai bản logic khác nhau thì số liệu đo
được ở Phase 0 sẽ không còn đúng cho hệ thống thật. Một nguồn sự thật duy nhất.

Đơn vị thời gian: mọi mốc t_start/t_end tính theo THỜI GIAN ÂM THANH
(số frame đã đẩy vào), không phải thời gian đồng hồ treo tường. Nhờ vậy kết quả
có tính tất định và test được mà không cần inject clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

# ---------------------------------------------------------------- hằng số
SAMPLE_RATE = 16000
FRAME_MS = 20
FRAME_SAMPLES = SAMPLE_RATE * FRAME_MS // 1000  # 320
FRAME_BYTES = FRAME_SAMPLES * 2  # 640 byte Int16

DEFAULT_SILENCE_MS = 350  # im lặng bao lâu thì cắt cụm từ
DEFAULT_MIN_SPEECH_MS = 600  # TIẾNG NÓI thực tối thiểu; ngắn hơn thì không nhả ra

# Cắt cưỡng bức khi cụm quá dài (người nói liên tục không nghỉ).
#
# Đây là TRẦN CỨNG CHO ĐỘ TRẺ: cắt ở N giây ⇒ trễ tối đa N/2 giây.
# Đo trên data_test/test_2.mp3 (36.5s) — xem Bảng 4 mục 5.3 của plan:
#   15000ms -> 3 cụm, trễ p50 6.75s  (quá trễ)
#    8000ms -> 5 cụm, trễ p50 4.03s  (chọn giá trị này)
#    6000ms -> 7 cụm, trễ p50 3.02s  (nhanh hơn nhưng 5/7 cụm bị cắt giữa câu)
# ⬜ TV3 cần đo WER ở cả 3 mức để chốt — hạ trần làm giảm trễ nhưng có thể
#    làm tăng WER do cắt giữa câu. Chưa có số WER thì chưa được hạ tiếp.
DEFAULT_MAX_UTTERANCE_MS = 8000
DEFAULT_VAD_MODE = 2  # 0..3, càng cao càng lọc nhiễu mạnh
DEFAULT_ENERGY_THRESHOLD = 500.0  # dùng cho fallback RMS, xem VadGate

# Ngưỡng coi một frame là "chết" (im lặng số tuyệt đối, ví dụ mic bị tắt tiếng).
# Xem chú thích dài trong VadGate.is_speech để biết vì sao cần chốt chặn này.
DEAD_FRAME_RMS = 1.0


@dataclass
class Utterance:
    """Một cụm từ đã hoàn chỉnh, sẵn sàng đưa vào model."""

    audio: np.ndarray  # int16, mono, 16kHz
    t_start: float  # giây, tính theo thời gian âm thanh
    t_end: float
    speech_frames: int
    total_frames: int

    @property
    def duration(self) -> float:
        return self.total_frames * FRAME_MS / 1000.0

    @property
    def vad_ratio(self) -> float:
        """Tỉ lệ frame thực sự có tiếng nói. Thấp => nghi ngờ là nhiễu."""
        if self.total_frames == 0:
            return 0.0
        return self.speech_frames / self.total_frames


class VadGate:
    """
    Bọc webrtcvad. Nếu không cài được thì tự động lùi về ngưỡng năng lượng RMS.

    Lý do có fallback: webrtcvad là extension C, có thể cài lỗi trên Windows.
    Không để buổi demo chết vì một dependency.
    """

    def __init__(
        self,
        mode: int = DEFAULT_VAD_MODE,
        energy_threshold: float = DEFAULT_ENERGY_THRESHOLD,
        dead_frame_rms: float = DEAD_FRAME_RMS,
    ) -> None:
        self.mode = mode
        self.energy_threshold = energy_threshold
        self.dead_frame_rms = dead_frame_rms
        self._vad = None

        try:
            import webrtcvad  # type: ignore

            self._vad = webrtcvad.Vad(mode)
            self.backend = "webrtcvad"
        except Exception as exc:  # ImportError hoặc lỗi khởi tạo
            self.backend = "rms"
            self._load_error = repr(exc)

    def is_speech(self, frame: bytes) -> bool:
        if len(frame) != FRAME_BYTES:
            raise ValueError(
                f"VAD cần frame {FRAME_BYTES} byte ({FRAME_MS}ms), nhận {len(frame)} byte"
            )

        samples = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(samples**2)))

        # ── Chốt chặn frame "chết" ───────────────────────────────────────────
        # ĐO ĐƯỢC: webrtcvad mode 2 phân loại frame toàn số 0 (im lặng số tuyệt
        # đối) là TIẾNG NÓI. Đây là hành vi đã biết của webrtcvad — nó dùng đặc
        # trưng phổ, mà frame toàn 0 cho phổ suy biến nên GMM phân loại sai.
        #
        # Hệ quả nếu không chặn: mic bị tắt tiếng (Chrome gửi toàn số 0) sẽ được
        # coi là "đang nói" → buffer phình tới ngưỡng force-flush → CTC decode
        # 8 giây im lặng và nhả ra rác. Lọc theo vad_ratio KHÔNG bắt được vì
        # vad_ratio sẽ bằng 1.0 (mọi frame đều bị coi là tiếng nói).
        #
        # Ngưỡng 1.0 an toàn: đo trên audio thật, mức nền nhiễu thấp nhất là
        # RMS 26.5 (VIVOSDEV01_R089.wav, 203 frame, không frame nào < 26). Biên
        # an toàn 26× nên không thể cắt nhầm tiếng nói thật.
        if rms < self.dead_frame_rms:
            return False

        if self._vad is not None:
            return bool(self._vad.is_speech(frame, SAMPLE_RATE))

        # Fallback: ngưỡng năng lượng.
        # Kém chính xác hơn ở phòng ồn — PHẢI hiệu chỉnh energy_threshold theo
        # mic thật của máy demo (đo RMS lúc im lặng và lúc nói, chọn ngưỡng ở giữa).
        return rms > self.energy_threshold


class UtteranceBuffer:
    """
    Gom frame 20ms thành cụm từ, cắt khi gặp khoảng lặng đủ dài.

    Vì sao cắt theo VAD mà không cắt cứng theo thời gian — xem mục 3.3/3.4 của
    PLAN_REALTIME_HYBRID_ASR.md. Tóm tắt: Wav2Vec2 là model non-streaming, cắt
    cứng làm đứt từ ở biên và CTC nhả rác trên đoạn im lặng.
    """

    def __init__(
        self,
        gate: Optional[VadGate] = None,
        silence_ms: int = DEFAULT_SILENCE_MS,
        min_speech_ms: int = DEFAULT_MIN_SPEECH_MS,
        max_utterance_ms: int = DEFAULT_MAX_UTTERANCE_MS,
    ) -> None:
        self.gate = gate or VadGate()
        self.silence_ms = silence_ms
        self.min_speech_ms = min_speech_ms
        self.max_utterance_ms = max_utterance_ms

        self._frames: list[bytes] = []
        self._silence_ms = 0
        self._speech_frames = 0
        self._pushed_frames = 0  # tổng số frame đã nhận, để tính mốc thời gian
        self._t_start = 0.0
        self.force_flushes = 0  # thống kê: bao nhiêu lần phải cắt cưỡng bức

    # ------------------------------------------------------------ API chính
    def push(self, frame: bytes) -> Optional[Utterance]:
        """
        Nhận một frame 20ms. Trả về Utterance nếu cụm từ vừa hoàn chỉnh, ngược lại None.
        """
        if len(frame) != FRAME_BYTES:
            raise ValueError(
                f"cần frame {FRAME_BYTES} byte ({FRAME_MS}ms), nhận {len(frame)} byte"
            )

        is_speech = self.gate.is_speech(frame)
        self._pushed_frames += 1

        if is_speech:
            if not self._frames:
                # Bắt đầu cụm từ mới — mốc thời gian tính theo thời gian âm thanh
                self._t_start = (self._pushed_frames - 1) * FRAME_MS / 1000.0
            self._silence_ms = 0
            self._speech_frames += 1
            self._frames.append(frame)
        else:
            # Chỉ theo dõi im lặng khi đang ở trong một cụm từ
            if not self._frames:
                return None

            self._silence_ms += FRAME_MS
            self._frames.append(frame)  # giữ luôn phần lặng đuôi làm ngữ cảnh

            # Điều kiện độ dài tối thiểu đo theo TIẾNG NÓI THỰC, không phải tổng
            # độ dài buffer. Nếu đo theo tổng thì một tiếng động 0.3s + 0.5s lặng
            # sẽ lọt qua thành "cụm từ 0.8s" và CTC nhả ra rác.
            if (
                self._silence_ms >= self.silence_ms
                and self._speech_frames * FRAME_MS >= self.min_speech_ms
            ):
                return self._emit()
            # Chưa đủ tiếng nói -> giữ nguyên buffer, gộp với cụm kế tiếp

        # Chống treo: người nói liên tục không nghỉ
        if len(self._frames) * FRAME_MS >= self.max_utterance_ms:
            self.force_flushes += 1
            return self._emit()

        return None

    def flush(self) -> Optional[Utterance]:
        """Cắt cưỡng bức phần còn lại. Gọi khi kết thúc phiên."""
        if not self._frames:
            return None
        return self._emit()

    def peek(self) -> Optional[np.ndarray]:
        """
        Audio đang tích luỹ, KHÔNG cắt buffer. Dùng cho interim decode.

        Khác biệt cốt lõi với flush(): peek() là không phá huỷ (non-destructive).
        Task nền gọi hàm này mỗi ~700ms để decode phần đang nói dở, trong khi
        buffer vẫn tiếp tục nhận frame và vẫn có thể emit bình thường sau đó.

        Trả về None nếu buffer rỗng. Không copy mảng — bên gọi chỉ nên đọc.
        """
        if not self._frames:
            return None
        return np.frombuffer(b"".join(self._frames), dtype=np.int16)

    # ------------------------------------------------------------ nội bộ
    def _emit(self) -> Utterance:
        audio = np.frombuffer(b"".join(self._frames), dtype=np.int16).copy()
        total = len(self._frames)

        utt = Utterance(
            audio=audio,
            t_start=self._t_start,
            t_end=self._t_start + total * FRAME_MS / 1000.0,
            speech_frames=self._speech_frames,
            total_frames=total,
        )

        self._frames = []
        self._silence_ms = 0
        self._speech_frames = 0
        return utt

    # ------------------------------------------------------------ tiện ích
    @property
    def pending_ms(self) -> int:
        """Số ms audio đang giữ trong buffer nhưng chưa nhả ra."""
        return len(self._frames) * FRAME_MS


def pcm_to_float32(pcm: np.ndarray) -> np.ndarray:
    """Int16 -> float32 trong [-1, 1]. Dạng mà Wav2Vec2/PhoWhisper mong đợi."""
    return pcm.astype(np.float32) / 32768.0
