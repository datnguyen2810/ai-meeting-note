package vn.httm.backend.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import vn.httm.backend.entity.ActionItem;
import vn.httm.backend.entity.MeetingNote;
import vn.httm.backend.entity.User;

import java.util.List;

public interface ActionItemRepository extends JpaRepository<ActionItem, Long> {
    List<ActionItem> findByMeetingNote(MeetingNote meetingNote);
    List<ActionItem> findByAssignee(User assignee);
}
