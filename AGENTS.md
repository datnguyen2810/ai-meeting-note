# AI Meeting Note — hướng dẫn làm việc cho agent

## Đọc trước khi làm việc

- Đây là bản đồ dự án, không thay thế mã nguồn. Khi có khác biệt, ưu tiên code/config đang checkout và cập nhật tài liệu này.
- **Hai file hướng dẫn phải đồng bộ:** `AGENTS.md` (bản đồ dự án, hợp đồng API, lệnh chạy — dùng cho mọi agent) và `CLAUDE.md` (nạp file này, bổ sung số đo, môi trường máy, việc còn mở, cách làm việc với người dùng). Khi kiến trúc, API, lệnh chạy, vị trí file hoặc hiện trạng đo được thay đổi, cập nhật cả hai trong cùng lượt, mỗi thông tin chỉ ghi ở một nơi.
- Bắt đầu bằng `git status --short --branch`; giữ nguyên thay đổi chưa commit của người dùng. Không tự reset, discard, commit hoặc push ngoài phạm vi yêu cầu.
- Chỉ đọc mục liên quan bên dưới, sau đó mở các file được chỉ dẫn. Không quét/đọc lại toàn repo mỗi lượt hoặc sau khi nén ngữ cảnh.
- Tìm symbol/endpoint bằng công cụ tìm kiếm của agent hoặc `git grep -n`; máy phát triển có thể không cài `rg`. Đọc UTF-8 (`Get-Content -Encoding utf8` trên PowerShell).
- Không đọc `venv/`, `node_modules/`, `target/`, `dist/`, cache/model weights, audio, PDF hoặc notebook lớn nếu tác vụ không cần chúng. Không đọc toàn bộ lockfile để tìm một dependency.
- Trong cùng phiên, giữ lại mục tiêu, quyết định, file đã sửa, kiểm tra đã chạy và việc còn lại; chỉ đọc lại khi file thay đổi hoặc cần xác minh.
- Chỉ cập nhật kiến thức bền vững ở đây khi kiến trúc, API, lệnh chạy hoặc vị trí file đổi. Không ghi log hội thoại, trạng thái nhánh, URL tunnel tạm, token hay thông tin riêng vào tài liệu.

## Tổng quan và kiến trúc thực tế

Đồ án HTTM/PTIT: nhận diện tiếng Việt từ âm thanh/cuộc họp, tạo bản phiên âm theo người nói, tóm tắt và hỏi đáp. Monorepo gồm ba tiến trình chạy độc lập:

| Thành phần | Công nghệ / cổng local | Trách nhiệm |
| --- | --- | --- |
| `frontend/` | React 19, Vite 8 / `5173` | Landing, đăng nhập, dashboard, ghi âm, phụ đề, upload, phân người + chat, xuất Markdown |
| `backend/` | Java 21, Spring Boot 4.1.1, Maven / `8080` | JWT, cuộc họp, file audio, transcript, người nói, note, action item, JPA/PostgreSQL |
| `ai-service/` | Python, FastAPI, PyTorch, Transformers / `8000` | WebSocket ASR, batch ASR, phân người nói, tóm tắt và hỏi đáp bằng LLM |

```text
Trình duyệt :5173
  ├─ /api/... → Vite proxy → Java :8080 → PostgreSQL online (dùng chung) + uploads/audio
  │                              └─ AiServiceClient → Python :8000 (/api/process-meeting, /api/meeting-chat)
  ├─ ws://localhost:8000/ws/live-stream → Wav2Vec2 → interim/final captions
  └─ http://localhost:8000/api/transcribe → PhoWhisper → Qwen → transcript + summary
```

**Phân biệt các luồng:**

- `App.jsx` quản lý trang bằng React state (`landing`, `auth`, `dashboard`), chưa dùng router. Dashboard có ba tab: `speaker` (mặc định), `live`, `upload`; cột trái là lịch sử cuộc họp lấy từ Java.
- Tab `speaker` (`SpeakerChatMeeting`) đi **qua Java**: ghi WAV hoặc chọn tệp → `POST /api/meetings/process-audio` → Java gọi Python `/api/process-meeting` (đồng bộ) → lưu transcript, người nói, các đoạn, summary. Chat cũng qua Java. Popup lịch sử có nút "Mở và hỏi đáp" để mở lại cuộc họp ở tab này. Component này **luôn được gắn** (chỉ ẩn khi sang tab khác) để đổi tab không mất bản ghi/kết quả; nút tab hiện "đang ghi âm/đang xử lý" qua `onBusyChange`. Chỉ nhận WAV/MP3/FLAC/OGG; một bản ghi đã xử lý xong thì khóa nút xử lý để không tạo cuộc họp trùng. Giao diện chia hai bước (âm thanh → xử lý), dùng class riêng `smc-*` vì `.btn-primary` của `App.css` có `width: 100%`. Ghi âm/chọn tệp mới khi đang xem cuộc họp cũ thì tự chuyển sang cuộc họp mới. Tên model ở dòng mô tả lấy từ `models` (khi vừa xử lý) hoặc `asrModel` của `/processing`; mẹo chọn số người chỉ hiện khi bộ phân người gần nhất (localStorage `speaker_view:last_engine`) không phải pyannote. Biên bản tô màu theo người nói và tô sáng đoạn đang phát; khung chat có câu hỏi gợi ý.
- Tab `live` (`LiveMeetingRoom`) và `upload` (`SpeechToTextDemo`) gọi Python trực tiếp (`/ws/live-stream`, `/api/transcribe`) rồi tự lưu qua `POST /api/meetings/save-session` (multipart: title, transcript, summary, durationSeconds, file).
- Sau khi dừng live, hook đóng gói WAV trong bộ nhớ; `LiveMeetingRoom` gửi WAV sang batch ASR + tóm tắt và cho xuất Markdown.
- API STT cũ `AudioService → SttService → AiServiceClient` vẫn còn nhưng không component nào gọi; nó chỉ lấy trường `transcript` và giữ transaction trong lúc chờ AI.
- `MeetingNoteService.generateNote()` sao chép raw transcript vào summary của note, chưa gọi LLM.
- `AuthModal.jsx` còn trong repo, nhưng luồng đăng nhập chính dùng `pages/AuthPage.jsx`.

## Bản đồ file: mở đâu khi sửa

Các đường dẫn Java bên dưới tính từ `backend/src/main/java/vn/httm/backend/`.

| Tác vụ | File/thư mục cần đọc trước |
| --- | --- |
| Landing, auth, điều hướng, lịch sử | `frontend/src/App.jsx`, `pages/LandingPage.jsx`, `pages/AuthPage.jsx` (hai thư mục `pages/` nằm dưới `frontend/src/`) |
| Giao diện/CSS | `frontend/src/App.css`, `index.css`, `styles/`, CSS đi kèm component |
| JWT client, request Java | `frontend/src/services/api.js`, `frontend/vite.config.js` |
| Phân người + chat (UI) | `frontend/src/components/SpeakerChatMeeting.jsx` và `.css`; `hooks/useWavRecorder.js` (ghi WAV không cần WS); `utils/meetingViewStorage.js` (cuộc họp đang xem, lịch sử chat) |
| Live UI, stop → batch, xuất Markdown | `frontend/src/components/LiveMeetingRoom.jsx` và `.css` |
| Micro, vòng đời socket, captions | `frontend/src/hooks/useLiveTranscription.js` |
| PCM / WAV | `frontend/public/capture.worklet.js`, `frontend/src/audio/capture.worklet.js`, `frontend/src/utils/encodeWav.js`, `utils/flushCapture.js` |
| Upload trực tiếp sang Python | `frontend/src/components/SpeechToTextDemo.jsx`, `MeetingNote.css` cùng thư mục |
| Hiển thị tóm tắt có định dạng | `frontend/src/components/SummaryContent.jsx`, `.css`, `frontend/src/utils/summaryMarkdown.js`; giữ Markdown gốc khi xuất `.md` |
| AI startup, ASR, HTTP/WS | `ai-service/main.py` (`lifespan`, `run_ctc_inference`, `websocket_live_stream`, mục 7–8 cho process-meeting/meeting-chat) |
| Pipeline phân người | `ai-service/meeting_processing/`: `service.py` (pipeline, `load_audio`), `diarize.py` (`diarize_with_engine`), `turns.py` (dọn lượt nói, nới biên ASR), `attribution.py` ("mình" → Người N), `chat.py` |
| Tóm tắt, prompt, dữ kiện, Markdown | `ai-service/summarization/`: `service.py`, `prompts.py`, `schema.py`, `validation.py`, `render.py` |
| VAD, cắt utterance, giao thức | `ai-service/vad_buffer.py`, `ai-service/ws_protocol.py` |
| Java API / nghiệp vụ / DB | `controller/` → `service/` → `repository/`, `entity/`, `dto/` |
| Java phân người + chat | `service/MeetingProcessingService.java`, `controller/MeetingController.java`, `entity/MeetingProcessingJob.java`, `TranscriptSpeaker.java`, `TranscriptSegment.java` |
| Java authentication | `config/SecurityConfig.java`, `security/`, `service/AuthService.java` |
| Java gọi AI, file upload | `client/AiServiceClient.java`, `config/RestTemplateConfig.java`, `service/AudioService.java`, `service/MeetingService.java` (`saveMeetingSession`) |
| DB, JWT, AI URL, upload limit | `backend/src/main/resources/application.properties`, `.env.example` |
| Thử nghiệm / benchmark | `models_testing/`, `ai-service/test_model.py`, `data_test/` (audio demo 3 người + đáp án ở `data_test/demo_meeting/`) — chỉ đọc khi cần đánh giá model |
| Mô tả tính năng cho nhóm/báo cáo | `TINH_NANG_PHAN_NGUOI_CHAT.md` (luồng, model, số đo, hạn chế); đổi pipeline/chat/số đo thì sửa cả file này |
| Kế hoạch tính năng | `PLAN_SPEAKERS_CHAT.md` (phân người + chat, DB chung); `PLAN_REALTIME_HYBRID_ASR.md` (realtime) — xác minh lại với code |

## Hợp đồng giao tiếp cần giữ đồng bộ

### Frontend ↔ Java

- `services/api.js`: API base `/api`; Vite proxy tới `http://localhost:8080` khi chạy dev. Proxy không tự tồn tại khi chỉ host thư mục build.
- Session lưu trong localStorage: `auth_token`, `auth_user`. Request Java gửi `Authorization: Bearer <token>`; mọi response 401/403 làm `api.js` xóa phiên và phát `auth_logout`.
- Response Java dùng `ApiResponse<T>`: `{success, message, data}`. JSON Java ↔ frontend dùng camelCase; Python ↔ Java dùng snake_case, Java tự ánh xạ.
- `GlobalExceptionHandler` trả mọi `RuntimeException` thành 400 kèm message; chưa có exception riêng cho 403/404/409. Không trả 403 cho lỗi nghiệp vụ: `api.js` coi 403 là hết phiên và đăng xuất.
- Quyền xem cuộc họp: `MeetingService.findAccessibleMeeting` (người tổ chức hoặc participant, cuộc họp chưa xóa mềm). Đang áp dụng cho `GET /{id}`, `/{id}/participants`, `/{id}/speakers`, `/{id}/segments`, `/{id}/processing`, `/{id}/chat`, `/{id}/audio/content`; các API audio/transcript/note cũ chưa kiểm tra.
- Auth: `POST /api/auth/register`, `POST /api/auth/login`. Security cho phép `/api/auth/**`, `/h2-console/**` (còn sót từ thời H2), `/error`; còn lại yêu cầu đăng nhập.
- Meetings: CRUD `/api/meetings`, `/api/meetings/{id}`; participants dưới `/{id}/participants`; `POST /api/meetings/save-session` cho tab live/upload.
- Phân người + chat:
  - `POST /api/meetings/process-audio`: multipart `file`, `title`, `clientRequestId`, `maxSpeakers`, `numSpeakers` (số người chính xác, 1–10, tùy chọn). Trả `{meetingId, jobId, status: "completed"|"failed", data|error}` với HTTP 200 kể cả khi AI lỗi; frontend phải kiểm tra `status`. Khi AI lỗi: job `FAILED` (giữ để tra lỗi), cuộc họp bị **xóa mềm** (`MeetingStatus` chưa có `FAILED`, thêm sẽ đổi schema DB chung), file audio bị xóa. Kết quả lưu trong một `TransactionTemplate`. Tên file upload được làm sạch qua `service/UploadFileNames`.
  - `GET /api/meetings/{id}/speakers`, `GET /api/meetings/{id}/segments?speakerId=`, `GET /api/meetings/{id}/processing` (`status`, `stage`, `errorMessage`, `diarizationEngine`, `asrModel`).
  - `POST /api/meetings/{id}/chat`: `{question, speakerId}` → `{answer, citations[{segmentId, speakerId, speakerLabel, startSeconds, endSeconds, quote}], insufficientEvidence}`. Java gửi mọi đoạn của cuộc họp kèm `speakerId` của bộ lọc; Python tự lọc.
- Audio: upload/list `/api/meetings/{meetingId}/audio` (GET trả danh sách JSON, không phải bytes); chi tiết `/api/meetings/audio/{audioId}`. Phát lại: `GET /api/meetings/{id}/audio/content` trả bytes file mới nhất, 404 nếu file không có trên máy chạy backend; frontend tải bằng `api.getMeetingAudio` (Blob, vì thẻ `<audio>` không gửi header JWT).
- STT cũ: `POST /api/audio/{audioId}/transcribe`; GET `/api/audio/{audioId}/transcript`, `/api/transcripts/{transcriptId}`.
- Notes: POST `/api/transcripts/{transcriptId}/notes`; GET `/api/meetings/{meetingId}/notes`; GET/PUT `/api/notes/{noteId}`; action items dưới `/api/notes/{noteId}/action-items`, PUT `/api/action-items/{itemId}`.
- Mô hình dữ liệu chính: User, Meeting, MeetingParticipant, AudioRecording, Transcript, TranscriptSegment, TranscriptSpeaker, MeetingProcessingJob, MeetingNote, ActionItem. Model đã dùng cho cuộc họp phân người lưu ở `Transcript.sttModelUsed` dạng `asr=...;diarization=...` (tránh đổi schema). Đọc entity trước khi đổi quan hệ; không trả trực tiếp JPA entity thay cho DTO.

### Frontend/Java ↔ Python

- `POST /api/transcribe`: multipart field `file`; nhận `.wav/.mp3/.m4a/.ogg/.flac`; trả `{status: "success", filename, transcript, summary}`. FastAPI lỗi dùng `detail`.
- `POST /api/summarize`: JSON `{transcript: "..."}`; trả `{status: "success", summary}`.
- `POST /api/process-meeting?max_speakers=&num_speakers=&job_id=`: multipart `file`. Trả kết quả v1 `{schema_version, transcript, summary, speakers, segments, warnings, models: {diarization, asr, summary}}`. `num_speakers` ngoài 1–10 hoặc audio không giải mã được → 400 có `detail`; đang có phiên live → 409. Danh sách `speakers` chỉ gồm người có ít nhất một đoạn có chữ. Mã `models.diarization`: `pyannote/speaker-diarization-community-1`, `acoustic-pitch-mfcc` (bộ dự phòng), `none` (phân người lỗi; đoạn có `speaker_id: null`, `attribution_status: "unknown"`).
- `POST /api/meeting-chat`: JSON `{question, segments, speaker_id}` → `{answer, citations, insufficient_evidence}`.
- `WS /ws/live-stream`: gửi JSON `{type:"start", sample_rate:16000}`, chờ `ready`, gửi binary PCM, kết thúc bằng `{type:"stop"}`; server trả `closed` sau khi flush.
- Message server: `ready`, `interim`, `final`, `lag`, `error`, `closed` (khai báo trong `ws_protocol.py`; xem handler để biết loại nào thực sự phát). UI thay interim bằng final theo `seq`; giữ các trường timing/`infer_ms` nếu sửa schema.
- Âm thanh wire: PCM Int16 mono 16 kHz; frame 20 ms = 320 mẫu = 640 byte. Worklet gom 10 frame = 200 ms = 3.200 mẫu = **6.400 byte**. Khi dừng, hook chờ worklet gửi phần còn lại và xác nhận `flushed` trước WS `stop`; packet cuối được đệm zero đủ frame cho VAD, WAV giữ số mẫu thật. Logic ở `frontend/src/utils/flushCapture.js`.
- Hook thử nạp `/capture.worklet.js` (bản `public/`) trước, rồi fallback bản `src/audio/`. Khi sửa processor, kiểm tra cả hai bản để không chạy code cũ. `useWavRecorder` dùng cùng worklet.
- Ghi âm gửi đi xử lý phải là WAV thật. Không dùng MediaRecorder: Chrome tạo WebM/Opus mà Python không đọc được khi máy chưa có FFmpeg.
- Sau khi dừng live có nút `Tải bản ghi âm` để lấy WAV gốc và test lại cùng âm thanh; object URL được thu hồi khi bắt đầu phiên mới hoặc unmount.
- CORS Python hiện là `allow_origins=["*"]`; WS chấp nhận Origin `localhost:5173`/`127.0.0.1:5173`, `*.trycloudflare.com` và mọi origin `https://`. Đổi host/port phải xem cả Python, Java CORS và các URL trực tiếp trong frontend; chỉ đổi Vite proxy không đủ.

## AI runtime và giới hạn hiện tại

- `lifespan` nạp ba model một lần vào `app.state`:
  - Live: `nguyenvulebinh/wav2vec2-base-vietnamese-250h`.
  - Batch: `vinai/PhoWhisper-small`.
  - Summary/chat: `Qwen/Qwen2.5-1.5B-Instruct`.
- Tự chọn `cuda:0` nếu `torch.cuda.is_available()`, nếu không dùng CPU. Qwen dùng float16 trên GPU, float32 trên CPU; CPU có thể chậm và tốn RAM.
- VAD có WebRTC và fallback RMS. Mặc định silence 350 ms, min speech 600 ms, max utterance 8.000 ms; ngưỡng nằm trong `vad_buffer.py`.
- Inference chạy qua `asyncio.to_thread` với `app.state.gpu_lock`. `/api/transcribe` và `/api/process-meeting` trả **409 khi có live session**. `stdio_utf8.ensure_utf8_stdio()` (gọi ở `main.py` và `tests/__init__.py`) đặt stdout UTF-8: thiếu nó, `print` lỗi tiếng Việt khi log chuyển ra file/pipe sẽ ném `UnicodeEncodeError`. Giữ việc flush/đóng phiên trước batch; không bỏ lock để chữa độ trễ.
- Upload Python dùng file tạm (giữ đuôi gốc) và dọn ở `finally`; không bỏ cleanup khi sửa xử lý lỗi.
- Pipeline phân người (`meeting_processing/service.py`):
  - `load_audio` đọc trước để lỗi giải mã thành 400 rõ ràng.
  - `diarize_with_engine` dùng pyannote khi đã cài và có token Hugging Face (biến `HF_TOKEN`, hoặc token lưu bằng `hf auth login` trong thư mục người dùng; model gated, phải đồng ý điều khoản trên trang model), ngược lại dùng bộ phân cụm pitch/MFCC. pyannote nhận dạng sóng đọc bằng librosa (`{"waveform", "sample_rate"}`), không nhận đường dẫn, để khỏi cần FFmpeg; lỗi phân người thì giữ transcript, đánh dấu `unknown`, không bịa người nói.
  - `prepare_turns` nhập lượt dưới 1,5 s vào lượt bên cạnh, nối lượt liền nhau cùng người, đánh lại Người 1/2... theo lần xuất hiện đầu tiên. Chuỗi lượt ngắn liền nhau được gán chung như một khối (pyannote hay sinh mẩu 0,01–0,4 s xen kẽ hai người ở chỗ chuyển lượt): theo người chiếm phần lớn khối nếu rõ rệt (≥ 1 s và gấp đôi người thứ hai), ngược lại theo lượt dài gần nhất. `padded_bounds` nới mỗi bên khi cắt audio cho ASR, không quá nửa khoảng nghỉ: 0,2 s với pitch/MFCC, 0,3 s với pyannote (biên sát hơn; `PYANNOTE_ASR_PAD_SECONDS`); mốc thời gian lưu vẫn là mốc gốc.
  - pyannote chạy với batch 8 (`PYANNOTE_BATCH_SIZE`; mặc định 32 cần thêm ~1,6 GB VRAM) và gọi `torch.cuda.empty_cache()` sau khi phân người. pyannote.audio 4.x cần torch ≥ 2.8, nên AI service chỉ dùng được pyannote khi chạy bằng môi trường có torch mới (xem CLAUDE.md).
  - Tóm tắt nhận văn bản **không nhãn** người nói; transcript lưu/hiển thị vẫn có `[Người N]:`. Sau đó `attribute_first_person_owners` đổi người nhận việc "mình/tôi/em..." thành nhãn người đang nói nếu nội dung việc khớp lượt nói của đúng một người (ưu tiên lượt có "mình/tôi/em sẽ <việc>", để câu chốt của chủ trì nhắc lại việc không làm mơ hồ). Ở chế độ tự đoán số người với bộ pitch/MFCC, `warnings` có lời nhắc chọn đúng số người. Cuối cùng `summary_supplement.supplement_summary` thêm vào tóm tắt các ý Qwen bỏ sót (Mục tiêu, Kết quả, Vấn đề, Quyết định) bằng quy tắc gom ý của chat, kèm "(Người N)": chỉ thêm, không sửa dòng của Qwen, bỏ ý đã có (khớp chữ). Chỉ áp dụng cho cuộc họp xử lý sau thay đổi này; tóm tắt cũ trong DB không đổi.
- Chat (`meeting_processing/chat.py`):
  - Câu hỏi nhắc "người 2/người hai/người số 2/người thứ hai" được lọc theo người đó (ưu tiên hơn bộ lọc UI). Chọn người ở bộ lọc UI rồi hỏi tổng quát cũng ra ý chính của người đó.
  - Cuộc họp > 35 đoạn: `rank_relevant_segments` chọn tối đa `top_k` đoạn theo thứ tự điểm (đoạn khớp + hai bên), còn chỗ mới bổ sung đoạn đầu; kết quả xếp lại theo thời gian.
  - Mã `[seg_XXXX]` model ghi trong câu trả lời được dùng để lấy trích dẫn rồi bỏ khỏi văn bản (`strip_segment_tags`).
  - Câu hỏi tổng quát về một người ("nói gì", "phát biểu", "ý kiến", "tóm tắt") trả **một đoạn ý chính** bằng quy tắc, không gọi model (Qwen 1.5B đảo nghĩa khi tóm lời một người): `split_ideas` tách ý tại dấu câu/từ nối và bỏ câu xã giao; `classify_idea` xếp nhóm (Mục tiêu, Quyết định, Đề xuất, Câu hỏi, Sẽ làm, Giao việc khi chủ thể trước "sẽ" không phải mình/tôi/em/nhóm, Đã làm, Vấn đề); `idea_phrase` biến mỗi ý thành cụm sau động từ dẫn ("báo", "nêu vấn đề", "sẽ", "đề xuất", "quyết định", "chốt lại:", "giao việc:"), bỏ câu hỏi, cắt ở mệnh đề mới (`NEW_CLAUSE`: từ nối hoặc chủ ngữ mới + động từ; trừ "vẫn còn", "phòng/trước/đôi khi"), quá 16 từ thì cắt ở "để/vì", không dừng ngay trước từ phủ định; các cụm nối bằng ";" theo thứ tự thời gian. Câu chữ lấy nguyên từ biên bản; trích dẫn là mọi lượt nói của người đó, chỉ có mốc thời gian (`quote` rỗng).
  - `display_idea` (bỏ khung câu, "(hạn: X)", tối đa 18 từ, "Quyết định" 40 từ) dùng cho `group_answer` và `extractive_answer`.
  - Câu hỏi chung có "mục tiêu/mục đích", "quyết định/chốt", "vấn đề/khó khăn/vướng", "đề xuất/đề nghị" trả bằng `group_answer`: liệt kê các ý thuộc nhóm đó (sau bộ lọc người nói), không gọi model; không có ý nào thì mới qua Qwen.
  - Câu hỏi về người tham gia ("bao nhiêu/mấy người", "những ai", "ai nói nhiều nhất") trả bằng `participant_answer` từ dữ liệu phân người (số lượt, số giây, %), kèm lưu ý số người có thể sai; không gọi model. Số lượt đếm bằng `count_turns`: các đoạn liền nhau của cùng người cách nhau ≤ 2 s là một lượt (pyannote hay chia một lượt thành nhiều đoạn). Nhóm "Quyết định" chỉ nhận "quyết định / chốt lại / chốt là / thống nhất là", không nhận "chốt" đứng riêng. "cuộc/họp/buổi/mọi" nằm trong stop words để khớp "cuộc họp" không được tính là căn cứ.
  - Câu hỏi khác qua Qwen (`_generate`, tách riêng để mock khi test). `grounding_ratio` đo tỷ lệ chữ nội dung của câu trả lời có trong các đoạn đưa cho model; dưới `GROUNDING_MIN` = 0,8 thì thay bằng `extractive_answer` (trích ý khớp nhất, cần khớp ≥ 2 từ khóa, ưu tiên ý cùng nhóm với câu hỏi) hoặc báo không đủ thông tin.
  - Giao diện rút gọn trích dẫn còn ~120 ký tự (rê chuột xem đủ) để câu trả lời không lặp nguyên văn quá dài.
- Tóm tắt: `summarization.service.run_summarize` trích xuất JSON gồm năm nhóm đoạn nguyên văn bằng greedy decoding. Code phân tích clause giao việc thành người/việc/thời hạn, kiểm tra với nguồn rồi dựng Markdown. Giữ response `summary` là chuỗi.
- Tên/ngày được giữ nguyên lời phiên âm; không tự quy đổi ngày tương đối hoặc bổ sung tháng/năm. Kiểm tra trích dẫn chỉ xác nhận khớp chữ, không đảm bảo quan hệ ngữ nghĩa hay sửa lỗi ASR. Công việc cùng người/nội dung nhưng khác thời hạn được giữ lại để xác nhận.
- Theo yêu cầu người dùng, `render.py` trình bày công việc ngắn gọn với `Hạn: ...` khi có hạn (dòng dạng `- **người:** việc. Hạn: ...`, `attribution.py` dựa vào định dạng này); bỏ nhãn `Thời hạn theo phiên âm`, câu xác nhận audio và ghi chú chung cuối bản. `needs_confirmation` vẫn phục vụ xử lý nội bộ; không in lời nhắc này cạnh từng công việc.
- `validation.align_actions_to_source` khớp tên/công việc vào clause đầy đủ trong nguồn trước khi dedup: phục hồi thời hạn bị cắt thành tiền tố, cắt metadata sau nhiệm vụ, giữ nguyên tên ASR (không tự đổi Lam thành Nam). Chỉ nối trong clause khớp, không chọn tùy ý giữa các ngày khác nhau. Không coi một tiền tố ngày và ngày đầy đủ cùng nguồn là hai thời hạn mâu thuẫn.
- Tách metadata nhiệm vụ dựa trên chủ thể được nhắc lại + thông tin chốt hạn, không phụ thuộc đúng chữ `chưa`. Khi mục kết quả kéo theo lời chào/mục tiêu, lấy lại chủ thể gần `đã hoàn thành` từ nguồn, không tự viết lại các từ ASR nghe sai.
- Chia nguồn theo token với overlap, hợp nhất mục trùng; giới hạn context/output trong `summarization/service.py`. Dừng generation khi đủ năm trường JSON để tránh sinh lặp. JSON/schema hoặc grounding lỗi được thử lại tối đa một lần mỗi đoạn; giữ phần đúng nếu retry thất bại.
- `validation.explicit_source_facts` bổ sung clause có mẫu giao việc rõ (`anh/chị ... sẽ/cần/phải ...`), câu tự nhận việc (`mình/tôi/em sẽ ...`, `first_person_commitments`, người nhận để là "mình"), yêu cầu chưa gán người (`Cần/Phải/Hãy ...`) và kết quả `đã hoàn thành` từ nguồn để giảm bỏ sót. "hạn (nộp) là X" tách thành hạn X. Câu tự nhận việc cũng là ranh giới kết thúc câu giao việc đứng trước. Phân công model trả dạng object (`name/work/deadline`, `action`) được `coerce_item` đổi sang schema; object ở mục sự kiện vẫn bị loại (đã thử chọn một giá trị: ra câu sai mục). Output JSON bị cụt vẫn bị loại, không vá. `merge_results` bỏ khỏi "Quyết định" câu chứa nội dung một việc đã có ở phân công. Đây là heuristic tiếng Việt, không phải bộ phân tích ngữ nghĩa tổng quát; cú pháp lạ/ngữ cảnh phủ định phức tạp cần đối chiếu. Không tạo được kết quả thì cảnh báo trong `summary`, không khẳng định cuộc họp không có nội dung.
- Lần đầu cần tải model từ Hugging Face. Không khởi động AI chỉ để kiểm tra thay đổi tài liệu/CSS; không tự tải lại model hay đổi dependency/model nếu tác vụ không cần.
- Không tự thêm nhiều worker: mỗi process nạp model riêng; lock/session counter hiện chỉ có phạm vi process.

## Chạy local bằng PowerShell

Yêu cầu: JDK 21 theo `backend/pom.xml`; Node.js tương thích Vite 8 (22.12+); Python 3.11 với venv có torch bản CUDA. `ai-service/requirements.txt` chưa khớp venv đang dùng (xem CLAUDE.md); `README.md` là hướng dẫn chạy demo cho nhóm (kịch bản demo, lỗi thường gặp); đổi lệnh chạy hoặc luồng demo thì sửa cả README. Các lệnh dưới chạy từ gốc repo, mỗi dịch vụ một terminal.

```powershell
# AI: chỉ tạo venv nếu chưa có, chỉ cài lại khi thiếu/đổi dependency
cd ai-service
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn main:app --port 8000
```

```powershell
# Backend (cần .env, xem bên dưới)
cd backend
.\mvnw.cmd spring-boot:run
```

```powershell
# Frontend: npm ci dành cho lần cài đầu hoặc khi lockfile đổi
cd frontend
npm ci
npm run dev -- --port 5173 --strictPort
```

- UI: `http://localhost:5173`; Python docs: `http://localhost:8000/docs`. Đợi `Application startup complete` trước khi thử AI.
- DB: PostgreSQL online **dùng chung cả nhóm**. Backend đọc `.env` ở gốc repo hoặc `backend/` (`spring.config.import`) với `DB_URL`, `DB_USERNAME`, `DB_PASSWORD`, `JWT_SECRET`; mẫu ở `.env.example`, `.env` bị Git bỏ qua. Không in, ghi vào tài liệu hay commit giá trị thật.
- `spring.jpa.hibernate.ddl-auto=update` và **chưa có Flyway**: chạy backend trên nhánh có entity mới sẽ đổi schema DB chung của cả nhóm. Không đổi entity hoặc chạy backend/test với entity mới khi chưa được người dùng đồng ý.
- Audio Java lưu ở `./uploads/audio/{meetingId}/` tương đối với working directory (thường là `backend/`); `**/uploads/` đã được Git bỏ qua. File chỉ có trên máy đã nhận nó, trong khi DB dùng chung.
- Giới hạn upload Java: 100 MB (WAV 16 kHz mono ≈ 54 phút). `RestTemplate` có connect timeout 30 s, read timeout 300 s, nên xử lý cuộc họp dài có thể bị Java ngắt dù AI vẫn chạy.
- Java AI URL: `app.ai-service.base-url` và `app.ai-service.transcribe-endpoint`. Frontend AI HTTP/WS của tab live/upload hardcode localhost; chưa có cơ chế `VITE_*` chung.
- Micro cần quyền trình duyệt và secure context (localhost hoặc HTTPS). Các ghi chú Kaggle/Cloudflare trong file không phải cấu hình triển khai đang hoạt động.

## Kiểm tra theo phạm vi thay đổi

| Thay đổi | Kiểm tra phù hợp |
| --- | --- |
| Chỉ tài liệu | Xác minh đường dẫn/lệnh/claim với source; `git diff --check`; không cần boot service |
| Frontend | Từ `frontend/`: `npm run build`; `npm run lint` (oxlint; không dùng `npx eslint` vì không có config) khi đổi JS; thử giao diện liên quan nếu có runtime |
| Định dạng summary trên frontend | Từ `frontend/`: `node tests/summaryMarkdown.test.js`; parser chỉ hỗ trợ heading/list/emphasis, không biến dữ liệu nguồn thành HTML |
| AudioWorklet, flush, WAV cuối phiên | Từ `frontend/`: `node tests/captureFlush.test.js`; kiểm tra đủ số mẫu, đệm packet WS, thứ tự flush → stop và hai bản worklet đồng bộ |
| Backend | Từ `backend/`: `.\mvnw.cmd -q -o compile`. `.\mvnw.cmd test` chỉ có `contextLoads` và **kết nối DB chung** với `ddl-auto=update`; chỉ chạy khi được đồng ý |
| VAD/buffer | Từ `ai-service/`: `.\venv\Scripts\python.exe test_vad_buffer.py` (script trực tiếp, không bắt buộc pytest) |
| Python không nạp model (tóm tắt, phân người, chat, HTTP contract) | Từ `ai-service/`: `.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"` |
| Chất lượng phân người | Từ `ai-service/`: `.\venv\Scripts\python.exe -m tests.evaluate_diarization --audio ../data_test/demo_meeting/demo_meeting.wav --reference ../data_test/demo_meeting/demo_meeting_reference.json` (`--num-speakers N`, `--raw`, `--engine acoustic` để ép pitch/MFCC); in bộ phân người đã dùng và thời gian |
| WS/audio protocol | AI đang chạy + `data_test/test_2.mp3`: `.\venv\Scripts\python.exe test_live_stream_ws.py`; thử mic/start/stop/batch trên browser |
| Prompt/model | Dùng audio/transcript mẫu liên quan, ghi nhận độ đúng/độ trễ; không chạy toàn bộ benchmark mặc định |

Benchmark summary tùy chọn, chỉ dùng model đã cache: từ `ai-service/`, `.\venv\Scripts\python.exe -m tests.evaluate_summary`. Có `--case customer_service`, `--output temp_summary_report.json`, `--baseline-ref <revision>` (revision phải chứa pipeline cũ). Fixtures ở `tests/fixtures/summary_cases.json`; mẫu ASR nhiễu dùng `--fixture tests/fixtures/realtime_regression.json`. Coverage keyword không thay thế việc đọc và đối chiếu nội dung; đo ASR/audio riêng.
Kết quả đo mẫu và giới hạn nằm ở `ai-service/tests/SUMMARY_EVALUATION.md`. Benchmark chỉ nạp Qwen, không đại diện VRAM/latency của cả ba model đang chạy cùng nhau.
Đánh giá ASR trên cùng audio: từ `ai-service/`, `.\venv\Scripts\python.exe -m tests.evaluate_asr --audio ../data_test/test_2.mp3 --output temp_asr_report.json`. Thêm `--reference <file.txt>` chỉ khi đã kiểm chứng bản chữ bằng nghe audio; không dùng transcript từ ASR làm ground truth. Xem `tests/ASR_EVALUATION.md` (gồm phát hiện về cắt audio sát mép khi ASR từng lượt). Chưa thay model/decoding mặc định chỉ vì tăng beam: trên file mẫu đã thử, beam 5 không đổi transcript và chậm hơn beam 1.
Audio demo 3 người có đáp án: `data_test/demo_meeting/` (tạo lại bằng `make_demo_audio.py`, cần venv riêng có `edge-tts soundfile numpy` và Internet). Giọng tổng hợp không thay được bản ghi người thật.

`ai-service/test_model.py` là benchmark có đường dẫn dataset Kaggle, không phải unit test local chạy mặc định. Chưa có script frontend unit test trong `package.json`. Không báo kiểm tra thành công nếu chưa chạy; phân biệt lỗi code với thiếu môi trường/network/quyền chạy process.

## Quy tắc thay đổi và bàn giao

- Giữ phạm vi sửa nhỏ; theo cách tổ chức hiện có. Khi đổi API/schema/status, cập nhật các bên gọi và test liên quan trong cùng thay đổi.
- Không nhầm việc UI hiển thị "tự lưu" với chức năng persistence đã nối. Muốn tự lưu phải thiết kế rõ chuỗi tạo meeting → upload → transcript/note và refresh lịch sử.
- Không ghi cố định tên model/bộ phân người trên giao diện; hiển thị theo `models`/`diarizationEngine` do backend trả.
- Không đưa URL tunnel tạm, credentials, model weights, audio người dùng hoặc file build vào commit. Không coi secret JWT mặc định trong `application.properties` là cấu hình production.
- Không sửa code người dùng chưa commit chỉ để làm sạch diff; không tự stash/pop nếu không cần. Nếu cần lưu tạm trong tác vụ Git được yêu cầu, khôi phục đúng phần sửa và báo trạng thái cuối.
- Sau cùng: tóm tắt kết quả, file đổi, kiểm tra đã chạy, giới hạn còn lại. Không commit/push chỉ vì đã hoàn tất sửa file.
- Khi cập nhật tài liệu này, sửa mục hiện hữu thay vì thêm đoạn trùng lặp; giữ nội dung đủ ngắn để dùng như điểm vào cho phiên tiếp theo. Cập nhật `CLAUDE.md` cùng lúc nếu thông tin thuộc phần của nó.
