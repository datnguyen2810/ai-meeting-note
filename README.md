# 🎙️ AI Meeting Note - Hệ Thống Ghi Chép & Tóm Tắt Cuộc Họp 

> **Đồ án môn học:** Hệ thống thông minh (HTTM) - Học viện Công nghệ Bưu chính Viễn thông (PTIT)

---

<!-- ## 👥 Thành Viên Nhóm

| STT | Họ và Tên | Mã Sinh Viên | Vai trò / Phụ trách |
| :-: | :--- | :---: | :--- |
| 1 | Nguyễn Văn A (Trưởng nhóm) | B21DCCNxxx | Backend & AI Service |
| 2 | Thành viên 2 | B21DCCNxxx | Frontend React |
| 3 | Thành viên 3 | B21DCCNxxx | Data & Báo cáo |

*(Vui lòng cập nhật lại thông tin chính xác của nhóm)*

--- -->

## 🏗️ Kiến Trúc Hệ Thống

Dự án được xây dựng theo mô hình Monorepo gồm 3 thành phần chính:

```text
AI_Meeting_Note/
├── ai-service/        # Dịch vụ AI (FastAPI + HuggingFace PhoWhisper ASR)
├── backend/           # Máy chủ điều phối & nghiệp vụ (Java Spring Boot)
├── frontend/          # Giao diện người dùng (ReactJS + Vite)
├── data_test/         # Dữ liệu âm thanh kiểm thử mẫu
└── README.md          # Hướng dẫn dự án
```

### 🛠️ Công Nghệ Sử Dụng

- **Frontend:** React 18, Vite, TailwindCSS / CSS Modules, Axios
- **Backend:** Java 17+, Spring Boot, Spring Web, Maven
- **AI Service:** Python 3.10+, FastAPI, Uvicorn, PyTorch, HuggingFace Transformers (`vinai/PhoWhisper-small`), Librosa

---

## 🚀 Hướng Dẫn Cài Đặt & Chạy Dự Án

### 1. Clone repository về máy

```bash
git clone https://github.com/datnguyen2810/ai-meeting-note.git
cd ai-meeting-note
```

---

### 2. Khởi chạy AI Service (FastAPI)

```bash
cd ai-service

# Tạo môi trường ảo
python -m venv venv

# Kích hoạt môi trường ảo:
# Windows (PowerShell):
.\venv\Scripts\Activate.ps1
# Windows (CMD):
.\venv\Scripts\activate.bat
# Linux/macOS:
source venv/bin/activate

# Cài đặt thư viện phụ thuộc
pip install -r requirements.txt

# Khởi chạy server FastAPI
uvicorn main:app --reload --port 8000
```
> 📍 AI Service sẽ chạy tại: `http://localhost:8000` (Tài liệu API Swagger: `http://localhost:8000/docs`)

---

### 3. Khởi chạy Backend (Spring Boot)

Yêu cầu: Máy đã cài đặt **JDK 17** trở lên.

```bash
cd backend

# Dành cho Windows:
.\mvnw.cmd spring-boot:run

# Dành cho Linux/macOS:
./mvnw spring-boot:run
```
> 📍 Backend API sẽ chạy tại: `http://localhost:8080`

---

### 4. Khởi chạy Frontend (React + Vite)

Yêu cầu: Máy đã cài đặt **Node.js** (v18+).

```bash
cd frontend

# Cài đặt node_modules
npm install

# Khởi chạy chế độ phát triển
npm run dev
```
> 📍 Mở trình duyệt truy cập: `http://localhost:5173`

---

## 📌 Quy Ước Làm Việc Nhóm Với Git

1. **Không commit đè trực tiếp lên `main`** khi phát triển tính năng mới.
2. Tạo nhánh riêng cho mỗi tính năng hoặc thành viên:
   ```bash
   git checkout -b feature/ten-tinh-nang
   # hoặc
   git checkout -b dev-frontend
   ```
3. Sau khi hoàn thiện, tạo **Pull Request (PR)** trên GitHub để trưởng nhóm review trước khi gộp vào nhánh `main`.
4. Luôn cập nhật code mới nhất từ `main` trước khi code:
   ```bash
   git checkout main
   git pull origin main
   ```
