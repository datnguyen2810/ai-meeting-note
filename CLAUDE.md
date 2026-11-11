# CLAUDE.md — AI Meeting Note

@AGENTS.md

AGENTS.md (nạp ở trên) là bản đồ dự án, hợp đồng API và lệnh chạy. File này chỉ giữ phần riêng: sự thật đã đo, môi trường máy, việc còn mở và cách làm việc với người dùng.

**Quy tắc đồng bộ (người dùng yêu cầu):** mỗi khi kiến trúc, API, lệnh chạy, vị trí file, hiện trạng đo được hoặc việc còn mở thay đổi, cập nhật **cả AGENTS.md và CLAUDE.md** trong cùng lượt. Thông tin chung cho mọi agent đặt ở AGENTS.md, phần dưới đây đặt ở CLAUDE.md; không chép trùng giữa hai file.

Tính năng phân người + chatbot + Gemini được gộp vào main từ nhánh `feat/speaker-meeting-ui-polish` (2026-11-11).

## Sự thật đã đo, đừng đo lại hay giả định ngược

- pyannote `speaker-diarization-community-1` (pyannote.audio 4.0.7) trên file demo: **tự đoán đúng 3 người** (pitch/MFCC ra 2); tự động và chọn 3 người cho cùng kết quả. Sau khi gom chuỗi mẩu ngắn theo khối (`turns.absorb_short_turns`): gán đúng 96,2%, bỏ sót 3,6%, 0/13 lượt sai, 16 lượt (trước khi sửa: 94,9%, 21 lượt). Pitch/MFCC chọn 3 người vẫn 97,4%. pyannote sinh chuỗi mẩu 0,01–0,4 s xen kẽ hai người ở chỗ chuyển lượt (Hà và Lan cùng giọng HoaiMy). Chưa đo bản thu qua micro hay giọng người thật.
- Ngưỡng gộp giọng pyannote (`clustering.threshold`, VBx) trên bản demo, tự đoán: 0,6 / 0,4 / 0,2 đều ra 3 người với phân chia giống hệt; 0,05 ra **2** người. Hạ ngưỡng không làm tăng số người (VBx gộp lại theo `Fa`/`Fb`), nên không phải cách sửa "Tự động" ra thiếu người. Chưa đo trên giọng thật.
- Bản ghi giọng thật đầu tiên (2026-11-11, 22 s, 3 lượt đầu kịch bản Hiếu/Đạt/Kiên, micro laptop): "Tự động" ra 1 người, chọn 3 người ra 3 người; chưa xác định đã dùng bộ phân người nào. ASR sai nhiều ("chờ hai bạn", "tái tiếp điểm lớn").
- Tốc độ pyannote cho 120 s audio: CPU 52 s; GPU RTX 4050 4,5–6,9 s. VRAM khi chạy: batch mặc định 32 cần +1,6 GB (đỉnh cả hệ thống 5890/6141 MiB); batch 8 +0,4 GB, cùng kết quả, 4,6 s, nên đặt `PYANNOTE_BATCH_SIZE = 8`; đỉnh cả hệ thống còn 5626–5652 MiB.
- Venv-next (torch 2.14.1+cu126) trên GPU: ba model cũ + pyannote nạp được (4,94 GB sau khi nạp), pipeline đầy đủ cho file demo 35–41 s, chat 1 s. PhoWhisper cho **cùng chữ** với torch 2.6 trên cùng đoạn audio; khác biệt chữ chỉ đến từ biên cắt đoạn.
- Biên cắt của pyannote làm PhoWhisper mất số: đoạn bắt đầu giữa câu ("vậy" bị tách riêng) bỏ hết từ chỉ số; nới 0,2 s đọc "thứ sáu tuần này" thành "thứ tư này", "ngày hai mươi tháng mười một" thành "ngày mười" (6/8 cụm đúng), nới 0,3 s đúng 8/8. Pitch/MFCC: 0,2 s 8/8, 0,3 s 7/8. Vì vậy nới theo bộ phân người (chỉ đo trên file demo).
- Bộ pitch/MFCC: chế độ tự đoán luôn ra 2 người (điểm silhouette 0,16–0,25, gần như phẳng theo k, nên mọi cách tự đoán số người đều không chắc); hai giọng nam cùng gốc không tách được kể cả ép đúng số người. Nhập đúng số người là cách đáng tin nhất hiện có.
- File demo `data_test/demo_meeting/demo_meeting.wav`: chọn 3 người → gán đúng 97,4%, bỏ sót 2,6%, 0/13 lượt sai. Phát qua loa rồi thu bằng micro → 82,3%, bỏ sót 12,6% (vang phòng lấp khoảng lặng giữa hai người). Nâng ngưỡng nhập mẩu ngắn lên 2,5–3,5 s làm xấu đi (70,8–80,5%); giữ 1,5 s.
- PhoWhisper **bỏ từ chỉ số khi cắt audio sát mép**; với biên pitch/MFCC nới 0,2 s mỗi bên lấy lại phần lớn ("năm đoạn", "thứ sáu", "mười lăm giây"), 0,1 s chưa đủ (pyannote: xem mục trên). Không phải do cấu hình chặn token. Lỗi nghe nhầm lặp lại: "họp" → "học", "chốt" → "chúc".
- Ghép nhãn `[Người N]:` vào văn bản tóm tắt làm Qwen trả sai cấu trúc, lọt nhãn vào kết quả và chậm gấp đôi.
- Qwen 1.5B không dùng được để gom ý của một người: hỏi qua chat thì chỉ nêu một ý, không ghi mã nguồn; chạy bộ tóm tắt trên lời của một người thì **đảo nghĩa** ("không đổi sang mô hình mới" thành "sang mô hình mới") và bỏ gần hết ý. Vì vậy ý chính theo người được gom bằng quy tắc.
- Qwen trả lời câu "mục tiêu cuộc họp" đã bịa ("chọn mô hình mới", "ngày 20/11"): tỷ lệ bám nguồn 0,69; các câu trả lời đúng đã thử đều 1,0. Ngưỡng 0,8 đặt theo các số này, chưa đo trên nhiều câu hỏi. Lần thử sau Qwen ghép chữ có thật thành mục tiêu không ai nói ("đánh giá phân biệt người nói, tối ưu trợ lý hỏi đáp…"): kiểm tra theo chữ **không bắt được**, nên câu hỏi về mục tiêu/quyết định/vấn đề/đề xuất chuyển sang trả bằng quy tắc.
- Ý chính theo người trên bản demo 3 người (lời ASR thật, cắt theo đáp án): đoạn 58 và 53 tiếng cho Khoa/Lan, 122 tiếng cho Hà (có câu "chốt lại" dài); cách đếm cũ cho dạng danh sách là ~150–210, nguyên văn ~350. Nghĩa giữ đúng trên bản này; chưa đo trên bản ghi người thật.
- Tóm tắt bản demo (lời ASR, 2 người do "Tự động") qua `/api/summarize` trên GPU, code cũ: chỉ còn Kết quả + 4 phân công, mất mục tiêu, vấn đề, quyết định và việc của Lan (23,7 s). Chạy cùng prompt trên CPU fp32: lần thử 1 trả object `{issue, description}` rồi lặp một phân công đến hết token (JSON cụt, 266 s); lần thử 2 đúng mục tiêu, 2 vấn đề, quyết định nhưng phân công dạng `{name, work, deadline}` nên bị loại.
- Demo 3 người để "Tự động": Hà (Người 1) đúng cả 5 lượt; Khoa và Lan bị gộp thành Người 2.
- **Gemini thay Qwen** (nhánh `feat/gemini-llm-backend`; đo trên lời đáp án demo đã bỏ dấu câu và viết thường, nối lượt bằng ". "): `gemini-3.5-flash` tóm tắt đúng mục tiêu, 2 kết quả, 2 vấn đề, quyết định, 5 phân công đúng người/hạn sau `attribute_first_person_owners` (2/2 lần, 12–25 s); chat 5/5 câu đi tới model đều đúng, có trích dẫn, 2–6 s, không câu nào bị grounding chặn. Trước khi tắt quy tắc vá: `align_actions_to_source` thay câu đầy đủ của Gemini bằng bản cụt ("chuẩn bị sẵn một"), `explicit_source_facts` thêm 3 phân công rác, `supplement_summary` thêm 2 dòng Quyết định trùng; không có dấu chấm giữa lượt thì "được" của lượt sau dính vào việc của Lan. Chưa chạy với chữ ASR thật qua giao diện.
- Gemini gói free: `gemini-3.8-flash` mất 56 s rồi quá 180 s cho câu hỏi một từ; `gemini-3.5-flash` 3 s, `gemini-3.5-flash-lite` 1 s; `gemini-2.5-flash` trả 404 với người dùng mới. `flash-lite` tóm tắt bản demo cũng đúng các mục (1 lần đo, trước khi tắt quy tắc vá).
- Hạn mức Gemini free (AI Studio, 2026-11-08): `gemini-3.5-flash` tính chung "Gemini 3.6 Flash" 5 RPM / **20 RPD** (đã vượt 21/20 trong ngày thử); 3.8 Flash 5/20; **3.5 Flash Lite 15 RPM / 500 RPD**. Flash Lite trên bản demo: tóm tắt đủ mọi mục 2/2 lần, chat 4/5 đúng đủ ("Lan cần làm gì" thiếu "chuẩn bị cuộc họp mẫu"), ~0,9 s → đặt làm mặc định, Flash làm dự phòng.
- Chạy qua giao diện lần đầu (2026-11-08): `gemini-3.5-flash` trả 503 "high demand" nên pipeline rơi về Qwen (37,7 s, cơ chế dự phòng đúng). Sau khi thêm thử lại: lần chạy giao diện tiếp theo 503 hai lần, lần thứ ba Gemini trả lời (tổng 90 s, không rơi về Qwen).
- edge-tts: giọng nam tiếng Việt không trả audio cho câu có từ tiếng Anh như "file", hoặc khi kèm tham số rate/pitch.

## Môi trường máy phát triển

- Windows 11, RTX 4050 Laptop 6 GB; ba model cũ chiếm đỉnh ~4,7 GB. Khi AI service đang chạy, GPU gần đầy: muốn thử model thì chạy CPU, hoặc gọi endpoint của service đang chạy (`/api/summarize`).
- `ai-service/venv`: Python 3.11.9, torch 2.6.0+cu124, transformers 5.17, sklearn 1.9, soundfile đọc được WAV/MP3/FLAC/OGG; không có pyannote. `requirements.txt` **không khớp** venv (ghim torch 2.14, thiếu torchaudio).
- **Venv-next** ở ngoài repo: `D:\Code\PTIT\HTTM\venv-next` (Python 3.11, torch 2.14.1+cu126, torchaudio 2.11.0+cu126, pyannote.audio 4.0.7, cùng phiên bản transformers/hub/numpy như venv chính; bỏ ghim sympy/mpmath/networkx vì xung đột với torch mới). Driver 560.92 chỉ hỗ trợ tới CUDA 12.6. Chạy AI service có pyannote: từ `ai-service/`, `D:\Code\PTIT\HTTM\venv-next\Scripts\python.exe -m uvicorn main:app --port 8000`. Venv cũ `ai-service/venv` giữ để quay lại.
- Venv `D:\Code\PTIT\HTTM\venv-pyannote` (torch 2.15 CPU) chỉ dùng thử ban đầu, có thể xóa. Token Hugging Face lưu bằng `hf auth login` (tài khoản đã đồng ý điều khoản model); model pyannote đã cache.
- Khóa Gemini (gói free, project `ai-meeting-note` trên AI Studio) nằm trong `.env` gốc repo; không in hay đọc giá trị. Máy khác trong nhóm không có khóa thì tự dùng Qwen.
- Chưa có FFmpeg; không có `rg`. Model đã cache: PhoWhisper-small, Qwen2.5-1.5B-Instruct, wav2vec2-vi (`HF_HUB_OFFLINE=1` khi chỉ dùng cache).
- IDE báo hàng loạt lỗi Java (`builder()`, getter, `log` không tìm thấy) do Lombok không chạy trong trình phân tích của editor; tin `mvnw compile`, không tin IDE.
- Script tạm (đo đạc, thử nghiệm) đặt ngoài repo; khi chạy từ thư mục khác phải thêm `ai-service` vào `sys.path`.

## Việc còn mở (biết trước để khỏi dò lại)

- Lỗ hổng còn lại: các API audio/transcript/note cũ (`AudioService`, `MeetingNoteService`, STT cũ) chưa kiểm tra quyền xem cuộc họp. Nhóm API phân người + chat đã kiểm tra (xem AGENTS.md).
- Xử lý đồng bộ (chưa có hàng đợi/worker, 202, polling); `ownerInstanceId`/`storageNode` viết cứng `"local-node"`; Python chưa chống chạy trùng, chưa có token nội bộ, CORS `*`, khóa GPU giữ suốt cả job.
- Audio chỉ nằm trên đĩa máy đã nhận upload: mở cuộc họp của máy khác trong DB chung thì `/audio/content` trả 404 và không tua được. Audio tải cả file về trình duyệt (Blob), chưa hỗ trợ Range cho file lớn.
- Kiểm tra quyền, `/audio/content`, xóa mềm khi AI lỗi và việc luôn gắn tab phân người mới qua `mvnw compile`/`npm run build`; chưa chạy thử đầu-cuối với backend + AI thật.
- Chưa giới hạn thời lượng ghi âm; chưa có Flyway và DB test riêng (PLAN_SPEAKERS_CHAT.md mục 3).
- Pyannote mới đo bằng script (pipeline + chat trên GPU); chưa chạy AI service bằng venv-next qua giao diện, chưa thử phiên live (Wav2Vec2 qua WS) trên torch mới (chỉ thử suy luận 3 s). `requirements.txt` chưa thêm `torchaudio`/`pyannote.audio` và bản torch CUDA; máy khác trong nhóm vẫn dùng pitch/MFCC.
- Trên GPU fp16 (venv-next), Qwen tóm tắt bản demo 3 người chỉ ra Kết quả + 5 phân công. `supplement_summary` (đo trên đúng output đó) thêm 7 dòng: mục tiêu, kết quả của Lan, 3 vấn đề, 2 quyết định, đều đúng theo đáp án; chưa chạy lại qua giao diện. Hai vấn đề của Lan ("vẫn còn chậm", "mất mười lăm giây") hiện thành 2 dòng vì là 2 đoạn riêng.
- Giao diện mới (hai bước, màu người nói, tô sáng đoạn đang phát, câu hỏi gợi ý, chừa chỗ cho nút "Hỏi đáp") mới qua `npm run build`; chưa xem trên trình duyệt.
- Bố cục tab phân người khóa vừa một màn hình. Trên laptop Windows scale 125% (khung nhìn ~1536 px) cột điều khiển từng bị cắt mất phần dưới, không cuộn được (2026-11-11). Đã sửa: cột điều khiển tự cuộn, cột điều khiển `clamp(300px, 22vw, 400px)`, cột lịch sử `clamp(260px, 18vw, 330px)`, màn hình ≤ 1280 px rộng hoặc ≤ 680 px cao thì cả khung cuộn và biên bản/tóm tắt cao `clamp(360px, 75vh, 640px)`. Mới qua `npm run build`/`lint`, chưa xem trên trình duyệt.
- Gemini: chưa chạy AI service thật qua giao diện; gói free có thể dùng dữ liệu để cải thiện sản phẩm (chỉ dùng cuộc họp demo); cần Internet; Qwen vẫn nạp (chưa giải phóng VRAM). Câu hỏi về mục tiêu/quyết định/người vẫn trả bằng quy tắc; có thể chuyển sang Gemini sau khi đo.
- Tóm tắt phụ thuộc lần thử nào của Qwen ra JSON hợp lệ: lần lặp vô hạn thì cả lần bị bỏ. Mục "Kết quả" vẫn dính hai kết quả liền nhau khi lời không có dấu câu. Thiếu dấu câu và lỗi ASR (lượt của Hà vẫn "hạn nộp là ngày tới", "tiệc văn bản", "bình rảnh") chưa xử lý.

## Cách làm việc với người dùng

- Trao đổi bằng tiếng Việt; người dùng là sinh viên làm đồ án nhóm 3 người, tự commit/push.
- Không commit/push khi chưa được yêu cầu. Khi gợi ý commit: không gộp thay đổi `note.txt` trong `.gitignore` (riêng của người dùng), hỏi trước khi đưa audio (`data_test/demo_meeting/*.wav`) lên repo, chọn đúng file thay vì `git add .`.
- Mỗi kết luận về chất lượng phải kèm số đo hoặc nói rõ là chưa đo; giọng tổng hợp không thay được bản ghi người thật. Khi phát hiện kết luận cũ sai, đính chính rõ ràng.
