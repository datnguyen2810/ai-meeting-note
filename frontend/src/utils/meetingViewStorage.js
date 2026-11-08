// Lưu trên trình duyệt: cuộc họp đang xem ở màn hình phân người và lịch sử chat
// theo từng cuộc họp. Khóa có kèm tài khoản để hai người dùng chung trình duyệt
// không thấy lịch sử chat của nhau. Mọi truy cập bọc try/catch vì storage có thể
// bị chặn (chế độ ẩn danh, chính sách trình duyệt); khi đó chỉ mất tiện ích này.
import { getStoredUser } from "../services/api";

const MAX_CHAT_MESSAGES = 50;

function owner() {
  const user = getStoredUser();
  return user?.username || user?.id || "anon";
}

const currentKey = () => `speaker_view:${owner()}:current`;
const chatKey = (meetingId) => `speaker_view:${owner()}:chat:${meetingId}`;

export function getStoredMeetingId() {
  try {
    const raw = sessionStorage.getItem(currentKey());
    const id = raw ? Number(raw) : NaN;
    return Number.isFinite(id) ? id : null;
  } catch {
    return null;
  }
}

export function storeMeetingId(meetingId) {
  try {
    if (meetingId == null) sessionStorage.removeItem(currentKey());
    else sessionStorage.setItem(currentKey(), String(meetingId));
  } catch {
    // storage bị chặn: bỏ qua
  }
}

export function loadChat(meetingId) {
  try {
    const parsed = JSON.parse(localStorage.getItem(chatKey(meetingId)) || "null");
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function saveChat(meetingId, messages) {
  if (meetingId == null) return;
  try {
    localStorage.setItem(chatKey(meetingId), JSON.stringify(messages.slice(-MAX_CHAT_MESSAGES)));
  } catch {
    // đầy bộ nhớ hoặc bị chặn: bỏ qua
  }
}

export function appendChat(meetingId, message) {
  saveChat(meetingId, [...(loadChat(meetingId) || []), message]);
}

export function removeChat(meetingId) {
  try {
    localStorage.removeItem(chatKey(meetingId));
  } catch {
    // bỏ qua
  }
}
