package vn.httm.backend.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.stereotype.Repository;
import vn.httm.backend.entity.TranscriptSpeaker;

import java.util.List;

@Repository
public interface TranscriptSpeakerRepository extends JpaRepository<TranscriptSpeaker, Long> {
    List<TranscriptSpeaker> findByTranscriptId(Long transcriptId);
}

