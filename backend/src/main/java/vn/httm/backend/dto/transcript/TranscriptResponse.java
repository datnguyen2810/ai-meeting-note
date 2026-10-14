package vn.httm.backend.dto.transcript;

import lombok.Builder;
import lombok.Data;
import vn.httm.backend.entity.enums.ProcessingStatus;

import java.time.LocalDateTime;
import java.util.List;

@Data
@Builder
public class TranscriptResponse {
    private Long id;
    private Long audioRecordingId;
    private String rawText;
    private String sttModelUsed;
    private Double processingTimeSeconds;
    private ProcessingStatus status;
    private String errorMessage;
    private LocalDateTime createdAt;
    private List<SegmentResponse> segments;

    @Data
    @Builder
    public static class SegmentResponse {
        private Long id;
        private String speakerLabel;
        private Double startTimeSec;
        private Double endTimeSec;
        private String textSegment;
        private Integer sequenceOrder;
    }
}
