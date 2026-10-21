# Kiến trúc và chức năng

## Tổng quan

Hệ thống hỗ trợ hai cách tạo biên bản:

1. **Họp trực tiếp:** trình duyệt lấy âm thanh microphone, gửi PCM qua WebSocket để hiện phụ đề gần thời gian thực. Khi dừng, toàn bộ âm thanh được đóng gói thành WAV và gửi lại AI Service để tạo bản ghi đầy đủ cùng tóm tắt.
2. **Tải tệp âm thanh:** người dùng gửi tệp WAV/MP3/M4A (AI Service còn hỗ trợ OGG/FLAC); AI Service trả transcript và tóm tắt, sau đó Frontend lưu phiên họp vào Backend.

```text
Browser (React/Vite)
 ├─ /api/* ───────────────► Spring Boot ───────────────► PostgreSQL
 │                              │
 │                              └─ HTTP /api/transcribe ─► FastAPI AI Service
 │
 ├─ WebSocket /ws/live-stream ─────────────────────────► FastAPI AI Service
 └─ HTTP /api/transcribe (tải tệp / hậu xử lý trực tiếp) ► FastAPI AI Service
```

Trong chế độ phát triển, Vite proxy các yêu cầu `/api` sang Backend cổng 8080. Riêng WebSocket và API AI trong các component hiện trỏ trực tiếp đến cổng 8000.

## Frontend

Điểm vào là `frontend/src/main.jsx` và `App.jsx`. Ứng dụng có ba trạng thái màn hình: landing, đăng nhập/đăng ký, và dashboard sau khi đăng nhập.

Các chức năng chính:

- Lưu JWT và thông tin người dùng vào `localStorage`.
- Tạo, xem, tìm kiếm, xóa mềm lịch sử cuộc họp và tải biên bản Markdown.
- `LiveMeetingRoom`: thu microphone, hiển thị phụ đề, gửi WAV hậu xử lý, sau đó lưu phiên hoàn chỉnh.
- `SpeechToTextDemo`: tải tệp âm thanh, hiển thị transcript/tóm tắt và lưu lịch sử.
- `useLiveTranscription`: quản lý AudioContext, AudioWorklet, WebSocket, timer và trạng thái phụ đề.

`capture.worklet.js` trộn audio về mono, nội suy/resample về 16 kHz, mã hóa PCM Int16 và gom 10 frame 20 ms thành một gói 200 ms trước khi gửi.

## Backend

Backend cung cấp REST API, kiểm soát truy cập bằng JWT dạng Bearer token, quản lý cuộc họp và lưu dữ liệu vào PostgreSQL. Các lớp được chia theo cấu trúc Spring quen thuộc: `controller` → `service` → `repository` → `entity`.

- `AuthService`: đăng ký, mã hóa mật khẩu bằng BCrypt và đăng nhập.
- `MeetingService`: tạo/cập nhật/xóa mềm cuộc họp, quản lý thành viên, lưu trọn phiên xử lý.
- `AudioService`: kiểm tra định dạng, ghi tệp âm thanh vào `uploads/audio/<meetingId>/`.
- `SttService` và `AiServiceClient`: gọi FastAPI với multipart audio, theo dõi trạng thái xử lý.
- `MeetingNoteService`: tạo/chỉnh sửa biên bản và action item.

Mọi API, trừ `/api/auth/**`, yêu cầu xác thực. Lỗi validation, đăng nhập, quá dung lượng và lỗi nghiệp vụ được chuẩn hóa bằng `ApiResponse` trong `GlobalExceptionHandler`.

## AI Service

FastAPI nạp mô hình một lần trong lifespan của ứng dụng:

| Nhiệm vụ | Mô hình | Cách dùng |
| --- | --- | --- |
| ASR trực tiếp | `nguyenvulebinh/wav2vec2-base-vietnamese-250h` | Decode caption interim/final cho các cụm giọng nói |
| ASR hậu xử lý | `vinai/PhoWhisper-small` | Phiên âm đầy đủ tệp audio |
| Tóm tắt | `Qwen/Qwen2.5-1.5B-Instruct` | Sinh tóm tắt tiếng Việt có mục đích, kết quả, vấn đề và phân công |

Một `asyncio.Lock` bảo vệ GPU; batch transcription bị từ chối với HTTP 409 khi đang có phiên live để tránh tranh chấp tài nguyên. Service chọn CUDA nếu khả dụng, nếu không chạy CPU.

Xem chi tiết ở [luồng xử lý âm thanh](audio-processing.md).
