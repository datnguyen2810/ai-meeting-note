package vn.httm.backend.controller;

import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import vn.httm.backend.dto.ApiResponse;
import vn.httm.backend.dto.audio.AudioRecordingResponse;
import vn.httm.backend.service.AudioService;

import java.io.IOException;
import java.util.List;

@RestController
@RequestMapping("/api/meetings")
@RequiredArgsConstructor
public class AudioController {

    private final AudioService audioService;

    @PostMapping("/{meetingId}/audio")
    public ResponseEntity<ApiResponse<AudioRecordingResponse>> upload(
            @PathVariable Long meetingId,
            @RequestParam("file") MultipartFile file) throws IOException {
        AudioRecordingResponse response = audioService.uploadAudio(meetingId, file);
        return ResponseEntity.ok(ApiResponse.ok("Đã upload file audio", response));
    }


    @GetMapping("/{meetingId}/audio")
    public ResponseEntity<ApiResponse<List<AudioRecordingResponse>>> getByMeeting(
            @PathVariable Long meetingId) {
        return ResponseEntity.ok(ApiResponse.ok(audioService.getByMeeting(meetingId)));
    }


    @GetMapping("/audio/{audioId}")
    public ResponseEntity<ApiResponse<AudioRecordingResponse>> getById(
            @PathVariable Long audioId) {
        return ResponseEntity.ok(ApiResponse.ok(audioService.getById(audioId)));
    }
}
