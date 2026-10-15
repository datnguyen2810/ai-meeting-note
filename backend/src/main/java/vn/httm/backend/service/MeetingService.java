package vn.httm.backend.service;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import vn.httm.backend.dto.meeting.MeetingRequest;
import vn.httm.backend.dto.meeting.MeetingResponse;
import vn.httm.backend.dto.meeting.ParticipantRequest;
import vn.httm.backend.dto.meeting.ParticipantResponse;
import vn.httm.backend.entity.Meeting;
import vn.httm.backend.entity.MeetingParticipant;
import vn.httm.backend.entity.User;
import vn.httm.backend.entity.enums.MeetingStatus;
import vn.httm.backend.entity.enums.ParticipantRole;
import vn.httm.backend.repository.AudioRecordingRepository;
import vn.httm.backend.repository.MeetingParticipantRepository;
import vn.httm.backend.repository.MeetingRepository;
import vn.httm.backend.repository.UserRepository;

import java.time.LocalDateTime;
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

    // ---- Mapper helpers ----

    private MeetingResponse toResponse(Meeting meeting) {
        int audioCount = audioRecordingRepository.findByMeetingOrderByUploadedAtDesc(meeting).size();
        int participantCount = participantRepository.findByMeeting(meeting).size();

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
