import os
import torch
from transformers import pipeline
from jiwer import wer

# 1. Khởi tạo phần cứng và mô hình
device = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"Đang sử dụng phần cứng: {device}")

# Sử dụng Whisper bản 'small' để cân bằng giữa tốc độ và độ chính xác
pipe = pipeline(
    "automatic-speech-recognition",
    model="vinai/PhoWhisper-small", # Hoặc "vinai/PhoWhisper-base"
    device=device,
    chunk_length_s=30
)
# 2. Cấu hình đường dẫn dữ liệu (THAY ĐỔI ĐƯỜNG DẪN NÀY)
# Dán đường dẫn bạn copy được từ Kaggle vào đây
base_path = "/kaggle/input/datasets/tuannguyenvananh/vivos-dataset/vivos" 
test_path = os.path.join(base_path, "test")
prompts_file = os.path.join(test_path, "prompts.txt")
waves_dir = os.path.join(test_path, "waves")

# 3. Đọc dữ liệu chuẩn (Ground Truth)
ground_truths = {}
with open(prompts_file, 'r', encoding='utf-8') as f:
    for line in f:
        # File có định dạng: VIVOSDEV01_001 nội dung văn bản
        parts = line.strip().split(' ', 1)
        if len(parts) == 2:
            audio_id, transcript = parts
            ground_truths[audio_id] = transcript.lower()

import librosa # Thêm thư viện đọc audio

# 4. Quá trình kiểm thử (Chạy thử 10 mẫu trước)
predictions = []
references = []
count = 0
max_test = 10 

import re

# Thêm hàm xóa dấu câu
def clean_text(text):
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text) # Xóa các ký tự không phải chữ/số/khoảng trắng
    return text

print("Bắt đầu nhận diện...")
for speaker in os.listdir(waves_dir):
    speaker_dir = os.path.join(waves_dir, speaker)
    if not os.path.isdir(speaker_dir):
        continue

    for audio_file in os.listdir(speaker_dir):
        if audio_file.endswith(".wav"):
            audio_id = audio_file.replace(".wav", "")
            
            if audio_id not in ground_truths:
                continue
                
            audio_path = os.path.join(speaker_dir, audio_file)
            
            # --- PHẦN CODE ĐƯỢC FIX ---
            # Đọc file bằng librosa và đưa về tần số lấy mẫu 16kHz (bắt buộc với Whisper)
            speech, sample_rate = librosa.load(audio_path, sr=16000)
            
            
            result = pipe(speech, generate_kwargs={"language": "vietnamese"})
            pred_text = clean_text(result["text"])
            
            predictions.append(pred_text)
            references.append(ground_truths[audio_id])
            
            print(f"[{count+1}] Audio ID: {audio_id}")
            print(f"Chuẩn: {ground_truths[audio_id]}")
            print(f"AI   : {pred_text}\n")
            
            count += 1
            if max_test and count >= max_test:
                break
    if max_test and count >= max_test:
        break

# 5. Đánh giá % lỗi (WER)
if len(predictions) > 0:
    error_rate = wer(references, predictions)
    print(f"==> Tỷ lệ lỗi (WER) trên {count} mẫu: {error_rate * 100:.2f}%")
else:
    print("Lỗi: Không tìm thấy file dữ liệu nào hợp lệ!")