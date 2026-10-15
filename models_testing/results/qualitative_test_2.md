# Phase 0.5 — Nghe cảm nhận (không có ground truth)

- **File:** `test_2.mp3` (36.5s)
- **Model:** `nguyenvulebinh/wav2vec2-base-vietnamese-250h`
- **VAD backend:** `webrtcvad`
- **Ngày chạy:** 2026-09-24 16:23

> Mục đích: kiểm tra bằng TAI. WER thấp chưa chắc đọc lên đã hiểu được.
> Chú ý các token `<unk>` — dấu hiệu model không nhận ra tiếng nói.

## `fixed_500`

- Số cụm: **65**
- Thời gian: **1.12s** (RTF ≈ 0.0307)
- Số token `<unk>`: **3**  ← càng nhiều càng tệ

```text
xin chào tất c <unk>mọi người hôm nay chúng ta hộp nhan <unk>để đánh s áctình hình làm việc trong tuần a và tnkhai kết hoạch cho anh tưới nhìn chung tếnđ bộ công việc ủa nhóm diễn gà rất tốt và nã hoàn thành vượt chỉ tiêu để da niên khâu chăm khách hàng vẫn còn một số ph ản hồi chưa hài lò tốc độ ph m hồi tin nhắn cón chắm nhọ thống nhất anh kiến kiểm tra lại tòa bộ quy chình trăm <unk>soc khách hn và đưa ga giải áp khắc phục trước ngày thứ sáu tuần này anh hiếux chuẩn bị bàn bóc cáo số kiểu tổng tđ gửicho ban gám đúc trước này hai mươi lăm tược họp hôm nay kết thốc tại n xi cảm ơn mọi người
```

## `fixed_1500`

- Số cụm: **24**
- Thời gian: **0.36s** (RTF ≈ 0.0100)
- Số token `<unk>`: **4**  ← càng nhiều càng tệ

```text
xin chào tất cả mọi người hôm nay chúng ta họp nhanh <unk>để đánh giá tình hình làm việc trong tuần qua và c riển khai kế hoạch cho tuần tới nhìn chung tiếnđ bộ công việc của nhóm diễn ra rất tốt và đã hoàn thành vượt chỉ tiêu để ra tùy <unk>nhiên khâu chăm sóc khách hàng vẫn còn một số phản hồi chưa hài lòng vì tốc độ ph phản hồi tin nhắn còn chẩm nhóm thống nhất anh kiên <unk>kiểm tra lại toàn bộ quy trình chăm sóc khách hàng và đưa ra giải pháp khắc phục trước ngày thứ sáu tuần này anh hiếu sẽ chuẩn bị bản báo cáo số liệu tổng tếtđể gửi cho ban giám đốc trước ngày hai mươi lăm cuộc họp hôm nay kết thúc tại đây <unk>xin cảm ơn mọi người
```

## `vad`

- Số cụm: **5**
- Thời gian: **0.17s** (RTF ≈ 0.0045)
- Số token `<unk>`: **0**  ← càng nhiều càng tệ

```text
xin chào tất cả mọi người hôm nay chúng ta họp nhanh để đánh giá tình hình làm việc trong tuần qua và triển khai kế hoạch cho tuần tới nhìn chung tiến độ công việc của nhóm diễn ra rất tốt và đã hoàn thành vượt chỉ tiêu đề ra tuy nhiên khâu chăm sóc khách hàng vẫn còn một số phản pản hồi chưa hài lòng vì tốc độ phản hồi tin nhắn còn chậm nhóm thống nhất anh kiên sẽ kiểm tra lại toàn bộ quy trình chăm sóc khách hàng và đưa ra giải pháp khắc phục trước ngày thứ sáu tuần này anh hiếu sẽ chuẩn bị bàn báo cáo số liệu tổng kết để gửi cho ban giám đốc trước ngày hai hai mươi lăm cuộc họp hôm nay kết thúc tại đây xin cảm ơn mọi người
```
