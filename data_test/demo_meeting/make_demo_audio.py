"""Tạo audio cuộc họp nhiều người nói từ kịch bản, kèm đáp án thời gian.

Dùng để demo và thử pipeline phân người nói + tóm tắt + chat. Giọng tổng hợp sạch
hơn giọng thật nhiều, nên kết quả trên file này KHÔNG thay thế đánh giá bằng người thật.

Cài đặt (nên dùng venv riêng, không cần cài vào ai-service/venv):
    python -m venv ttsenv
    .\\ttsenv\\Scripts\\python.exe -m pip install edge-tts soundfile numpy

Chạy (cần Internet, edge-tts gọi dịch vụ đọc của Microsoft):
    .\\ttsenv\\Scripts\\python.exe data_test\\demo_meeting\\make_demo_audio.py

Kết quả trong cùng thư mục với script:
    demo_meeting.wav             audio mono PCM 16-bit
    demo_meeting_reference.json  ai nói, từ giây nào đến giây nào, nội dung
    demo_meeting_reference.txt   bản dễ đọc có mốc thời gian
    demo_meeting_transcript.txt  chỉ lời nói, dùng làm --reference khi đo WER
"""

import argparse
import asyncio
import json
import os
import tempfile

import edge_tts
import numpy as np
import soundfile as sf

# Mỗi người một giọng. Tiếng Việt chỉ có hai giọng Microsoft, nên người thứ ba
# dùng lại giọng nữ rồi kéo giãn tín hiệu trên máy: stretch 1.18 nghĩa là chậm
# hơn 18% và trầm hơn khoảng 3 nửa cung, nghe như một người nữ khác.
# Đã thử hai giọng nam cùng gốc NamMinh (chỉ khác stretch): bộ phân người bằng
# pitch/MFCC không tách được, nên không dùng cách đó.
# Không dùng tham số rate/pitch của edge-tts vì giọng NamMinh kèm tham số này
# thường không trả audio.
SPEAKERS = {
    "ha": {"name": "Hà", "voice": "vi-VN-HoaiMyNeural", "stretch": 1.0},
    "khoa": {"name": "Khoa", "voice": "vi-VN-NamMinhNeural", "stretch": 1.0},
    "lan": {"name": "Lan", "voice": "vi-VN-HoaiMyNeural", "stretch": 1.18},
}

# Kịch bản: Hà chủ trì, Khoa và Lan báo cáo. Tuấn được giao việc nhưng không
# có mặt, để thử phân biệt người phát biểu với người được nhắc tên.
# Số và ngày viết bằng chữ để bản đáp án khớp cách đọc. Tránh từ tiếng Anh (file,
# demo, chatbot...): giọng tiếng Việt của edge-tts có câu chứa từ này không trả audio.
DIALOGUE = [
    ("ha", "Chào mọi người, hôm nay mình họp nhanh để chốt tiến độ đồ án ghi chú cuộc họp trước buổi báo cáo. "
           "Mục tiêu là thống nhất phần nào đã xong, phần nào còn thiếu và phân công cho tuần tới."),
    ("khoa", "Bên mình đã hoàn thành phần nhận dạng giọng nói. Hệ thống chuyển được tệp ghi âm thành văn bản "
             "tiếng Việt, độ chính xác khá ổn với giọng đọc rõ ràng."),
    ("lan", "Phần giao diện cũng đã xong trang lịch sử cuộc họp. Người dùng có thể mở lại bản ghi, "
              "xem tóm tắt và xuất kết quả ra tệp văn bản."),
    ("ha", "Tốt quá, cảm ơn hai bạn. Vậy hiện giờ nhóm mình đang vướng ở chỗ nào nhiều nhất, "
           "có việc gì cần xử lý gấp không?"),
    ("khoa", "Vấn đề lớn nhất là phân biệt người nói. Khi hai người có giọng gần giống nhau, "
             "hệ thống đôi khi gán nhầm lời của người này sang người kia."),
    ("lan", "Ngoài ra trợ lý hỏi đáp vẫn còn chậm. Mỗi câu hỏi mất khoảng mười lăm giây mới trả lời, "
              "nên lúc trình diễn có thể làm thầy phải chờ lâu."),
    ("ha", "Vậy mình quyết định thế này. Nhóm sẽ giữ mô hình hiện tại cho buổi báo cáo, "
           "không đổi sang mô hình mới vì không đủ thời gian kiểm thử."),
    ("khoa", "Mình đồng ý. Mình sẽ thu thêm năm đoạn ghi âm của người thật để đánh giá lại "
             "phần phân biệt người nói, hạn là thứ Sáu tuần này."),
    ("lan", "Còn mình sẽ tối ưu trợ lý hỏi đáp để thời gian trả lời dưới mười giây, "
              "đồng thời hiển thị đoạn nguồn bên cạnh câu trả lời."),
    ("ha", "Được. Ngoài ra Tuấn sẽ phụ trách viết báo cáo và làm bài trình chiếu, "
           "hạn nộp là ngày hai mươi tháng mười một. Mình sẽ nhắn riêng cho Tuấn sau buổi họp."),
    ("khoa", "Nhân tiện, mình đề xuất cả nhóm chạy thử toàn bộ hệ thống trên máy của Lan vào tối thứ Năm, "
             "để kiểm tra trước khi báo cáo."),
    ("lan", "Tối thứ Năm mình rảnh. Mình sẽ chuẩn bị sẵn một cuộc họp mẫu trong lịch sử "
              "để phòng khi trình diễn trực tiếp bị lỗi."),
    ("ha", "Vậy chốt lại: Khoa đánh giá phân biệt người nói trước thứ Sáu, Lan tối ưu trợ lý hỏi đáp, "
           "Tuấn làm báo cáo trước ngày hai mươi tháng mười một, và cả nhóm chạy thử vào tối thứ Năm. "
           "Cảm ơn mọi người, kết thúc buổi họp."),
]

# Khoảng nghỉ giữa các lượt (giây), lặp vòng để nhịp không đều như họp thật.
PAUSES = [0.7, 0.9, 0.6, 1.0, 0.8]
LEAD_SILENCE = 0.5
TAIL_SILENCE = 0.8


async def synthesize(text, cfg, path, retries=3):
    for attempt in range(1, retries + 1):
        try:
            await edge_tts.Communicate(text, cfg["voice"]).save(path)
            return
        except Exception as exc:  # mạng chập chờn: thử lại
            if attempt == retries:
                raise RuntimeError(
                    f"Không tạo được giọng {cfg['voice']} cho câu: {text[:60]}... ({exc}). "
                    "Nếu lỗi lặp lại, thử bỏ từ tiếng Anh hoặc tách câu."
                ) from exc
            await asyncio.sleep(2 * attempt)


def load_mono(path):
    audio, sr = sf.read(path, dtype="float32", always_2d=True)
    return audio.mean(axis=1), sr


def stretch(audio, factor):
    """Kéo giãn tín hiệu: factor > 1 làm giọng chậm và trầm hơn cùng lúc."""
    if abs(factor - 1.0) < 1e-6:
        return audio
    n_out = int(round(len(audio) * factor))
    src = np.linspace(0, len(audio) - 1, n_out)
    return np.interp(src, np.arange(len(audio)), audio).astype(np.float32)


def trim_silence(audio, sr, rel_db=-40.0, pad_s=0.05):
    """Cắt khoảng lặng đầu/cuối để mốc thời gian đáp án bám sát tiếng nói."""
    frame = max(1, int(sr * 0.01))
    n = len(audio) // frame
    if n == 0:
        return audio
    rms = np.sqrt(np.mean(audio[: n * frame].reshape(n, frame) ** 2, axis=1) + 1e-12)
    voiced = np.where(20 * np.log10(rms / rms.max()) > rel_db)[0]
    if len(voiced) == 0:
        return audio
    pad = int(sr * pad_s)
    start = max(0, voiced[0] * frame - pad)
    end = min(len(audio), (voiced[-1] + 1) * frame + pad)
    return audio[start:end]


def fmt(t):
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


async def build(out_dir, name):
    os.makedirs(out_dir, exist_ok=True)
    clips, sr = [], None
    with tempfile.TemporaryDirectory() as tmp:
        for i, (key, text) in enumerate(DIALOGUE):
            path = os.path.join(tmp, f"turn_{i:02d}.mp3")
            await synthesize(text, SPEAKERS[key], path)
            audio, clip_sr = load_mono(path)
            if sr is None:
                sr = clip_sr
            elif clip_sr != sr:
                raise RuntimeError(f"Tần số mẫu không đồng nhất: {clip_sr} khác {sr}")
            clips.append(stretch(trim_silence(audio, sr), SPEAKERS[key]["stretch"]))
            print(f"[{i + 1}/{len(DIALOGUE)}] {SPEAKERS[key]['name']}: {len(clips[-1]) / sr:.1f}s")

    # Nhãn Người 1, 2, ... theo thứ tự xuất hiện, giống quy ước của hệ thống.
    order = list(dict.fromkeys(key for key, _ in DIALOGUE))
    label_of = {key: f"Người {i + 1}" for i, key in enumerate(order)}
    id_of = {key: f"speaker_{i + 1}" for i, key in enumerate(order)}

    parts = [np.zeros(int(sr * LEAD_SILENCE), dtype=np.float32)]
    cursor = LEAD_SILENCE
    segments = []
    for i, ((key, text), clip) in enumerate(zip(DIALOGUE, clips)):
        start = cursor
        end = start + len(clip) / sr
        segments.append({
            "segment_id": f"ref_{i + 1:02d}",
            "speaker_id": id_of[key],
            "label": label_of[key],
            "name": SPEAKERS[key]["name"],
            "start_seconds": round(start, 2),
            "end_seconds": round(end, 2),
            "text": text,
        })
        parts.append(clip)
        cursor = end
        gap = TAIL_SILENCE if i == len(DIALOGUE) - 1 else PAUSES[i % len(PAUSES)]
        parts.append(np.zeros(int(sr * gap), dtype=np.float32))
        cursor += gap

    audio = np.concatenate(parts)
    peak = float(np.max(np.abs(audio)))
    if peak > 0:
        audio = audio * (0.9 / peak)  # chuẩn hóa âm lượng, tránh vỡ tiếng
    duration = len(audio) / sr

    wav_path = os.path.join(out_dir, f"{name}.wav")
    sf.write(wav_path, audio, sr, subtype="PCM_16")

    speakers = [{
        "speaker_id": id_of[k],
        "label": label_of[k],
        "name": SPEAKERS[k]["name"],
        "voice": SPEAKERS[k]["voice"],
        "stretch": SPEAKERS[k]["stretch"],
        "first_start_seconds": next(s["start_seconds"] for s in segments if s["speaker_id"] == id_of[k]),
    } for k in order]

    reference = {
        "audio": os.path.basename(wav_path),
        "sample_rate": sr,
        "duration_seconds": round(duration, 2),
        "note": "Giọng tổng hợp edge-tts; mốc thời gian lấy từ lúc ghép, sai số khoảng 0,05 giây ở biên.",
        "absent_but_mentioned": ["Tuấn"],
        "speakers": speakers,
        "segments": segments,
    }
    with open(os.path.join(out_dir, f"{name}_reference.json"), "w", encoding="utf-8") as f:
        json.dump(reference, f, ensure_ascii=False, indent=2)

    with open(os.path.join(out_dir, f"{name}_reference.txt"), "w", encoding="utf-8") as f:
        f.write(f"Thời lượng: {fmt(duration)} | {len(order)} người nói | {len(segments)} lượt\n")
        for sp in speakers:
            f.write(f"{sp['label']} = {sp['name']} ({sp['voice']}, stretch {sp['stretch']})\n")
        f.write("Tuấn được giao việc nhưng không phát biểu.\n\n")
        for s in segments:
            f.write(f"[{fmt(s['start_seconds'])} - {fmt(s['end_seconds'])}] {s['label']} ({s['name']}): {s['text']}\n")

    with open(os.path.join(out_dir, f"{name}_transcript.txt"), "w", encoding="utf-8") as f:
        f.write(" ".join(s["text"] for s in segments) + "\n")

    print(f"\nĐã tạo {wav_path} ({fmt(duration)}, {sr} Hz)")
    return reference


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out-dir", default=os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument("--name", default="demo_meeting")
    args = parser.parse_args()
    asyncio.run(build(args.out_dir, args.name))


if __name__ == "__main__":
    main()
