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
    private final vn.httm.backend.service.MeetingProcessingService meetingProcessingService;

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
    public ResponseEntity<ApiResponse<MeetingResponse>> getById(
            @PathVariable Long id,
            @AuthenticationPrincipal UserDetails userDetails) {
        return ResponseEntity.ok(ApiResponse.ok(meetingService.getMeetingById(id, userDetails.getUsername())));
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
    public ResponseEntity<ApiResponse<List<ParticipantResponse>>> getParticipants(
            @PathVariable Long id,
            @AuthenticationPrincipal UserDetails userDetails) {
        return ResponseEntity.ok(ApiResponse.ok(meetingService.getParticipants(id, userDetails.getUsername())));
    }

    // ==========================================
    // API M1: Xu ly cuoc hop voi Speaker Diarization
    // ==========================================
    @PostMapping(value = "/process-audio", consumes = org.springframework.http.MediaType.MULTIPART_FORM_DATA_VALUE)
    public ResponseEntity<ApiResponse<java.util.Map<String, Object>>> processAudio(
            @RequestParam("file") org.springframework.web.multipart.MultipartFile file,
            @RequestParam(value = "title", required = false) String title,
            @RequestParam(value = "clientRequestId", required = false) String clientRequestId,
            @RequestParam(value = "maxSpeakers", required = false) Integer maxSpeakers,
            @RequestParam(value = "numSpeakers", required = false) Integer numSpeakers,
            @AuthenticationPrincipal UserDetails userDetails) throws java.io.IOException {
        java.util.Map<String, Object> result = meetingProcessingService.processMeetingAudio(
                title, file, userDetails.getUsername(), clientRequestId, maxSpeakers, numSpeakers);
        return ResponseEntity.ok(ApiResponse.ok("Xử lý cuộc họp thành công", result));
    }

    @GetMapping("/{id}/processing")
    public ResponseEntity<ApiResponse<java.util.Map<String, Object>>> getProcessingInfo(
            @PathVariable Long id,
            @AuthenticationPrincipal UserDetails userDetails) {
        return ResponseEntity.ok(ApiResponse.ok(
                meetingProcessingService.getProcessingInfo(id, userDetails.getUsername())));
    }

    /**
     * Phát lại audio của cuộc họp (file mới nhất). Trả 404 khi file không có trên máy chạy
     * backend này: audio lưu trên đĩa máy đã nhận upload, còn DB dùng chung cả nhóm.
     */
    @GetMapping("/{id}/audio/content")
    public ResponseEntity<org.springframework.core.io.Resource> getAudioContent(
            @PathVariable Long id,
            @AuthenticationPrincipal UserDetails userDetails) {
        java.nio.file.Path path = meetingProcessingService.getLatestAudioFile(id, userDetails.getUsername());
        if (path == null) {
            return ResponseEntity.notFound().build();
        }
        String name = path.getFileName().toString().toLowerCase();
        String type = name.endsWith(".mp3") ? "audio/mpeg"
                : name.endsWith(".flac") ? "audio/flac"
                : name.endsWith(".ogg") ? "audio/ogg"
                : name.endsWith(".m4a") ? "audio/mp4"
                : name.endsWith(".webm") ? "audio/webm"
                : "audio/wav";
        return ResponseEntity.ok()
                .contentType(org.springframework.http.MediaType.parseMediaType(type))
                .body(new org.springframework.core.io.FileSystemResource(path));
    }

    @GetMapping("/{id}/speakers")
    public ResponseEntity<ApiResponse<List<java.util.Map<String, Object>>>> getSpeakers(
            @PathVariable Long id,
            @AuthenticationPrincipal UserDetails userDetails) {
        return ResponseEntity.ok(ApiResponse.ok(meetingProcessingService.getSpeakers(id, userDetails.getUsername())));
    }

    @GetMapping("/{id}/segments")
    public ResponseEntity<ApiResponse<List<java.util.Map<String, Object>>>> getSegments(
            @PathVariable Long id,
            @RequestParam(value = "speakerId", required = false) String speakerId,
            @AuthenticationPrincipal UserDetails userDetails) {
        return ResponseEntity.ok(ApiResponse.ok(
                meetingProcessingService.getSegments(id, speakerId, userDetails.getUsername())));
    }

    @PostMapping("/{id}/chat")
    public ResponseEntity<ApiResponse<java.util.Map<String, Object>>> chat(
            @PathVariable Long id,
            @RequestBody java.util.Map<String, String> body,
            @AuthenticationPrincipal UserDetails userDetails) {
        String question = body.get("question");
        String speakerId = body.get("speakerId");
        return ResponseEntity.ok(ApiResponse.ok(
                meetingProcessingService.chatWithMeeting(id, question, speakerId, userDetails.getUsername())));
    }
}
