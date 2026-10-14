package vn.httm.backend.entity;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;
import vn.httm.backend.entity.enums.ProcessingStatus;

import java.time.LocalDateTime;

@Entity
@Table(name = "audio_recordings",
    indexes = @Index(name = "idx_audio_meeting", columnList = "meeting_id"))
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class AudioRecording {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "meeting_id", nullable = false)
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private Meeting meeting;

    @Column(name = "file_path", nullable = false)
    private String filePath;

    @Column(name = "original_filename", length = 255)
    private String originalFilename;

    @Column(name = "duration_seconds")
    private Integer durationSeconds;

    @Column(name = "sample_rate")
    private Integer sampleRate;

    @Column(length = 20)
    private String format;

    @Column(name = "file_size_bytes")
    private Long fileSizeBytes;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    @Builder.Default
    private ProcessingStatus status = ProcessingStatus.PENDING;

    @CreationTimestamp
    @Column(name = "uploaded_at", updatable = false)
    private LocalDateTime uploadedAt;

    @OneToOne(mappedBy = "audioRecording", cascade = CascadeType.ALL, fetch = FetchType.LAZY)
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private Transcript transcript;
}
