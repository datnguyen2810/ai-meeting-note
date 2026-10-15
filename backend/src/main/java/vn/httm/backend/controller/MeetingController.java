package vn.httm.backend.controller;

import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.*;
import vn.httm.backend.dto.ApiResponse;
import vn.httm.backend.dto.meeting.MeetingRequest;
import vn.httm.backend.dto.meeting.MeetingResponse;
import vn.httm.backend.dto.meeting.ParticipantRequest;
import vn.httm.backend.dto.meeting.ParticipantResponse;
import vn.httm.backend.service.MeetingService;

import java.util.List;

@RestController
@RequestMapping("/api/meetings")
@RequiredArgsConstructor
public class MeetingController {

    private final MeetingService meetingService;

    @PostMapping
    public ResponseEntity<ApiResponse<MeetingResponse>> create(
            @Valid @RequestBody MeetingRequest request,
            @AuthenticationPrincipal UserDetails userDetails) {
        MeetingResponse response = meetingService.createMeeting(request, userDetails.getUsername());
        return ResponseEntity.ok(ApiResponse.ok("Đã tạo cuộc họp", response));
    }

    @GetMapping
    public ResponseEntity<ApiResponse<List<MeetingResponse>>> getMyMeetings(
            @AuthenticationPrincipal UserDetails userDetails) {
        List<MeetingResponse> list = meetingService.getAllMyMeetings(userDetails.getUsername());
        return ResponseEntity.ok(ApiResponse.ok(list));
    }

    @GetMapping("/{id}")
    public ResponseEntity<ApiResponse<MeetingResponse>> getById(@PathVariable Long id) {
        return ResponseEntity.ok(ApiResponse.ok(meetingService.getMeetingById(id)));
    }

    @PutMapping("/{id}")
    public ResponseEntity<ApiResponse<MeetingResponse>> update(
            @PathVariable Long id,
            @RequestBody MeetingRequest request,
            @AuthenticationPrincipal UserDetails userDetails) {
        return ResponseEntity.ok(ApiResponse.ok("Đã cập nhật",
            meetingService.updateMeeting(id, request, userDetails.getUsername())));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<ApiResponse<Void>> delete(
            @PathVariable Long id,
            @AuthenticationPrincipal UserDetails userDetails) {
        meetingService.deleteMeeting(id, userDetails.getUsername());
        return ResponseEntity.ok(ApiResponse.ok("Đã xóa cuộc họp", null));
    }

    @PostMapping("/{id}/participants")
    public ResponseEntity<ApiResponse<ParticipantResponse>> addParticipant(
            @PathVariable Long id,
            @Valid @RequestBody ParticipantRequest request,
            @AuthenticationPrincipal UserDetails userDetails) {
        return ResponseEntity.ok(ApiResponse.ok("Đã thêm thành viên",
            meetingService.addParticipant(id, request, userDetails.getUsername())));
    }

    @GetMapping("/{id}/participants")
    public ResponseEntity<ApiResponse<List<ParticipantResponse>>> getParticipants(@PathVariable Long id) {
        return ResponseEntity.ok(ApiResponse.ok(meetingService.getParticipants(id)));
    }
}
