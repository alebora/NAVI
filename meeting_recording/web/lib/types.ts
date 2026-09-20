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
  lastHeartbeatAt: string;
};
