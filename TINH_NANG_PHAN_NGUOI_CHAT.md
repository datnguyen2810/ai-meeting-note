# Tính năng: Phân vai người nói, tóm tắt và hỏi đáp cuộc họp

Tài liệu cho các thành viên nhóm đọc để hiểu và trình bày với giảng viên. Cách chạy demo xem `README.md`; chi tiết kỹ thuật cho người sửa code xem `AGENTS.md`.

## 1. Tính năng làm được gì

Người dùng đưa vào một bản ghi cuộc họp tiếng Việt (ghi âm trực tiếp trên trình duyệt hoặc chọn file WAV/MP3/FLAC/OGG). Hệ thống trả về:

1. **Biên bản theo người nói:** mỗi đoạn có nhãn `Người 1`, `Người 2`…, mốc thời gian; bấm vào đoạn để nghe lại đúng chỗ đó.
2. **Bản tóm tắt có cấu trúc:** Mục tiêu, Kết quả, Vấn đề, Quyết định, Phân công (ai làm gì, hạn khi nào).
3. **Chatbot hỏi đáp** về nội dung cuộc họp. Mỗi câu trả lời kèm **trích dẫn** (người nói + mốc thời gian) để kiểm chứng lại.

Mọi kết quả được lưu vào CSDL, mở lại được từ lịch sử cuộc họp.

## 2. Luồng xử lý tổng thể

```text
Trình duyệt (React)                Java Spring Boot                   Python FastAPI (AI)
──────────────────                 ────────────────                   ───────────────────
Ghi âm WAV / chọn file
  │ POST /api/meetings/process-audio
  │ (file, số người nếu biết) ───► Tạo cuộc họp + job xử lý
                                   Lưu file audio
                                     │ POST /api/process-meeting ───► 1. Đọc audio
                                                                      2. Phân người nói
                                                                      3. Dọn lượt nói
                                                                      4. ASR từng lượt
                                                                      5. Tóm tắt (Gemini/Qwen)
                                                                      6. Hậu xử lý tóm tắt
                                     ◄──────────────────── JSON: transcript, speakers,
                                                                 segments, summary, models
                                   Lưu transcript, người nói,
                                   các đoạn, tóm tắt (1 transaction)
  ◄──────────────────────────────  Trả kết quả
Hiển thị biên bản + tóm tắt

Hỏi chatbot
  │ POST /api/meetings/{id}/chat ► Kiểm tra quyền, lấy các đoạn
                                     │ POST /api/meeting-chat ──────► Chọn cách trả lời
                                     ◄──────────────────────────────  answer + citations
  ◄──────────────────────────────
```

**Vì sao đi qua Java mà không gọi thẳng Python?** Java giữ phần nghiệp vụ: đăng nhập (JWT), kiểm tra người dùng có quyền xem cuộc họp, lưu dữ liệu vào PostgreSQL. Python chỉ làm phần AI và không giữ trạng thái.

**Vì sao ghi âm ra WAV chứ không dùng MediaRecorder?** Chrome ghi ra WebM/Opus, Python không đọc được nếu máy chưa cài FFmpeg. Frontend tự gom mẫu PCM qua AudioWorklet rồi đóng gói WAV 16 kHz.

## 3. Các bước trong AI service

Code: `ai-service/meeting_processing/service.py` (hàm `process_meeting_pipeline`).

### Bước 1 — Đọc audio

Đọc bằng `librosa`/`soundfile`, chuyển về mono 16 kHz. File hỏng thì báo lỗi 400 rõ ràng ngay, không chạy tiếp.

### Bước 2 — Phân người nói (speaker diarization)

Trả lời câu hỏi "ai nói lúc nào": chia bản ghi thành các lượt `[bắt đầu, kết thúc, người]`. Có hai bộ, chọn tự động (`diarize.py`):

| Bộ | Khi nào dùng | Cách hoạt động |
| --- | --- | --- |
| **pyannote** `speaker-diarization-community-1` | Máy đã cài `pyannote.audio` (cần torch ≥ 2.8) và đăng nhập Hugging Face | Mạng nơ-ron huấn luyện sẵn: phát hiện tiếng nói, tạo vector đặc trưng giọng (embedding) cho từng đoạn, phân cụm thành từng người. Tự đoán số người. |
| **Pitch/MFCC** (nhóm tự viết, `acoustic-pitch-mfcc`) | Mặc định khi không có pyannote; không cần Internet hay token | Tách các khúc có tiếng bằng ngưỡng năng lượng, trích đặc trưng âm học (cao độ F0, MFCC, spectral centroid/bandwidth), chuẩn hóa rồi phân cụm **Agglomerative Clustering** (sklearn). Số người: dùng số người dùng nhập, nếu không thì chọn theo điểm silhouette. |

Nếu cả hai lỗi, hệ thống vẫn phiên âm và tóm tắt cả bản ghi nhưng đánh dấu "Chưa rõ người nói", **không gán người giả**.

### Bước 3 — Dọn lượt nói (`turns.py`)

Kết quả phân người thô có nhiều mẩu rất ngắn (pyannote sinh chuỗi mẩu 0,01–0,4 s xen kẽ hai người ở chỗ chuyển lượt). Hệ thống:

- Nhập lượt dưới **1,5 s** vào lượt bên cạnh; chuỗi mẩu ngắn liền nhau gán chung cho người chiếm phần lớn khối đó.
- Nối các lượt liền nhau của cùng một người.
- Đánh số lại `Người 1, 2, 3…` theo thứ tự xuất hiện.

### Bước 4 — Nhận dạng giọng nói (ASR) từng lượt

Model: **`vinai/PhoWhisper-small`** (Whisper được VinAI huấn luyện thêm cho tiếng Việt).

Mỗi lượt được cắt riêng rồi đưa vào PhoWhisper, nên mỗi câu chữ gắn chắc với một người và một mốc thời gian. Khi cắt, **nới mỗi bên 0,2 s** (pitch/MFCC) hoặc **0,3 s** (pyannote): cắt sát mép thì PhoWhisper hay bỏ mất từ, nhất là các từ chỉ số ("thứ sáu", "mười lăm giây").

### Bước 5 — Tóm tắt bằng LLM

Model: **Gemini API** (`gemini-3.5-flash-lite`, dự phòng `gemini-3.5-flash`; đổi bằng `GEMINI_MODEL`) khi có `GEMINI_API_KEY`; không có khóa hoặc Gemini lỗi thì dùng **`Qwen/Qwen2.5-1.5B-Instruct`** chạy local (code ở `ai-service/summarization/`, chọn model ở `ai-service/llm_backend.py`).

- **Với Gemini:** API ép trả đúng cấu trúc JSON (5 nhóm; phân công là object người / việc / hạn / câu gốc, mỗi trường chép nguyên văn). Các lượt nói được nối bằng dấu chấm (vẫn không có nhãn) để model biết chỗ chuyển người. Code vẫn kiểm tra từng trường có thật trong biên bản. Các quy tắc vá cho Qwen (nối câu bị cắt, thêm câu giao việc bằng regex, bước 6 "bổ sung ý bị sót") **tắt** vì trên lời không dấu câu chúng cắt sai và thêm dòng trùng (đã đo).
- **Với Qwen** (các ý dưới đây):

- Prompt yêu cầu Qwen **trích nguyên văn** các đoạn thuộc 5 nhóm và trả về JSON, giải mã greedy (không ngẫu nhiên).
- Văn bản đưa vào **không kèm nhãn** `[Người N]`: khi kèm nhãn, Qwen trả sai cấu trúc, nhãn lọt vào kết quả và chạy chậm gấp đôi (đã đo).
- Bản ghi dài được chia thành nhiều phần có chồng lấn rồi gộp lại. JSON lỗi thì thử lại một lần.
- Code kiểm tra mỗi ý có thật trong biên bản không (khớp chữ), tách câu giao việc thành người / việc / hạn, rồi dựng Markdown.

### Bước 6 — Hậu xử lý tóm tắt bằng quy tắc

Model nhỏ hay bỏ sót, nên có hai bước bù:

- **Gán người nhận việc** (`attribution.py`): câu "mình sẽ làm X" thì người nhận việc là chính người đang nói, đổi "mình" thành `Người N`.
- **Bổ sung ý bị sót** (`summary_supplement.py`, chỉ khi tóm tắt do Qwen tạo): nếu tóm tắt thiếu Mục tiêu/Kết quả/Vấn đề/Quyết định, lấy các câu thuộc nhóm đó trong biên bản thêm vào, kèm `(Người N)`. Chỉ thêm, không sửa dòng Qwen đã viết.

## 4. Chatbot hỏi đáp

Code: `ai-service/meeting_processing/chat.py` (hàm `run_meeting_chat`). Chatbot **không đưa mọi câu cho LLM**. Nó phân loại câu hỏi trước: các loại dưới đây được trả bằng quy tắc vì Qwen 1.5B từng bịa hoặc đảo nghĩa với chúng; khi dùng Gemini vẫn giữ để không tốn request và trả lời được cả khi mất mạng. Các câu gợi ý trên giao diện đều thuộc nhóm trả bằng quy tắc.

| Loại câu hỏi | Ví dụ | Cách trả lời |
| --- | --- | --- |
| Về người tham gia | "Có bao nhiêu người?", "Ai nói nhiều nhất?" | Thống kê từ dữ liệu phân người (số lượt, số giây, %), không gọi model |
| Tổng quát về một người | "Người 2 nói gì?" | Tách lời người đó thành từng ý, xếp nhóm (Mục tiêu, Quyết định, Đề xuất, Sẽ làm, Đã làm, Vấn đề, Giao việc), ghép thành một đoạn ý chính. Dùng nguyên chữ trong biên bản, không gọi model |
| Theo nhóm nội dung | "Mục tiêu là gì?", "Đã quyết định gì?", "Có vấn đề gì?", "Có đề xuất gì?" | Liệt kê các ý thuộc nhóm đó, không gọi model |
| Câu hỏi khác | "Ai làm báo cáo, hạn khi nào?" | Chọn các đoạn liên quan nhất (theo từ khóa) đưa cho **Gemini** (hoặc Qwen khi không có khóa/Gemini lỗi) trả lời kèm mã đoạn để trích dẫn |

**Chống bịa (grounding check):** với câu trả lời của LLM (Gemini hoặc Qwen), hệ thống đo tỷ lệ chữ nội dung có xuất hiện trong các đoạn nguồn. Dưới **0,8** thì bỏ câu trả lời của model, thay bằng câu trích từ biên bản khớp nhất, hoặc báo "không đủ thông tin".

Câu hỏi có nhắc "người 2 / người thứ hai…" được tự lọc theo người đó; cũng có thể chọn người ở bộ lọc trên giao diện.

## 5. Dữ liệu lưu ở đâu

| Bảng (entity Java) | Nội dung |
| --- | --- |
| `Meeting` | Cuộc họp: tên, người tạo |
| `AudioRecording` | Đường dẫn file audio trên máy chạy backend |
| `MeetingProcessingJob` | Trạng thái xử lý (đang chạy / xong / lỗi), thông báo lỗi nếu có |
| `Transcript` | Biên bản đầy đủ; model đã dùng ghi dạng `asr=...;diarization=...` |
| `TranscriptSpeaker` | Danh sách người nói |
| `TranscriptSegment` | Từng đoạn: người nói, bắt đầu, kết thúc, chữ |
| `MeetingNote` | Bản tóm tắt |

Nếu AI lỗi: job chuyển `FAILED` (giữ lại để tra lỗi), cuộc họp bị xóa mềm, file audio bị xóa.

## 6. Kết quả đo được

Đo trên **file demo** `data_test/demo_meeting/demo_meeting.wav`: 2 phút, 3 người, giọng tổng hợp bằng edge-tts, có đáp án từng lượt. **Chưa đo đầy đủ trên bản ghi người thật**: bản ghi giọng thật đầu tiên (22 s, 3 giọng nam, micro laptop) để "Tự động" chỉ ra 1 người, chọn 3 người thì ra đúng 3. Kịch bản để ghi thêm: `data_test/kich_ban_ghi_am_3_nguoi.md`.

| Chỉ số | pyannote | Pitch/MFCC |
| --- | --- | --- |
| Số người khi để "Tự động" | Đúng 3 | Ra 2 (gộp hai người) |
| Gán đúng người (theo thời lượng), chọn 3 người | 96,2% | 97,4% |
| Lượt bị gán sai người | 0/13 | 0/13 |
| Phát qua loa rồi thu lại bằng micro, chọn 3 người | chưa đo | 82,3% (vang phòng làm nhòe ranh giới) |

| Tốc độ (RTX 4050 Laptop 6 GB) | Thời gian |
| --- | --- |
| pyannote cho 120 s audio, GPU / CPU | 4,5–6,9 s / 52 s |
| Toàn bộ pipeline cho file demo (GPU, có pyannote) | 35–41 s |
| Một câu hỏi chatbot | ~1 s |
| VRAM ba model (Wav2Vec2 + PhoWhisper + Qwen) | đỉnh ~4,7 GB |

Chống bịa: một câu trả lời bịa của Qwen ("mục tiêu cuộc họp") có tỷ lệ bám nguồn 0,69, các câu trả lời đúng đã thử đều 1,0. Ngưỡng 0,8 đặt theo các số này.

**Gemini so với Qwen** (lời thoại đáp án của bản demo, bỏ dấu câu và viết thường cho giống chữ ASR; chưa chạy với chữ ASR thật qua giao diện):

| | Qwen 1.5B (GPU) | Gemini `gemini-3.5-flash` (gói free) |
| --- | --- | --- |
| Tóm tắt: mục nào đúng theo đáp án | chỉ Kết quả + phân công; thiếu mục tiêu, vấn đề, quyết định | đủ mục tiêu, 2 kết quả, 2 vấn đề, quyết định, 5 phân công đúng người và hạn (2/2 lần chạy) |
| Thời gian tóm tắt | ~24 s | 12–25 s (qua mạng) |
| Chat, 5 câu hỏi đi tới model | nhiều câu bịa, phải trả bằng quy tắc | 5/5 đúng, có trích dẫn, câu không có trong biên bản báo đúng "không có thông tin"; 2–6 s mỗi câu |

`gemini-3.5-flash-lite` (mặc định): tóm tắt đúng như bản Flash (2/2 lần), chat 4/5 câu đúng đủ (câu "Lan cần làm gì" thiếu một việc), ~0,9 s mỗi câu. Chọn làm mặc định vì gói free cho 500 request/ngày, còn `gemini-3.5-flash` chỉ 20/ngày và hay quá tải (503). `gemini-3.8-flash` ở gói free mất 56 s đến quá 180 s cho một câu hỏi ngắn.

## 7. Hạn chế (nên nói thẳng khi báo cáo)

- Bộ pitch/MFCC **không tự đoán đúng số người** (điểm silhouette gần như phẳng) và không tách được hai giọng cùng giới quá giống nhau. Cách đáng tin nhất là người dùng nhập số người.
- Số đo trên giọng tổng hợp, sạch; giọng người thật, nói chen, tiếng ồn sẽ kém hơn.
- PhoWhisper vẫn nghe nhầm một số từ ("họp" → "học", "chốt" → "chúc") và không có dấu câu, nên tóm tắt đôi khi gộp hai ý.
- Chế độ "Tự động" có thể đoán thiếu người trên giọng thật cùng giới (bản ghi thật đầu tiên ra 1 người thay vì 3); khi demo nên chọn đúng số người.
- Gemini cần Internet; gói miễn phí giới hạn 500 request/ngày (Flash Lite) và có thể dùng dữ liệu gửi lên để cải thiện sản phẩm, nên chỉ dùng với cuộc họp demo. Lỗi hoặc hết hạn mức thì tự quay về Qwen.
- Qwen 1.5B (khi không có Gemini) nhỏ: tóm tắt phụ thuộc lần chạy có ra JSON hợp lệ không; vì vậy nhiều phần dùng quy tắc thay cho model.
- Xử lý đồng bộ: bản ghi dài có thể vượt timeout 300 s của Java dù AI vẫn chạy.
- File audio chỉ có trên máy đã upload; cuộc họp do máy khác tạo (DB dùng chung) không phát lại được audio.

## 8. Câu hỏi giảng viên có thể hỏi

**Vì sao phân người trước rồi mới ASR, không ASR cả bài rồi chia?**
Mỗi đoạn chữ gắn chắc với một người và một mốc thời gian, không cần căn chỉnh chữ với thời gian sau đó. Đổi lại phải nới biên khi cắt để không mất từ.

**Vì sao có bộ pitch/MFCC khi đã có pyannote?**
pyannote cần torch mới, token Hugging Face và đồng ý điều khoản model; không phải máy nào trong nhóm cũng cài được. Bộ pitch/MFCC chạy ở mọi nơi, không cần mạng, và là phương án dự phòng.

**Vì sao chatbot không dùng LLM cho mọi câu?**
Đã thử: khi tóm lời một người, Qwen 1.5B đảo nghĩa ("không đổi sang mô hình mới" thành "sang mô hình mới"); khi hỏi mục tiêu, nó ghép chữ có thật thành mục tiêu không ai nói. Với các câu hỏi này, trích từ biên bản theo quy tắc đáng tin hơn.

**Làm sao biết câu trả lời không bịa?**
Mỗi câu trả lời có trích dẫn (người + thời gian) để bấm nghe lại, và câu trả lời của LLM phải qua kiểm tra bám nguồn ≥ 0,8. Tóm tắt của Gemini còn bị ép đúng cấu trúc JSON, từng ý phải là đoạn chép nguyên văn có trong biên bản.

**Sao không dùng model lớn hơn?**
GPU 6 GB phải chứa cùng lúc ba model (~4,7 GB), nên model chạy local không lớn hơn được. Vì vậy tóm tắt và chat gọi **Gemini API** (model lớn chạy trên máy chủ Google), còn Qwen 1.5B chạy local làm dự phòng khi mất mạng hoặc hết hạn mức. ASR và phân người vẫn chạy local.

## 9. Bản đồ code

| Phần | File |
| --- | --- |
| Giao diện | `frontend/src/components/SpeakerChatMeeting.jsx`, `hooks/useWavRecorder.js` |
| API Java | `backend/.../controller/MeetingController.java`, `service/MeetingProcessingService.java`, `client/AiServiceClient.java` |
| Pipeline AI | `ai-service/main.py` (endpoint), `meeting_processing/service.py` |
| Phân người | `meeting_processing/diarize.py`, `turns.py` |
| Tóm tắt | `ai-service/summarization/`, `meeting_processing/attribution.py`, `summary_supplement.py` |
| Chọn LLM (Gemini/Qwen) | `ai-service/llm_backend.py` |
| Chatbot | `meeting_processing/chat.py` |
| Đánh giá | `ai-service/tests/evaluate_diarization.py`, `data_test/demo_meeting/`, `data_test/kich_ban_ghi_am_3_nguoi.md` |
