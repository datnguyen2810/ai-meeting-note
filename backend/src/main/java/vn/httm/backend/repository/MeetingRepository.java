package vn.httm.backend.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import vn.httm.backend.entity.Meeting;
import vn.httm.backend.entity.User;
import vn.httm.backend.entity.enums.MeetingStatus;

import java.util.List;
import java.util.Optional;

public interface MeetingRepository extends JpaRepository<Meeting, Long> {

    List<Meeting> findByOrganizerAndDeletedAtIsNullOrderByCreatedAtDesc(User organizer);

    @Query("SELECT mp.meeting FROM MeetingParticipant mp WHERE mp.user = :user AND mp.meeting.deletedAt IS NULL ORDER BY mp.meeting.createdAt DESC")
    List<Meeting> findMeetingsByParticipant(@Param("user") User user);

    Optional<Meeting> findByIdAndDeletedAtIsNull(Long id);

    List<Meeting> findByStatusAndDeletedAtIsNull(MeetingStatus status);
}
