package vn.httm.backend.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import vn.httm.backend.client.AiServiceClient;
import vn.httm.backend.dto.transcript.TranscriptResponse;
import vn.httm.backend.entity.AudioRecording;
import vn.httm.backend.entity.Transcript;
import vn.httm.backend.entity.enums.ProcessingStatus;
import vn.httm.backend.repository.AudioRecordingRepository;
import vn.httm.backend.repository.TranscriptRepository;

import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class SttService {

    private final AiServiceClient aiServiceClient;
    private final AudioRecordingRepository audioRecordingRepository;
    private final TranscriptRepository transcriptRepository;

    @Transactional
    public TranscriptResponse transcribe(Long audioId) {
        AudioRecording recording = audioRecordingRepository.findById(audioId)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy audio: " + audioId));

        // Nếu đã có transcript hoàn tất, trả về luôn
        if (recording.getTranscript() != null
                && recording.getTranscript().getStatus() == ProcessingStatus.DONE) {
            log.info("Audio {} đã có transcript, trả về kết quả cũ", audioId);
            return toResponse(recording.getTranscript());
        }

        // Cập nhật trạng thái: đang xử lý
        recording.setStatus(ProcessingStatus.PROCESSING);
        audioRecordingRepository.save(recording);

        // Tạo hoặc lấy transcript record
        Transcript transcript;
        if (recording.getTranscript() != null) {
            transcript = recording.getTranscript();
        } else {
            transcript = Transcript.builder()
                .audioRecording(recording)
                .sttModelUsed("PhoWhisper-small")
                .status(ProcessingStatus.PROCESSING)
                .build();
        }
        transcript.setStatus(ProcessingStatus.PROCESSING);
        transcript = transcriptRepository.save(transcript);

        try {
            long startTime = System.currentTimeMillis();

            // Gọi AI service Python
            String rawText = aiServiceClient.transcribeAudio(recording.getFilePath());

            double elapsedSec = (System.currentTimeMillis() - startTime) / 1000.0;

            // Lưu kết quả thành công
            transcript.setRawText(rawText);
            transcript.setProcessingTimeSeconds(elapsedSec);
            transcript.setStatus(ProcessingStatus.DONE);
            transcriptRepository.save(transcript);

            recording.setStatus(ProcessingStatus.DONE);
            audioRecordingRepository.save(recording);

            log.info("STT hoàn thành cho audio {} trong {}s", audioId, elapsedSec);
            return toResponse(transcript);

        } catch (Exception e) {
            log.error("STT thất bại cho audio {}: {}", audioId, e.getMessage());

            transcript.setStatus(ProcessingStatus.FAILED);
            transcript.setErrorMessage(e.getMessage());
            transcriptRepository.save(transcript);

            recording.setStatus(ProcessingStatus.FAILED);
            audioRecordingRepository.save(recording);

            throw new RuntimeException("STT thất bại: " + e.getMessage());
        }
    }

    public TranscriptResponse getTranscript(Long audioId) {
        AudioRecording recording = audioRecordingRepository.findById(audioId)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy audio"));
        Transcript transcript = transcriptRepository.findByAudioRecording(recording)
            .orElseThrow(() -> new RuntimeException("Chưa có transcript cho audio này. Hãy gọi /transcribe trước."));
        return toResponse(transcript);
    }

    public TranscriptResponse getTranscriptById(Long transcriptId) {
        Transcript transcript = transcriptRepository.findById(transcriptId)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy transcript"));
        return toResponse(transcript);
    }

    private TranscriptResponse toResponse(Transcript t) {
        return TranscriptResponse.builder()
            .id(t.getId())
            .audioRecordingId(t.getAudioRecording().getId())
            .rawText(t.getRawText())
            .sttModelUsed(t.getSttModelUsed())
            .processingTimeSeconds(t.getProcessingTimeSeconds())
            .status(t.getStatus())
            .errorMessage(t.getErrorMessage())
            .createdAt(t.getCreatedAt())
            .segments(List.of())
            .build();
    }
}
