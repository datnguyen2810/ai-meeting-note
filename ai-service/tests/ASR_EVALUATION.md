# Kiểm tra ASR và bản ghi cố định

## So sánh cùng file

Đã chạy PhoWhisper-small từ cache, cùng pipeline chunk 30 s và cùng audio `data_test/test_2.mp3` dài 36,48 s. Chỉ nạp ASR để đo; không đo toàn bộ hệ thống đang chạy ba model.

| Cấu hình | Thời gian một lượt | Kết quả |
| --- | --- | --- |
| `num_beams=1`, không sampling, tiếng Việt, transcribe | 8,78 s | Giống hệt cấu hình beam 5 |
| `num_beams=5`, không sampling, tiếng Việt, transcribe | 11,78 s | Không cải thiện văn bản trên file này |

Không đổi cấu hình ASR mặc định dựa trên thử nghiệm này. Chưa có bản chữ chuẩn đã nghe xác minh nên không báo WER hay kết luận mô hình nào chính xác hơn. Tăng beam không sửa được các từ sai trên mẫu đã thử. Kết quả của file này không đại diện cho audio micro mới của người dùng.

```powershell
# Chạy từ ai-service; chỉ dùng weights đã có trong cache
.\venv\Scripts\python.exe -m tests.evaluate_asr --audio ../data_test/test_2.mp3 --output temp_asr_report.json

# Đo WER khi đã có bản chữ nghe xác minh từ đúng file audio
.\venv\Scripts\python.exe -m tests.evaluate_asr --audio path/to/meeting.wav --reference path/to/verified.txt --output temp_asr_report.json
```

`--device cpu` dùng khi GPU không đủ bộ nhớ; `--beams 1 5` chọn các cấu hình cần đối chiếu. Script chuẩn hóa Unicode, chữ thường, dấu câu và khoảng trắng khi tính WER; không sửa từ hoặc tên riêng.

## Sửa đường thu âm để kiểm thử được

- Worklet trước đây chỉ phát các chunk đủ 200 ms; khi dừng có thể bỏ lại phần chưa đủ một chunk và một frame trong bộ đệm.
- Worklet nay nhận `flush`, phát PCM còn lại rồi xác nhận `flushed`, ngừng gom mẫu mới. Hook đợi xác nhận (timeout hữu hạn) rồi gửi WS `stop`.
- Phần cuối gửi cho server được đệm zero tới bội số 640 byte để VAD không bỏ phần frame ngắn. WAV xuất ra giữ số mẫu thật, không thêm phần đệm này.
- Hai bản processor `public/` và `src/audio/` có kiểm tra phải giống nhau. Kiểm tra tự động xác nhận bản ghi 4.010 mẫu giữ đủ cả chunk và đuôi, bản ngắn 100 mẫu không bị bỏ, flush không phát lại audio và thứ tự PCM → stop.
- Sau khi dừng cuộc họp, nút **Tải bản ghi âm** giữ WAV để tải lại vào tab upload hoặc chạy script. File vẫn tải được khi batch ASR lỗi. Không tự tải lên nơi khác hoặc lưu vào database.

Để kiểm thử lại bằng micro: khởi động lại AI Service, tải lại trang để nạp worklet mới, đọc cùng đoạn, dừng và tải WAV. So sánh các cấu hình trên WAV đó, nghe và viết reference một lần; không đọc lại mỗi cấu hình vì tốc độ nói, vị trí micro và tiếng ồn thay đổi.

Chưa thu âm từ micro hoặc thao tác trình duyệt thật trong lượt kiểm tra của agent. Kiểm tra audio worklet dùng môi trường mô phỏng; việc flush sửa mất mẫu cuối, không chứng minh đã hết lỗi nhận diện tên/ngày hay lỗi giữa câu.
