package vn.httm.backend.controller;

import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import vn.httm.backend.dto.ApiResponse;
import vn.httm.backend.dto.transcript.TranscriptResponse;
import vn.httm.backend.service.SttService;

@RestController
@RequestMapping("/api")
@RequiredArgsConstructor
public class TranscriptController {

    private final SttService sttService;

    @PostMapping("/audio/{audioId}/transcribe")
    public ResponseEntity<ApiResponse<TranscriptResponse>> transcribe(@PathVariable Long audioId) {
        TranscriptResponse response = sttService.transcribe(audioId);
        return ResponseEntity.ok(ApiResponse.ok("STT hoàn thành", response));
    }

    @GetMapping("/audio/{audioId}/transcript")
    public ResponseEntity<ApiResponse<TranscriptResponse>> getTranscript(@PathVariable Long audioId) {
        return ResponseEntity.ok(ApiResponse.ok(sttService.getTranscript(audioId)));
    }

    @GetMapping("/transcripts/{transcriptId}")
    public ResponseEntity<ApiResponse<TranscriptResponse>> getById(@PathVariable Long transcriptId) {
        return ResponseEntity.ok(ApiResponse.ok(sttService.getTranscriptById(transcriptId)));
    }
}
