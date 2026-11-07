package vn.httm.backend.service;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
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

    /**
     * Quy trinh nhan file, tao Job va xu ly qua AI Service.
     */
    public Map<String, Object> processMeetingAudio(
            String title,
            MultipartFile file,
            String username,
            String clientRequestId,
            Integer maxSpeakers
    ) throws IOException {
        User user = userRepository.findByUsername(username)
                .orElseGet(() -> userRepository.findAll().stream().findFirst()
                        .orElseGet(() -> userRepository.save(User.builder()
                                .username("admin")
                                .email("admin@example.com")
                                .passwordHash("$2a$10$e74O7vQ5pG61pU8b1h6q7eI0eU4/8c27I9H62I60j7Q1y6n8H5t2C")
                                .fullName("Admin")
                                .build())));

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

        String originalFilename = file.getOriginalFilename() != null ? file.getOriginalFilename() : "meeting.wav";
        String timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"));
        String storedFilename = timestamp + "_" + originalFilename;
        Path targetPath = uploadPath.resolve(storedFilename);

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
                    String.valueOf(job.getId())
            );

            // Luu ket qua vao DB
            saveAiResultToDatabase(meeting, audio, aiResult);

            job.setStatus(JobStatus.COMPLETED);
            job.setStage("COMPLETED");
            jobRepository.save(job);

            meeting.setStatus(MeetingStatus.COMPLETED);
            meeting.setEndTime(LocalDateTime.now());
            meetingRepository.save(meeting);

            Map<String, Object> response = new HashMap<>();
            response.put("meetingId", meeting.getId());
            response.put("jobId", job.getId());
            response.put("status", "completed");
            response.put("data", aiResult);
            return response;

        } catch (Exception e) {
            log.error("Loi xu ly AI cho meeting {}: {}", meeting.getId(), e.getMessage(), e);
            job.setStatus(JobStatus.FAILED);
            job.setErrorCode("AI_PROCESSING_ERROR");
            job.setSafeErrorMessage(e.getMessage());
            jobRepository.save(job);

            Map<String, Object> response = new HashMap<>();
            response.put("meetingId", meeting.getId());
            response.put("jobId", job.getId());
            response.put("status", "failed");
            response.put("error", e.getMessage());
            return response;
        }
    }

    @Transactional
    @SuppressWarnings("unchecked")
    public void saveAiResultToDatabase(Meeting meeting, AudioRecording audio, Map<String, Object> aiResult) {
        String fullTranscript = (String) aiResult.get("transcript");
        String summary = (String) aiResult.get("summary");

        // Luu Transcript
        Transcript transcript = Transcript.builder()
                .audioRecording(audio)
                .rawText(fullTranscript)
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

    public List<Map<String, Object>> getSpeakers(Long meetingId) {
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

    public List<Map<String, Object>> getSegments(Long meetingId, String speakerKey) {
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

    @SuppressWarnings("unchecked")
    public Map<String, Object> chatWithMeeting(Long meetingId, String question, String speakerKey) {
        List<Map<String, Object>> segments = getSegments(meetingId, speakerKey);
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
