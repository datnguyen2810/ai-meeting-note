# Kế hoạch: phiên âm theo người nói và hỏi đáp cuộc họp

## 1. Phạm vi đã chốt

- Phát triển từ main sau khi hoàn tất các việc bắt buộc ở mục 3. Mốc code hiện tại là `2232aa0` (commit sau đó chỉ thêm tài liệu); chưa coi mốc này đã đạt mọi kiểm thử nghiệp vụ.
- **Cả nhóm dùng chung một DB Supabase.** Mỗi thành viên tự chạy frontend, backend và AI trên máy mình. Truy cập từ xa qua HTTPS là phương án bổ sung.
- Audio lưu trên máy nhận file. Transcript, tóm tắt, người nói và các đoạn nằm trong DB nên xem được từ mọi máy; audio và retry chỉ dùng được trên máy giữ file (mục 4).
- Giữ ghi âm micro và tải tệp; bỏ hiển thị phụ đề trực tiếp trong luồng mới. Không gửi âm thanh qua WebSocket khi đang ghi.
- Chức năng là **phân biệt người nói (diarization)**, không phải nhận diện danh tính. Tự gán Người 1, Người 2… theo lần xuất hiện đầu tiên trong bản ghi, không theo thứ tự nhãn thô của model. Nhãn chỉ có phạm vi một cuộc họp; "Người 1" ở hai cuộc họp không phải cùng một người.
- Bản đầu đánh giá trên 2–4 người thật, nói lần lượt. Một người đọc hai vai không phải mẫu chuẩn để đánh giá phân biệt giọng.
- Hỏi đáp trong một cuộc họp đang mở, có đoạn nguồn và thời gian. Chưa làm hỏi xuyên cuộc họp, đăng ký giọng hoặc đổi tên người nói.
- Giữ tài khoản và lịch sử cũ; cuộc họp cũ không có nhãn được hiển thị bình thường, không tự bịa người nói.

## 2. Hiện trạng đã xác minh trong code

### Luồng xử lý

- React gọi Python trực tiếp cho ASR, sau đó gửi audio/transcript/summary vào Java `/api/meetings/save-session`. Luồng mới chuyển sang Java điều phối xử lý và lưu kết quả.
- Java đã có `TranscriptSegment` với speakerLabel, startTimeSec, endTimeSec, textSegment, sequenceOrder, nhưng chưa có speaker_id và attribution_status; `SttService.toResponse` luôn trả `segments` rỗng. Tận dụng bảng này, không tạo bảng đoạn trùng chức năng.
- `AiServiceClient.transcribeAudio` chỉ trả String transcript; cần DTO kết quả chứa cả summary, segments và speakers.
- `RestTemplateConfig` tạo `new RestTemplate()` không đặt timeout, nên lời gọi AI có thể treo vô hạn.
- `/api/transcribe` giữ `gpu_lock` suốt cả ASR và tóm tắt, chưa truyền `return_timestamps`.
- Có mẫu ~97 giây bị mất một đoạn lớn ở phiên âm batch. Phải nghe WAV, đối chiếu các cửa sổ ASR và ghép đoạn trước khi kết luận do model. Không lấy bản trực tiếp làm bản chữ chuẩn.

### DB và bảo mật

- `application.properties` trỏ thẳng vào Supabase với `ddl-auto=update`. Repo chưa có Flyway/Liquibase, chưa có cấu hình DB riêng cho test. Hệ quả: bất kỳ ai chạy backend hoặc `mvnw test` trên nhánh có entity mới đều tự đổi schema DB chung.
- Mật khẩu DB và JWT secret đang nằm dạng rõ trong file đã push. Xóa khỏi file không đủ vì lịch sử Git vẫn giữ, nên phải đổi giá trị.
- `.gitignore` chưa có `backend/uploads/`, nên `git add .` sẽ đưa audio thật lên repo.
- Backend đã từng lỗi DNS, thiếu kết nối session pooler và tenant/user not found. Xác minh DB hoạt động trước tích hợp; không báo hoàn tất dựa chỉ trên biên dịch.
- `spring.jpa.open-in-view` chưa đặt nên đang bật mặc định, có thể giữ DB connection suốt request. Chat gọi AI đồng bộ nên phải xử lý.
- `GlobalExceptionHandler` trả mọi `RuntimeException` thành 400 kèm message gốc; có message chứa đường dẫn file. Chưa có exception cho 403/404/409/429/503.
- Nhiều API chưa kiểm tra quyền, xem mục 6 (Người 2, việc 5).

### Môi trường AI và audio

- Máy phát triển: RTX 4050 Laptop 6141 MiB. Ba model hiện tại đo được đỉnh 4,72 GB (reserved 5,06 GB), chưa tính pyannote.
- venv đang dùng torch/torchaudio 2.6.0+cu124, Python 3.11.9. `requirements.txt` ghim torch 2.14.0 và không có torchaudio, nên file này không mô tả đúng môi trường đang chạy.
- pyannote.audio 4.0.7 (bản mới nhất khi kiểm tra trên PyPI, 11/2026) yêu cầu torch>=2.8, torchaudio>=2.8, torchcodec>=0.7, nên **không cài được vào venv hiện tại nếu không nâng torch**.
- `pyannote/speaker-diarization-community-1` là model gated, license CC-BY-4.0. Mỗi người phải chấp nhận điều kiện trên Hugging Face và dùng token của mình.
- Frontend hiện ghi WAV 16 kHz mono qua worklet + `encodeWav`, chưa dùng MediaRecorder.
- soundfile trong venv không đọc được WebM/M4A, máy phát triển chưa có FFmpeg, Python chưa nhận `.webm`.
- Config PhoWhisper có `alignment_heads` và `no_timestamps_token_id`, nhưng **chưa kiểm chứng** model sau fine-tune cho mốc thời gian đủ tốt.
- Python để CORS `*` và chưa có xác thực nội bộ.

### API

- `GET /api/meetings/{meetingId}/audio` đã tồn tại và trả danh sách JSON. Không được khai báo endpoint phát audio trùng đường dẫn này, vì Spring sẽ lỗi ambiguous mapping khi khởi động.
- `docs/` và `AGENTS.md` còn thông tin H2 và luồng lưu cũ; cập nhật theo code khi triển khai, phân biệt hiện trạng với thiết kế tương lai.

## 3. Việc bắt buộc trước khi tạo nhánh (M0)

Người 2 thực hiện, người tích hợp kiểm tra. Làm đúng thứ tự vì các bước sau phụ thuộc bước trước.

| # | Việc | Điều kiện hoàn thành |
| --- | --- | --- |
| 1 | Sao lưu DB bằng `pg_dump` (schema + data), giữ ngoài Git | Có file backup, đã thử đọc lại |
| 2 | Đổi mật khẩu DB và JWT secret; chuyển cấu hình sang biến môi trường; thêm `.env.example` không chứa giá trị thật | Không còn secret trong file theo dõi bởi Git; cả nhóm chạy được bằng biến môi trường. Đổi JWT secret sẽ đăng xuất mọi phiên, đây là điều bình thường |
| 3 | Đổi `ddl-auto` sang `validate`; profile mặc định không trỏ tới Supabase | `mvnw test` và chạy không khai báo profile đều không thể chạm DB chung |
| 4 | Tạo profile `shared`, `local` (Postgres Docker) và `test` (DB riêng, `@ActiveProfiles("test")`) | `contextLoads` chạy được với DB riêng |
| 5 | Thêm Flyway (kiểm tra đúng starter cho Spring Boot 4.1 và module PostgreSQL); lấy schema hiện tại làm `V1__baseline.sql`; baseline DB chung ở version 1 | DB local dựng được từ đầu bằng Flyway; `validate` qua trên cả local và DB chung |
| 6 | Thêm `backend/uploads/` vào `.gitignore` | `git status` không còn hiện thư mục này |
| 7 | Cả nhóm pull bản này rồi mới tạo nhánh | Không còn ai chạy backend với `ddl-auto=update` |

Bước 7 quan trọng: chỉ một người còn chạy bản cũ cũng đủ để Hibernate sửa schema DB chung.

Cũng tại M0, cả nhóm chốt: fixture v1, danh sách endpoint, người tích hợp, các ngưỡng ở mục 9 và mẫu âm thanh.

## 4. Vận hành DB chung và audio theo máy

### Quy tắc migration

- File đặt tại `backend/src/main/resources/db/migration`. Người tích hợp cấp số version để tránh hai nhánh trùng số.
- Lập trình và thử schema mới trên profile `local`. Không thử lên DB chung.
- Migration chỉ được **thêm**: bảng mới, cột nullable hoặc có default. Không xóa, đổi tên, đổi kiểu cột trong giai đoạn này, để người chưa pull vẫn chạy được.
- Profile `shared` tắt Flyway. Chỉ người tích hợp áp dụng migration lên DB chung bằng lệnh/profile riêng, theo thứ tự: backup, áp dụng, kiểm tra `validate`, báo nhóm pull.
- Thứ tự gộp: migration lên main và áp dụng trước, code dùng schema mới sau. Với `validate`, nếu code mới chạy trước migration thì backend báo lỗi khi khởi động, đây là hành vi mong muốn.

### Định danh máy và hàng đợi

- Mỗi backend bắt buộc có `APP_INSTANCE_ID` duy nhất (ví dụ `tv1-laptop`); thiếu thì từ chối khởi động profile `shared`.
- Job có `owner_instance_id` là máy đã nhận file. **Chỉ máy đó được nhận và chạy job**, vì file chỉ có ở đó. Hàng đợi là bảng trong DB, không phải queue trong RAM.
- Nhận job bằng cập nhật nguyên tử: `UPDATE ... SET status='PROCESSING' WHERE id=? AND status='QUEUED' AND owner_instance_id=?`, chỉ thành công khi đúng một dòng bị đổi.
- Mỗi máy một worker. Worker được đánh thức ngay sau khi commit job mới, có polling thưa làm dự phòng để không tốn kết nối pooler.
- Job đang chạy gia hạn `lease_expires_at` định kỳ (đề xuất heartbeat 30 giây, lease 2 phút) bằng transaction ngắn.
- **Khi khởi động, backend chỉ đánh dấu INTERRUPTED các job PROCESSING của chính `APP_INSTANCE_ID` đó.** Tuyệt đối không quét job của máy khác; nếu không, một người restart sẽ làm hỏng job đang chạy của người khác.
- Job của máy khác quá hạn lease được hiển thị là "máy xử lý không phản hồi"; không máy nào khác được tiếp quản.
- Giới hạn hàng đợi tính theo từng máy (đề xuất tối đa 3 job QUEUED + PROCESSING); vượt thì trả 429.

### Audio và kết nối

- Lưu file theo tên UUID. `audio_recordings` thêm `storage_node` (= `APP_INSTANCE_ID`) và `storage_key` (đường dẫn tương đối so với `app.upload.audio-dir`). Không trả đường dẫn hệ thống cho client.
- Bản ghi cũ có hai cột này null: thử đọc theo `file_path` cũ, không có file thì báo audio không khả dụng.
- Mở cuộc họp từ máy khác: vẫn xem transcript, tóm tắt, người nói và chat bình thường (chat dùng AI của máy đang mở). Audio trả 409 `audio_not_on_this_instance`; UI ẩn trình phát và nói rõ audio nằm ở máy khác. Retry cũng trả 409.
- Nếu nhóm cần nghe audio từ mọi máy, nâng cấp sau bằng kho lưu trữ chung qua cùng trường `storage_key`. Trước khi chọn phải kiểm tra giới hạn dung lượng và kích thước file của gói Supabase đang dùng.
- Hikari nhỏ: đề xuất `maximumPoolSize` 3–4, `minimumIdle` 1 mỗi máy. Kiểm tra giới hạn kết nối thực tế của pooler trước khi chốt.
- Dữ liệu thử trên DB chung đặt tiêu đề bắt đầu bằng `[TEST]`. Test tự động không bao giờ ghi lên DB chung.
- Transcript nằm trên DB cả nhóm truy cập được, nên chỉ dùng bản ghi mà người tham gia đã đồng ý. Audio riêng tư chỉ lưu local.

## 5. Kiến trúc và hợp đồng chung

```text
Browser: ghi WAV hoặc chọn tệp
  → Java: xác thực, kiểm tra file, lưu file, tạo job (owner_instance_id)
  → Worker của đúng máy đó nhận job qua DB
  → Python: chuẩn hóa audio
      ├─ PhoWhisper: text + thời gian
      └─ pyannote: người nói + thời gian
      → ghép lời với người → Qwen tóm tắt
  → Java lưu transcript + segments + summary + người nói (transaction ngắn)
  → Browser xem kết quả và lịch sử

Browser hỏi trong cuộc họp
  → Java kiểm tra quyền, lấy các đoạn của đúng cuộc họp (và đúng người nếu có)
  → Python xếp hạng đoạn liên quan → Qwen trả lời + ID nguồn
  → Java kiểm tra ID, lấy nguyên văn từ DB → Browser hiển thị nguồn
```

Mô hình dự kiến: giữ `vinai/PhoWhisper-small`, thêm `pyannote/speaker-diarization-community-1`, dùng lại `Qwen/Qwen2.5-1.5B-Instruct` cho tóm tắt và hỏi đáp. Đây là lựa chọn thử nghiệm, chưa bảo đảm chất lượng/bộ nhớ.

Chạy các bước theo thứ tự và quản lý nạp/giải phóng model theo đo thực tế GPU 6 GB. Dùng một khóa GPU chung, **giữ khóa theo từng bước chứ không giữ cả job**, để chat có cơ hội chạy giữa các bước. Không thêm nhiều worker nạp model trùng nhau. Chưa cần model embedding/vector DB: một cuộc họp chỉ có vài trăm đoạn, nên xếp hạng từ khóa trong Python là đủ. Nâng cấp tìm kiếm ngữ nghĩa chỉ khi phép đo cho thấy thiếu.

### Quy ước đặt tên

- Java ↔ frontend: JSON **camelCase**, bọc `ApiResponse<T>`. Thêm trường tùy chọn `errorCode` để frontend phân biệt lỗi.
- Python ↔ Java: JSON **snake_case**, schema riêng. Java tự ánh xạ, frontend không thấy snake_case.
- Trạng thái job trên API: `queued`, `processing`, `completed`, `failed`, `interrupted`. Không thêm giá trị vào enum `ProcessingStatus`/`MeetingStatus` hiện có; job có enum riêng. Cuộc họp đang xử lý để `IN_PROGRESS`, xong chuyển `COMPLETED`; khi lỗi giữ `IN_PROGRESS`, UI đọc trạng thái từ job.

### Dữ liệu kết quả AI v1 (Python → Java)

```json
{
  "schema_version": 1,
  "transcript": "Nội dung đầy đủ...",
  "summary": "### Mục tiêu cuộc họp\n...",
  "speakers": [{"speaker_id": "speaker_1", "label": "Người 1", "first_start_seconds": 1.2}],
  "segments": [{"segment_id": "seg_0001", "speaker_id": "speaker_1", "start_seconds": 1.2, "end_seconds": 4.8, "text": "Nhóm đã hoàn thành giao diện.", "attribution_status": "assigned"}],
  "warnings": []
}
```

- Thời gian tính bằng giây từ đầu bản ghi, không âm, end > start.
- `seg_0001` chỉ có ý nghĩa trong kết quả AI. Sau khi lưu, **DB id của `TranscriptSegment` là `segmentId` công khai**, dùng cho API, chat và citations.
- speaker_id có thể null khi không đủ cơ sở gán; attribution_status gồm assigned, unknown, overlap. Đoạn chồng tiếng không buộc vào một người nếu không xác định được.
- Phân người chạy trên cùng timeline audio với ASR. Không gán cả câu dài cho người chiếm thời gian nhiều nhất một cách mù quáng: phải chia ở ranh giới người nói hoặc đánh dấu chưa rõ. Dùng `exclusive_speaker_diarization` của community-1 để đơn giản hóa bước ghép.
- Sắp nhãn theo mốc tiếng nói đầu tiên của mỗi cụm giọng; giữ ánh xạ nhất quán trong toàn bản ghi. Khoảng nghỉ không tạo người mới.
- Chỉ giới hạn `max_speakers`, không đặt `min_speakers`, để bản ghi một người không bị tách giả. Nếu số cụm chạm `max_speakers`, thêm cảnh báo vì có thể đã gộp nhầm người.
- Diarization lỗi nhưng ASR xong: vẫn lưu transcript, các đoạn để `unknown`, thêm `warnings`, không làm hỏng cả job.
- Phân biệt người phát biểu và người được nhắc đến/giao việc. Không suy speaker_id từ tên trong câu.
- Tóm tắt chạy trên văn bản không có nhãn kỹ thuật người nói, nên nhãn không lọt vào phần tên người được giao việc. Tiếp tục dùng pipeline đối chiếu nguồn hiện có.

### Thay đổi DB (migration V2, chỉ thêm)

| Bảng | Nội dung |
| --- | --- |
| `meeting_processing_jobs` (mới) | meeting_id, audio_recording_id, requested_by, client_request_id, status, stage, owner_instance_id, lease_expires_at, attempt_count, error_code, safe_error_message, created_at, updated_at. Unique `(requested_by, client_request_id)`. Partial unique index: một job đang hoạt động trên mỗi meeting |
| `transcript_speakers` (mới) | transcript_id, speaker_key, label, first_start_seconds. Unique `(transcript_id, speaker_key)` |
| `transcript_segments` | Thêm speaker_key, attribution_status (nullable; đoạn cũ không có nhãn). Thêm unique `(transcript_id, sequence_order)` nếu dữ liệu cũ cho phép |
| `audio_recordings` | Thêm storage_node, storage_key (nullable) |

Cuộc họp từ `process-audio` có đúng một audio và một transcript. `/segments` đọc transcript của audio đã xử lý xong mới nhất.

### API Java cho frontend

| API | Trách nhiệm |
| --- | --- |
| POST `/api/meetings/process-audio` | Multipart `file`, `title` (tùy chọn), `source` (recording/upload), `durationSeconds` nếu biết, `clientRequestId`; trả HTTP 202 với meetingId, jobId và status |
| GET `/api/meetings/{id}/processing` | status, stage, ownerInstanceId, cờ máy xử lý không phản hồi; lỗi có thông báo an toàn, không lộ token/path |
| GET `/api/meetings/{id}` | Metadata, summary/transcript; giữ tương thích response cũ, thêm processingStatus, audioAvailable |
| GET `/api/meetings/{id}/speakers` | Danh sách người nói cho bộ lọc; rỗng với cuộc họp cũ |
| GET `/api/meetings/{id}/segments` | Có phân trang, filter speakerId tùy chọn; giới hạn page size (đề xuất mặc định 100, tối đa 200) |
| GET `/api/meetings/{id}/audio/content` | Trả bytes audio có xác thực, không bọc `ApiResponse`; 409 nếu file ở máy khác. **Không dùng `/{id}/audio`**, đường dẫn đó giữ nguyên là danh sách bản ghi |
| POST `/api/meetings/{id}/chat` | JSON question, speakerId tùy chọn, lịch sử hội thoại giới hạn; trả answer, citations, insufficientEvidence |
| POST `/api/meetings/{id}/retry-processing` | Chỉ cho job failed/interrupted, tái dùng file cũ, chỉ trên máy giữ file; ngăn chạy trùng |

`citations: [{segmentId, speakerId, startSeconds, endSeconds, quote}]`. Nguồn phải thuộc đúng meeting. Câu không đủ thông tin trả `insufficientEvidence=true`.

Mã lỗi: 400 sai dữ liệu, 403 không có quyền, 404 không tồn tại, 409 sai trạng thái hoặc file ở máy khác, 413 quá dung lượng, 429 đầy hàng đợi, 503 AI hoặc GPU đang bận (kèm `Retry-After`). Thêm exception riêng cho từng loại; không dựa vào handler `RuntimeException`.

`clientRequestId` giúp retry mạng không tạo nhiều cuộc họp/tác vụ: trùng ID thì trả lại job đã có. Nếu đổi audio phải dùng ID mới. Lịch sử chat bản đầu giữ trong trình duyệt theo meeting, không tạo bảng chat. Không cho hội thoại cũ vượt quyền hoặc thay thế nguồn.

Quyền: organizer và participant được xem, nghe, chat; chỉ organizer được retry.

### Định dạng và giới hạn audio

- **Ghi âm trên browser dùng WAV 16 kHz mono**, tái sử dụng worklet và `encodeWav`. Không dùng MediaRecorder/WebM ở bản đầu: tránh phụ thuộc FFmpeg và lỗi tua trên file WebM thiếu duration.
- Upload nhận wav, mp3, flac, ogg. m4a chỉ bật khi FFmpeg đã cài và kiểm thử trên máy đó.
- Python là nơi xác nhận cuối cùng: file không giải mã được trả mã `unsupported_audio`, không dựa riêng vào đuôi file.
- Giới hạn 100 MB tương đương khoảng 54 phút WAV (32.000 byte/giây). UI hiện thời lượng, cảnh báo từ phút 45 và tự dừng an toàn trước giới hạn, để không xảy ra họp xong mới bị 413.
- Frontend tải audio bằng `fetch` có JWT thành Blob rồi tạo object URL, vì thẻ `<audio src>` không gửi được header Authorization. Không đặt token trên query URL. Tua trên Blob nên Range không bắt buộc ở bản đầu.

### API Python nội bộ

- POST `/api/process-meeting`: nhận audio, `job_id`, `max_speakers` (mặc định 4); trả kết quả v1.
- POST `/api/meeting-chat`: nhận question, `speaker_id` tùy chọn và các đoạn do Java gửi (toàn bộ đoạn trong phạm vi được phép); trả answer + ID nguồn.
- Giữ `/api/transcribe` và `/api/summarize` trong giai đoạn chuyển tiếp. Chỉ bỏ WS/live cũ khi frontend mới hoạt động và test cũ đã thay thế đúng phạm vi.

Quy tắc chung:

- Python chỉ bind `127.0.0.1`. Endpoint mới yêu cầu header token nội bộ lấy từ biến môi trường, Java gửi kèm. CORS giới hạn đúng origin thay vì `*`.
- **Chống chạy trùng:** Python chỉ có một slot job. Cùng `job_id` đang chạy trả 409; job khác trả 503. Thread trong `asyncio.to_thread` không hủy được, nên Java timeout không có nghĩa Python đã dừng. Python kiểm tra deadline giữa các bước và bỏ phần còn lại khi quá hạn; retry chỉ thành công sau khi slot trống.
- `/api/process-meeting` trả 409 khi có phiên live, giống `/api/transcribe`.
- Timeout Java tính theo thời lượng audio: `max(10 phút, thời lượng × hệ số)`, hệ số lấy từ số đo M1. Chat có timeout riêng ngắn hơn.
- Chat chờ khóa GPU có giới hạn (đề xuất 30 giây), quá thì trả 503 để UI báo đang bận, không để request treo.
- Lỗi một tác vụ không được khóa vĩnh viễn tác vụ sau; slot và khóa phải được trả trong `finally`.
- Cờ `ENABLE_LIVE_ASR` quyết định có nạp Wav2Vec2 không. Mặc định bật cho tới khi luồng mới thay thế xong, sau đó tắt. Mọi số đo VRAM cho luồng mới phải đo ở trạng thái tắt.

### Chat: phân chia trách nhiệm

| Bước | Bên phụ trách |
| --- | --- |
| Kiểm tra quyền, trạng thái cuộc họp | Java |
| Xác định phạm vi: đúng meeting, đúng người | Java. Lấy `speakerId` từ bộ lọc UI; nếu trống thì nhận dạng mẫu "người 2", "người số 2", "người hai" trong câu hỏi. Không suy từ tên riêng |
| Xếp hạng đoạn liên quan, thêm đoạn lân cận làm ngữ cảnh | Python, chuẩn hóa chữ có/không dấu |
| Sinh câu trả lời và chọn ID nguồn | Python/Qwen. Model chỉ trả ID, không tự viết `quote` |
| Kiểm tra ID thuộc phạm vi, lấy nguyên văn, thời gian, người nói từ DB | Java. Không còn ID hợp lệ thì trả `insufficientEvidence=true` |

- Java đọc đoạn trong transaction ngắn, kết thúc transaction rồi mới gọi AI. Không giữ DB connection trong lúc chờ Qwen.
- Câu hỏi tổng hợp cả cuộc họp hoặc một người: chia đoạn theo ngân sách token, tóm từng phần rồi gộp, không chỉ lấy vài đoạn đầu. Context có giới hạn 4096 token và pipeline tóm tắt hiện dùng khoảng 1000 token nguồn mỗi lượt, nên phải đo thời gian với cuộc họp dài và đặt giới hạn số lượt.
- ID hợp lệ chỉ chứng minh nguồn tồn tại, không chứng minh câu trả lời đúng, nên vẫn phải đọc tay khi đánh giá.
- Văn bản nguồn và lịch sử chat là dữ liệu, không phải lệnh; lịch sử chat không phải bằng chứng.
- Cuộc họp cũ chưa có người nói: báo không trả lời theo người được, vẫn hỏi nội dung nếu có transcript. Cuộc họp chưa xử lý xong trả 409.

## 6. Phân công ba người

### Người 1 — AI (`feat/speaker-ai`)

1. **Môi trường:** ghi lại đầy đủ phiên bản đang chạy; thử nâng torch/torchaudio >=2.8 kèm torchcodec trên Windows + CUDA trong venv thử riêng. Truyền waveform trong bộ nhớ cho pyannote (`{"waveform", "sample_rate"}`) để không phụ thuộc giải mã của torchcodec. Kiểm tra PhoWhisper và Qwen vẫn cho kết quả tương đương sau khi nâng. **Quyết định ở M1:** dùng chung một venv hay tách pyannote thành process riêng. Thử trong venv riêng chưa đủ để qua mốc nếu chưa chốt cách chạy chung.
2. Sửa `requirements.txt` khớp môi trường đã chốt, gồm torchaudio và chỉ dẫn cài bản CUDA, để máy thứ hai không nhận nhầm bản chỉ chạy CPU.
3. Tạo hướng dẫn HF_TOKEN qua môi trường, chấp nhận điều kiện model và tải trước. Không ghi token trong repo/log/chat. Đo dung lượng tải thực tế và kiểm tra lần sau chạy được từ cache không cần mạng.
4. **Đo mốc thời gian PhoWhisper ngay đầu M1** với `return_timestamps=True` và `"word"`, so với mốc gán tay. Chọn một trong hai hướng:
   - Hướng A, mốc đủ tốt: ASR cả file, ghép với kết quả phân người.
   - Hướng B, mốc kém: chạy pyannote trước, gộp các lượt nói ngắn liền kề của cùng người, chạy ASR từng lượt (mỗi lượt không quá 30 giây). Hướng này không cần mốc từ ASR, có thể giúp tránh lỗi ghép cửa sổ, nhưng phải đo xem lượt ngắn có làm giảm độ đúng không.
5. Điều tra mất đoạn ASR trên WAV đã xác minh (file khoảng 96 giây trong `backend/uploads/audio/6/` có thể là mẫu này, cần xác nhận); kiểm tra không bỏ/lặp câu ở biên, không chỉ tăng beam.
6. Tách module audio/ASR/diarization/alignment, trả kết quả v1 với unknown/overlap và cảnh báo phần xử lý thiếu. Làm `/api/process-meeting` theo quy tắc ở mục 5: slot job, deadline, khóa theo bước, token nội bộ.
7. Chat: xếp hạng đoạn, tổng hợp theo phần, trả ID nguồn. Bắt đầu ngay từ M1 bằng fixture, không cần đợi diarization xong.
8. Benchmark Qwen hiện có trước quyết định đổi model. Ghi độ đúng, thời gian và bộ nhớ theo từng bước, không công bố chất lượng chỉ từ keyword.

Đọc/sửa chính: ai-service/main.py, requirements.txt, summarization/, package mới diarization/ hoặc meeting_processing/, chat/, tests/. Bàn giao schema, fixture JSON, script tải model và báo cáo thử nghiệm.

### Người 2 — Backend và DB (`feat/meeting-api`)

1. Hoàn tất mục 3 trước khi nhóm tạo nhánh.
2. Chốt DTO v1, API và mã lỗi với hai người còn lại; cung cấp response giả để frontend bắt đầu.
3. Viết migration V2 theo mục 5, thử trên profile `local`, đưa qua người tích hợp theo mục 4. Không xóa bảng/dữ liệu cũ.
4. API nhận file, tạo job và worker theo mục 4. Không giữ transaction/DB connection lúc chờ AI: lưu job/file trước, gọi AI ngoài transaction, transaction ngắn để ghi kết quả cuối. Tắt `open-in-view` và thêm `@Transactional(readOnly = true)` cho các service đọc dữ liệu lazy; test lại các API cũ vì `toResponse` có thể lỗi LazyInitializationException.
5. Tạo một hàm kiểm tra quyền dùng chung và áp dụng cho **toàn bộ** API theo meeting, gồm cả API cũ:
   - `/api/meetings/{id}`, `/{id}/participants`, `/{id}/audio` (GET, POST), `/api/meetings/audio/{audioId}`
   - `/api/audio/{audioId}/transcript`, `/api/transcripts/{transcriptId}`
   - `/api/meetings/{id}/notes`, `/api/transcripts/{id}/notes`, `/api/notes/{id}`, `/api/notes/{id}/action-items`, `/api/action-items/{id}`
   - Mọi API mới: processing, speakers, segments, audio/content, chat, retry
6. Khóa `POST /api/audio/{audioId}/transcribe`: API này đi vòng qua hàng đợi và giữ transaction suốt lời gọi AI. Hiện không có component nào gọi; `api.js` chỉ có hàm bọc. Bỏ hàm bọc đó, hoặc chuyển API sang tạo job.
7. Xử lý file: tên UUID, giới hạn dung lượng/định dạng, cleanup và rollback phù hợp. Không để audio người dùng vào Git. Áp dụng cùng kiểm tra cho `save-session` trong thời gian còn giữ.
8. Thêm exception và `errorCode`; không trả message nội bộ cho client. Đặt timeout `RestTemplate` theo mục 5.
9. Chat theo bảng trách nhiệm ở mục 5: truyền đúng đoạn, kiểm tra ID, dựng citations từ DB.

Đọc/sửa chính: AiServiceClient.java, RestTemplateConfig.java, GlobalExceptionHandler.java, service/MeetingService.java, SttService.java, AudioService.java, các controller, entity/TranscriptSegment.java, DTO/repository mới, application*.properties, db/migration. Bàn giao migration, API, kiểm thử quyền và phục hồi lỗi.

### Người 3 — Frontend (`feat/meeting-ui`)

1. Thay LiveMeetingRoom bằng màn hình ghi âm sau họp: bắt đầu/dừng, thời lượng, mức micro, xem/nghe lại và gửi xử lý. Không mở WS/không hiện captions. Giữ bản ghi để người dùng tải lại nếu xử lý lỗi.
2. Tách phần thu âm khỏi `useLiveTranscription` thành hook mới không phụ thuộc WS, tái dùng worklet và `encodeWav`. Giữ cơ chế flush để dừng là đủ mẫu cuối (đồng bộ hai bản worklet, chạy `tests/captureFlush.test.js`). Dọn stream/object URL. Thêm cảnh báo và tự dừng theo giới hạn thời lượng ở mục 5.
3. Một luồng chung cho ghi âm và upload: gửi file tới Java, hiện stage, polling có backoff/timeout/dừng khi unmount. Đóng modal không tạo job mới hoặc hủy nhầm job đã gửi. Mở lại trang lấy trạng thái từ server.
4. Hiển thị lượt nói có Người 1/2, thời gian và bộ lọc; nguồn unknown có nhãn dễ hiểu. Bấm đoạn tua audio; tải audio theo mục 5.
5. Hiển thị đủ trạng thái của DB chung: audio ở máy khác (ẩn trình phát, vẫn xem chữ và chat), retry không khả dụng, máy xử lý không phản hồi, AI đang bận.
6. Chat trong trang chi tiết: câu hỏi gợi ý, đang trả lời/lỗi, xử lý 503 có thử lại, citations bấm tới đoạn và audio, chặn gửi trùng; đổi meeting không để câu trả lời cũ chen vào.
7. Xuất Markdown gồm phiên âm theo người và tóm tắt. Cuộc họp cũ thiếu segments vẫn xem/export được; không gắn nhãn người giả.
8. Tập trung URL qua services/api, Vite proxy Java; không hardcode Python localhost trong component mới. Local là mặc định; nếu thử khác mạng phải cấu hình HTTPS/proxy, micro quyền và CORS đúng nguồn.

Đọc/sửa chính: App.jsx, components/LiveMeetingRoom.jsx, SpeechToTextDemo.jsx, services/api.js, hooks/useLiveTranscription.js, hook ghi âm mới, component phiên âm/chat mới. Bàn giao giao diện dùng fixture trước, nối API thật sau.

## 7. Mốc tích hợp và phụ thuộc

| Mốc | Công việc song song | Điều kiện qua mốc |
| --- | --- | --- |
| M0: nền và hợp đồng | Người 2 làm mục 3; cả nhóm chốt API, schema, ngưỡng, mẫu âm thanh, người tích hợp | Mục 3 xong, cả nhóm đã pull; có fixture v1 và danh sách endpoint |
| M1: thử AI, dựng nền | AI: môi trường, mốc thời gian, diarization, chat trên fixture. Backend: mock API, migration V2, phân quyền. Frontend: ghi âm và UI theo fixture | Chốt cách chạy pyannote; chọn hướng A hoặc B; xử lý được file hai người trong môi trường tích hợp; có số đo VRAM khi tắt Wav2Vec2 |
| M2: phiên âm theo người | Nối upload → job → AI → DB → UI | Đạt ngưỡng mục 9; mở lại lịch sử được, kể cả từ máy khác; restart một máy không ảnh hưởng job máy khác |
| M3: tóm tắt và chat | AI + backend chat, frontend dẫn nguồn | Trả lời đúng người/cuộc họp, nguồn truy vết được, không đủ bằng chứng thì không bịa; chat khi đang có job trả kết quả hoặc 503, không treo |
| M4: bàn giao | Thử 2–4 người, lỗi mạng/restart, máy thứ hai | Hướng dẫn cài chạy lặp lại được, dữ liệu cũ còn nguyên, báo cáo giới hạn |

Chưa cam kết số ngày cho đến khi M1 xác minh dependency, tốc độ và bộ nhớ. Không đợi cả ba hoàn thành rồi mới nối: tích hợp từng mốc nhỏ.

## 8. Phương án dự phòng

| Rủi ro | Phương án |
| --- | --- |
| Không nâng được torch mà vẫn giữ PhoWhisper/Qwen ổn định | Tách pyannote thành process/venv riêng, giao tiếp nội bộ qua localhost |
| torchcodec không chạy được trên Windows | Kiểm tra pyannote có chạy được khi truyền waveform trong bộ nhớ không; nếu không, dùng process riêng hoặc bản pyannote tương thích và ghi lại phiên bản |
| Không đủ VRAM | Giải phóng model giữa các bước; nếu vẫn thiếu thì chạy diarization trên CPU và chấp nhận chậm hơn |
| Phân người không đạt ngưỡng | Vẫn lưu transcript và tóm tắt, hiển thị nhãn là "ước tính", báo cáo giới hạn; không chặn luồng chính |
| Mốc thời gian ASR kém và hướng B làm giảm độ đúng | Giữ ASR cả file làm bản chữ chính; gán người ở mức câu và đánh dấu `unknown` khi không chắc |
| Qwen 1.5B trả lời không đạt | So sánh model khác vừa VRAM trước khi đổi. Tạm thời chat chỉ trả các đoạn nguồn liên quan, không sinh câu trả lời |

## 9. Kiểm thử và tiêu chí nghiệm thu

### Ngưỡng đề xuất (nhóm chốt ở M0, sửa nếu số đo M1 cho thấy không hợp lý)

| Hạng mục | Ngưỡng |
| --- | --- |
| Đầy đủ nội dung | File ~97 giây không mất câu nào so với reference đã nghe |
| Gán người | Từ 90% thời gian tiếng nói gán đúng trên mẫu 2 người nói lần lượt; nhãn Người 1/2 đúng thứ tự xuất hiện |
| VRAM | Đỉnh toàn pipeline không quá 5,5 GB |
| Tốc độ | Khi đã nạp model, thời gian xử lý không dài hơn thời lượng audio |
| Chat | Từ 10/12 câu đúng và có nguồn phù hợp; không có nguồn sai cuộc họp; câu không có thông tin đều trả `insufficientEvidence` |

### Danh sách kiểm thử

- Audio: mẫu hai người nói thật, bốn người, một người, khoảng lặng, nói chen, file hỏng, file quá giới hạn; tên/ngày/task đã nghe và ghi reference. Dữ liệu riêng tư chỉ lưu local hoặc nơi nhóm cho phép.
- ASR: đối chiếu cả đoạn giữa và biên cửa sổ trên file ~97 giây đã gặp lỗi; đo WER/CER từ reference nghe xác minh, không dùng ASR làm chuẩn. So sánh trước và sau khi nâng torch.
- Diarization: đo sai gán người/thời gian với nhãn thủ công; nếu tính DER phải ghi rõ cách tính, xử lý overlap và tolerance. Kiểm tra nhãn từ người nói đầu tiên, không phụ thuộc ID thô. Bản ghi một người không bị tách thành hai.
- Chat: ít nhất 12 câu gồm tổng hợp một người, một chủ đề, quyết định, phân công, người được nhắc khác người phát biểu, thông tin không có, nguồn mâu thuẫn và câu hỏi ngoài cuộc họp. Đọc tay câu trả lời + nguồn, không chỉ kiểm keyword. Nguồn chứa câu lệnh phải được xử lý như dữ liệu, không điều khiển chatbot.
- Backend: test chạy trên DB riêng; người A không xem/audio/chat/retry dữ liệu người B ngoài quyền trên **mọi** API ở mục 6; retry không tạo phiên trùng; lỗi AI không mất file hay giữ transaction; lịch sử cũ đọc được.
- DB chung (thử bằng hai máy): chỉ máy chủ job nhận job; restart máy A không đổi trạng thái job của máy B; hai request cùng `clientRequestId` chỉ tạo một job; mở cuộc họp của máy khác xem được chữ và báo đúng audio không khả dụng; schema cũ và mới cùng chạy được sau migration; số kết nối của ba máy nằm trong giới hạn pooler.
- AI: Java timeout rồi retry không làm hai job chạy cùng lúc; chat khi đang có job trả kết quả hoặc 503; job lỗi không khóa job sau; thiếu token nội bộ bị từ chối.
- Frontend: đủ mẫu cuối sau stop, quyền micro bị từ chối, tự dừng theo giới hạn thời lượng, upload lỗi/retry, refresh khi đang xử lý, đổi meeting khi chat đang chạy, hiển thị Markdown và văn bản nguồn an toàn.
- Hiệu năng: thời gian/độ dài audio và đỉnh VRAM toàn pipeline; cold/warm riêng. Không cam kết mô hình luôn vừa GPU 6 GB trước đo.
- Cài máy thứ hai: ghi phiên bản Python/Node/Java, dependency, FFmpeg nếu cần, quyền pyannote, cache và dung lượng đã đo. Không phát hành weights/token kèm Git.
- Hoàn tất khi ghi âm/tải tệp → xử lý → lưu → mở lại → hỏi đáp có nguồn hoạt động, cùng các bài kiểm thử và giới hạn được ghi rõ. Chat tốt không chứng minh ASR/nhãn người luôn đúng.

## 10. Quy trình Git và bàn giao

- Main là mốc chung sau khi mục 3 đã gộp; mỗi người tạo nhánh riêng từ cùng commit đó. Không merge web-speech-api vào phạm vi này.
- Chỉ định một trong ba người làm người tích hợp; không cần người thứ tư. Người tích hợp cấp số migration và là người duy nhất áp dụng migration lên DB chung. Hợp đồng/API đổi phải báo hai người còn lại và cập nhật fixture trong cùng thay đổi.
- Gộp các thay đổi nhỏ đã kiểm thử, xử lý migration theo thứ tự; không gộp để xóa xung đột bằng cách bỏ mất chức năng người khác.
- Không đưa audio riêng tư, token, mật khẩu, model weights, venv/node_modules/build vào commit. Giữ backend/uploads ngoài Git.
- Kế hoạch chưa phải code đã triển khai. Không tự tải model, đổi dependency, chạy migration DB chung, khởi động AI hoặc push chỉ để chuẩn bị tài liệu này.
