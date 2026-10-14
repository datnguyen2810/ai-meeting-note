package vn.httm.backend.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import vn.httm.backend.entity.Meeting;
import vn.httm.backend.entity.MeetingParticipant;
import vn.httm.backend.entity.User;

import java.util.List;
import java.util.Optional;

public interface MeetingParticipantRepository extends JpaRepository<MeetingParticipant, Long> {
    List<MeetingParticipant> findByMeeting(Meeting meeting);
    Optional<MeetingParticipant> findByMeetingAndUser(Meeting meeting, User user);
    boolean existsByMeetingAndUser(Meeting meeting, User user);
    void deleteByMeetingAndUser(Meeting meeting, User user);
}
