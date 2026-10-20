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

    @PostMapping(value = "/save-session", consumes = org.springframework.http.MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<ApiResponse<MeetingResponse>> saveSession(
            @RequestParam(value = "title", required = false) String title,
            @RequestParam(value = "description", required = false) String description,
            @RequestParam(value = "transcript", required = false) String transcript,
            @RequestParam(value = "summary", required = false) String summary,
            @RequestParam(value = "durationSeconds", required = false) Integer durationSeconds,
            @RequestParam(value = "file", required = false) org.springframework.web.multipart.MultipartFile file,
            @AuthenticationPrincipal UserDetails userDetails) throws java.io.IOException {
        MeetingResponse response = meetingService.saveMeetingSession(
                title, description, transcript, summary, durationSeconds, file, userDetails.getUsername());
        return ResponseEntity.ok(ApiResponse.ok("Đã lưu lịch sử cuộc họp thành công", response));
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
