# API và mô hình dữ liệu

## Quy ước API Backend

Base URL phát triển: `http://localhost:8080`. Các API Backend trả bao bọc `ApiResponse` (thông thường gồm `success`, `message`, `data`). Ngoại trừ nhóm xác thực, gửi header:

```http
Authorization: Bearer <jwt>
```

| Nhóm | Endpoint nổi bật | Mục đích |
| --- | --- | --- |
| Auth | `POST /api/auth/register`, `POST /api/auth/login` | Tạo tài khoản và nhận JWT |
| Meeting | `POST/GET /api/meetings`, `GET/PUT/DELETE /api/meetings/{id}` | CRUD cuộc họp; DELETE là xóa mềm |
| Session | `POST /api/meetings/save-session` | Lưu meeting, audio tùy chọn, transcript và summary từ form-data |
| Thành viên | `POST/GET /api/meetings/{id}/participants` | Thêm và liệt kê thành viên |
| Audio | `POST/GET /api/meetings/{id}/audio`, `GET /api/meetings/audio/{audioId}` | Tải lên và truy vấn recording |
| Transcript | `POST /api/audio/{audioId}/transcribe`, `GET /api/audio/{audioId}/transcript`, `GET /api/transcripts/{id}` | Điều phối STT và lấy transcript |
| Note | `POST /api/transcripts/{id}/notes`, `GET /api/meetings/{id}/notes`, `PUT /api/notes/{id}` | Tạo, truy vấn, cập nhật biên bản |
| Action item | `POST/GET /api/notes/{id}/action-items`, `PUT /api/action-items/{id}` | Quản lý đầu việc |

Endpoint AI độc lập (cổng 8000): `POST /api/transcribe`, `POST /api/summarize`, `WS /ws/live-stream`.

## Dữ liệu cốt lõi

```text
User 1 ── * Meeting (organizer)
User * ── * Meeting qua MeetingParticipant
Meeting 1 ── * AudioRecording ── 1 Transcript ── * TranscriptSegment
Meeting 1 ── * MeetingNote ── * ActionItem
MeetingNote * ── 1 Transcript (tùy chọn)
```

| Entity | Nội dung chính |
| --- | --- |
| `User` | username/email duy nhất, BCrypt password hash, họ tên, thời điểm tạo/xóa mềm |
| `Meeting` | tiêu đề, người tổ chức, thời gian, trạng thái `SCHEDULED/IN_PROGRESS/COMPLETED`, mô tả, `deletedAt` |
| `MeetingParticipant` | liên kết meeting-user duy nhất, vai trò `HOST/MEMBER` |
| `AudioRecording` | đường dẫn tệp, tên gốc, định dạng, dung lượng, thời lượng, trạng thái xử lý |
| `Transcript` | raw text, model STT, thời gian xử lý, trạng thái/lỗi |
| `TranscriptSegment` | text, mốc đầu/cuối, nhãn người nói, thứ tự |
| `MeetingNote` | summary, key points, model sinh nội dung, người/thời điểm chỉnh sửa |
| `ActionItem` | mô tả, người nhận việc, hạn, trạng thái `PENDING/IN_PROGRESS/DONE` |

Trạng thái xử lý dùng chung là `PENDING`, `PROCESSING`, `DONE`, `FAILED`. Backend sử dụng Hibernate `ddl-auto=update`, do đó schema được đồng bộ khi khởi động; production nên thay bằng migration có kiểm soát.
