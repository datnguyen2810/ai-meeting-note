package vn.httm.backend.client;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.*;
import org.springframework.stereotype.Component;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.HttpStatusCodeException;
import org.springframework.web.client.RestTemplate;

import java.io.File;
import java.util.Map;

/**
 * HTTP client gọi sang AI Service (FastAPI Python) để thực hiện STT.
 */
@Slf4j
@Component
@RequiredArgsConstructor
public class AiServiceClient {

    @Value("${app.ai-service.base-url}")
    private String baseUrl;

    @Value("${app.ai-service.transcribe-endpoint}")
    private String transcribeEndpoint;

    private final RestTemplate restTemplate;

    /**
     * Gọi POST /api/transcribe trên Python AI service với file audio.
     * @param filePath đường dẫn tuyệt đối đến file audio trên disk
     * @return raw transcript text
     */
    @SuppressWarnings("unchecked")
    public String transcribeAudio(String filePath) {
        File audioFile = new File(filePath);
        if (!audioFile.exists()) {
            throw new RuntimeException("File không tồn tại: " + filePath);
        }

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("file", new FileSystemResource(audioFile));

        HttpEntity<MultiValueMap<String, Object>> request = new HttpEntity<>(body, headers);
        String url = baseUrl + transcribeEndpoint;

        log.info("Gọi AI service STT: {} — file: {}", url, audioFile.getName());

        ResponseEntity<Map> response = restTemplate.postForEntity(url, request, Map.class);

        if (response.getStatusCode().is2xxSuccessful() && response.getBody() != null) {
            Map<String, Object> result = response.getBody();
            String transcript = (String) result.get("transcript");
            log.info("STT hoàn thành, độ dài text: {} ký tự", transcript != null ? transcript.length() : 0);
            return transcript;
        }

        throw new RuntimeException("AI service trả về lỗi: " + response.getStatusCode());
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> processMeetingAudio(String filePath, int maxSpeakers, Integer numSpeakers, String jobId) {
        File audioFile = new File(filePath);
        if (!audioFile.exists()) {
            throw new RuntimeException("File không tồn tại: " + filePath);
        }

        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("file", new FileSystemResource(audioFile));

        HttpEntity<MultiValueMap<String, Object>> request = new HttpEntity<>(body, headers);
        String url = baseUrl + "/api/process-meeting?max_speakers=" + maxSpeakers
                + (numSpeakers != null ? "&num_speakers=" + numSpeakers : "")
                + (jobId != null ? "&job_id=" + jobId : "");

        log.info("Gọi AI process-meeting: {} — file: {}", url, audioFile.getName());
        ResponseEntity<Map> response;
        try {
            response = restTemplate.postForEntity(url, request, Map.class);
        } catch (HttpStatusCodeException e) {
            // FastAPI trả lỗi dạng {"detail": "..."}; chuyển thông báo đó cho người dùng
            // thay vì chuỗi lỗi HTTP thô.
            throw new RuntimeException(extractDetail(e), e);
        }

        if (response.getStatusCode().is2xxSuccessful() && response.getBody() != null) {
            return response.getBody();
        }

        throw new RuntimeException("AI service process-meeting trả về lỗi: " + response.getStatusCode());
    }

    private static String extractDetail(HttpStatusCodeException e) {
        try {
            Map<?, ?> body = e.getResponseBodyAs(Map.class);
            if (body != null && body.get("detail") instanceof String detail && !detail.isBlank()) {
                return detail;
            }
        } catch (RuntimeException ignored) {
            // Thân lỗi không phải JSON: dùng thông báo mặc định bên dưới
        }
        return "AI service trả về lỗi " + e.getStatusCode().value();
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> meetingChat(String question, Object segments, String speakerId) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.APPLICATION_JSON);

        Map<String, Object> body = new java.util.HashMap<>();
        body.put("question", question);
        body.put("segments", segments);
        if (speakerId != null) {
            body.put("speaker_id", speakerId);
        }

        HttpEntity<Map<String, Object>> request = new HttpEntity<>(body, headers);
        String url = baseUrl + "/api/meeting-chat";

        log.info("Gọi AI meeting-chat: {} — question: {}", url, question);
        ResponseEntity<Map> response = restTemplate.postForEntity(url, request, Map.class);

        if (response.getStatusCode().is2xxSuccessful() && response.getBody() != null) {
            return response.getBody();
        }

        throw new RuntimeException("AI service meeting-chat trả về lỗi: " + response.getStatusCode());
    }
}
