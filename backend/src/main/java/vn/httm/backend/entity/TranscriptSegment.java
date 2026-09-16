package vn.httm.backend.entity;

import jakarta.persistence.*;
import lombok.*;

@Entity
@Table(name = "transcript_segments",
    indexes = @Index(name = "idx_segment_transcript", columnList = "transcript_id"))
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class TranscriptSegment {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "transcript_id", nullable = false)
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private Transcript transcript;

    @Column(name = "speaker_label", length = 50)
    private String speakerLabel;

    // Giây bắt đầu trong file audio
    @Column(name = "start_time_sec")
    private Double startTimeSec;

    // Giây kết thúc trong file audio
    @Column(name = "end_time_sec")
    private Double endTimeSec;

    @Column(name = "text_segment", columnDefinition = "TEXT")
    private String textSegment;

    @Column(name = "sequence_order")
    private Integer sequenceOrder;
}
