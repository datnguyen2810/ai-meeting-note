package vn.httm.backend.repository;

import org.springframework.data.jpa.repository.JpaRepository;
import vn.httm.backend.entity.AudioRecording;
import vn.httm.backend.entity.Transcript;

import java.util.Optional;

public interface TranscriptRepository extends JpaRepository<Transcript, Long> {
    Optional<Transcript> findByAudioRecording(AudioRecording audioRecording);
}
