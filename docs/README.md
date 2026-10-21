# Tài liệu dự án AI Meeting Note

AI Meeting Note là hệ thống ghi âm cuộc họp, chuyển giọng nói tiếng Việt thành văn bản và tạo biên bản tóm tắt bằng AI. Dự án được tổ chức theo monorepo với giao diện web, dịch vụ nghiệp vụ và dịch vụ AI chạy độc lập.

## Mục lục

- [Kiến trúc và chức năng](architecture.md)
- [Luồng xử lý âm thanh](audio-processing.md)
- [API và dữ liệu](api-and-data.md)
- [Cài đặt, chạy và vận hành](setup-and-operations.md)

## Thành phần mã nguồn

| Thư mục | Vai trò | Công nghệ chính |
| --- | --- | --- |
| `frontend/` | Ứng dụng web, đăng nhập, họp trực tiếp, tải tệp và lịch sử | React 19, Vite |
| `backend/` | API nghiệp vụ, xác thực, lưu trữ lịch sử cuộc họp | Java 21, Spring Boot, JPA, PostgreSQL |
| `ai-service/` | Nhận dạng giọng nói, tóm tắt và WebSocket thời gian thực | Python, FastAPI, PyTorch, Transformers |
| `models_testing/` | Notebook và benchmark các mô hình/chunking | Python, Jupyter |
| `data_test/` | Tệp âm thanh kiểm thử mẫu | MP3, WAV |

## Phạm vi phiên bản tài liệu

Tài liệu này được lập từ mã nguồn đang có trong repository. Các URL mặc định trong môi trường phát triển là: Frontend `http://localhost:5173`, Backend `http://localhost:8080` và AI Service `http://localhost:8000`.

> Lưu ý: tài liệu không sao chép mật khẩu cơ sở dữ liệu hoặc khóa JWT đang xuất hiện trong cấu hình cục bộ. Các giá trị này cần được đưa ra biến môi trường trước khi triển khai thực tế.
