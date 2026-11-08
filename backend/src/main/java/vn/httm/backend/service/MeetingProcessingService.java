package vn.httm.backend.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.web.multipart.MultipartFile;
import vn.httm.backend.client.AiServiceClient;
import vn.httm.backend.entity.*;
import vn.httm.backend.entity.enums.JobStatus;
import vn.httm.backend.entity.enums.MeetingStatus;
import vn.httm.backend.entity.enums.ParticipantRole;
import vn.httm.backend.entity.enums.ProcessingStatus;
import vn.httm.backend.repository.*;

import java.io.File;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.*;

@Slf4j
@Service
@RequiredArgsConstructor
public class MeetingProcessingService {

    @Value("${app.upload.audio-dir:./uploads/audio}")
    private String audioUploadDir;

    private final MeetingRepository meetingRepository;
    private final AudioRecordingRepository audioRecordingRepository;
    private final TranscriptRepository transcriptRepository;
    private final TranscriptSegmentRepository transcriptSegmentRepository;
    private final TranscriptSpeakerRepository transcriptSpeakerRepository;
    private final MeetingNoteRepository meetingNoteRepository;
    private final MeetingProcessingJobRepository jobRepository;
    private final UserRepository userRepository;
    private final MeetingParticipantRepository participantRepository;
    private final AiServiceClient aiServiceClient;
    private final MeetingService meetingService;
    private final PlatformTransactionManager transactionManager;

    /** Giới hạn số người nhập tay; phải khớp MAX_NUM_SPEAKERS bên ai-service/main.py. */
    private static final int MAX_NUM_SPEAKERS = 10;

    /**
     * Quy trinh nhan file, tao Job va xu ly qua AI Service.
     */
    public Map<String, Object> processMeetingAudio(
            String title,
            MultipartFile file,
            String username,
            String clientRequestId,
            Integer maxSpeakers,
            Integer numSpeakers
    ) throws IOException {
        // numSpeakers: số người chính xác do người dùng nhập; null = để AI tự đoán.
        // Kiểm tra trước khi tạo meeting/lưu file để không để lại bản ghi rác.
        if (numSpeakers != null && (numSpeakers < 1 || numSpeakers > MAX_NUM_SPEAKERS)) {
            throw new RuntimeException("Số người trong cuộc họp phải từ 1 đến " + MAX_NUM_SPEAKERS);
        }

        // Trước đây không thấy user thì lấy user đầu tiên hoặc tự tạo tài khoản "admin"
        // có mật khẩu viết cứng; endpoint đã yêu cầu đăng nhập nên chỉ cần báo lỗi.
        User user = userRepository.findByUsername(username)
                .orElseThrow(() -> new RuntimeException("Không tìm thấy người dùng: " + username));

        // 1. Kiem tra xem clientRequestId da co job chua
        if (clientRequestId != null && !clientRequestId.isBlank()) {
            Optional<MeetingProcessingJob> existingJob = jobRepository.findByClientRequestId(clientRequestId);
            if (existingJob.isPresent()) {
                MeetingProcessingJob j = existingJob.get();
                Map<String, Object> res = new HashMap<>();
                res.put("meetingId", j.getMeeting().getId());
                res.put("jobId", j.getId());
                res.put("status", j.getStatus().name().toLowerCase());
                return res;
            }
        }

        // 2. Tao meeting moi
        String meetingTitle = (title != null && !title.isBlank())
                ? title
                : "Cuộc họp " + LocalDateTime.now().format(DateTimeFormatter.ofPattern("dd/MM/yyyy HH:mm"));

        Meeting meeting = Meeting.builder()
                .title(meetingTitle)
                .organizer(user)
                .status(MeetingStatus.IN_PROGRESS)
                .startTime(LocalDateTime.now())
                .build();
        meeting = meetingRepository.save(meeting);

        // Tao participant HOST
        MeetingParticipant host = MeetingParticipant.builder()
                .meeting(meeting)
                .user(user)
                .role(ParticipantRole.HOST)
                .build();
        participantRepository.save(host);

        // 3. Luu file audio vao disk
        Path uploadPath = Paths.get(audioUploadDir, String.valueOf(meeting.getId())).toAbsolutePath();
        Files.createDirectories(uploadPath);

        // Tên gốc do client gửi có thể chứa "../"; làm sạch trước khi ghép đường dẫn
        String originalFilename = UploadFileNames.sanitize(file.getOriginalFilename(), "meeting.wav");
        Path targetPath = UploadFileNames.storedPath(uploadPath, originalFilename, "meeting.wav");
        String storedFilename = targetPath.getFileName().toString();

        Files.copy(file.getInputStream(), targetPath, java.nio.file.StandardCopyOption.REPLACE_EXISTING);

        AudioRecording audio = AudioRecording.builder()
                .meeting(meeting)
                .filePath(targetPath.toString())
                .originalFilename(originalFilename)
                .fileSizeBytes(file.getSize())
                .status(ProcessingStatus.PROCESSING)
                .storageNode("local-node")
                .storageKey(meeting.getId() + "/" + storedFilename)
                .build();
        audio = audioRecordingRepository.save(audio);

        // 4. Tao MeetingProcessingJob
        MeetingProcessingJob job = MeetingProcessingJob.builder()
                .meeting(meeting)
                .audioRecording(audio)
                .requestedBy(user)
                .clientRequestId(clientRequestId)
                .status(JobStatus.PROCESSING)
                .stage("ASR_DIARIZATION")
                .ownerInstanceId("local-node")
                .build();
        job = jobRepository.save(job);

        // 5. Goi AI Service (dong bo hoac background, o M1 xu ly ngay de tra ve ket qua)
        try {
            int speakersLimit = (maxSpeakers != null && maxSpeakers > 0) ? maxSpeakers : 4;
            Map<String, Object> aiResult = aiServiceClient.processMeetingAudio(
                    audio.getFilePath(),
                    speakersLimit,
                    numSpeakers,
                    String.valueOf(job.getId())
            );

            // Lưu kết quả trong một transaction thật: lỗi giữa chừng thì không để lại
            // transcript/người nói/đoạn dở dang. (@Transactional trên hàm gọi bằng
            // this không có tác dụng vì đi vòng qua proxy của Spring.)
            final Meeting savedMeeting = meeting;
            final AudioRecording savedAudio = audio;
            final MeetingProcessingJob savedJob = job;
            transactionTemplate().executeWithoutResult(status -> {
                saveAiResultToDatabase(savedMeeting, savedAudio, aiResult);

                savedJob.setStatus(JobStatus.COMPLETED);
                savedJob.setStage("COMPLETED");
                jobRepository.save(savedJob);

                savedMeeting.setStatus(MeetingStatus.COMPLETED);
                savedMeeting.setEndTime(LocalDateTime.now());
                meetingRepository.save(savedMeeting);
            });

            Map<String, Object> response = new HashMap<>();
            response.put("meetingId", meeting.getId());
            response.put("jobId", job.getId());
            response.put("status", "completed");
            response.put("data", aiResult);
            return response;

        } catch (Exception e) {
            log.error("Loi xu ly AI cho meeting {}: {}", meeting.getId(), e.getMessage(), e);
            job.setStatus(JobStatus.FAILED);
            job.setStage("FAILED");
            job.setErrorCode("AI_PROCESSING_ERROR");
            job.setSafeErrorMessage(truncate(e.getMessage(), 500));
            jobRepository.save(job);

            // Không để cuộc họp lỗi treo ở IN_PROGRESS trong lịch sử. MeetingStatus chưa
            // có FAILED và thêm giá trị sẽ đổi schema DB chung, nên xóa mềm cuộc họp
            // (job FAILED vẫn giữ để tra lỗi) và xóa file audio đã lưu.
            audio.setStatus(ProcessingStatus.FAILED);
            audioRecordingRepository.save(audio);
            meeting.setDeletedAt(LocalDateTime.now());
            meetingRepository.save(meeting);
            try {
                Files.deleteIfExists(targetPath);
            } catch (IOException ioe) {
                log.warn("Khong xoa duoc file audio loi {}: {}", targetPath, ioe.getMessage());
            }

            Map<String, Object> response = new HashMap<>();
            response.put("meetingId", meeting.getId());
            response.put("jobId", job.getId());
            response.put("status", "failed");
            response.put("error", e.getMessage());
            return response;
        }
    }

    private TransactionTemplate transactionTemplate() {
        return new TransactionTemplate(transactionManager);
    }

    private static String truncate(String value, int max) {
        if (value == null) return null;
        return value.length() > max ? value.substring(0, max) : value;
    }

    /** Chỉ gọi bên trong transaction (xem processMeetingAudio). */
    @SuppressWarnings("unchecked")
    void saveAiResultToDatabase(Meeting meeting, AudioRecording audio, Map<String, Object> aiResult) {
        String fullTranscript = (String) aiResult.get("transcript");
        String summary = (String) aiResult.get("summary");

        // Luu Transcript
        Transcript transcript = Transcript.builder()
                .audioRecording(audio)
                .rawText(fullTranscript)
                .sttModelUsed(encodeModels(aiResult.get("models")))
                .status(ProcessingStatus.DONE)
                .build();
        transcript = transcriptRepository.save(transcript);

        // Luu Speakers
        List<Map<String, Object>> speakers = (List<Map<String, Object>>) aiResult.get("speakers");
        if (speakers != null) {
            for (Map<String, Object> spk : speakers) {
                TranscriptSpeaker s = TranscriptSpeaker.builder()
                        .transcript(transcript)
                        .speakerKey((String) spk.get("speaker_id"))
                        .label((String) spk.get("label"))
                        .firstStartSeconds(spk.get("first_start_seconds") != null ? Double.valueOf(spk.get("first_start_seconds").toString()) : 0.0)
                        .build();
                transcriptSpeakerRepository.save(s);
            }
        }

        // Luu Segments
        List<Map<String, Object>> segments = (List<Map<String, Object>>) aiResult.get("segments");
        if (segments != null) {
            int seq = 1;
            for (Map<String, Object> seg : segments) {
                TranscriptSegment ts = TranscriptSegment.builder()
                        .transcript(transcript)
                        .sequenceOrder(seq++)
                        .speakerKey((String) seg.get("speaker_id"))
                        .speakerLabel((String) seg.get("speaker_label"))
                        .startTimeSec(seg.get("start_seconds") != null ? Double.valueOf(seg.get("start_seconds").toString()) : 0.0)
                        .endTimeSec(seg.get("end_seconds") != null ? Double.valueOf(seg.get("end_seconds").toString()) : 0.0)
                        .textSegment((String) seg.get("text"))
                        .attributionStatus((String) seg.get("attribution_status"))
                        .build();
                transcriptSegmentRepository.save(ts);
            }
        }

        // Luu MeetingNote
        if (summary != null && !summary.isBlank()) {
            MeetingNote note = MeetingNote.builder()
                    .meeting(meeting)
                    .transcript(transcript)
                    .summaryText(summary)
                    .status(ProcessingStatus.DONE)
                    .build();
            meetingNoteRepository.save(note);
        }

        audio.setStatus(ProcessingStatus.DONE);
        audioRecordingRepository.save(audio);
    }

    /** Người dùng phải là người tổ chức hoặc thành viên của cuộc họp. */
    private void requireAccess(Long meetingId, String username) {
        meetingService.findAccessibleMeeting(meetingId, username);
    }

    /**
     * File audio mới nhất của cuộc họp để phát lại, hoặc null nếu file không có trên máy
     * này (audio lưu ở đĩa máy đã nhận upload, trong khi DB dùng chung cả nhóm).
     */
    public Path getLatestAudioFile(Long meetingId, String username) {
        requireAccess(meetingId, username);
        List<AudioRecording> audios = audioRecordingRepository.findByMeetingId(meetingId);
        for (int i = audios.size() - 1; i >= 0; i--) {
            String stored = audios.get(i).getFilePath();
            if (stored == null) continue;
            Path path = Paths.get(stored).toAbsolutePath().normalize();
            if (Files.isRegularFile(path)) return path;
        }
        return null;
    }

    public List<Map<String, Object>> getSpeakers(Long meetingId, String username) {
        requireAccess(meetingId, username);
        Transcript transcript = getTranscriptByMeetingId(meetingId);
        if (transcript == null) return Collections.emptyList();

        List<TranscriptSpeaker> list = transcriptSpeakerRepository.findByTranscriptId(transcript.getId());
        List<Map<String, Object>> res = new ArrayList<>();
        for (TranscriptSpeaker s : list) {
            Map<String, Object> m = new HashMap<>();
            m.put("speakerId", s.getSpeakerKey());
            m.put("label", s.getLabel());
            m.put("firstStartSeconds", s.getFirstStartSeconds());
            res.add(m);
        }
        return res;
    }

    public List<Map<String, Object>> getSegments(Long meetingId, String speakerKey, String username) {
        requireAccess(meetingId, username);
        return loadSegments(meetingId, speakerKey);
    }

    private List<Map<String, Object>> loadSegments(Long meetingId, String speakerKey) {
        Transcript transcript = getTranscriptByMeetingId(meetingId);
        if (transcript == null) return Collections.emptyList();

        List<TranscriptSegment> list = transcriptSegmentRepository.findByTranscriptIdOrderBySequenceOrderAsc(transcript.getId());
        List<Map<String, Object>> res = new ArrayList<>();
        for (TranscriptSegment s : list) {
            if (speakerKey != null && !speakerKey.isBlank() && !speakerKey.equalsIgnoreCase(s.getSpeakerKey())) {
                continue;
            }
            Map<String, Object> m = new HashMap<>();
            m.put("segmentId", "seg_" + String.format("%04d", s.getSequenceOrder()));
            m.put("speakerId", s.getSpeakerKey());
            m.put("speakerLabel", s.getSpeakerLabel());
            m.put("startSeconds", s.getStartTimeSec());
            m.put("endSeconds", s.getEndTimeSec());
            m.put("text", s.getTextSegment());
            m.put("attributionStatus", s.getAttributionStatus());
            res.add(m);
        }
        return res;
    }

    /**
     * Thông tin xử lý của cuộc họp: trạng thái job và model đã dùng. Giao diện dùng
     * để hiển thị đúng bộ phân người (pyannote hay bộ dự phòng) khi mở lại từ lịch sử.
     */
    public Map<String, Object> getProcessingInfo(Long meetingId, String username) {
        requireAccess(meetingId, username);
        Map<String, Object> res = new HashMap<>();
        jobRepository.findTopByMeetingIdOrderByIdDesc(meetingId).ifPresent(job -> {
            res.put("status", job.getStatus().name().toLowerCase());
            res.put("stage", job.getStage());
            res.put("errorMessage", job.getSafeErrorMessage());
        });
        Transcript transcript = getTranscriptByMeetingId(meetingId);
        Map<String, String> models = decodeModels(transcript != null ? transcript.getSttModelUsed() : null);
        res.put("diarizationEngine", models.get("diarization"));
        res.put("asrModel", models.get("asr"));
        return res;
    }

    // Lưu model đã dùng vào cột stt_model_used sẵn có (tránh đổi schema DB chung):
    // "asr=vinai/PhoWhisper-small;diarization=acoustic-pitch-mfcc"
    private static String encodeModels(Object models) {
        if (!(models instanceof Map<?, ?> map)) return null;
        String value = "asr=" + map.get("asr") + ";diarization=" + map.get("diarization");
        return value.length() > 100 ? value.substring(0, 100) : value;
    }

    private static Map<String, String> decodeModels(String stored) {
        Map<String, String> res = new HashMap<>();
        if (stored == null || !stored.contains("=")) {
            // Bản ghi cũ chỉ có tên ASR, không biết bộ phân người
            if (stored != null && !stored.isBlank()) res.put("asr", stored);
            return res;
        }
        for (String part : stored.split(";")) {
            int eq = part.indexOf('=');
            if (eq > 0) res.put(part.substring(0, eq).trim(), part.substring(eq + 1).trim());
        }
        return res;
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> chatWithMeeting(Long meetingId, String question, String speakerKey, String username) {
        requireAccess(meetingId, username);
        if (question == null || question.isBlank()) {
            throw new RuntimeException("Câu hỏi không được để trống");
        }
        // Gửi mọi đoạn, kèm speakerKey của bộ lọc; Python tự lọc. Nếu câu hỏi nhắc
        // "người 3" thì Python trả lời theo Người 3 dù bộ lọc đang chọn người khác.
        List<Map<String, Object>> segments = loadSegments(meetingId, null);
        if (segments.isEmpty()) {
            Map<String, Object> emptyRes = new HashMap<>();
            emptyRes.put("answer", "Cuộc họp chưa có dữ liệu phiên âm để trả lời.");
            emptyRes.put("citations", Collections.emptyList());
            emptyRes.put("insufficientEvidence", true);
            return emptyRes;
        }

        // Chuan bi payload gui qua Python
        List<Map<String, Object>> pySegments = new ArrayList<>();
        for (Map<String, Object> s : segments) {
            Map<String, Object> item = new HashMap<>();
            item.put("segment_id", s.get("segmentId"));
            item.put("speaker_id", s.get("speakerId"));
            item.put("speaker_label", s.get("speakerLabel"));
            item.put("start_seconds", s.get("startSeconds"));
            item.put("end_seconds", s.get("endSeconds"));
            item.put("text", s.get("text"));
            pySegments.add(item);
        }

        Map<String, Object> pyRes = aiServiceClient.meetingChat(question, pySegments, speakerKey);
        Map<String, Object> res = new HashMap<>();
        res.put("answer", pyRes.get("answer"));
        res.put("insufficientEvidence", pyRes.get("insufficient_evidence"));

        List<Map<String, Object>> rawCitations = (List<Map<String, Object>>) pyRes.get("citations");
        List<Map<String, Object>> citations = new ArrayList<>();
        if (rawCitations != null) {
            for (Map<String, Object> rc : rawCitations) {
                Map<String, Object> c = new HashMap<>();
                c.put("segmentId", rc.get("segment_id"));
                c.put("speakerId", rc.get("speaker_id"));
                c.put("speakerLabel", rc.get("speaker_label"));
                c.put("startSeconds", rc.get("start_seconds"));
                c.put("endSeconds", rc.get("end_seconds"));
                c.put("quote", rc.get("quote"));
                citations.add(c);
            }
        }
        res.put("citations", citations);
        return res;
    }

    private Transcript getTranscriptByMeetingId(Long meetingId) {
        List<AudioRecording> audios = audioRecordingRepository.findByMeetingId(meetingId);
        if (audios.isEmpty()) return null;
        AudioRecording latest = audios.get(audios.size() - 1);
        return latest.getTranscript();
    }
}
