package vn.httm.backend.service;

import java.nio.file.Path;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

/**
 * Tên file lưu trên đĩa cho tệp người dùng tải lên.
 *
 * Tên gốc do client gửi có thể chứa đường dẫn ("../../x") hoặc ký tự lạ; ghép thẳng vào
 * Path sẽ ghi file ra ngoài thư mục upload. Chỉ giữ chữ, số, '.', '-', '_' và tối đa 100
 * ký tự; file luôn nằm trong thư mục đích.
 */
public final class UploadFileNames {

    private static final int MAX_NAME_LENGTH = 100;

    private UploadFileNames() {
    }

    /** Tên gốc đã làm sạch (bỏ thư mục, ký tự lạ); rỗng thì dùng {@code fallback}. */
    public static String sanitize(String originalFilename, String fallback) {
        String name = originalFilename == null ? "" : originalFilename;
        // Bỏ phần thư mục theo cả hai kiểu dấu phân cách
        int slash = Math.max(name.lastIndexOf('/'), name.lastIndexOf('\\'));
        name = name.substring(slash + 1);
        name = name.replaceAll("[^\\p{L}\\p{N}._-]", "_").replaceAll("^\\.+", "");
        if (name.length() > MAX_NAME_LENGTH) {
            name = name.substring(name.length() - MAX_NAME_LENGTH);
        }
        return name.isBlank() || name.chars().allMatch(c -> c == '_' || c == '.') ? fallback : name;
    }

    /** Đường dẫn file lưu trong {@code dir}: "yyyyMMdd_HHmmss_<tên đã làm sạch>". */
    public static Path storedPath(Path dir, String originalFilename, String fallback) {
        String timestamp = LocalDateTime.now().format(DateTimeFormatter.ofPattern("yyyyMMdd_HHmmss"));
        Path base = dir.toAbsolutePath().normalize();
        Path target = base.resolve(timestamp + "_" + sanitize(originalFilename, fallback)).normalize();
        if (!target.startsWith(base)) {
            throw new RuntimeException("Tên tệp không hợp lệ");
        }
        return target;
    }
}
