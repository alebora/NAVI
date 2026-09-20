export type MeetingSummary = {
  meetingId: string;
  robotId: string;
  title: string;
  startedAt: string;
  endedAt?: string;
  durationSeconds?: number;
  status: "recording" | "processing" | "ready" | "failed";
  recordingType: "audio_only";
  summary?: string;
  transcript?: string;
  decisions: string[];
  actionItems: {
    task: string;
    owner?: string | null;
    due?: string | null;
    done?: boolean;
  }[];
};

export type RobotStatus = {
  robotId: string;
  online: boolean;
  robotState: string;
  faceState: string;
  meetingRecordingActive: boolean;
  currentDestinationName?: string;
  batteryPercent?: number;
  lastHeartbeatAt: string;
};

export type GuidanceSession = {
  sessionId: string;
  robotId: string;
  cardId?: string;
  displayName?: string;
  requestedDestinationText: string;
  matchedDestinationName?: string;
  clearanceDecision: "allowed" | "denied" | "unknown";
  denialReason?: string;
  startedAt: string;
  endedAt?: string;
  finalState: "arrived" | "denied" | "cancelled" | "failed" | "in_progress";
  routeSummary?: string;
};

export type SecurityEvent = {
  eventId: string;
  robotId: string;
  type: string;
  severity: "info" | "warning" | "critical";
  status: "open" | "acknowledged" | "resolved" | "dismissed";
  title: string;
  description: string;
  createdAt: string;
  locationLabel?: string;
  relatedCardId?: string;
  relatedSessionId?: string;
};
