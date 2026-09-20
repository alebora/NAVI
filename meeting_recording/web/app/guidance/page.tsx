import Link from "next/link";
import { MapPinned } from "lucide-react";
import { listGuidanceSessions } from "../../lib/api";

export default async function GuidancePage() {
  const sessions = await listGuidanceSessions().catch(() => []);
  return (
    <main className="shell">
      <header className="topbar">
        <div className="title">
          <h1>Guidance Logs</h1>
          <p>Where NAVI guided people, what was requested, and how it ended.</p>
        </div>
        <Link href="/">Overview</Link>
      </header>
      {sessions.length ? sessions.map((session) => (
        <article className="card" key={session.sessionId}>
          <strong><MapPinned size={16} /> {session.matchedDestinationName || session.requestedDestinationText}</strong>
          <div className="meta-line">
            <span className={session.clearanceDecision === "denied" ? "tag red" : session.clearanceDecision === "allowed" ? "tag green" : "tag amber"}>{session.clearanceDecision}</span>
            <span className="tag">{session.finalState}</span>
            <span className="tag">{new Date(session.startedAt).toLocaleString()}</span>
          </div>
          <p className="muted">{session.displayName || "Unknown badge"} · {session.robotId}</p>
          {session.routeSummary ? <p className="summary">{session.routeSummary}</p> : null}
        </article>
      )) : <div className="panel empty">No guidance sessions yet.</div>}
    </main>
  );
}
