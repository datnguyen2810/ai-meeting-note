package vn.httm.backend.entity;

import jakarta.persistence.*;
import lombok.*;
import org.hibernate.annotations.CreationTimestamp;
import vn.httm.backend.entity.enums.ParticipantRole;

import java.time.LocalDateTime;

@Entity
@Table(name = "meeting_participants",
    uniqueConstraints = @UniqueConstraint(columnNames = {"meeting_id", "user_id"}))
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class MeetingParticipant {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "meeting_id", nullable = false)
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private Meeting meeting;

    @ManyToOne(fetch = FetchType.LAZY)
    @JoinColumn(name = "user_id", nullable = false)
    @ToString.Exclude
    @EqualsAndHashCode.Exclude
    private User user;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    @Builder.Default
    private ParticipantRole role = ParticipantRole.MEMBER;

    @CreationTimestamp
    @Column(name = "joined_at", updatable = false)
    private LocalDateTime joinedAt;
}
