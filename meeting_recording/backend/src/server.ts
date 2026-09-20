import "dotenv/config";
import cors from "cors";
import express from "express";
import { z } from "zod";
import { meetingsCollection } from "./db.js";
import type { RobotStatus } from "./types.js";

const app = express();
const port = Number(process.env.PORT ?? 8787);

app.use(cors());
app.use(express.json({ limit: "1mb" }));

app.get("/health", (_req, res) => {
  res.json({ ok: true });
});

app.get("/api/meetings", async (req, res, next) => {
  try {
    const limit = Math.min(Number(req.query.limit ?? 50), 100);
    const collection = await meetingsCollection();
    const meetings = await collection
      .find({}, { projection: { transcript: 0 } })
      .sort({ startedAt: -1 })
      .limit(limit)
      .toArray();
    res.json({ meetings });
  } catch (error) {
    next(error);
  }
});

app.get("/api/meetings/:meetingId", async (req, res, next) => {
  try {
    const params = z.object({ meetingId: z.string().min(1) }).parse(req.params);
    const collection = await meetingsCollection();
    const meeting = await collection.findOne({ meetingId: params.meetingId });
    if (!meeting) {
      res.status(404).json({ error: "meeting_not_found" });
      return;
    }
    res.json({ meeting });
  } catch (error) {
    next(error);
  }
});

app.get("/api/robot/status", (_req, res) => {
  const status: RobotStatus = {
    robotId: process.env.ROBOT_ID ?? "bracketbot-189",
    online: true,
    robotState: "IDLE",
    faceState: "IDLE",
    meetingRecordingActive: false,
    lastHeartbeatAt: new Date().toISOString(),
  };
  res.json({ status });
});

app.use((error: unknown, _req: express.Request, res: express.Response, _next: express.NextFunction) => {
  console.error(error);
  res.status(500).json({ error: "internal_error" });
});

app.listen(port, () => {
  console.log(`NAVI meeting backend listening on :${port}`);
});
