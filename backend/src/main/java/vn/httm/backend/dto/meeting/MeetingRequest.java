package vn.httm.backend.dto.meeting;

import jakarta.validation.constraints.NotBlank;
import lombok.Data;
import vn.httm.backend.entity.enums.MeetingStatus;

import java.time.LocalDateTime;

@Data
public class MeetingRequest {

    @NotBlank(message = "Tên cuộc họp không được để trống")
    private String title;

    private String description;
    private LocalDateTime startTime;
    private LocalDateTime endTime;
    private MeetingStatus status;
}
