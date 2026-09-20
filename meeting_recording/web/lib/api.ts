import type { GuidanceSession, MeetingSummary, RobotStatus, SecurityEvent } from "./types";

const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8787";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function listMeetings() {
  const data = await getJson<{ meetings: MeetingSummary[] }>("/api/meetings");
  return data.meetings;
}

export async function getMeeting(meetingId: string) {
  const data = await getJson<{ meeting: MeetingSummary }>(`/api/meetings/${meetingId}`);
  return data.meeting;
}

export async function getRobotStatus() {
  const data = await getJson<{ status: RobotStatus }>("/api/robot/status");
  return data.status;
}

export async function listGuidanceSessions() {
  const data = await getJson<{ sessions: GuidanceSession[] }>("/api/guidance-sessions");
  return data.sessions;
}

export async function listSecurityEvents() {
  const data = await getJson<{ events: SecurityEvent[] }>("/api/security-events");
  return data.events;
}
