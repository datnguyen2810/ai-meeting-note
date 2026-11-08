# 🎙️ AI Meeting Note - Hệ Thống Ghi Chép & Tóm Tắt Cuộc Họp

> **Đồ án môn học:** Hệ thống thông minh (HTTM) - Học viện Công nghệ Bưu chính Viễn thông (PTIT)

Ghi âm hoặc tải lên file cuộc họp tiếng Việt → phiên âm theo từng người nói → tóm tắt (mục tiêu, kết quả, vấn đề, quyết định, phân công) → hỏi đáp về nội dung cuộc họp, có trích dẫn mốc thời gian.

---

## 🏗️ Kiến Trúc Hệ Thống

```text
Trình duyệt :5173 (React)
  ├─ /api/...  → Java Spring Boot :8080 → PostgreSQL (dùng chung cả nhóm)
  │                     └─ gọi Python :8000 để phân người nói, tóm tắt, hỏi đáp
  └─ ws / http → Python FastAPI :8000 (phụ đề trực tiếp, phiên âm file)
```

| Thư mục | Công nghệ | Vai trò |
| --- | --- | --- |
| `frontend/` | React 19, Vite 8 | Giao diện, ghi âm, phân người + chat |
| `backend/` | Java 21, Spring Boot 4, Maven | Đăng nhập JWT, lưu cuộc họp, audio, kết quả |
| `ai-service/` | Python 3.11, FastAPI, PyTorch, Transformers | ASR, phân người nói, tóm tắt, hỏi đáp |
| `data_test/` | | Audio mẫu; `demo_meeting/` là cuộc họp 3 người có đáp án |

Model AI (tự tải từ Hugging Face lần chạy đầu, tổng vài GB):

- Phụ đề trực tiếp: `nguyenvulebinh/wav2vec2-base-vietnamese-250h`
- Phiên âm file: `vinai/PhoWhisper-small`
- Tóm tắt + hỏi đáp: **Gemini API** (`gemini-3.5-flash-lite`, dự phòng `gemini-3.5-flash`) nếu có khóa, ngược lại `Qwen/Qwen2.5-1.5B-Instruct` chạy local. Qwen luôn được nạp làm dự phòng khi Gemini lỗi (mất mạng, hết hạn mức).
  - Bật Gemini: lấy khóa miễn phí ở https://aistudio.google.com/api-keys, thêm `GEMINI_API_KEY=...` vào file `.env` ở gốc repo (mẫu trong `.env.example`). `LLM_BACKEND=local` để ép dùng Qwen. Lúc khởi động AI service in ra model đang dùng.
  - Gói miễn phí của Gemini có thể dùng dữ liệu gửi lên để cải thiện sản phẩm: chỉ dùng với cuộc họp demo. Cần Internet khi demo. Hạn mức free (xem ở AI Studio → Rate Limit): Flash Lite 15 request/phút, 500/ngày; Flash chỉ 20/ngày. Mỗi lần tóm tắt và mỗi câu chat tốn 1 request.
- Phân người nói: `pyannote/speaker-diarization-community-1` nếu đã cài (tùy chọn); nếu không, dùng bộ phân cụm pitch/MFCC có sẵn

---

## 🚀 Chạy demo trên máy

### 0. Yêu cầu

- **JDK 21**, **Node.js 22.12+**, **Python 3.11**
- Khuyến nghị GPU NVIDIA ≥ 6 GB VRAM. Chạy CPU vẫn được nhưng xử lý một cuộc họp mất vài phút.
- Lần đầu cần Internet để tải model.

### 1. Lấy code

```powershell
git clone https://github.com/datnguyen2810/ai-meeting-note.git
cd ai-meeting-note
git checkout feat/speaker-count-eval   # nhánh có phân người + chatbot (bỏ qua nếu đã gộp vào main)
```

### 2. Tạo file `.env` (cho backend)

```powershell
copy .env.example .env
```

Điền `DB_URL`, `DB_USERNAME`, `DB_PASSWORD`, `JWT_SECRET`. **Giá trị thật xin trong nhóm chat**, không commit `.env` lên Git.

> ⚠️ Cả nhóm dùng chung một database và backend tự cập nhật schema (`ddl-auto=update`). Đừng sửa entity Java rồi chạy backend khi chưa báo nhóm.

### 3. AI service (terminal 1)

```powershell
cd ai-service
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe -m uvicorn main:app --port 8000
```

- **Máy có GPU NVIDIA:** cài thêm torch bản CUDA cho đúng driver theo <https://pytorch.org/get-started/locally/>, ví dụ:
  `.\venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cu124 --force-reinstall`.
  Log khởi động in thiết bị đang dùng (`cuda:0` hoặc `cpu`).
- Đợi dòng `Application startup complete` rồi mới thử. Tài liệu API: <http://localhost:8000/docs>.
- `requirements.txt` chưa khớp hoàn toàn venv của người viết; nếu cài lỗi phiên bản, báo lại trong nhóm.

**Tùy chọn — dùng pyannote để phân người nói chính xác hơn:** cần torch ≥ 2.8 (nên tạo venv riêng), cài `pyannote.audio` và `torchaudio`, vào trang model `pyannote/speaker-diarization-community-1` trên Hugging Face bấm đồng ý điều khoản, rồi chạy `hf auth login`. Không làm bước này thì hệ thống tự dùng bộ pitch/MFCC, vẫn demo được.

### 4. Backend (terminal 2)

```powershell
cd backend
.\mvnw.cmd spring-boot:run
```

Chạy tại `http://localhost:8080`.

### 5. Frontend (terminal 3)

```powershell
cd frontend
npm ci
npm run dev -- --port 5173 --strictPort
```

Mở <http://localhost:5173>. Dùng Chrome/Edge; micro chỉ hoạt động trên `localhost` hoặc HTTPS.

---

## 🎬 Kịch bản demo

1. Đăng ký tài khoản (hoặc đăng nhập) → vào Dashboard.
2. Tab **"Phân vai người nói & Chat"**:
   - **Bước 1 – Âm thanh:** chọn file `data_test/demo_meeting/demo_meeting.wav` (cuộc họp 3 người, 2 phút), hoặc bấm ghi âm trực tiếp từ micro.
   - **Bước 2 – Xử lý:** ở ô **"Số người"** chọn **3** rồi bấm xử lý. Biết số người thì nên chọn: chế độ "Tự động" với bộ pitch/MFCC thường chỉ tách ra 2 người.
3. Xem kết quả: biên bản tô màu theo người nói (bấm vào đoạn để nghe lại), bản tóm tắt, danh sách người nói.
4. Hỏi chatbot bằng các câu gợi ý, ví dụ: "Mục tiêu cuộc họp là gì?", "Nhóm đã quyết định gì?", "Người 2 nói gì?", "Có bao nhiêu người tham gia?". Câu trả lời kèm trích dẫn mốc thời gian.
5. Cột trái là lịch sử cuộc họp; bấm **"Mở và hỏi đáp"** để mở lại cuộc họp cũ.

Đáp án để đối chiếu: `data_test/demo_meeting/demo_meeting_reference.txt`.

Các tab khác: **"Cuộc họp trực tiếp"** (phụ đề realtime qua micro, dừng lại sẽ phiên âm + tóm tắt cả bản ghi) và **"Tải file & Phân tích"** (phiên âm + tóm tắt một file, không phân người).

### Lỗi thường gặp

| Hiện tượng | Cách xử lý |
| --- | --- |
| Xử lý báo lỗi kết nối / 500 | AI service chưa chạy xong hoặc chưa in `Application startup complete` |
| Báo đang có phiên trực tiếp (409) | Dừng phiên ở tab "Cuộc họp trực tiếp" rồi thử lại |
| Bị đăng xuất liên tục | Kiểm tra `JWT_SECRET` trong `.env`, đăng nhập lại |
| Không phát lại được audio của cuộc họp do máy khác tạo | Bình thường: file audio chỉ lưu trên máy đã upload, DB thì dùng chung |
| File ghi âm lỗi định dạng | Chỉ nhận WAV/MP3/FLAC/OGG (máy chưa cài FFmpeg) |
| Hết VRAM | Tắt ứng dụng khác dùng GPU; ba model chiếm khoảng 4,7 GB |

---

## 🧪 Kiểm tra trước khi push

```powershell
# AI (không nạp model)
cd ai-service; .\venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py"
# Frontend
cd frontend; npm run build; npm run lint
# Backend
cd backend; .\mvnw.cmd -q -o compile
```

Mô tả tính năng phân người + chatbot (luồng, model, số đo, hạn chế) để báo cáo: xem `TINH_NANG_PHAN_NGUOI_CHAT.md`. Chi tiết kiến trúc, API và cách đánh giá model: xem `AGENTS.md`.

---

## 📌 Quy Ước Làm Việc Nhóm Với Git

1. **Không commit đè trực tiếp lên `main`** khi phát triển tính năng mới.
2. Tạo nhánh riêng cho mỗi tính năng hoặc thành viên:

   ```bash
   git checkout -b feature/ten-tinh-nang
   ```

3. Sau khi hoàn thiện, tạo **Pull Request (PR)** trên GitHub để trưởng nhóm review trước khi gộp vào nhánh `main`.
4. Luôn cập nhật code mới nhất từ `main` trước khi code:

   ```bash
   git checkout main
   git pull origin main
   ```

5. Không commit `.env`, `venv/`, `node_modules/`, `uploads/`, model weights hay file audio cá nhân.
