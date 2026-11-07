package vn.httm.backend.entity;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "transcript_speakers",
    uniqueConstraints = @UniqueConstraint(name = "uk_transcript_speaker", columnNames = {"transcript_id", "speaker_key"}),
    indexes = @Index(name = "idx_speaker_transcript", columnList = "transcript_id"))
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TranscriptSpeaker {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "transcript_id", nullable = false)
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private Transcript transcript;

    @Column(name = "speaker_key", length = 50, nullable = false)
    private String speakerKey;

    @Column(name = "label", length = 50, nullable = false)
    private String label;

    @Column(name = "first_start_seconds")
    private Double firstStartSeconds;
}

