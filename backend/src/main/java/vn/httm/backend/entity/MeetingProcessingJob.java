package vn.httm.backend.entity;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;
import org.hibernate.annotations.UpdateTimestamp;
import vn.httm.backend.entity.enums.JobStatus;

import java.time.LocalDateTime;

@Entity
@Table(name = "meeting_processing_jobs",
    indexes = {
        @Index(name = "idx_job_meeting", columnList = "meeting_id"),
        @Index(name = "idx_job_status", columnList = "status")
    })
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class MeetingProcessingJob {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "meeting_id", nullable = false)
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private Meeting meeting;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "audio_recording_id")
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private AudioRecording audioRecording;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "requested_by")
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private User requestedBy;

    @Column(name = "client_request_id", length = 100)
    private String clientRequestId;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 30)
    @Builder.Default
    private JobStatus status = JobStatus.QUEUED;

    @Column(length = 50)
    private String stage;

    @Column(name = "owner_instance_id", length = 100)
    private String ownerInstanceId;

    @Column(name = "lease_expires_at")
    private LocalDateTime leaseExpiresAt;

    @Column(name = "attempt_count")
    @Builder.Default
    private Integer attemptCount = 0;

    @Column(name = "error_code", length = 50)
    private String errorCode;

    @Column(name = "safe_error_message", length = 500)
    private String safeErrorMessage;

    @CreationTimestamp
    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    @UpdateTimestamp
    @Column(name = "updated_at")
    private LocalDateTime updatedAt;
}

