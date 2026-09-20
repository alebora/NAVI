import Link from "next/link";
import { Activity, AlertTriangle, FileAudio, MapPinned, Radio } from "lucide-react";
import { getRobotStatus, listGuidanceSessions, listMeetings, listSecurityEvents } from "../lib/api";

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
  const [sessions, events] = await Promise.all([
    listGuidanceSessions().catch(() => []),
    listSecurityEvents().catch(() => []),
  ]);
  const latest = meetings[0];
  const openEvents = events.filter((event) => event.status === "open");

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

      <nav className="nav">
        <Link href="/">Overview</Link>
        <Link href="/meetings">Meetings</Link>
        <Link href="/guidance">Guidance</Link>
        <Link href="/security">Security</Link>
      </nav>

      <section className="kpis">
        <div className="kpi"><span>Meetings</span><strong>{meetings.length}</strong></div>
        <div className="kpi"><span>Guidance sessions</span><strong>{sessions.length}</strong></div>
        <div className="kpi"><span>Open security events</span><strong>{openEvents.length}</strong></div>
      </section>

      <section className="grid">
        <aside className="panel">
          <h2>Robot</h2>
          <p className="muted">{status?.robotId ?? "No backend connection"}</p>
          <p className="row-title"><Radio size={16} /> {status?.online ? "Online" : "Unknown"}</p>
          <p className="row-title"><Activity size={16} /> {status?.robotState ?? "Unavailable"}</p>
          <p className="muted">Face: {status?.faceState ?? "Unavailable"}</p>
          {status?.currentDestinationName ? <p className="muted">Destination: {status.currentDestinationName}</p> : null}
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

          <div className="list-header">
            <h2>Recent Meetings</h2>
            <Link href="/meetings">View all</Link>
          </div>
          {meetings.map((meeting) => (
            <Link className="card" key={meeting.meetingId} href={`/meetings/${meeting.meetingId}`}>
              <strong><FileAudio size={16} /> {meeting.title}</strong>
              <div className="meta-line">
                <span className="tag">{formatDate(meeting.startedAt)}</span>
                <span className={`tag ${meeting.status === "failed" ? "red" : meeting.status === "ready" ? "green" : "amber"}`}>{meeting.status}</span>
              </div>
            </Link>
          ))}

          <div className="list-header">
            <h2>Operations</h2>
          </div>
          <Link className="card" href="/guidance">
            <strong><MapPinned size={16} /> Guidance logs</strong>
            <p className="muted">Recent destinations, badge decisions, and route outcomes.</p>
          </Link>
          <Link className="card" href="/security">
            <strong><AlertTriangle size={16} /> Security events</strong>
            <p className="muted">Access denials, unknown cards, robot errors, and review items.</p>
          </Link>
        </section>
      </section>
    </main>
  );
}
