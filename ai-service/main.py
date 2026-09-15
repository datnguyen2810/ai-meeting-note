import os
import torch
import librosa
from fastapi import FastAPI, UploadFile, File, HTTPException
from transformers import pipeline
from fastapi.middleware.cors import CORSMiddleware

# Khởi tạo API Server
app = FastAPI(title="AI Meeting Note Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # địa chỉ React
    allow_methods=["*"],
    allow_headers=["*"],
)

# 1. Tải mô hình 1 lần duy nhất khi khởi động server
device = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"Đang tải mô hình lên {device}...")

pipe = pipeline(
    "automatic-speech-recognition",
    model="vinai/PhoWhisper-small",
    device=device,
    chunk_length_s=30
)
print("Sẵn sàng nhận file!")

# 2. Tạo API nhận file âm thanh từ Spring Boot
@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    if not file.filename.endswith(('.wav', '.mp3', '.m4a')):
        raise HTTPException(status_code=400, detail="Chỉ hỗ trợ file .wav, .mp3, .m4a")

    # Lưu file tạm thời vào máy tính
    temp_file_path = f"temp_{file.filename}"
    try:
        with open(temp_file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        # Đọc file bằng librosa với tần số 16kHz chuẩn của Whisper
        speech, sample_rate = librosa.load(temp_file_path, sr=16000)
        
        # Đưa vào AI nhận diện
        result = pipe(speech, generate_kwargs={"language": "vietnamese"})
        
        return {
            "status": "success",
            "filename": file.filename,
            "transcript": result["text"]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    finally:
        # Xóa file tạm sau khi xử lý xong để dọn rác ổ cứng
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)