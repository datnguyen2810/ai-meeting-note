# Kế hoạch: phiên âm theo người nói và hỏi đáp cuộc họp

## 1. Phạm vi đã chốt

- Phát triển từ main sau khi gộp test, mốc code `2232aa0`. Chưa coi mốc này đã đạt mọi kiểm thử nghiệp vụ.
- Chạy trên máy cá nhân; thành viên khác có thể tự cài, tải model và chạy trên máy mình. Truy cập từ xa qua HTTPS là phương án bổ sung.
- Giữ ghi âm micro và tải tệp; bỏ hiển thị phụ đề trực tiếp trong luồng mới. Không cần gửi âm thanh qua WebSocket khi đang ghi.
- Bản đầu đánh giá trên 2–4 người thật, nói lần lượt. Một người đọc hai vai không phải mẫu chuẩn để đánh giá phân biệt giọng.
- Tự gán Người 1, Người 2… theo lần xuất hiện đầu tiên trong bản ghi, không theo thứ tự nhãn thô của model. Nhãn chỉ có phạm vi một cuộc họp; không nhận diện tên thật hoặc nhớ giọng giữa các cuộc họp.
- Hỏi đáp trong một cuộc họp đang mở, có đoạn nguồn và thời gian. Chưa làm hỏi xuyên cuộc họp, đăng ký giọng hoặc đổi tên người nói.
- Giữ tài khoản và lịch sử cũ; cuộc họp cũ không có nhãn được hiển thị bình thường, không tự bịa người nói.

## 2. Hiện trạng và việc phải xử lý trước

- React hiện gọi Python trực tiếp cho ASR, sau đó gửi audio/transcript/summary vào Java `/api/meetings/save-session`. Luồng mới chuyển sang Java điều phối xử lý và lưu kết quả.
- Java đã có `TranscriptSegment` với speakerLabel, startTimeSec, endTimeSec, textSegment, sequenceOrder. Tận dụng cấu trúc này thay vì tạo bảng đoạn phiên âm trùng chức năng.
- `AiServiceClient.transcribeAudio` hiện chỉ trả String transcript; cần DTO kết quả chứa cả summary, segments và speakers.
- Python đang nạp Wav2Vec2/PhoWhisper/Qwen. Luồng mới bỏ nạp Wav2Vec2 mặc định sau khi luồng ghi âm mới được nối hoàn chỉnh.
- Có mẫu ~97 giây bị mất một đoạn lớn ở phiên âm batch. Phải nghe WAV, đối chiếu các cửa sổ ASR và ghép đoạn trước khi kết luận do model. Không lấy bản trực tiếp làm bản chữ chuẩn.
- Backend đã từng lỗi DNS, thiếu kết nối session pooler và tenant/user not found. Xác minh DB hoạt động trước tích hợp; không báo hoàn tất dựa chỉ trên biên dịch.
- Cần bổ sung kiểm tra quyền theo organizer/participant, xử lý file an toàn và quản lý pool DB nhỏ. Không để test tự ghi lên DB chung.
- docs và AGENTS có thông tin H2/luồng lưu cũ; cập nhật theo code khi triển khai, phân biệt hiện trạng với thiết kế tương lai.

## 3. Kiến trúc mục tiêu

```text
Browser: ghi âm hoặc chọn tệp
  → Java: xác thực, kiểm tra file, tạo phiên xử lý và giữ file
  → Hàng đợi xử lý có giới hạn
  → Python: chuẩn hóa audio
      ├─ PhoWhisper: text + thời gian
      └─ pyannote: người nói + thời gian
      → ghép lời với người → Qwen tóm tắt
  → Java lưu transcript + segments + summary + người nói
  → Browser xem kết quả và lịch sử

Browser hỏi trong cuộc họp
  → Java kiểm tra quyền, lấy các đoạn của đúng cuộc họp
  → lọc theo người/chủ đề → Python/Qwen trả lời
  → Java kiểm tra nguồn trích dẫn → Browser hiển thị nguồn
```

Mô hình dự kiến: giữ `vinai/PhoWhisper-small`, thêm `pyannote/speaker-diarization-community-1`, dùng lại `Qwen/Qwen2.5-1.5B-Instruct` cho tóm tắt và hỏi đáp. Đây là lựa chọn thử nghiệm, chưa bảo đảm chất lượng/bộ nhớ.

Chạy các bước theo thứ tự và quản lý nạp/giải phóng model theo đo thực tế GPU 6 GB; một khóa GPU chung cho phiên âm, phân người, tóm tắt và chat. Giới hạn hàng đợi, không thêm nhiều worker nạp model trùng nhau. Chưa cần model embedding/vector DB; ưu tiên lọc speaker_id và tìm kiếm văn bản. Nâng cấp tìm kiếm ngữ nghĩa chỉ khi phép đo cho thấy thiếu.

## 4. Hợp đồng chung để ba người làm song song

### Dữ liệu kết quả AI v1

```json
{
  "schema_version": 1,
  "transcript": "Nội dung đầy đủ...",
  "summary": "### Mục tiêu cuộc họp\n...",
  "speakers": [{"speaker_id": "speaker_1", "label": "Người 1", "first_start_seconds": 1.2}],
  "segments": [{"segment_id": "seg_0001", "speaker_id": "speaker_1", "start_seconds": 1.2, "end_seconds": 4.8, "text": "Nhóm đã hoàn thành giao diện.", "attribution_status": "assigned"}],
  "warnings": []
}
```

- Thời gian tính bằng giây từ đầu bản ghi, không âm, end > start. segment_id ổn định sau khi lưu; khi tạo DB ID, lưu hoặc ánh xạ ID nguồn để chat không trích nhầm đoạn.
- speaker_id có thể null khi không đủ cơ sở gán; attribution_status gồm assigned, unknown, overlap. Đoạn chồng tiếng không buộc vào một người nếu không xác định được.
- Phân người chạy trên cùng timeline audio với ASR. Ưu tiên ASR mốc từ nếu khả dụng và kiểm chứng; nếu chỉ có mốc đoạn, phải chia ở ranh giới người nói hoặc đánh dấu chưa rõ, không gán cả câu dài cho người chiếm thời gian nhiều nhất một cách mù quáng.
- Sắp nhãn theo mốc tiếng nói đầu tiên của mỗi cụm giọng; giữ ánh xạ nhất quán trong toàn bản ghi. Khoảng nghỉ không tạo người mới.
- Phân biệt người phát biểu và người được nhắc đến/giao việc. Không suy speaker_id từ tên trong câu.
- Tóm tắt chung tiếp tục dùng pipeline đối chiếu nguồn; bỏ nhãn kỹ thuật người nói khỏi phần tên người được giao việc.

### API Java cho frontend (đề xuất chốt trước lập trình)

| API | Trách nhiệm |
| --- | --- |
| POST `/api/meetings/process-audio` | Multipart `file`, `source` (recording/upload), `durationSeconds` nếu biết, `clientRequestId`; trả HTTP 202 với meetingId, jobId và status |
| GET `/api/meetings/{id}/processing` | Trạng thái queued/processing/completed/failed và stage; lỗi có thông báo an toàn, không lộ token/path |
| GET `/api/meetings/{id}` | Metadata và kết quả summary/transcript; giữ tương thích response cũ |
| GET `/api/meetings/{id}/segments` | Danh sách đoạn có phân trang, filter speaker_id tùy chọn; giới hạn page size |
| GET `/api/meetings/{id}/audio` | Trả audio có xác thực, hỗ trợ phát và tua theo thời gian; không trả đường dẫn hệ thống |
| POST `/api/meetings/{id}/chat` | JSON question, speaker_id tùy chọn, lịch sử hội thoại giới hạn; trả answer, citations, insufficient_evidence |
| POST `/api/meetings/{id}/retry-processing` | Chỉ thử lại phiên lỗi, tái dùng file cũ; ngăn chạy trùng khi đang xử lý |

Java tiếp tục bọc `ApiResponse<T>`, Python có schema riêng. Quy ước chat `citations: [{segment_id, speaker_id, start_seconds, end_seconds, quote}]`; nguồn phải thuộc đúng meeting và nội dung trích khớp. Câu không đủ thông tin trả insufficient_evidence=true. Mã trạng thái lỗi quyền 403, không thấy 404, sai dữ liệu 400, quá dung lượng 413, đầy hàng đợi 429/503 theo hợp đồng chốt.

`clientRequestId` giúp retry mạng không tạo nhiều cuộc họp/tác vụ. Nếu đổi audio phải dùng ID mới. Lịch sử chat bản đầu có thể giữ trong trình duyệt theo meeting, không bắt buộc tạo bảng chat. Không cho hội thoại cũ vượt quyền hoặc thay thế nguồn.

### API Python nội bộ

- POST `/api/process-meeting`: nhận audio và giới hạn số người (mặc định khoảng 2–4 cho thử nghiệm, không ép mọi file có ít nhất hai người); trả kết quả v1. Java giữ kết nối trong worker nền, frontend không chờ request dài.
- POST `/api/meeting-chat`: nhận question, phạm vi người nói và các đoạn nguồn do Java lựa chọn; trả answer + IDs nguồn. Không cho client ngoài tự chọn nguồn của cuộc họp khác.
- Giữ `/api/transcribe` và `/api/summarize` trong giai đoạn chuyển tiếp. Chỉ bỏ WS/live cũ khi frontend mới hoạt động và test cũ đã thay thế đúng phạm vi.
- Cấu hình AI URL, timeout phù hợp file dài, hủy/timeout hữu hạn; lỗi một tác vụ không khóa vĩnh viễn tác vụ sau.

## 5. Phân công ba người

### Người 1 — AI (`feat/speaker-ai`)

1. Thử pyannote trên bản ghi hai người; kiểm tra tương thích Python/PyTorch/torchaudio, quyền model, dung lượng weights và VRAM trước tải/nâng dependency. Dùng môi trường thử riêng nếu phiên bản xung đột; không nâng toàn bộ requirements vô điều kiện.
2. Tạo hướng dẫn HF_TOKEN qua môi trường, chấp nhận điều kiện model và tải trước. Không ghi token trong repo/log/chat. Đo dung lượng tải thực tế và kiểm tra lần sau dùng cache.
3. Điều tra mất đoạn ASR trên WAV đã xác minh; chia cửa sổ có overlap, ghép theo thời gian; kiểm tra không bỏ/lặp câu ở biên, không chỉ tăng beam.
4. Tách module audio/ASR/diarization/alignment, trả kết quả v1. Có nhãn unknown/overlap và cảnh báo phần xử lý thiếu.
5. Chat: lọc đúng người, chọn đoạn liên quan và dùng nguồn để trả lời; với câu hỏi tổng hợp toàn bộ người, tổng hợp theo các phần thay vì chỉ lấy vài đoạn đầu. Giữ đủ context quanh đoạn được chọn; lịch sử chat không phải bằng chứng.
6. Benchmark Qwen hiện có trước quyết định đổi model. Ghi độ đúng, thời gian và bộ nhớ theo từng bước, không công bố chất lượng chỉ từ keyword.

Đọc/sửa chính: ai-service/main.py, requirements.txt, summarization/, package mới diarization/ hoặc meeting_processing/, chat/, tests/. Bàn giao schema, fixture JSON, script tải model và báo cáo thử nghiệm.

### Người 2 — Backend và DB (`feat/meeting-api`)

1. Chốt DTO v1, API và mã lỗi với hai người còn lại; cung cấp response giả để frontend bắt đầu.
2. Migration bổ sung bảng/metadata speaker theo transcript và bảng tác vụ xử lý; tận dụng TranscriptSegment. Thêm trường nullable/default cho lịch sử cũ, không xóa bảng/dữ liệu. Không dùng create-drop trên DB chung.
3. API nhận file và tạo job; hàng đợi giới hạn. Không giữ transaction/DB connection suốt lúc chờ AI. Lưu job/file trước, gọi AI ngoài transaction, transaction ngắn để ghi kết quả cuối.
4. Xử lý restart: job đang chạy bị đánh dấu gián đoạn và có thể retry; file còn giữ được. Không giả định queue trong RAM sống qua restart. Một job chỉ được một worker nhận.
5. Kiểm tra quyền organizer/participant ở API chi tiết, segments, audio, chat, retry và note. Truy vấn theo meeting được phép; không chỉ dựa vào việc đã đăng nhập.
6. File có tên lưu UUID, giới hạn dung lượng/định dạng, cleanup và rollback phù hợp. Ghi âm browser có thể là WebM; kiểm tra Python giải mã được trước chốt codec. Không để audio người dùng vào Git.
7. Cấu hình Hikari nhỏ theo DB nhóm, secrets qua môi trường, test tách DB. Tạo migration và hướng dẫn áp dụng có bản sao lưu, không chạy ngầm trên DB chung khi viết test.
8. Chat truyền đúng các đoạn thuộc cuộc họp, kiểm tra citations và trạng thái xử lý. Chưa có speaker ở cuộc họp cũ thì thông báo không thể trả lời theo người, vẫn hỗ trợ hỏi nội dung nếu có transcript.

Đọc/sửa chính: AiServiceClient.java, service/MeetingService.java, SttService.java, controller/MeetingController.java, entity/TranscriptSegment.java, DTO/repository mới, application.properties. Bàn giao migration, API, kiểm thử quyền và phục hồi lỗi.

### Người 3 — Frontend (`feat/meeting-ui`)

1. Thay LiveMeetingRoom bằng màn hình ghi âm sau họp: bắt đầu/dừng, thời lượng, mức micro, xem/nghe lại và gửi xử lý. Không mở WS/không hiện captions. Giữ bản ghi để người dùng tải lại nếu xử lý lỗi.
2. Ghi âm qua MediaRecorder hoặc bộ thu hiện tại; chốt MIME cùng AI/backend, có kiểm tra hỗ trợ trình duyệt và dọn stream/object URL. Dừng phải đợi đủ dữ liệu cuối.
3. Một luồng chung cho ghi âm và upload: gửi file tới Java, hiện stage, polling có backoff/timeout/dừng khi unmount. Đóng modal không tạo job mới hoặc hủy nhầm job đã gửi.
4. Hiển thị lượt nói có Người 1/2, thời gian và bộ lọc; nguồn unknown có nhãn dễ hiểu. Bấm đoạn tua audio; tải audio qua endpoint có JWT, không đặt token trên query URL.
5. Chat trong trang chi tiết: câu hỏi gợi ý, đang trả lời/lỗi, citations bấm tới đoạn và audio, chặn gửi trùng; đổi meeting không để câu trả lời cũ chen vào.
6. Xuất Markdown gồm phiên âm theo người và tóm tắt. Cuộc họp cũ thiếu segments vẫn xem/export được; không gắn nhãn người giả.
7. Tập trung URL qua services/api, Vite proxy Java; không hardcode Python localhost trong component mới. Local là mặc định; nếu thử khác mạng phải cấu hình HTTPS/proxy, micro quyền và CORS đúng nguồn.

Đọc/sửa chính: App.jsx, components/LiveMeetingRoom.jsx, SpeechToTextDemo.jsx, services/api.js, hook ghi âm mới/tái sử dụng capture + encodeWav, component phiên âm/chat mới. Bàn giao giao diện dùng fixture trước, nối API thật sau.

## 6. Mốc tích hợp và phụ thuộc

| Mốc | Công việc song song | Điều kiện qua mốc |
| --- | --- | --- |
| M0: hợp đồng | Cả nhóm chốt API, schema, mẫu âm thanh, môi trường | Fixture v1 + danh sách endpoint + người phụ trách tích hợp được thống nhất |
| M1: thử AI, dựng nền | AI kiểm tra diarization/ASR; backend mock API + migration; frontend ghi âm và dựng UI theo fixture | Chứng minh xử lý được file hai người và đánh giá bộ nhớ; UI không phụ thuộc model thật |
| M2: phiên âm theo người | Nối upload → job → AI → DB → UI | Hai người được gán nhất quán theo thứ tự, đầy đủ đoạn, mở lại lịch sử được |
| M3: tóm tắt và chat | AI + backend chat, frontend dẫn nguồn | Trả lời theo đúng người/cuộc họp, nguồn truy vết được, không đủ bằng chứng không bịa |
| M4: bàn giao | Thử 2–4 người, lỗi mạng/restart, máy thứ hai | Hướng dẫn cài chạy lặp lại được, dữ liệu cũ còn nguyên, báo cáo giới hạn |

Chưa cam kết số ngày cho đến khi M1 xác minh dependency, tốc độ và bộ nhớ. Không đợi cả ba hoàn thành rồi mới nối: tích hợp từng mốc nhỏ.

## 7. Kiểm thử và tiêu chí nghiệm thu

- Audio: mẫu hai người nói thật, bốn người, một người, khoảng lặng, nói chen, file hỏng, file quá giới hạn; tên/ngày/task đã nghe và ghi reference. Dữ liệu riêng tư chỉ lưu local hoặc nơi nhóm cho phép.
- ASR: đối chiếu cả đoạn giữa và biên cửa sổ trên file ~97 giây đã gặp lỗi; đo WER/CER từ reference nghe xác minh, không dùng ASR làm chuẩn.
- Diarization: đo sai gán người/thời gian với nhãn thủ công; nếu tính DER phải ghi rõ cách tính, xử lý overlap và tolerance. Kiểm tra nhãn từ người nói đầu tiên, không phụ thuộc ID thô.
- Chat: ít nhất 12 câu gồm tổng hợp một người, một chủ đề, quyết định, phân công, người được nhắc khác người phát biểu, thông tin không có, nguồn mâu thuẫn và câu hỏi ngoài cuộc họp. Đọc tay câu trả lời + nguồn, không chỉ kiểm keyword. Nguồn chứa câu lệnh phải được xử lý như dữ liệu, không điều khiển chatbot.
- Backend: kiểm thử tách khỏi Supabase chung; người A không xem/audio/chat/retry dữ liệu người B ngoài quyền, retry không tạo phiên trùng, lỗi AI không mất file hay giữ transaction, lịch sử cũ đọc được.
- Frontend: đủ mẫu cuối sau stop, quyền micro bị từ chối, upload lỗi/retry, refresh khi đang xử lý, đổi meeting khi chat đang chạy, hiển thị Markdown và văn bản nguồn an toàn.
- Hiệu năng: thời gian/độ dài audio và đỉnh VRAM toàn pipeline; cold/warm riêng. Không cam kết mô hình luôn vừa GPU 6 GB trước đo.
- Cài máy thứ hai: ghi phiên bản Python/Node/Java, dependency, FFmpeg nếu cần, quyền pyannote, cache và dung lượng đã đo. Không phát hành weights/token kèm Git.
- Hoàn tất khi ghi âm/tải tệp → xử lý → lưu → mở lại → hỏi đáp có nguồn hoạt động, cùng các bài kiểm thử và giới hạn được ghi rõ. Chat tốt không chứng minh ASR/nhãn người luôn đúng.

## 8. Quy trình Git và bàn giao

- Main là mốc chung sau khi code nền được push; mỗi người tạo nhánh riêng từ cùng commit. Không merge web-speech-api vào phạm vi này.
- Chỉ định một trong ba người làm người tích hợp; không cần người thứ tư. Hợp đồng/API đổi phải báo hai người còn lại và cập nhật fixture trong cùng thay đổi.
- Gộp các thay đổi nhỏ đã kiểm thử, xử lý migration theo thứ tự; không gộp để xóa xung đột bằng cách bỏ mất chức năng người khác.
- Không đưa audio riêng tư, token, mật khẩu, model weights, venv/node_modules/build vào commit. Giữ backend/uploads ngoài Git.
- Kế hoạch chưa phải code đã triển khai. Không tự tải model, đổi dependency, chạy migration DB chung, khởi động AI hoặc push chỉ để chuẩn bị tài liệu này.
