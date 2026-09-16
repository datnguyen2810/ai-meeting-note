package vn.httm.backend.dto.meeting;

import lombok.Builder;
import lombok.Data;
import vn.httm.backend.entity.enums.ParticipantRole;

import java.time.LocalDateTime;

@Data
@Builder
public class ParticipantResponse {
    private Long id;
    private Long userId;
    private String username;
    private String fullName;
    private ParticipantRole role;
    private LocalDateTime joinedAt;
}
