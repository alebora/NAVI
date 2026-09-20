import { MongoClient } from "mongodb";
import type { GuidanceSession, MeetingSummary, RobotStatus, SecurityEvent } from "./types.js";

const uri = process.env.MONGODB_URI ?? "mongodb://127.0.0.1:27017";
const dbName = process.env.MONGODB_DATABASE ?? "navi";
const meetingCollectionName = process.env.MONGODB_COLLECTION ?? "meetingSummaries";

let client: MongoClient | null = null;

async function getClient() {
  if (!client) {
    const nextClient = new MongoClient(uri);
    await nextClient.connect();
    client = nextClient;
  }
  return client;
}

export async function meetingsCollection() {
  const connected = await getClient();
  return connected.db(dbName).collection<MeetingSummary>(meetingCollectionName);
}

export async function robotStatusCollection() {
  const connected = await getClient();
  return connected.db(dbName).collection<RobotStatus>("robotStatus");
}

export async function guidanceSessionsCollection() {
  const connected = await getClient();
  return connected.db(dbName).collection<GuidanceSession>("guidanceSessions");
}

export async function securityEventsCollection() {
  const connected = await getClient();
  return connected.db(dbName).collection<SecurityEvent>("securityEvents");
}

export async function closeDb() {
  if (client) {
    await client.close();
    client = null;
  }
}
