// API client module for Spring Boot Backend

const API_BASE = "/api";

export function getStoredToken() {
  return localStorage.getItem("auth_token") || null;
}

export function getStoredUser() {
  const userStr = localStorage.getItem("auth_user");
  try {
    return userStr ? JSON.parse(userStr) : null;
  } catch {
    return null;
  }
}

export function saveAuthSession(token, user) {
  if (token) localStorage.setItem("auth_token", token);
  if (user) localStorage.setItem("auth_user", JSON.stringify(user));
}

export function clearAuthSession() {
  localStorage.removeItem("auth_token");
  localStorage.removeItem("auth_user");
}

async function request(endpoint, options = {}) {
  const headers = options.headers || {};
  const token = getStoredToken();

  if (token && !headers["Authorization"]) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  // If body is NOT FormData, set application/json
  if (options.body && !(options.body instanceof FormData) && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers,
  });

  // Handle unauthorized/forbidden
  if (response.status === 401 || response.status === 403) {
    if (token && endpoint !== "/auth/login" && endpoint !== "/auth/register") {
      clearAuthSession();
      window.dispatchEvent(new Event("auth_logout"));
    }
  }

  let data;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    const errorMsg = data?.message || data?.error || `HTTP ${response.status}: ${response.statusText}`;
    throw new Error(errorMsg);
  }

  return data;
}

export const api = {
  // Auth
  async login(username, password) {
    const res = await request("/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password }),
    });
    if (res?.data?.token) {
      saveAuthSession(res.data.token, res.data);
    }
    return res.data;
  },

  async register(username, email, password, fullName) {
    const res = await request("/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, email, password, fullName }),
    });
    if (res?.data?.token) {
      saveAuthSession(res.data.token, res.data);
    }
    return res.data;
  },

  logout() {
    clearAuthSession();
    window.dispatchEvent(new Event("auth_logout"));
  },

  // Meetings
  async getMeetings() {
    const res = await request("/meetings", { method: "GET" });
    return res.data || [];
  },

  async createMeeting(title, description = "") {
    const res = await request("/meetings", {
      method: "POST",
      body: JSON.stringify({ title, description }),
    });
    return res.data;
  },

  async getMeeting(id) {
    const res = await request(`/meetings/${id}`, { method: "GET" });
    return res.data;
  },

  // Save complete meeting session (audio, transcript, summary)
  async saveMeetingSession({ title, description, transcript, summary, durationSeconds, file }) {
    const formData = new FormData();
    if (title) formData.append("title", title);
    if (description) formData.append("description", description);
    if (transcript) formData.append("transcript", transcript);
    if (summary) formData.append("summary", summary);
    if (durationSeconds !== undefined && durationSeconds !== null) {
      formData.append("durationSeconds", durationSeconds);
    }
    if (file) formData.append("file", file);

    const res = await request("/meetings/save-session", {
      method: "POST",
      body: formData,
    });
    return res.data;
  },

  async deleteMeeting(id) {
    const res = await request(`/meetings/${id}`, {
      method: "DELETE",
    });
    return res.data;
  },

  // Audio Upload
  async uploadAudio(meetingId, file) {
    const formData = new FormData();
    formData.append("file", file);
    const res = await request(`/meetings/${meetingId}/audio`, {
      method: "POST",
      body: formData,
    });
    return res.data;
  },

  // Transcribe (STT)
  async transcribeAudio(audioId) {
    const res = await request(`/audio/${audioId}/transcribe`, {
      method: "POST",
    });
    return res.data;
  },

  // Meeting Notes (LLM Summary)
  async generateNote(transcriptId) {
    const res = await request(`/transcripts/${transcriptId}/notes`, {
      method: "POST",
    });
    return res.data;
  },

  async getMeetingNotes(meetingId) {
    const res = await request(`/meetings/${meetingId}/notes`, {
      method: "GET",
    });
    return res.data || [];
  },
};
