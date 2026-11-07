import time
import torch
from transformers import pipeline

device = "cuda:0" if torch.cuda.is_available() else "cpu"
print(f"Testing PhoWhisper on {device}...")

pipe = pipeline(
    "automatic-speech-recognition",
    model="vinai/PhoWhisper-small",
    device=device,
    chunk_length_s=30,
    return_timestamps=True,
)

audio_path = r"C:\Users\ADMIN\coding\nam4_ki1\ai-meeting-note\data_test\VIVOSDEV01_R089.wav"
t0 = time.perf_counter()
res = pipe(audio_path, return_timestamps=True)
dur = time.perf_counter() - t0

print(f"Inference time: {dur:.2f}s")
print("Full transcript:", res.get("text"))
print("Chunks:")
for c in res.get("chunks", []):
    print(f"  [{c['timestamp'][0]}s -> {c['timestamp'][1]}s]: {c['text']}")

