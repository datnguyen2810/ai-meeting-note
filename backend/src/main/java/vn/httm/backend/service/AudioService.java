package vn.httm.backend.service;

import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import vn.httm.backend.dto.audio.AudioRecordingResponse;
import vn.httm.backend.entity.AudioRecording;
import vn.httm.backend.entity.Meeting;
import vn.httm.backend.entity.enums.ProcessingStatus;
import vn.httm.backend.repository.AudioRecordingRepository;
import vn.httm.backend.repository.MeetingRepository;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class AudioService {

    private final AudioRecordingRepository audioRecordingRepository;
    private final MeetingRepository meetingRepository;

    @Value("${app.upload.audio-dir}")
    private String audioUploadDir;

    @Transactional
    public AudioRecordingResponse uploadAudio(Long meetingId, MultipartFile file) throws IOException {
        Meeting meeting = meetingRepository.findByIdAndDeletedAtIsNull(meetingId)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy cuộc họp"));

        String originalFilename = file.getOriginalFilename();
        String extension = getExtension(originalFilename);
        validateAudioFormat(extension);

        // Tạo thư mục lưu theo meetingId
        Path uploadPath = Paths.get(audioUploadDir, String.valueOf(meetingId));
        Files.createDirectories(uploadPath);

        // Đặt tên file duy nhất
        String timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"));
        String storedFilename = timestamp + "_" + originalFilename;
        Path filePath = uploadPath.resolve(storedFilename);

        Files.copy(file.getInputStream(), filePath, StandardCopyOption.REPLACE_EXISTING);

        AudioRecording recording = AudioRecording.builder()
            .meeting(meeting)
            .filePath(filePath.toString())
            .originalFilename(originalFilename)
            .format(extension)
            .fileSizeBytes(file.getSize())
            .status(ProcessingStatus.PENDING)
            .build();

        recording = audioRecordingRepository.save(recording);
        return toResponse(recording);
    }

    public List<AudioRecordingResponse> getByMeeting(Long meetingId) {
        Meeting meeting = meetingRepository.findByIdAndDeletedAtIsNull(meetingId)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy cuộc họp"));
        return audioRecordingRepository.findByMeetingOrderByUploadedAtDesc(meeting).stream()
            .map(this::toResponse)
            .collect(Collectors.toList());
    }

    public AudioRecordingResponse getById(Long id) {
        AudioRecording recording = audioRecordingRepository.findById(id)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy bản ghi"));
        return toResponse(recording);
    }

    private AudioRecordingResponse toResponse(AudioRecording r) {
        Long transcriptId = (r.getTranscript() != null) ? r.getTranscript().getId() : null;
        return AudioRecordingResponse.builder()
            .id(r.getId())
            .meetingId(r.getMeeting().getId())
            .originalFilename(r.getOriginalFilename())
            .format(r.getFormat())
            .fileSizeBytes(r.getFileSizeBytes())
            .durationSeconds(r.getDurationSeconds())
            .status(r.getStatus())
            .uploadedAt(r.getUploadedAt())
            .transcriptId(transcriptId)
            .build();
    }

    private String getExtension(String filename) {
        if (filename == null) return "";
        int dot = filename.lastIndexOf('.');
        return dot >= 0 ? filename.substring(dot + 1).toLowerCase() : "";
    }

    private void validateAudioFormat(String ext) {
        if (!List.of("wav", "mp3", "m4a", "ogg", "flac", "webm").contains(ext)) {
            throw new RuntimeException("Chỉ hỗ trợ file audio: wav, mp3, m4a, ogg, flac, webm");
        }
    }
}
