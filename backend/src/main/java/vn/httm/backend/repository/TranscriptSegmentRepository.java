package vn.httm.backend.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import vn.httm.backend.entity.Transcript;
import vn.httm.backend.entity.TranscriptSegment;

import java.util.List;

public interface TranscriptSegmentRepository extends JpaRepository<TranscriptSegment, Long> {
    List<TranscriptSegment> findByTranscriptOrderBySequenceOrder(Transcript transcript);
}
