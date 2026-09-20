import Link from "next/link";
import { FileAudio } from "lucide-react";
import { listMeetings } from "../../lib/api";

export default async function MeetingsPage() {
  const meetings = await listMeetings().catch(() => []);
  return (
    <main className="shell">
      <header className="topbar">
        <div className="title">
          <h1>Meeting Summaries</h1>
          <p>Audio-only recordings, transcripts, decisions, and action items.</p>
        </div>
        <Link href="/">Overview</Link>
      </header>
      {meetings.length ? meetings.map((meeting) => (
        <Link className="card" href={`/meetings/${meeting.meetingId}`} key={meeting.meetingId}>
          <strong><FileAudio size={16} /> {meeting.title}</strong>
          <p className="muted">{new Date(meeting.startedAt).toLocaleString()}</p>
          <p className="summary">{meeting.summary || "Summary is not ready yet."}</p>
        </Link>
      )) : <div className="panel empty">No meetings recorded yet.</div>}
    </main>
  );
}
