package vn.httm.backend.service;

import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import vn.httm.backend.dto.note.ActionItemRequest;
import vn.httm.backend.dto.note.ActionItemResponse;
import vn.httm.backend.dto.note.MeetingNoteResponse;
import vn.httm.backend.dto.note.MeetingNoteUpdateRequest;
import vn.httm.backend.entity.ActionItem;
import vn.httm.backend.entity.Meeting;
import vn.httm.backend.entity.MeetingNote;
import vn.httm.backend.entity.Transcript;
import vn.httm.backend.entity.User;
import vn.httm.backend.entity.enums.ActionItemStatus;
import vn.httm.backend.entity.enums.ProcessingStatus;
import vn.httm.backend.repository.ActionItemRepository;
import vn.httm.backend.repository.MeetingNoteRepository;
import vn.httm.backend.repository.MeetingRepository;
import vn.httm.backend.repository.TranscriptRepository;
import vn.httm.backend.repository.UserRepository;

import java.time.LocalDateTime;
import java.util.List;
import java.util.stream.Collectors;

@Service
@RequiredArgsConstructor
public class MeetingNoteService {

    private final MeetingNoteRepository meetingNoteRepository;
    private final TranscriptRepository transcriptRepository;
    private final ActionItemRepository actionItemRepository;
    private final UserRepository userRepository;
    private final MeetingRepository meetingRepository;

    @Transactional
    public MeetingNoteResponse generateNote(Long transcriptId) {
        Transcript transcript = transcriptRepository.findById(transcriptId)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy transcript"));

        if (transcript.getStatus() != ProcessingStatus.DONE) {
            throw new RuntimeException("Transcript chưa hoàn tất STT (status: " + transcript.getStatus() + ")");
        }

        // Kiểm tra nếu đã có note rồi
        var existingOpt = meetingNoteRepository.findByTranscript(transcript);
        if (existingOpt.isPresent()) {
            // Trả về note đã có thay vì ném lỗi
            return toResponse(existingOpt.get());
        }

        Meeting meeting = transcript.getAudioRecording().getMeeting();

        MeetingNote note = MeetingNote.builder()
            .meeting(meeting)
            .transcript(transcript)
            .summaryText(transcript.getRawText())
            .generatedByModel(transcript.getSttModelUsed())
            .status(ProcessingStatus.DONE)
            .build();

        note = meetingNoteRepository.save(note);
        return toResponse(note);
    }

    public List<MeetingNoteResponse> getByMeeting(Long meetingId) {
        Meeting meeting = meetingRepository.findByIdAndDeletedAtIsNull(meetingId)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy cuộc họp"));
        return meetingNoteRepository.findByMeetingOrderByCreatedAtDesc(meeting).stream()
            .map(this::toResponse)
            .collect(Collectors.toList());
    }

    public MeetingNoteResponse getById(Long id) {
        MeetingNote note = meetingNoteRepository.findById(id)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy biên bản"));
        return toResponse(note);
    }

    @Transactional
    public MeetingNoteResponse updateNote(Long id, MeetingNoteUpdateRequest request, String username) {
        MeetingNote note = meetingNoteRepository.findById(id)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy biên bản"));

        User editor = userRepository.findByUsername(username)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy user"));

        if (request.getSummaryText() != null) note.setSummaryText(request.getSummaryText());
        if (request.getKeyPoints() != null) note.setKeyPoints(request.getKeyPoints());
        note.setEditedByUser(editor);
        note.setEditedAt(LocalDateTime.now());

        return toResponse(meetingNoteRepository.save(note));
    }

    @Transactional
    public ActionItemResponse addActionItem(Long noteId, ActionItemRequest request) {
        MeetingNote note = meetingNoteRepository.findById(noteId)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy biên bản"));

        User assignee = null;
        if (request.getAssigneeId() != null) {
            assignee = userRepository.findById(request.getAssigneeId()).orElse(null);
        }

        ActionItem item = ActionItem.builder()
            .meetingNote(note)
            .description(request.getDescription())
            .assignee(assignee)
            .dueDate(request.getDueDate())
            .status(request.getStatus() != null ? request.getStatus() : ActionItemStatus.PENDING)
            .build();

        return toActionItemResponse(actionItemRepository.save(item));
    }

    public List<ActionItemResponse> getActionItems(Long noteId) {
        MeetingNote note = meetingNoteRepository.findById(noteId)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy biên bản"));
        return actionItemRepository.findByMeetingNote(note).stream()
            .map(this::toActionItemResponse)
            .collect(Collectors.toList());
    }

    @Transactional
    public ActionItemResponse updateActionItem(Long itemId, ActionItemRequest request) {
        ActionItem item = actionItemRepository.findById(itemId)
            .orElseThrow(() -> new RuntimeException("Không tìm thấy action item"));

        if (request.getDescription() != null) item.setDescription(request.getDescription());
        if (request.getDueDate() != null) item.setDueDate(request.getDueDate());
        if (request.getStatus() != null) item.setStatus(request.getStatus());
        if (request.getAssigneeId() != null) {
            userRepository.findById(request.getAssigneeId()).ifPresent(item::setAssignee);
        }

        return toActionItemResponse(actionItemRepository.save(item));
    }

    // ---- Mapper helpers ----

    private MeetingNoteResponse toResponse(MeetingNote note) {
        List<ActionItemResponse> items = actionItemRepository.findByMeetingNote(note).stream()
            .map(this::toActionItemResponse)
            .collect(Collectors.toList());

        return MeetingNoteResponse.builder()
            .id(note.getId())
            .meetingId(note.getMeeting().getId())
            .transcriptId(note.getTranscript() != null ? note.getTranscript().getId() : null)
            .summaryText(note.getSummaryText())
            .keyPoints(note.getKeyPoints())
            .generatedByModel(note.getGeneratedByModel())
            .status(note.getStatus())
            .createdAt(note.getCreatedAt())
            .editedByUserId(note.getEditedByUser() != null ? note.getEditedByUser().getId() : null)
            .editedAt(note.getEditedAt())
            .actionItems(items)
            .build();
    }

    private ActionItemResponse toActionItemResponse(ActionItem item) {
        return ActionItemResponse.builder()
            .id(item.getId())
            .description(item.getDescription())
            .assigneeId(item.getAssignee() != null ? item.getAssignee().getId() : null)
            .assigneeName(item.getAssignee() != null ? item.getAssignee().getFullName() : null)
            .dueDate(item.getDueDate())
            .status(item.getStatus())
            .build();
    }
}
