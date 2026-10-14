package vn.httm.backend.dto.audio;

import lombok.Builder;
import lombok.Data;
import vn.httm.backend.entity.enums.ProcessingStatus;

import java.time.LocalDateTime;

@Data
@Builder
public class AudioRecordingResponse {
    private Long id;
    private Long meetingId;
    private String originalFilename;
    private String format;
    private Long fileSizeBytes;
    private Integer durationSeconds;
    private ProcessingStatus status;
    private LocalDateTime uploadedAt;
    private Long transcriptId;
}
