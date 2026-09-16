package vn.httm.backend.dto.note;

import lombok.Builder;
import lombok.Data;
import vn.httm.backend.entity.enums.ProcessingStatus;

import java.time.LocalDateTime;
import java.util.List;

@Data
@Builder
public class MeetingNoteResponse {
    private Long id;
    private Long meetingId;
    private Long transcriptId;
    private String summaryText;
    private String keyPoints;
    private String generatedByModel;
    private ProcessingStatus status;
    private LocalDateTime createdAt;
    private Long editedByUserId;
    private LocalDateTime editedAt;
    private List<ActionItemResponse> actionItems;
}
