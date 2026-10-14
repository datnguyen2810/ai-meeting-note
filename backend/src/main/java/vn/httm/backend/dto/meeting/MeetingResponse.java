package vn.httm.backend.dto.meeting;

import lombok.Builder;
import lombok.Data;
import vn.httm.backend.entity.enums.MeetingStatus;

import java.time.LocalDateTime;

@Data
@Builder
public class MeetingResponse {
    private Long id;
    private String title;
    private String description;
    private Long organizerId;
    private String organizerName;
    private LocalDateTime startTime;
    private LocalDateTime endTime;
    private MeetingStatus status;
    private LocalDateTime createdAt;
    private int participantCount;
    private int audioCount;
}
