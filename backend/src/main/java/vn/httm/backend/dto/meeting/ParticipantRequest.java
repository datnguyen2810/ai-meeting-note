package vn.httm.backend.dto.meeting;

import jakarta.validation.constraints.NotNull;
import lombok.Data;
import vn.httm.backend.entity.enums.ParticipantRole;

@Data
public class ParticipantRequest {

    @NotNull(message = "userId không được để trống")
    private Long userId;

    private ParticipantRole role = ParticipantRole.MEMBER;
}
