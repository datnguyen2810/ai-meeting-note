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

## ASR từng lượt nói sau phân người (`/api/process-meeting`)

Pipeline phân người trước rồi chạy PhoWhisper trên từng lượt. Đo trên `data_test/demo_meeting/demo_meeting.wav` (giọng tổng hợp edge-tts, 3 người, có đáp án thời gian và lời; tạo bằng `make_demo_audio.py` cùng thư mục):

- **Cắt audio sát mép lượt làm PhoWhisper bỏ từ chỉ số.** Cùng một lượt, cắt sát: "thu thêm đoạn ghi âm… hạn là thứ tuần này", "mất khoảng giây"; nới mỗi bên 0,2 s: "thu thêm năm đoạn… thứ sáu tuần này", "mất khoảng mười lăm giây". Lặp lại ổn định ở 0,2 và 0,3 s; 0,1 s chưa đủ. Một lượt vẫn mất "ngày hai mươi tháng mười một" ở mọi mức nới, nên đây là cải thiện, không phải đã hết lỗi.
- Wav2Vec2 trên cùng đoạn nghe đủ các số, xác nhận âm thanh có số và lỗi nằm ở ASR.
- Mẩu ngắn ở chỗ chuyển người (khoảng 1 s) bị gán nhầm người và cắt giữa từ ("xuất kết quả" thành "và giúp" + "quả ra tiệp"). Nhập mẩu dưới 1,5 s vào lượt bên cạnh rồi mới ASR thì hết các lỗi này trên file demo.
- Logic ở `meeting_processing/turns.py` (`prepare_turns`, `padded_bounds`): nới tối đa 0,2 s nhưng không quá nửa khoảng nghỉ tới lượt bên cạnh để không lẫn lời người khác. Mốc thời gian lưu vẫn là mốc gốc.

Chấm phân người (đã dọn lượt nói, nhập 3 người): gán đúng 97,4% thời gian tiếng nói, bỏ sót 2,6%, 0/13 lượt sai; kết quả thô trước khi dọn là 87,8% và 10,5%. Chạy lại bằng `python -m tests.evaluate_diarization` (thêm `--raw` để xem kết quả thô). Đây là giọng tổng hợp sạch; phải đo lại trên bản ghi người thật gán nhãn tay.
