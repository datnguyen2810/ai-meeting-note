# Kiểm tra tóm tắt — 20/10/2026

## Thay đổi

Giữ Qwen2.5-1.5B-Instruct và hợp đồng HTTP cũ. Model chọn đoạn nguyên văn theo năm nhóm; code kiểm tra nguồn, tách công việc/thời hạn và dựng Markdown. Bổ sung các clause giao việc rõ và kết quả `đã hoàn thành` từ chính nguồn nếu model bỏ sót. Không tự sửa ASR hay quy đổi ngày.

Generation dùng greedy decoding, có context/output budget và dừng khi đủ năm trường JSON. Mỗi đoạn thử lại tối đa một lần nếu cấu trúc/trích dẫn lỗi. Không chấp nhận chuỗi bị cắt giữa chừng; giữ dữ kiện hợp lệ kèm cảnh báo nếu chỉ xử lý được một phần.

## Kiểm tra tự động

Chạy từ `ai-service/`:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -p "test_summarization*.py" -v
```

34 tests đã đạt: schema, grounding, loại thông tin thêm, giữ người/ngày nguyên văn, khôi phục dữ kiện hợp lệ khi mục khác lỗi, JSON dở dang, retry hữu hạn, dedup (kể cả tên có/không có xưng hô), thời hạn mâu thuẫn, token budget, Markdown escaping, HTTP và thứ tự WS final → closed. HTTP/WS tests dùng model/ASR giả, kiểm tra cả chặn batch khi live, dọn file tạm và giải phóng live session.

Frontend có 9 kiểm tra: 4 cho định dạng, escape và dữ liệu HTML dạng chữ (`node tests/summaryMarkdown.test.js`), 5 cho audio flush/WAV (`node tests/captureFlush.test.js`), chạy từ `frontend/`; build đã đạt. Lint hoàn tất với 7 cảnh báo sẵn có ở các component/hook cũ, không có cảnh báo trong parser/component tóm tắt mới.

## Thử model thật

Dùng model đã cache, CUDA float16 trên RTX 4050 Laptop 6 GB. Chỉ nạp Qwen, không nạp hai model ASR. Sáu fixture là transcript cố định, không phải kết quả chạy lại audio.

| Fixture | Thời gian tóm tắt | Dữ kiện bắt buộc bị thiếu theo keyword | Keyword sai bị phát hiện |
| --- | --- | --- | --- |
| `customer_service` | 8,08 s | 0/4 | Không có |
| `project_review` | 9,71 s | 0/5 | Không có |
| `missing_owner` | 4,97 s | 0/1 | Không có |
| `greeting_only` | 1,06 s | Không áp dụng | Không có |
| `no_actions` | 2,11 s | 0/2 | Không có |
| `conflicting_deadlines` | 2,34 s | 0/2 | Không có |

Đỉnh bộ nhớ GPU được PyTorch ghi nhận khoảng 2.985–3.005 MiB cho process benchmark; không phải VRAM tổng của hệ thống. Thời gian là một lượt đo, có thể dao động theo tải máy, warmup và số lần retry. Mẫu `missing_owner` được chạy lại riêng sau khi bổ sung phục hồi yêu cầu chưa gán người từ câu `Cần/Phải/Hãy ...`.

Đối chiếu thủ công hai ví dụ chính:

- Chăm sóc khách hàng: giữ đúng Kiên/Hiếu, tin nhắn, nhiệm vụ và `trước ngày hai mươi lăm`; `trước ngày thứ tuần này` được đánh dấu cần xác nhận. Không thêm email, chức danh hoặc báo cáo cuối năm.
- Dự án: giữ Nam/Lan và công việc tương ứng; giữ `trước ngày thứ sáu tuần này`, `trước ngày hai tháng tháng chín`; ngày lỗi được đánh dấu. Không sinh `15/9` hay đổi thành `28/9`.
- Thời hạn mâu thuẫn: giữ cả thứ sáu và thứ hai, yêu cầu xác nhận.
- Chưa có người phụ trách: không tự gán tên. Chỉ chào hỏi: không tạo phân công hoặc kết quả tưởng tượng.

Baseline lấy từ `HEAD:ai-service/main.py` trước thay đổi, seed 42: mẫu chăm sóc khách hàng mất 8,21 s, thiếu 3/4 keyword; mẫu dự án mất 7,88 s, thiếu 5/5 keyword và tự sinh `15/9`. Sampling cũ khiến kết quả dao động. Đây là so sánh hẹp trên hai mẫu, không chứng minh cải thiện tổng quát hay tăng tốc; pipeline mới có thể chậm hơn vì kiểm tra/thử lại.

Tái chạy:

```powershell
.\venv\Scripts\python.exe -m tests.evaluate_summary --output temp_summary_report.json
# So sánh với commit chứa pipeline cũ, ví dụ commit merge trước thay đổi này:
.\venv\Scripts\python.exe -m tests.evaluate_summary --baseline-ref 0d0ee09
```

Script dùng `local_files_only=True`: không tự tải model. `--trace` in JSON thô, chỉ dùng với fixture công khai; không dùng để log phiên âm riêng tư. Báo cáo `temp_*` đã được gitignore.

## Bổ sung từ bản kiểm thử realtime có ASR nhiễu

Fixture `tests/fixtures/realtime_regression.json` lưu đúng transcript kiểm thử tiếp theo và một đầu ra model bị cắt cụt. Kiểm tra hồi quy xác nhận:

- Phục hồi thời hạn của Lan từ tiền tố `trước ngày nay` thành nguyên văn `trước ngày nay ngày hai mươi năm tháng mười` trong cùng clause, không đổi thành ngày hợp lệ do phỏng đoán.
- Gộp tên ngắn và tên có xưng hô sau khi căn lại nguồn; không gộp hai người có xưng hô khác nhau hoặc hai ngày thực sự khác nhau.
- Cắt nhiệm vụ của Minh trước đoạn `công việc của anh minh chữa chốt thời án...`; câu xác nhận chưa chốt hạn không làm mất nhiệm vụ phía trước.
- Cắt kết quả hoàn thành khỏi lời chào, mục tiêu và vấn đề ở phần sau.
- UI render heading, danh sách, chữ đậm; chuỗi Markdown gốc vẫn được giữ cho xuất `.md`.

Chạy model thật trên fixture mới: 8,16 s, đỉnh PyTorch GPU 3.012 MiB; đủ 5/5 keyword bắt buộc, không có keyword sai được liệt kê. Đọc thủ công đầu ra thấy đúng 3 phân công: `thanh lam`, `chị lan`, `anh minh`; thời hạn đầy đủ, không có cảnh báo mâu thuẫn giả. Đây vẫn là kiểm tra từ văn bản có sẵn, không phải lần thu micro mới. Sáu số đo trong bảng phía trên thuộc lượt đánh giá trước bản bổ sung này.

```powershell
.\venv\Scripts\python.exe -m tests.evaluate_summary --fixture tests/fixtures/realtime_regression.json --output temp_summary_realtime_report.json
```

## Giới hạn

Mẫu mới `realtime_asr_repeated_subject` kiểm tra các từ ASR sai như `cho tuần qua`, `chơi chốt thể hạt`. Kết quả Qwen thật: 10,17 s; đỉnh GPU PyTorch 3.012 MiB, đủ 5/5 keyword bắt buộc và không có keyword sai đã liệt kê. Mục kết quả bắt đầu tại `nhóm đã hoàn thành...`; nhiệm vụ Minh kết thúc tại `nhiệm vụ được giao`; giữ tên `chị lam` và thời hạn nguyên văn. Các câu đệm/xác nhận cạnh công việc và ghi chú cuối đã được bỏ theo yêu cầu người dùng; metadata xác nhận vẫn tồn tại trong xử lý nội bộ.

- Khớp trích dẫn xác nhận nguồn chữ, không đảm bảo đúng quan hệ ngữ nghĩa, phủ định hay đầy đủ mọi ý.
- Tách người/ngày theo dấu hiệu tiếng Việt là heuristic; ngữ pháp khác có thể giữ nguyên quote và để trường chưa xác định. Tên/ngày ASR nghe sai vẫn cần người dùng sửa hoặc đối chiếu audio.
- Model có thể bỏ sót ý; nguồn có phần không xác minh được sẽ sinh cảnh báo thay vì một bản tóm tắt trôi chảy nhưng bịa.
- Chưa thử thao tác micro, chạy ASR thật, UI trình duyệt hoặc biên bản dài trên cả ba model đồng thời trong lượt kiểm tra này. Các phần đó không được suy ra từ kết quả unit/API test.
