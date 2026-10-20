package vn.httm.backend.service;

import lombok.RequiredArgsConstructor;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import vn.httm.backend.dto.meeting.MeetingRequest;
import vn.httm.backend.dto.meeting.MeetingResponse;
import vn.httm.backend.dto.meeting.ParticipantRequest;
import vn.httm.backend.dto.meeting.ParticipantResponse;
import vn.httm.backend.entity.AudioRecording;
import vn.httm.backend.entity.Meeting;
import vn.httm.backend.entity.MeetingNote;
import vn.httm.backend.entity.MeetingParticipant;
import vn.httm.backend.entity.Transcript;
import vn.httm.backend.entity.User;
import vn.httm.backend.entity.enums.MeetingStatus;
import vn.httm.backend.entity.enums.ParticipantRole;
import vn.httm.backend.entity.enums.ProcessingStatus;
import vn.httm.backend.repository.AudioRecordingRepository;
import vn.httm.backend.repository.MeetingNoteRepository;
import vn.httm.backend.repository.MeetingParticipantRepository;
import vn.httm.backend.repository.MeetingRepository;
import vn.httm.backend.repository.TranscriptRepository;
import vn.httm.backend.repository.UserRepository;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

@Service
@RequiredArgsConstructor
public class MeetingService {

    private final MeetingRepository meetingRepository;
    private final MeetingParticipantRepository participantRepository;
    private final UserRepository userRepository;
    private final AudioRecordingRepository audioRecordingRepository;
    private final TranscriptRepository transcriptRepository;
    private final MeetingNoteRepository meetingNoteRepository;

    @Value("${app.upload.audio-dir:./uploads/audio}")
    private String audioUploadDir;

    @Transactional
    public MeetingResponse createMeeting(MeetingRequest request, String organizerUsername) {
        User organizer = findUserByUsername(organizerUsername);

        Meeting meeting = Meeting.builder()
            .title(request.getTitle())
            .description(request.getDescription())
            .organizer(organizer)
            .startTime(request.getStartTime())
            .endTime(request.getEndTime())
            .status(request.getStatus() != null ? request.getStatus() : MeetingStatus.SCHEDULED)
            .build();

        meeting = meetingRepository.save(meeting);

        // Tự động thêm organizer là HOST
        MeetingParticipant host = MeetingParticipant.builder()
            .meeting(meeting)
            .user(organizer)
            .role(ParticipantRole.HOST)
            .build();
        participantRepository.save(host);

        return toResponse(meeting);
    }

    public List<MeetingResponse> getAllMyMeetings(String username) {
        User user = findUserByUsername(username);
        List<Meeting> organized = meetingRepository.findByOrganizerAndDeletedAtIsNullOrderByCreatedAtDesc(user);
        List<Meeting> participated = meetingRepository.findMeetingsByParticipant(user);

        // Gộp, loại trùng theo ID
        return Stream.concat(organized.stream(), participated.stream())
            .collect(Collectors.toMap(
                Meeting::getId,
                m -> m,
                (existing, dup) -> existing,
                LinkedHashMap::new
            ))
            .values().stream()
            .map(this::toResponse)
            .collect(Collectors.toList());
    }

    public MeetingResponse getMeetingById(Long id) {
        Meeting meeting = meetingRepository.findByIdAndDeletedAtIsNull(id)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy cuộc họp"));
        return toResponse(meeting);
    }

    @Transactional
    public MeetingResponse updateMeeting(Long id, MeetingRequest request, String username) {
        Meeting meeting = meetingRepository.findByIdAndDeletedAtIsNull(id)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy cuộc họp"));

        if (!meeting.getOrganizer().getUsername().equals(username)) {
            throw new RuntimeException("Chỉ người tổ chức mới có quyền chỉnh sửa");
        }

        if (request.getTitle() != null) meeting.setTitle(request.getTitle());
        if (request.getDescription() != null) meeting.setDescription(request.getDescription());
        if (request.getStartTime() != null) meeting.setStartTime(request.getStartTime());
        if (request.getEndTime() != null) meeting.setEndTime(request.getEndTime());
        if (request.getStatus() != null) meeting.setStatus(request.getStatus());

        return toResponse(meetingRepository.save(meeting));
    }

    @Transactional
    public void deleteMeeting(Long id, String username) {
        Meeting meeting = meetingRepository.findByIdAndDeletedAtIsNull(id)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy cuộc họp"));

        if (!meeting.getOrganizer().getUsername().equals(username)) {
            throw new RuntimeException("Chỉ người tổ chức mới có quyền xóa");
        }

        // Soft delete
        meeting.setDeletedAt(LocalDateTime.now());
        meetingRepository.save(meeting);
    }

    @Transactional
    public ParticipantResponse addParticipant(Long meetingId, ParticipantRequest request, String organizerUsername) {
        Meeting meeting = meetingRepository.findByIdAndDeletedAtIsNull(meetingId)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy cuộc họp"));

        if (!meeting.getOrganizer().getUsername().equals(organizerUsername)) {
            throw new RuntimeException("Chỉ người tổ chức mới có quyền thêm thành viên");
        }

        User user = userRepository.findById(request.getUserId())
            .orElseThrow(() -> new RuntimeException("Không tìm thấy user"));

        if (participantRepository.existsByMeetingAndUser(meeting, user)) {
            throw new RuntimeException("User đã là thành viên của cuộc họp");
        }

        MeetingParticipant participant = MeetingParticipant.builder()
            .meeting(meeting)
            .user(user)
            .role(request.getRole())
            .build();

        participant = participantRepository.save(participant);
        return toParticipantResponse(participant);
    }

    public List<ParticipantResponse> getParticipants(Long meetingId) {
        Meeting meeting = meetingRepository.findByIdAndDeletedAtIsNull(meetingId)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy cuộc họp"));
        return participantRepository.findByMeeting(meeting).stream()
            .map(this::toParticipantResponse)
            .collect(Collectors.toList());
    }

    @Transactional
    public MeetingResponse saveMeetingSession(
            String title,
            String description,
            String transcriptText,
            String summaryText,
            Integer durationSeconds,
            MultipartFile file,
            String username) throws IOException {

        User organizer = findUserByUsername(username);

        String meetingTitle = (title != null && !title.trim().isEmpty())
                ? title.trim()
                : "Cuộc họp " + LocalDateTime.now().format(DateTimeFormatter.ofPattern("HH:mm dd/MM/yyyy"));

        LocalDateTime now = LocalDateTime.now();
        LocalDateTime startTime = (durationSeconds != null && durationSeconds > 0)
                ? now.minusSeconds(durationSeconds)
                : now;

        Meeting meeting = Meeting.builder()
                .title(meetingTitle)
                .description(description)
                .organizer(organizer)
                .startTime(startTime)
                .endTime(now)
                .status(MeetingStatus.COMPLETED)
                .build();
        meeting = meetingRepository.save(meeting);

        // Thêm organizer là HOST
        MeetingParticipant host = MeetingParticipant.builder()
                .meeting(meeting)
                .user(organizer)
                .role(ParticipantRole.HOST)
                .build();
        participantRepository.save(host);

        AudioRecording recording = null;
        if (file != null && !file.isEmpty()) {
            String originalFilename = file.getOriginalFilename();
            String extension = "";
            if (originalFilename != null && originalFilename.lastIndexOf('.') >= 0) {
                extension = originalFilename.substring(originalFilename.lastIndexOf('.') + 1).toLowerCase();
            }

            Path uploadPath = Paths.get(audioUploadDir, String.valueOf(meeting.getId()));
            Files.createDirectories(uploadPath);

            String timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"));
            String storedFilename = timestamp + "_" + (originalFilename != null ? originalFilename : "audio.wav");
            Path filePath = uploadPath.resolve(storedFilename);

            Files.copy(file.getInputStream(), filePath, StandardCopyOption.REPLACE_EXISTING);

            recording = AudioRecording.builder()
                    .meeting(meeting)
                    .filePath(filePath.toString())
                    .originalFilename(originalFilename)
                    .format(extension.isEmpty() ? "wav" : extension)
                    .fileSizeBytes(file.getSize())
                    .durationSeconds(durationSeconds)
                    .status(ProcessingStatus.DONE)
                    .build();
            recording = audioRecordingRepository.save(recording);
        }

        Transcript transcript = null;
        if ((transcriptText != null && !transcriptText.trim().isEmpty()) || recording != null) {
            transcript = Transcript.builder()
                    .audioRecording(recording)
                    .rawText(transcriptText != null ? transcriptText.trim() : "")
                    .sttModelUsed("PhoWhisper-small")
                    .status(ProcessingStatus.DONE)
                    .build();
            transcript = transcriptRepository.save(transcript);
        }

        if (summaryText != null && !summaryText.trim().isEmpty()) {
            MeetingNote note = MeetingNote.builder()
                    .meeting(meeting)
                    .transcript(transcript)
                    .summaryText(summaryText.trim())
                    .generatedByModel("Qwen2.5-1.5B-Instruct")
                    .status(ProcessingStatus.DONE)
                    .build();
            meetingNoteRepository.save(note);
        }

        return toResponse(meeting);
    }

    // ---- Mapper helpers ----

    private MeetingResponse toResponse(Meeting meeting) {
        int audioCount = audioRecordingRepository.findByMeetingOrderByUploadedAtDesc(meeting).size();
        int participantCount = participantRepository.findByMeeting(meeting).size();

        String summary = null;
        String transcript = null;

        List<MeetingNote> notes = meetingNoteRepository.findByMeetingOrderByCreatedAtDesc(meeting);
        if (notes != null && !notes.isEmpty()) {
            summary = notes.get(0).getSummaryText();
            if (notes.get(0).getTranscript() != null) {
                transcript = notes.get(0).getTranscript().getRawText();
            }
        }

        if (transcript == null) {
            List<AudioRecording> audios = audioRecordingRepository.findByMeetingOrderByUploadedAtDesc(meeting);
            if (audios != null) {
                for (AudioRecording a : audios) {
                    if (a.getTranscript() != null && a.getTranscript().getRawText() != null) {
                        transcript = a.getTranscript().getRawText();
                        break;
                    }
                }
            }
        }

        return MeetingResponse.builder()
            .id(meeting.getId())
            .title(meeting.getTitle())
            .description(meeting.getDescription())
            .organizerId(meeting.getOrganizer().getId())
            .organizerName(meeting.getOrganizer().getFullName() != null
                ? meeting.getOrganizer().getFullName() : meeting.getOrganizer().getUsername())
            .startTime(meeting.getStartTime())
            .endTime(meeting.getEndTime())
            .status(meeting.getStatus())
            .createdAt(meeting.getCreatedAt())
            .participantCount(participantCount)
            .audioCount(audioCount)
            .summary(summary)
            .transcript(transcript)
            .build();
    }

    private ParticipantResponse toParticipantResponse(MeetingParticipant p) {
        return ParticipantResponse.builder()
            .id(p.getId())
            .userId(p.getUser().getId())
            .username(p.getUser().getUsername())
            .fullName(p.getUser().getFullName())
            .role(p.getRole())
            .joinedAt(p.getJoinedAt())
            .build();
    }

    private User findUserByUsername(String username) {
        return userRepository.findByUsername(username)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy user: " + username));
    }
}
