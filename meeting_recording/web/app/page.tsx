import Link from "next/link";
import { Activity, FileAudio, Radio } from "lucide-react";
import { getRobotStatus, listMeetings } from "../lib/api";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(new Date(value));
}

export default async function HomePage() {
  const [meetings, status] = await Promise.all([
    listMeetings().catch(() => []),
    getRobotStatus().catch(() => null),
  ]);
  const latest = meetings[0];

  return (
    <main className="shell">
      <header className="topbar">
        <div className="title">
          <h1>NAVI Meetings</h1>
          <p>Audio summaries recorded by the robot.</p>
        </div>
        <span className="status">
          <span className={`dot ${status?.meetingRecordingActive ? "recording" : ""}`} />
          {status?.meetingRecordingActive ? "Recording" : "Ready"}
        </span>
      </header>

      <section className="grid">
        <aside className="panel">
          <h2>Robot</h2>
          <p className="muted">{status?.robotId ?? "No backend connection"}</p>
          <p><Radio size={16} /> {status?.online ? "Online" : "Unknown"}</p>
          <p><Activity size={16} /> {status?.robotState ?? "Unavailable"}</p>
          <p className="muted">Face: {status?.faceState ?? "Unavailable"}</p>
        </aside>

        <section>
          <div className="panel">
            <h2>Latest Summary</h2>
            {latest ? (
              <>
                <h3>{latest.title}</h3>
                <p className="muted">{formatDate(latest.startedAt)} · {latest.status}</p>
                <p className="summary">{latest.summary ?? "Summary is not ready yet."}</p>
                <Link href={`/meetings/${latest.meetingId}`}>Open meeting</Link>
              </>
            ) : (
              <div className="empty">No meetings yet.</div>
            )}
          </div>

          <h2>All Meetings</h2>
          {meetings.map((meeting) => (
            <Link className="card" key={meeting.meetingId} href={`/meetings/${meeting.meetingId}`}>
              <strong><FileAudio size={16} /> {meeting.title}</strong>
              <p className="muted">{formatDate(meeting.startedAt)} · {meeting.status}</p>
            </Link>
          ))}
        </section>
      </section>
    </main>
  );
}
