# Luồng xử lý âm thanh và AI

## Streaming ASR

Giao thức WebSocket dùng endpoint `ws://localhost:8000/ws/live-stream`.

1. Client mở socket và gửi JSON `{"type":"start","sample_rate":16000}`.
2. Server trả `ready` kèm `session_id`.
3. Client gửi binary PCM mono, 16-bit little-endian, 16 kHz; gói mặc định dài 200 ms.
4. Server tách thành frame 20 ms (320 mẫu / 640 byte), chạy WebRTC VAD và gom thành cụm phát ngôn.
5. Cứ khoảng 700 ms, server decode phần đệm bằng Wav2Vec2 và trả `interim`.
6. Khi im lặng đủ ngưỡng hoặc client dừng, server decode cụm hoàn chỉnh và trả `final`, gồm text, mốc thời gian audio, tỷ lệ VAD và thời gian inference.
7. Client gửi `stop`; server flush phần âm thanh còn lại, trả `closed` rồi đóng socket.

Các loại message server: `ready`, `interim`, `final`, `lag`, `error`, `closed`. Hằng số giao thức được định nghĩa trong `ai-service/ws_protocol.py`.

`UtteranceBuffer` trong `vad_buffer.py` là nguồn logic dùng chung cho production và benchmark. Ngưỡng mặc định gồm 20 ms/frame, 350 ms im lặng để cắt cụm và 600 ms tiếng nói tối thiểu. Cụm có `vad_ratio < 0.3` không được đưa vào ASR final.

## Hậu xử lý chất lượng cao

Khi người dùng kết thúc phiên live, Frontend giữ các chunk đã gửi và tạo một Blob WAV 16 kHz. Blob đó, hoặc tệp do người dùng chọn, được POST multipart đến `POST /api/transcribe` của AI Service.

FastAPI thực hiện:

1. Kiểm tra phần mở rộng: WAV, MP3, M4A, OGG, FLAC.
2. Lưu tạm tệp, dùng Librosa đọc mono 16 kHz.
3. Chạy PhoWhisper-small với `language=vietnamese` để tạo transcript đầy đủ.
4. Đưa transcript vào Qwen 2.5 1.5B với prompt biên bản có cấu trúc.
5. Trả JSON `status`, `filename`, `transcript`, `summary`, sau đó xóa tệp tạm.

Kết quả batch được hiển thị cạnh bản ghi live để người dùng đối chiếu. Frontend tự động gọi Backend `/api/meetings/save-session` để lưu transcript, summary và audio.

## Hạn chế cần lưu ý

- Các mô hình có kích thước lớn và đặc biệt phù hợp GPU; lần khởi động đầu tiên cần tải model từ Hugging Face.
- Địa chỉ AI Service và WebSocket hiện được hard-code ở một số file frontend cho môi trường local; khi deploy cần cấu hình qua biến môi trường.
- Không có speaker diarization trong luồng hiện tại; `TranscriptSegment` có trường nhãn người nói nhưng chưa được tạo từ AI Service.
