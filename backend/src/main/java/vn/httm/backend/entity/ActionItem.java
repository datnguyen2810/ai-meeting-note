package vn.httm.backend.entity;

import jakarta.persistence.*;
import lombok.*;
import vn.httm.backend.entity.enums.ActionItemStatus;

import java.time.LocalDate;

@Entity
@Table(name = "action_items",
    indexes = @Index(name = "idx_action_note", columnList = "meeting_note_id"))
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class ActionItem {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "meeting_note_id", nullable = false)
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private MeetingNote meetingNote;

    @Column(nullable = false, columnDefinition = "TEXT")
    private String description;

    // Người được giao việc (nullable)
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "assignee_id")
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private User assignee;

    @Column(name = "due_date")
    private LocalDate dueDate;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    @Builder.Default
    private ActionItemStatus status = ActionItemStatus.PENDING;
}
