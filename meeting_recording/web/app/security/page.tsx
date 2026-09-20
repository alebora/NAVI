import Link from "next/link";
import { AlertTriangle } from "lucide-react";
import { listSecurityEvents } from "../../lib/api";

function severityClass(severity: string) {
  if (severity === "critical") return "tag red";
  if (severity === "warning") return "tag amber";
  return "tag";
}

export default async function SecurityPage() {
  const events = await listSecurityEvents().catch(() => []);
  return (
    <main className="shell">
      <header className="topbar">
        <div className="title">
          <h1>Security Events</h1>
          <p>Review access denials, unknown cards, robot errors, and manual notes.</p>
        </div>
        <Link href="/">Overview</Link>
      </header>
      {events.length ? events.map((event) => (
        <article className="card" key={event.eventId}>
          <strong><AlertTriangle size={16} /> {event.title}</strong>
          <div className="meta-line">
            <span className={severityClass(event.severity)}>{event.severity}</span>
            <span className="tag">{event.status}</span>
            <span className="tag">{new Date(event.createdAt).toLocaleString()}</span>
          </div>
          <p className="summary">{event.description}</p>
          {event.locationLabel ? <p className="muted">Location: {event.locationLabel}</p> : null}
        </article>
      )) : <div className="panel empty">No security events yet.</div>}
    </main>
  );
}
