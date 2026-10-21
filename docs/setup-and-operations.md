# Cài đặt, chạy và vận hành

## Yêu cầu

- Node.js 18+ cho Frontend.
- JDK 21 (theo `backend/pom.xml`) cho Backend.
- Python 3.10+ cho AI Service.
- PostgreSQL có schema được phép tạo/cập nhật bởi Hibernate.
- Khuyến nghị GPU CUDA cho AI Service do phải nạp ba model lớn.

## Cấu hình an toàn

Trước khi chạy ngoài máy cá nhân, không giữ thông tin nhạy cảm trong `application.properties`. Chuyển các giá trị datasource và JWT sang biến môi trường hoặc profile riêng, ví dụ:

```properties
spring.datasource.url=${DB_URL}
spring.datasource.username=${DB_USERNAME}
spring.datasource.password=${DB_PASSWORD}
app.jwt.secret=${JWT_SECRET}
app.ai-service.base-url=${AI_SERVICE_URL:http://localhost:8000}
```

Đặt `spring.jpa.hibernate.ddl-auto=validate` hoặc dùng Flyway/Liquibase khi production. Cấu hình CORS, URL frontend và URL WebSocket cũng phải khớp tên miền triển khai.

## Khởi chạy local

Mở ba terminal từ thư mục gốc repository.

```powershell
# Terminal 1 — AI Service
cd ai-service
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

```powershell
# Terminal 2 — Backend
cd backend
.\mvnw.cmd spring-boot:run
```

```powershell
# Terminal 3 — Frontend
cd frontend
npm install
npm run dev
```

Truy cập `http://localhost:5173`, tạo tài khoản, đăng nhập và cho phép microphone để kiểm thử live mode. FastAPI có Swagger tại `http://localhost:8000/docs`.

## Kiểm thử và benchmark sẵn có

- `ai-service/test_vad_buffer.py`: kiểm tra logic VAD/buffer.
- `ai-service/test_live_stream_ws.py`: kiểm tra WebSocket streaming.
- `ai-service/test_model.py`: kiểm tra nạp/chạy mô hình.
- `models_testing/benchmark_chunking.py` và các notebook: so sánh ASR/chunking.

Chạy test Python trong virtual environment phù hợp, ví dụ `pytest ai-service/test_vad_buffer.py`. Backend có skeleton test tại `backend/src/test`.

## Vận hành và rủi ro đã nhận diện

- Backend giới hạn upload 100 MB; đảm bảo thư mục `uploads/audio` có quyền ghi và chính sách dọn dẹp/tồn trữ tệp.
- Batch ASR bị khóa khi có live session. Đây là hành vi chủ động để tránh GPU quá tải, nên UI/queue triển khai thực tế cần thông báo rõ cho người dùng.
- Repository hiện có cấu hình database/JWT mang tính bí mật trong file cấu hình. Cần thay vòng đời credential trước khi public repository hoặc triển khai.
- Các API quản lý meeting/note có phạm vi xác thực JWT, nhưng một số endpoint đọc theo ID không kiểm tra quyền sở hữu ở controller/service. Cần bổ sung kiểm tra authorization theo organizer/participant trước khi đưa vào production.
