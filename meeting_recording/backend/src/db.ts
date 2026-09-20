import { MongoClient } from "mongodb";
import type { MeetingSummary } from "./types.js";

const uri = process.env.MONGODB_URI ?? "mongodb://127.0.0.1:27017";
const dbName = process.env.MONGODB_DATABASE ?? "navi";
const collectionName = process.env.MONGODB_COLLECTION ?? "meetingSummaries";

let client: MongoClient | null = null;

async function getClient() {
  if (!client) {
    client = new MongoClient(uri);
    await client.connect();
  }
  return client;
}

export async function meetingsCollection() {
  const connected = await getClient();
  return connected.db(dbName).collection<MeetingSummary>(collectionName);
}

export async function closeDb() {
  if (client) {
    await client.close();
    client = null;
  }
}
