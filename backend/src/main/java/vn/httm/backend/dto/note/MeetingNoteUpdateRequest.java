package vn.httm.backend.dto.note;

import lombok.Data;

@Data
public class MeetingNoteUpdateRequest {
    private String summaryText;
    private String keyPoints;
}
