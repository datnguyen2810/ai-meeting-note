package vn.httm.backend.controller;

import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.*;
import vn.httm.backend.dto.ApiResponse;
import vn.httm.backend.dto.note.ActionItemRequest;
import vn.httm.backend.dto.note.ActionItemResponse;
import vn.httm.backend.dto.note.MeetingNoteResponse;
import vn.httm.backend.dto.note.MeetingNoteUpdateRequest;
import vn.httm.backend.service.MeetingNoteService;

import java.util.List;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class MeetingNoteController {

    private final MeetingNoteService meetingNoteService;

    @PostMapping("/transcripts/{transcriptId}/notes")
    public ResponseEntity<ApiResponse<MeetingNoteResponse>> generate(@PathVariable Long transcriptId) {
        return ResponseEntity.ok(ApiResponse.ok("Đã tạo biên bản", meetingNoteService.generateNote(transcriptId)));
    }

    @GetMapping("/meetings/{meetingId}/notes")
    public ResponseEntity<ApiResponse<List<MeetingNoteResponse>>> getByMeeting(@PathVariable Long meetingId) {
        return ResponseEntity.ok(ApiResponse.ok(meetingNoteService.getByMeeting(meetingId)));
    }

    @GetMapping("/notes/{noteId}")
    public ResponseEntity<ApiResponse<MeetingNoteResponse>> getById(@PathVariable Long noteId) {
        return ResponseEntity.ok(ApiResponse.ok(meetingNoteService.getById(noteId)));
    }

    @PutMapping("/notes/{noteId}")
    public ResponseEntity<ApiResponse<MeetingNoteResponse>> update(
            @PathVariable Long noteId,
            @RequestBody MeetingNoteUpdateRequest request,
            @AuthenticationPrincipal UserDetails userDetails) {
        return ResponseEntity.ok(ApiResponse.ok("Đã cập nhật",
            meetingNoteService.updateNote(noteId, request, userDetails.getUsername())));
    }

    @PostMapping("/notes/{noteId}/action-items")
    public ResponseEntity<ApiResponse<ActionItemResponse>> addActionItem(
            @PathVariable Long noteId,
            @RequestBody ActionItemRequest request) {
        return ResponseEntity.ok(ApiResponse.ok("Đã thêm action item",
            meetingNoteService.addActionItem(noteId, request)));
    }

    @GetMapping("/notes/{noteId}/action-items")
    public ResponseEntity<ApiResponse<List<ActionItemResponse>>> getActionItems(@PathVariable Long noteId) {
        return ResponseEntity.ok(ApiResponse.ok(meetingNoteService.getActionItems(noteId)));
    }

    @PutMapping("/action-items/{itemId}")
    public ResponseEntity<ApiResponse<ActionItemResponse>> updateActionItem(
            @PathVariable Long itemId,
            @RequestBody ActionItemRequest request) {
        return ResponseEntity.ok(ApiResponse.ok("Đã cập nhật action item",
            meetingNoteService.updateActionItem(itemId, request)));
    }
}
