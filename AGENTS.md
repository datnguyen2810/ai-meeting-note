# AI Meeting Note — hướng dẫn làm việc cho agent

## Đọc trước khi làm việc

- Đây là bản đồ dự án, không thay thế mã nguồn. Khi có khác biệt, ưu tiên code/config đang checkout và cập nhật tài liệu này.
- Bắt đầu bằng `git status --short --branch`; giữ nguyên thay đổi chưa commit của người dùng. Không tự reset, discard, commit hoặc push ngoài phạm vi yêu cầu.
- Chỉ đọc mục liên quan bên dưới, sau đó mở các file được chỉ dẫn. Không quét/đọc lại toàn repo mỗi lượt hoặc sau khi nén ngữ cảnh.
- Dùng `rg -n` để tìm symbol/endpoint và đọc vùng cần sửa; dùng `rg --files <thư-mục>` để tìm file. Đọc UTF-8 (`Get-Content -Encoding utf8` trên PowerShell).
- Không đọc `venv/`, `node_modules/`, `target/`, `dist/`, cache/model weights, audio, PDF hoặc notebook lớn nếu tác vụ không cần chúng. Không đọc toàn bộ lockfile để tìm một dependency.
- Trong cùng phiên, giữ lại mục tiêu, quyết định, file đã sửa, kiểm tra đã chạy và việc còn lại; chỉ đọc lại khi file thay đổi hoặc cần xác minh.
- Chỉ cập nhật kiến thức bền vững ở đây khi kiến trúc, API, lệnh chạy hoặc vị trí file đổi. Không ghi log hội thoại, trạng thái nhánh, URL tunnel tạm, token hay thông tin riêng vào tài liệu.

## Tổng quan và kiến trúc thực tế

Đồ án HTTM/PTIT: nhận diện tiếng Việt từ âm thanh/cuộc họp trực tiếp, tạo bản phiên âm và tóm tắt. Monorepo gồm ba tiến trình chạy độc lập:

| Thành phần | Công nghệ / cổng local | Trách nhiệm |
| --- | --- | --- |
| `frontend/` | React 19, Vite 8 / `5173` | Landing, đăng nhập, dashboard, micro, phụ đề, upload, xuất Markdown |
| `backend/` | Java 21, Spring Boot 4.1.1, Maven / `8080` | JWT, cuộc họp, file audio, transcript, note, action item, JPA/H2 |
| `ai-service/` | Python, FastAPI, PyTorch, Transformers / `8000` | WebSocket ASR, batch ASR, tóm tắt bằng LLM |

```text
Trình duyệt :5173
  ├─ /api/auth, /api/meetings... → Vite proxy → Java :8080 → H2 + uploads/audio
  │                                               └─ AiServiceClient → Python :8000
  ├─ ws://localhost:8000/ws/live-stream → Wav2Vec2 → interim/final captions
  └─ http://localhost:8000/api/transcribe → PhoWhisper → Qwen → transcript + summary
```

**Phân biệt luồng đã nối và chức năng backend có sẵn:**

- `App.jsx` quản lý trang bằng React state (`landing`, `auth`, `dashboard`), chưa dùng router. Dashboard có lịch sử cuộc họp lấy từ Java.
- Hai công cụ đang gắn vào dashboard là `LiveMeetingRoom` và `SpeechToTextDemo`; chúng gọi Python trực tiếp, không qua API Java và chưa tự lưu kết quả vào lịch sử.
- Sau khi dừng live, hook đóng gói WAV trong bộ nhớ; `LiveMeetingRoom` gửi WAV sang batch ASR + tóm tắt và cho xuất Markdown.
- Backend đã có API lưu audio và chạy STT: `AudioService → SttService → AiServiceClient`. Client chỉ lấy trường `transcript`, chưa lưu `summary` Python trả về.
- `MeetingNoteService.generateNote()` hiện sao chép raw transcript vào summary của note, chưa gọi LLM. Không mô tả luồng này là tóm tắt Qwen đã tích hợp.
- `AuthModal.jsx` còn trong repo, nhưng luồng đăng nhập chính hiện dùng `pages/AuthPage.jsx`.

## Bản đồ file: mở đâu khi sửa

Các đường dẫn Java bên dưới tính từ `backend/src/main/java/vn/httm/backend/`.

| Tác vụ | File/thư mục cần đọc trước |
| --- | --- |
| Landing, auth, điều hướng, lịch sử | `frontend/src/App.jsx`, `pages/LandingPage.jsx`, `pages/AuthPage.jsx` (hai thư mục `pages/` nằm dưới `frontend/src/`) |
| Giao diện/CSS | `frontend/src/App.css`, `index.css`, `styles/`, CSS đi kèm component |
| JWT client, request Java | `frontend/src/services/api.js`, `frontend/vite.config.js` |
| Live UI, stop → batch, xuất Markdown | `frontend/src/components/LiveMeetingRoom.jsx` và `.css` |
| Micro, vòng đời socket, captions | `frontend/src/hooks/useLiveTranscription.js` |
| PCM / WAV | `frontend/public/capture.worklet.js`, `frontend/src/audio/capture.worklet.js`, `frontend/src/utils/encodeWav.js` |
| Upload trực tiếp sang Python | `frontend/src/components/SpeechToTextDemo.jsx`, `MeetingNote.css` cùng thư mục |
| Hiển thị tóm tắt có định dạng | `frontend/src/components/SummaryContent.jsx`, `.css`, `frontend/src/utils/summaryMarkdown.js`; dùng chung cho upload và live, giữ Markdown gốc khi xuất `.md` |
| AI startup, ASR, HTTP/WS | `ai-service/main.py` (`lifespan`, `run_ctc_inference`, `websocket_live_stream`); `run_summarize` được import từ package riêng |
| Tóm tắt, prompt, dữ kiện, Markdown | `ai-service/summarization/`: `service.py`, `prompts.py`, `schema.py`, `validation.py`, `render.py` |
| VAD, cắt utterance, giao thức | `ai-service/vad_buffer.py`, `ai-service/ws_protocol.py` |
| Java API / nghiệp vụ / DB | `controller/` → `service/` → `repository/`, `entity/`, `dto/` |
| Java authentication | `config/SecurityConfig.java`, `security/`, `service/AuthService.java` |
| Java gọi AI, file upload | `client/AiServiceClient.java`, `service/SttService.java`, `service/AudioService.java` |
| DB, JWT, AI URL, upload limit | `backend/src/main/resources/application.properties` |
| Thử nghiệm / benchmark | `models_testing/`, `ai-service/test_model.py`, `data_test/` — chỉ đọc khi cần đánh giá model |
| Thiết kế realtime chi tiết | `PLAN_REALTIME_HYBRID_ASR.md` — tài liệu thiết kế; xác minh lại với code |

## Hợp đồng giao tiếp cần giữ đồng bộ

### Frontend ↔ Java

- `services/api.js`: API base `/api`; Vite proxy tới `http://localhost:8080` khi chạy dev. Proxy không tự tồn tại khi chỉ host thư mục build.
- Session lưu trong localStorage: `auth_token`, `auth_user`. Request Java gửi `Authorization: Bearer <token>`; sự kiện `auth_logout` đồng bộ UI khi hết phiên.
- Response Java dùng `ApiResponse<T>`: `{success, message, data}`. Response FastAPI có schema riêng, không bọc trong `data`.
- Auth: `POST /api/auth/register`, `POST /api/auth/login`. Security hiện cho phép `/api/auth/**`, `/h2-console/**`, `/error`; các đường dẫn còn lại yêu cầu đăng nhập.
- Meetings: CRUD `/api/meetings`, `/api/meetings/{id}`; participants dưới `/{id}/participants`.
- Audio: upload/list `/api/meetings/{meetingId}/audio`; chi tiết `/api/meetings/audio/{audioId}`.
- STT: `POST /api/audio/{audioId}/transcribe`; GET `/api/audio/{audioId}/transcript`, `/api/transcripts/{transcriptId}`.
- Notes: POST `/api/transcripts/{transcriptId}/notes`; GET `/api/meetings/{meetingId}/notes`; GET/PUT `/api/notes/{noteId}`; action items dưới `/api/notes/{noteId}/action-items`, PUT `/api/action-items/{itemId}`.
- Mô hình dữ liệu chính: User, Meeting, MeetingParticipant, AudioRecording, Transcript, TranscriptSegment, MeetingNote, ActionItem. Đọc entity trước khi đổi quan hệ; không trả trực tiếp JPA entity thay cho DTO.

### Frontend/Java ↔ Python

- `POST /api/transcribe`: multipart field `file`; nhận `.wav/.mp3/.m4a/.ogg/.flac`; trả `{status: "success", filename, transcript, summary}`. FastAPI lỗi dùng `detail`.
- `POST /api/summarize`: JSON `{transcript: "..."}`; trả `{status: "success", summary}`.
- `WS /ws/live-stream`: gửi JSON `{type:"start", sample_rate:16000}`, chờ `ready`, gửi binary PCM, kết thúc bằng `{type:"stop"}`; server trả `closed` sau khi flush.
- Message server: `ready`, `interim`, `final`, `lag`, `error`, `closed` (khai báo trong `ws_protocol.py`; xem handler để biết loại nào thực sự phát). UI thay interim bằng final theo `seq`; giữ các trường timing/`infer_ms` nếu sửa schema.
- Âm thanh wire: PCM Int16 mono 16 kHz; frame 20 ms = 320 mẫu = 640 byte. Worklet gom 10 frame = 200 ms = 3.200 mẫu = **6.400 byte**. Khi dừng, hook chờ worklet gửi phần còn lại và xác nhận `flushed` trước WS `stop`; packet cuối được đệm zero đủ frame cho VAD, WAV giữ số mẫu thật. Logic ở `frontend/src/utils/flushCapture.js`.
- Hook thử nạp `/capture.worklet.js` (bản `public/`) trước, rồi fallback bản `src/audio/`. Khi sửa processor, kiểm tra cả hai bản để không chạy code cũ.
- Sau khi dừng live có nút `Tải bản ghi âm` để lấy WAV gốc và test lại cùng âm thanh; object URL được thu hồi khi bắt đầu phiên mới hoặc unmount. Đây là bản ghi trong browser, không có nghĩa đã lưu vào lịch sử backend.
- Python kiểm tra Origin WS và CORS cho `localhost:5173`/`127.0.0.1:5173`. Đổi host/port phải xem cả Python, Java CORS và các URL trực tiếp trong frontend; chỉ đổi Vite proxy không đủ.

## AI runtime và giới hạn hiện tại

- `lifespan` nạp ba model một lần vào `app.state`:
  - Live: `nguyenvulebinh/wav2vec2-base-vietnamese-250h`.
  - Batch: `vinai/PhoWhisper-small`.
  - Summary: `Qwen/Qwen2.5-1.5B-Instruct`.
- Tự chọn `cuda:0` nếu `torch.cuda.is_available()`, nếu không dùng CPU. Qwen dùng float16 trên GPU, float32 trên CPU; CPU có thể chậm và tốn RAM.
- VAD có WebRTC và fallback RMS. Mặc định silence 350 ms, min speech 600 ms, max utterance 8.000 ms; ngưỡng nằm trong `vad_buffer.py`.
- Inference chạy qua `asyncio.to_thread` với `app.state.gpu_lock`. `/api/transcribe` trả **409 khi có live session**. Giữ việc flush/đóng phiên trước batch; không bỏ lock để chữa độ trễ.
- Upload Python dùng file tạm và dọn ở `finally`; không bỏ cleanup khi sửa xử lý lỗi.
- Tóm tắt: `summarization.service.run_summarize` trích xuất JSON gồm năm nhóm đoạn nguyên văn bằng greedy decoding. Code phân tích clause giao việc thành người/việc/thời hạn, kiểm tra với nguồn rồi dựng Markdown. Giữ response `summary` là chuỗi; chưa đổi API Java/frontend.
- Tên/ngày được giữ nguyên lời phiên âm; không tự quy đổi ngày tương đối hoặc bổ sung tháng/năm. Kiểm tra trích dẫn chỉ xác nhận khớp chữ, không đảm bảo quan hệ ngữ nghĩa hay sửa lỗi ASR. Công việc cùng người/nội dung nhưng khác thời hạn được giữ lại để xác nhận.
- Theo yêu cầu người dùng, `render.py` trình bày công việc ngắn gọn với `Hạn: ...` khi có hạn; bỏ nhãn `Thời hạn theo phiên âm`, câu xác nhận audio và ghi chú chung cuối bản. `needs_confirmation` vẫn phục vụ xử lý nội bộ; không in lời nhắc này cạnh từng công việc.
- `validation.align_actions_to_source` khớp tên/công việc vào clause đầy đủ trong nguồn trước khi dedup: phục hồi thời hạn bị cắt thành tiền tố, cắt metadata sau nhiệm vụ, giữ nguyên tên ASR (không tự đổi Lam thành Nam). Chỉ nối trong clause khớp, không chọn tùy ý giữa các ngày khác nhau. Không coi một tiền tố ngày và ngày đầy đủ cùng nguồn là hai thời hạn mâu thuẫn.
- Tách metadata nhiệm vụ dựa trên chủ thể được nhắc lại + thông tin chốt hạn, không phụ thuộc đúng chữ `chưa`. Khi mục kết quả kéo theo lời chào/mục tiêu, lấy lại chủ thể gần `đã hoàn thành` từ nguồn, không tự viết lại các từ ASR nghe sai.
- Chia nguồn theo token với overlap, hợp nhất mục trùng; giới hạn context/output trong `summarization/service.py`. Dừng generation khi đủ năm trường JSON để tránh sinh lặp. JSON/schema hoặc grounding lỗi được thử lại tối đa một lần mỗi đoạn; giữ phần đúng nếu retry thất bại.
- `validation.explicit_source_facts` bổ sung clause có mẫu giao việc rõ (`anh/chị ... sẽ/cần/phải ...`), yêu cầu chưa gán người (`Cần/Phải/Hãy ...`) và kết quả `đã hoàn thành` từ nguồn để giảm bỏ sót. Đây là heuristic tiếng Việt, không phải bộ phân tích ngữ nghĩa tổng quát; cú pháp lạ/ngữ cảnh phủ định phức tạp cần đối chiếu. Không tạo được kết quả thì cảnh báo trong `summary`, không khẳng định cuộc họp không có nội dung.
- Lần đầu cần tải model từ Hugging Face. Không khởi động AI chỉ để kiểm tra thay đổi tài liệu/CSS; không tự tải lại model hay đổi dependency/model nếu tác vụ không cần.
- Không tự thêm nhiều worker: mỗi process nạp model riêng; lock/session counter hiện chỉ có phạm vi process.

## Chạy local bằng PowerShell

Yêu cầu: JDK 21 theo `backend/pom.xml`; Node.js tương thích Vite 8 (22.12+); Python phù hợp các package đã pin trong `ai-service/requirements.txt`. README có thể còn thông tin stack cũ; ưu tiên manifest. Các lệnh dưới chạy từ gốc repo, mỗi dịch vụ một terminal.

```powershell
# AI: chỉ tạo venv nếu chưa có, chỉ cài lại khi thiếu/đổi dependency
cd ai-service
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn main:app --port 8000
```

```powershell
# Backend
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
- Backend hiện dùng H2 in-memory `httmdb`, `ddl-auto=create-drop`; restart làm mất tài khoản và dữ liệu DB. Không cần MySQL cho cấu hình local này.
- Audio Java lưu ở `./uploads/audio` tương đối với working directory (thường là `backend/`). File trên đĩa và dữ liệu H2 có vòng đời khác nhau.
- Giới hạn upload Java: 100 MB. Không suy ra Python cũng có cùng giới hạn.
- Java AI URL: `app.ai-service.base-url` và `app.ai-service.transcribe-endpoint`. Frontend AI HTTP/WS hiện hardcode localhost ở component/hook; chưa có cơ chế `VITE_*` chung.
- Micro cần quyền trình duyệt và secure context (localhost hoặc HTTPS). Các ghi chú Kaggle/Cloudflare trong file không phải cấu hình triển khai đang hoạt động.

## Kiểm tra theo phạm vi thay đổi

| Thay đổi | Kiểm tra phù hợp |
| --- | --- |
| Chỉ tài liệu | Xác minh đường dẫn/lệnh/claim với source; `git diff --check`; không cần boot service |
| Frontend | Từ `frontend/`: `npm run build`; `npm run lint` khi đổi JS; thử giao diện liên quan nếu có runtime |
| Định dạng summary trên frontend | Từ `frontend/`: `node tests/summaryMarkdown.test.js`; parser chỉ hỗ trợ heading/list/emphasis, không biến dữ liệu nguồn thành HTML |
| AudioWorklet, flush, WAV cuối phiên | Từ `frontend/`: `node tests/captureFlush.test.js`; kiểm tra đủ số mẫu, đệm packet WS, thứ tự flush → stop và hai bản worklet đồng bộ |
| Backend | Từ `backend/`: `.\mvnw.cmd test`; hiện có test `contextLoads`, không coi là đã kiểm tra đủ nghiệp vụ |
| VAD/buffer | Từ `ai-service/`: `.\venv\Scripts\python.exe test_vad_buffer.py` (script trực tiếp, không bắt buộc pytest) |
| Logic + HTTP contract tóm tắt (không nạp model) | Từ `ai-service/`: `.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_summarization*.py" -v` |
| WS/audio protocol | AI đang chạy + `data_test/test_2.mp3`: `.\venv\Scripts\python.exe test_live_stream_ws.py`; thử mic/start/stop/batch trên browser |
| Prompt/model | Dùng audio/transcript mẫu liên quan, ghi nhận độ đúng/độ trễ; không chạy toàn bộ benchmark mặc định |

Benchmark summary tùy chọn, chỉ dùng model đã cache: từ `ai-service/`, `.\venv\Scripts\python.exe -m tests.evaluate_summary`. Có `--case customer_service`, `--output temp_summary_report.json`, `--baseline-ref <revision>` (revision phải chứa pipeline cũ). Fixtures ở `tests/fixtures/summary_cases.json`; mẫu ASR nhiễu dùng `--fixture tests/fixtures/realtime_regression.json`. Coverage keyword không thay thế việc đọc và đối chiếu nội dung; đo ASR/audio riêng.
Kết quả đo mẫu và giới hạn nằm ở `ai-service/tests/SUMMARY_EVALUATION.md`. Benchmark chỉ nạp Qwen, không đại diện VRAM/latency của cả ba model đang chạy cùng nhau.
Đánh giá ASR trên cùng audio: từ `ai-service/`, `.\venv\Scripts\python.exe -m tests.evaluate_asr --audio ../data_test/test_2.mp3 --output temp_asr_report.json`. Thêm `--reference <file.txt>` chỉ khi đã kiểm chứng bản chữ bằng nghe audio; không dùng transcript từ ASR làm ground truth. Xem `tests/ASR_EVALUATION.md`. Chưa thay model/decoding mặc định chỉ vì tăng beam: trên file mẫu đã thử, beam 5 không đổi transcript và chậm hơn beam 1.

`ai-service/test_model.py` là benchmark có đường dẫn dataset Kaggle, không phải unit test local chạy mặc định. Chưa có script frontend unit test trong `package.json`. Không báo kiểm tra thành công nếu chưa chạy; phân biệt lỗi code với thiếu môi trường/network/quyền chạy process.

## Quy tắc thay đổi và bàn giao

- Giữ phạm vi sửa nhỏ; theo cách tổ chức hiện có. Khi đổi API/schema/status, cập nhật các bên gọi và test liên quan trong cùng thay đổi.
- Không nhầm việc UI hiển thị "tự lưu" với chức năng persistence đã nối. Muốn tự lưu phải thiết kế rõ chuỗi tạo meeting → upload → transcript/note và refresh lịch sử.
- Không đưa URL tunnel tạm, credentials, model weights, audio người dùng hoặc file build vào commit. Không coi secret JWT local hiện có là cấu hình production.
- Không sửa code người dùng chưa commit chỉ để làm sạch diff; không tự stash/pop nếu không cần. Nếu cần lưu tạm trong tác vụ Git được yêu cầu, khôi phục đúng phần sửa và báo trạng thái cuối.
- Sau cùng: tóm tắt kết quả, file đổi, kiểm tra đã chạy, giới hạn còn lại. Không commit/push chỉ vì đã hoàn tất sửa file.
- Khi cập nhật tài liệu này, sửa mục hiện hữu thay vì thêm đoạn trùng lặp; giữ nội dung đủ ngắn để dùng như điểm vào cho phiên tiếp theo.
