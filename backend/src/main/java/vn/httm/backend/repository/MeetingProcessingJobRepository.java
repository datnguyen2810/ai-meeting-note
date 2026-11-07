package vn.httm.backend.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import vn.httm.backend.entity.MeetingProcessingJob;
import vn.httm.backend.entity.enums.JobStatus;

import java.util.List;
import java.util.Optional;

@Repository
public interface MeetingProcessingJobRepository extends JpaRepository<MeetingProcessingJob, Long> {
    Optional<MeetingProcessingJob> findTopByMeetingIdOrderByIdDesc(Long meetingId);
    Optional<MeetingProcessingJob> findByClientRequestId(String clientRequestId);
    List<MeetingProcessingJob> findByStatusAndOwnerInstanceId(JobStatus status, String ownerInstanceId);
}

