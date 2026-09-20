# Meeting recording backend

Small MongoDB-backed API for the NAVI meeting-recording website.

This service is separate from the robot runtime. The Jetson recorder writes
documents to MongoDB; the website reads them through this API.

## Run

```bash
cd meeting_recording/backend
cp .env.example .env
npm install
npm run dev
```

## Endpoints

```text
GET /health
GET /api/meetings
GET /api/meetings/:meetingId
GET /api/robot/status
```

The API is intentionally read-only for the website MVP.
