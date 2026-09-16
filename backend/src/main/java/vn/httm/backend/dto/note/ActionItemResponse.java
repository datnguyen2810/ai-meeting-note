package vn.httm.backend.dto.note;

import lombok.Builder;
import lombok.Data;
import vn.httm.backend.entity.enums.ActionItemStatus;

import java.time.LocalDate;

@Data
@Builder
public class ActionItemResponse {
    private Long id;
    private String description;
    private Long assigneeId;
    private String assigneeName;
    private LocalDate dueDate;
    private ActionItemStatus status;
}
