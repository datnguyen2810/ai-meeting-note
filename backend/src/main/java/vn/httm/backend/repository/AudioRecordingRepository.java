package vn.httm.backend.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import vn.httm.backend.entity.AudioRecording;
import vn.httm.backend.entity.Meeting;

import java.util.List;

public interface AudioRecordingRepository extends JpaRepository<AudioRecording, Long> {
    List<AudioRecording> findByMeetingOrderByUploadedAtDesc(Meeting meeting);
}
