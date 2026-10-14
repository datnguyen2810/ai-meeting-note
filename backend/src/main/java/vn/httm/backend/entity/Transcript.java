package vn.httm.backend.entity;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;
import vn.httm.backend.entity.enums.ProcessingStatus;

import java.time.LocalDateTime;
import java.util.List;

@Entity
@Table(name = "transcripts",
    indexes = @Index(name = "idx_transcript_audio", columnList = "audio_recording_id"))
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class Transcript {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @OneToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "audio_recording_id", unique = true, nullable = false)
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private AudioRecording audioRecording;

    @Column(name = "raw_text", columnDefinition = "LONGTEXT")
    private String rawText;

    @Column(name = "stt_model_used", length = 100)
    private String sttModelUsed;

    @Column(name = "processing_time_seconds")
    private Double processingTimeSeconds;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    @Builder.Default
    private ProcessingStatus status = ProcessingStatus.PENDING;

    @Column(name = "error_message", columnDefinition = "TEXT")
    private String errorMessage;

    @CreationTimestamp
    @Column(name = "created_at", updatable = false)
    private LocalDateTime createdAt;

    @OneToMany(mappedBy = "transcript", cascade = CascadeType.ALL, fetch = FetchType.LAZY, orphanRemoval = true)
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private List<TranscriptSegment> segments;

    @OneToMany(mappedBy = "transcript", cascade = CascadeType.ALL, fetch = FetchType.LAZY)
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private List<MeetingNote> meetingNotes;
}
