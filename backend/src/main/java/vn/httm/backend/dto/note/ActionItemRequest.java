package vn.httm.backend.dto.note;

import lombok.Data;
import vn.httm.backend.entity.enums.ActionItemStatus;

import java.time.LocalDate;

@Data
public class ActionItemRequest {
    private String description;
    private Long assigneeId;
    private LocalDate dueDate;
    private ActionItemStatus status;
}
