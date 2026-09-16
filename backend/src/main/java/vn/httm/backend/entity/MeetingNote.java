package vn.httm.backend.entity;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;
import vn.httm.backend.entity.enums.ProcessingStatus;

import java.time.LocalDateTime;
import java.util.List;

@Entity
@Table(name = "meeting_notes",
    indexes = @Index(name = "idx_note_meeting", columnList = "meeting_id"))
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class MeetingNote {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "meeting_id", nullable = false)
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private Meeting meeting;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "transcript_id")
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private Transcript transcript;

    // Tóm tắt do AI sinh ra (hoặc toàn bộ transcript)
    @Column(name = "summary_text", columnDefinition = "LONGTEXT")
    private String summaryText;

    // Các điểm chính (lưu dạng JSON string đơn giản)
    @Column(name = "key_points", columnDefinition = "TEXT")
    private String keyPoints;

    @Column(name = "generated_by_model", length = 100)
    private String generatedByModel;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    @Builder.Default
    private ProcessingStatus status = ProcessingStatus.PENDING;

    @CreationTimestamp
    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    // Người dùng chỉnh sửa lại (nullable)
    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "edited_by_user_id")
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private User editedByUser;

    @Column(name = "edited_at")
    private LocalDateTime editedAt;

    @OneToMany(mappedBy = "meetingNote", cascade = CascadeType.ALL, fetch = FetchType.LAZY, orphanRemoval = true)
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private List<ActionItem> actionItems;
}
