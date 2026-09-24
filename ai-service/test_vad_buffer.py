"""
Test cho vad_buffer.py — chạy trực tiếp, không cần pytest:

    python test_vad_buffer.py

Bao phủ 7 nhóm: chốt chặn frame chết, peek() không phá huỷ buffer, buffer rỗng,
mic tắt tiếng, vòng lặp interim, cắt cưỡng bức, và độ bền với nhiễu phòng họp.

Ghi chú về các ngưỡng trong test: âm thanh tổng hợp ở đây dùng mức nền nhiễu
σ=2.0 cho khoảng nghỉ, KHÔNG phải số 0 tuyệt đối. Lý do: đo trên audio thật
(VIVOSDEV01_R089.wav) cho thấy frame im lặng thật có RMS p50 = 1.3, tức là có
mức nền nhiễu chứ không phải im lặng số. Dùng số 0 tuyệt đối sẽ test nhầm một
tình huống không tồn tại, và bỏ sót hành vi dương tính giả của webrtcvad.
"""

import io
import os
import sys

import numpy as np

# Console Windows mặc định cp1252 -> không in được tiếng Việt
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from vad_buffer import FRAME_BYTES, FRAME_SAMPLES, UtteranceBuffer, VadGate  # noqa: E402

RNG = np.random.default_rng(42)
ok = fail = 0
def check(name, cond, extra=''):
    global ok, fail
    if cond: ok += 1;  print(f'  PASS  {name}')
    else:    fail += 1; print(f'  FAIL  {name}   {extra}')

def tone(n, amp=8000, f=220.0):
    out = []
    for i in range(n):
        t = np.arange(FRAME_SAMPLES) / 16000.0
        out.append((amp*np.sin(2*np.pi*f*t + i*0.1)).astype(np.int16).tobytes())
    return out

def pause(n, floor=2.0):
    """Khoang nghi THAT: muc nen rat thap (do tren VIVOS: p50 RMS = 1.3)."""
    return [(RNG.normal(0, floor, FRAME_SAMPLES)).astype(np.int16).tobytes() for _ in range(n)]

def dead(n):
    """Mic bi tat tieng: Chrome gui toan so 0."""
    return [np.zeros(FRAME_SAMPLES, dtype=np.int16).tobytes() for _ in range(n)]

print('=== 1. Chot chan frame "chet" (mic tat tieng) ===')
g = VadGate()
check('backend = webrtcvad', g.backend == 'webrtcvad', g.backend)
check('zeros -> KHONG phai tieng noi', g.is_speech(dead(1)[0]) is False)
check('tone  -> LA tieng noi',          g.is_speech(tone(1)[0]) is True)

print()
print('=== 2. peek() khong pha huy buffer ===')
buf = UtteranceBuffer(gate=VadGate())
for f in tone(100): buf.push(f)                       # 2.0s tieng noi
p1, p2 = buf.peek(), buf.peek()
check('peek() tra ve dung 100 frame',
      p1 is not None and len(p1) == 100*FRAME_SAMPLES, None if p1 is None else len(p1))
check('peek() lan 2 giong lan 1 (khong tieu hao)',
      p2 is not None and len(p2) == len(p1))
utt = None
for f in pause(40):                                   # 0.8s nghi
    r = buf.push(f)
    if r is not None: utt = r
check('sau peek(), flush() VAN hoat dong', utt is not None)
if utt:
    # Flush o lan nghi >=350ms dau tien -> tong trong [100+18, 100+40].
    # Vai frame nghi bi duong tinh gia nen moc flush lech vai frame.
    check('  flush sau khi gap khoang nghi', 118 <= utt.total_frames <= 140, utt.total_frames)
    check('  tieng noi giu nguyen (100 +-3)', 97 <= utt.speech_frames <= 103, utt.speech_frames)
    check('  audio khop so frame', len(utt.audio) == utt.total_frames*FRAME_SAMPLES)

print()
print('=== 3. peek() tren buffer rong ===')
b2 = UtteranceBuffer(gate=VadGate())
check('buffer rong -> None', b2.peek() is None)
for f in pause(50): b2.push(f)
check('chi co im lang -> van None', b2.peek() is None)

print()
print('=== 4. Mic tat tieng KHONG sinh cum rac (lo hong vua vá) ===')
b3 = UtteranceBuffer(gate=VadGate())
em = [r for r in (b3.push(f) for f in dead(500)) if r is not None]
check('500 frame zeros -> 0 cum', len(em) == 0, f'{len(em)} cum')
check('buffer van rong', b3.peek() is None)
check('khong co cat cuong buc', b3.force_flushes == 0, b3.force_flushes)

print()
print('=== 5. Vong lap interim 700ms ===')
b4 = UtteranceBuffer(gate=VadGate())
interims, final = [], None
for i, f in enumerate(tone(400) + pause(40)):         # 8.0s noi + 0.8s nghi
    if (i+1)*20 % 700 == 0:
        a = b4.peek()
        if a is not None and len(a) >= FRAME_SAMPLES*5:
            interims.append(len(a)/16000)
    r = b4.push(f)
    if r is not None: final = r
check('co >=5 interim cho cau 8s', len(interims) >= 5, len(interims))
check('interim dau tien < 1.0s', interims[0] < 1.0, interims[0])
check('final xuat hien', final is not None)
if final:
    check('final ~8.0-8.8s (tieng noi + lang duoi)', 8.0 <= final.duration <= 8.8, final.duration)
    check('  giu du 8.0s tieng noi', final.speech_frames >= 397, final.speech_frames)
print(f'    -> {len(interims)} interim, dau {interims[0]:.2f}s, cuoi {interims[-1]:.2f}s')

print()
print('=== 6. Cat cuong buc khi noi lien tuc 10s ===')
b5 = UtteranceBuffer(gate=VadGate(), max_utterance_ms=8000)
em = [r for r in (b5.push(f) for f in tone(500)) if r is not None]
check('co cum bi cat cuong buc', len(em) >= 1, len(em))
check('force_flushes duoc dem', b5.force_flushes >= 1, b5.force_flushes)
if em: check('cum dau <= 8s (tran cung)', em[0].duration <= 8.0, em[0].duration)

print()
print('=== 7. Do ben voi nhieu phong hop ===')
for sigma in [1, 5, 20, 80]:
    b = UtteranceBuffer(gate=VadGate()); segs = []
    for _ in range(4):
        for f in tone(200) + pause(50, floor=sigma):
            r = b.push(f)
            if r is not None: segs.append(r)
    r = b.flush()
    if r is not None: segs.append(r)
    check(f'muc nen sigma={sigma:>3} -> dung 4 cum, 0 cat cuong buc',
          len(segs) == 4 and b.force_flushes == 0,
          f'{len(segs)} cum, {b.force_flushes} cat cuong buc')

print()
print('=== 8. Chan frame sai kich thuoc ===')
b6 = UtteranceBuffer(gate=VadGate())
for bad in [b'\x00' * 100, b'\x00' * (FRAME_BYTES - 1), b'\x00' * (FRAME_BYTES + 1), b'']:
    try:
        b6.push(bad)
        check(f'frame {len(bad)} byte -> phai raise ValueError', False, 'khong raise')
    except ValueError:
        check(f'frame {len(bad):>4} byte -> raise ValueError', True)
check('frame dung 640 byte -> khong raise',
      b6.push(b'\x00' * FRAME_BYTES) is None)

print()
print(f'===== KET QUA: {ok} PASS / {fail} FAIL =====')
sys.exit(1 if fail else 0)
