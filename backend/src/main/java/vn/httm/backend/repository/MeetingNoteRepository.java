package vn.httm.backend.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import vn.httm.backend.entity.Meeting;
import vn.httm.backend.entity.MeetingNote;
import vn.httm.backend.entity.Transcript;

import java.util.List;
import java.util.Optional;

public interface MeetingNoteRepository extends JpaRepository<MeetingNote, Long> {
    List<MeetingNote> findByMeetingOrderByCreatedAtDesc(Meeting meeting);
    Optional<MeetingNote> findByTranscript(Transcript transcript);
}
