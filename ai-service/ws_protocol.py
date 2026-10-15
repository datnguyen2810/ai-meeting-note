"""
ws_protocol.py - Định nghĩa giao thức WebSocket cho Live Stream ASR.
Theo mục 4.2 của PLAN_REALTIME_HYBRID_ASR.md
"""

# Client -> Server message types
CLIENT_START = "start"
CLIENT_STOP = "stop"

# Server -> Client message types
SERVER_READY = "ready"
SERVER_INTERIM = "interim"
SERVER_FINAL = "final"
SERVER_LAG = "lag"
SERVER_ERROR = "error"
SERVER_CLOSED = "closed"

# Cấu hình âm thanh
EXPECTED_SAMPLE_RATE = 16000
BYTES_PER_SAMPLE = 2  # Int16
FRAME_MS = 20
FRAME_SAMPLES = EXPECTED_SAMPLE_RATE * FRAME_MS // 1000  # 320
FRAME_BYTES = FRAME_SAMPLES * BYTES_PER_SAMPLE          # 640

# Client gom 10 frame (200ms) = 3200 bytes
CLIENT_CHUNK_MS = 200
CLIENT_CHUNK_BYTES = (EXPECTED_SAMPLE_RATE * CLIENT_CHUNK_MS // 1000) * BYTES_PER_SAMPLE  # 3200
