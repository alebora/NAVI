# NAVI meeting website

Web dashboard for audio-only meeting summaries. This is not the mobile app.

```bash
cd meeting_recording/web
cp .env.example .env.local
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_BASE_URL` to the backend URL, for example:

```text
NEXT_PUBLIC_API_BASE_URL=http://localhost:8787
```
