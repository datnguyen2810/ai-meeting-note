import os
import torch
import librosa
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from transformers import pipeline, AutoTokenizer, AutoModelForCausalLM

# ==========================================
# Khoi tao API Server
# ==========================================
app = FastAPI(title="AI Meeting Note Service")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # dia chi React
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# 1. Tai mo hinh 1 lan duy nhat khi khoi dong server
# ==========================================

device = "cpu"
# device = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"[INFO] Loading models on {device}...")

# --- Mo hinh STT: PhoWhisper ---
print("[INFO] Loading PhoWhisper (Speech-to-Text)...")
stt_pipe = pipeline(
    "automatic-speech-recognition",
    model="vinai/PhoWhisper-small",
    device=device,
    chunk_length_s=30
)
print("[INFO] PhoWhisper loaded.")

# --- Mo hinh LLM: Qwen2.5-1.5B-Instruct (Tom tat) ---
print("[INFO] Loading Qwen2.5-1.5B-Instruct (Summarization)...")
llm_model_id = "Qwen/Qwen2.5-1.5B-Instruct"

llm_tokenizer = AutoTokenizer.from_pretrained(llm_model_id)
llm_model = AutoModelForCausalLM.from_pretrained(
    llm_model_id,
    dtype=torch.float16 if device != "cpu" else torch.float32,
).to(device)
print("[INFO] All models loaded. Ready to receive requests!")


# ==========================================
# 2. Ham tien ich: Tóm tat van ban bang Qwen
# ==========================================
def summarize_text(transcript: str) -> str:
    """Nhan dau vao la van ban phien am, tra ve ban tom tat dang gach dau dong chuan tieng Viet."""
    system_prompt = (
        "Bạn là thư ký cuộc họp AI chuyên nghiệp. Nhiệm vụ của bạn là đọc nội dung phiên âm cuộc họp "
        "và tóm tắt lại các ý chính một cách súc tích, chính xác bằng tiếng Việt.\n\n"
        "Quy tắc bắt buộc:\n"
        "- Tuyệt đối KHÔNG viết lời chào hỏi hoặc kết thư (cấm viết 'Chào các bạn', 'Rất mong mọi người...').\n"
        "- Chỉ tập trung vào sự thật có trong nội dung, không suy diễn hoặc bịa đặt thêm thông tin.\n"
        "- Trình bày kết quả rõ ràng theo cấu trúc gạch đầu dòng sau:\n"
        "Mục đích cuộc họp:\n"
        "Đánh giá tiến độ & Kết quả đạt được:\n"
        "Vấn đề tồn đọng:\n"
        "Phân công công việc & Thời hạn:"
    )

    user_prompt = f"Hãy tóm tắt nội dung cuộc họp sau đây theo đúng quy tắc:\n\n{transcript}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    text = llm_tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = llm_tokenizer([text], return_tensors="pt").to(device)

    with torch.no_grad():
        outputs = llm_model.generate(
            **inputs,
            max_new_tokens=400,
            temperature=0.1,        # Nhiet do thap giup model bam sat su that, tranh bia dat
            repetition_penalty=1.1,  # Han che lap tu
            do_sample=True
        )

    # Chi lay phan text moi sinh ra (bo phan prompt truyen vao)
    generated_ids = outputs[0][inputs.input_ids.shape[1]:]
    summary = llm_tokenizer.decode(generated_ids, skip_special_tokens=True)
    return summary.strip()


# ==========================================
# 3. API: Nhan file am thanh -> Phien am + Tom tat
# ==========================================
@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    if not file.filename.endswith(('.wav', '.mp3', '.m4a')):
        raise HTTPException(status_code=400, detail="Only .wav, .mp3, .m4a files are supported")

    temp_file_path = f"temp_{file.filename}"
    try:
        # Luu file tam vao dia
        with open(temp_file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # Doc file bang librosa voi tan so 16kHz chuan cua Whisper
        speech, sample_rate = librosa.load(temp_file_path, sr=16000)

        # Buoc 1: Nhan dien giong noi -> van ban
        print(f"[INFO] Transcribing {file.filename}...")
        stt_result = stt_pipe(speech, generate_kwargs={"language": "vietnamese"})
        transcript = stt_result["text"]
        print(f"[INFO] Transcription done ({len(transcript)} chars). Summarizing...")

        # Buoc 2: Tom tat van ban bang LLM
        summary = summarize_text(transcript)
        print("[INFO] Summarization done.")

        return {
            "status": "success",
            "filename": file.filename,
            "transcript": transcript,
            "summary": summary
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Xoa file tam de don dep o cung
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)


# ==========================================
# 4. API: Tom tat van ban thuong (khong can file am thanh)
# ==========================================
class SummarizeRequest(BaseModel):
    transcript: str


@app.post("/api/summarize")
async def summarize_endpoint(body: SummarizeRequest):
    if not body.transcript or not body.transcript.strip():
        raise HTTPException(status_code=400, detail="transcript must not be empty")

    try:
        summary = summarize_text(body.transcript)
        return {
            "status": "success",
            "summary": summary
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))