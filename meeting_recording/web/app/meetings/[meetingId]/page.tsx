import Link from "next/link";
import { getMeeting } from "../../../lib/api";

export default async function MeetingPage({ params }: { params: Promise<{ meetingId: string }> }) {
  const { meetingId } = await params;
  const meeting = await getMeeting(meetingId);

  return (
    <main className="shell">
      <header className="topbar">
        <div className="title">
          <h1>{meeting.title}</h1>
          <p>{meeting.status} · {meeting.recordingType}</p>
        </div>
        <Link href="/">Back</Link>
      </header>

      <section className="grid">
        <aside className="panel">
          <h2>Details</h2>
          <p className="muted">Robot: {meeting.robotId}</p>
          <p className="muted">Started: {new Date(meeting.startedAt).toLocaleString()}</p>
          {meeting.endedAt ? <p className="muted">Ended: {new Date(meeting.endedAt).toLocaleString()}</p> : null}
          {meeting.durationSeconds ? <p className="muted">Duration: {Math.round(meeting.durationSeconds)}s</p> : null}
        </aside>

        <section className="panel">
          <h2>Summary</h2>
          <p className="summary">{meeting.summary || "Summary is not ready yet."}</p>

          <h2>Decisions</h2>
          {meeting.decisions.length ? (
            <ul>{meeting.decisions.map((item) => <li key={item}>{item}</li>)}</ul>
          ) : (
            <p className="muted">No decisions detected.</p>
          )}

          <h2>Action Items</h2>
          {meeting.actionItems.length ? (
            <ul>
              {meeting.actionItems.map((item) => (
                <li key={item.task}>{item.task}{item.owner ? ` — ${item.owner}` : ""}</li>
              ))}
            </ul>
          ) : (
            <p className="muted">No action items detected.</p>
          )}

          <h2>Transcript Preview</h2>
          <p className="summary">{meeting.transcript || "Transcript unavailable."}</p>
        </section>
      </section>
    </main>
  );
}
