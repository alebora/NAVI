# NAVI Mobile App README

## Purpose

This README describes the phone app that works with the NAVI robot, backend, and dashboard. Agents should use this file when building the mobile side of NAVI.

The app is phone-first and should be usable on an iPhone. The preferred stack is React Native with Expo and TypeScript because it lets agents write mostly web-style JavaScript/TypeScript while still producing an iOS app that can be opened in Xcode and installed on an iPhone.

The app must stay consistent with `NAVI_CODING_CONTEXT.md`. NAVI is not just a mobile app. It is an embodied robot system with:

- Bracket Bot robot hardware.
- Jetson-side Python scripts.
- Two RGB cameras for 3D SLAM.
- ESP32 PN532 NFC reader over USB serial.
- Jetson-connected face monitor.
- Google AI for STT, TTS, LLM, summaries, and optional vision.
- Backend/shared database for meetings, guidance logs, robot state, and security events.

The app should not directly control low-level robot movement. It should read and write high-level backend state, show summaries, show robot/admin logs, and receive security/operations notifications.

---

## Recommended Tech Stack

Use this stack unless there is a strong reason not to:

- React Native.
- Expo.
- TypeScript.
- Expo Router for file-based navigation.
- Firebase Auth for sign-in.
- Firestore for realtime data.
- Cloud Storage for audio/transcript artifacts if needed.
- Cloud Functions or Cloud Run for backend APIs.
- Firebase Cloud Messaging or Expo Notifications for push notifications.
- React Query or simple Firestore listeners for data sync.
- Zod for runtime validation of API responses if time allows.
- NativeWind, Tamagui, React Native Paper, or simple StyleSheet components for UI.

Why Expo:

- Agents can build quickly using TS/JS.
- The app can run in Expo Go for early testing.
- `npx expo prebuild -p ios` can generate an iOS project.
- The generated iOS project can be opened in Xcode.
- The team can install on an iPhone through Xcode or TestFlight later.

Preferred app folder:

```text
mobile/
  README.md
  app.json
  package.json
  tsconfig.json
  src/
    app/
      _layout.tsx
      index.tsx
      meetings/
        index.tsx
        [meetingId].tsx
      robot/
        index.tsx
      admin/
        index.tsx
        sessions.tsx
      security/
        index.tsx
      settings/
        index.tsx
    components/
      AppShell.tsx
      EmptyState.tsx
      LoadingState.tsx
      MeetingSummaryCard.tsx
      RobotStatusCard.tsx
      SecurityEventCard.tsx
      GuidanceSessionCard.tsx
    features/
      auth/
      meetings/
      robot/
      navigationLogs/
      security/
      admin/
    lib/
      api.ts
      firebase.ts
      types.ts
      permissions.ts
      formatters.ts
```

---

## Product Goals

The app has three main product goals.

1. Meeting summaries

Users should be able to see summaries from meetings that belong to them. A meeting belongs to a user if the backend associates their account, NFC card ID, role, or demo participant record with that meeting.

2. Security notifications

Admins should be able to see security-relevant robot events, such as access denied, robot entering restricted zones, robot needing help, or future badge-related observations. "Someone seen without a badge" is a stretch feature and should not be treated as reliable for the MVP.

3. Admin robot activity

Admins should be able to see where the robot guided people and which people/cards went where using the robot. This includes successful guidance, denied guidance, cancelled routes, and errors.

---

## MVP Scope

Build these first:

- Sign-in or demo user picker.
- Meeting summaries list.
- Meeting summary detail screen.
- Robot status screen.
- Admin guidance log screen.
- Security notifications feed.
- Basic role handling: user versus admin.
- Shared backend data contracts with the robot system.

The app should work even if some data is mocked at first, as long as the mock data matches the backend schemas in this README.

---

## Stretch Scope

Build these only after the MVP works:

- Push notifications.
- iPhone NFC badge scan to link a phone user to a hacker badge.
- Gemini image-analysis security events from periodic robot images.
- Live robot map view.
- Admin destination editor.
- Admin clearance editor.
- Direct "request robot guide" feature from the phone.

---

## Important Product Boundaries

Do not overclaim security.

NAVI can log access-control decisions and support security workflows, but the prototype should not claim to be a complete security system.

Do not require iPhone NFC scan for the MVP.

iPhone NFC support can be tricky depending on tag format, permissions, and time. The MVP should let the backend associate a user with a card ID manually or through demo login.

Do not require badge detection from images for the MVP.

"Person seen without a badge" can be represented as a future security event type. It may later be implemented by taking periodic robot images and asking Gemini vision to inspect whether a visible person appears to have a badge. For now, agents should build the app feed and schema so the feature has somewhere to land.

Do not let the app directly drive the robot's low-level motors.

The app can request high-level actions through the backend, but movement must remain controlled by the Jetson mission controller and Bracket Bot navigation stack.

---

## User Roles

Use simple role-based access:

```ts
type UserRole = "visitor" | "participant" | "organizer" | "admin" | "security";
```

Visitor or participant:

- Can view their own meeting summaries.
- Can view basic robot status if allowed.
- Cannot view all guidance logs.
- Cannot view private security events unless explicitly allowed.

Organizer:

- Can view event-level meeting summaries if granted.
- Can view robot status.
- Can view operational logs.

Admin:

- Can view all meeting summaries.
- Can view all guidance sessions.
- Can view and resolve security events.
- Can manage cards, users, destinations, and clearance groups if that screen exists.

Security:

- Can view security events.
- Can view access-denied guidance sessions.
- Can view current robot status and location.

---

## Core Screens

## Home Screen

The home screen should quickly show:

- Robot status.
- Latest meeting summary.
- Latest security notification if the user has permission.
- Shortcut to meeting summaries.
- Shortcut to admin logs if the user is admin/security.

## Meeting Summaries Screen

Shows meetings the current user is allowed to view.

Each item should show:

- Meeting title or generated short summary.
- Date/time.
- Duration.
- Participants if available.
- Recording type: always `audio_only`.
- Summary status: processing, ready, failed.

## Meeting Detail Screen

Shows:

- Summary.
- Decisions.
- Action items.
- Participants.
- Location/time markers if available.
- Transcript preview if available.
- Link to full transcript if allowed.

Do not show raw audio unless needed. The main user value is the summary.

## Robot Status Screen

Shows:

- Robot online/offline.
- Current robot state.
- Current face state.
- Current destination if navigating.
- Current map/floor if available.
- Meeting recording state.
- Battery if available.
- Last heartbeat time.

## Admin Guidance Logs Screen

Shows where the robot guided people and which people/cards went where.

Each row/card should show:

- Session ID.
- Card/user display name if allowed.
- Card ID masked if needed.
- Requested destination.
- Clearance decision.
- Start time.
- End time.
- Final state: arrived, denied, cancelled, failed.
- Robot ID.

## Security Notifications Screen

Shows security and operations events.

MVP event examples:

- Access denied for restricted destination.
- Unknown card scanned.
- Robot stopped due to error.
- Robot disconnected.
- Meeting recording failed.
- Manual security note from admin.

Stretch event examples:

- Possible person seen without badge.
- Person in restricted area.
- Robot camera/vision confidence too low.

Each security event should show:

- Severity.
- Event type.
- Time.
- Robot ID.
- Location if known.
- Short description.
- Status: open, acknowledged, resolved, dismissed.

---

## Shared Data Models

These models must match the backend and robot-side expectations.

## App User

```ts
export type AppUser = {
  userId: string;
  displayName: string;
  email?: string;
  role: "visitor" | "participant" | "organizer" | "admin" | "security";
  linkedCardIds: string[];
  clearanceGroups: string[];
};
```

## Meeting Summary

```ts
export type MeetingSummary = {
  meetingId: string;
  title: string;
  ownerUserIds: string[];
  participantCardIds: string[];
  startedAt: string;
  endedAt?: string;
  status: "recording" | "processing" | "ready" | "failed";
  recordingType: "audio_only";
  summary?: string;
  decisions: string[];
  actionItems: {
    task: string;
    owner?: string;
    due?: string | null;
    done?: boolean;
  }[];
  locations: {
    timestamp: string;
    mapNodeId?: string;
    label?: string;
  }[];
};
```

## Robot Status

```ts
export type RobotStatus = {
  robotId: string;
  online: boolean;
  robotState:
    | "IDLE"
    | "CARD_ACTIVE"
    | "DESTINATION_REQUESTED"
    | "CHECKING_CLEARANCE"
    | "CLEARANCE_DENIED"
    | "PLANNING_ROUTE"
    | "GUIDING"
    | "WAITING_FOR_USER"
    | "REROUTING"
    | "ARRIVED"
    | "CANCELLED"
    | "ERROR";
  faceState:
    | "IDLE"
    | "LISTENING"
    | "THINKING"
    | "NAVIGATING"
    | "ACCESS_GRANTED"
    | "ACCESS_DENIED"
    | "RECORDING"
    | "SUMMARIZING"
    | "ELEVATOR"
    | "ERROR";
  currentDestinationId?: string;
  currentDestinationName?: string;
  currentMapId?: string;
  currentFloor?: number;
  meetingRecordingActive: boolean;
  batteryPercent?: number;
  lastHeartbeatAt: string;
};
```

## Guidance Session

```ts
export type GuidanceSession = {
  sessionId: string;
  robotId: string;
  cardId: string;
  userId?: string;
  displayName?: string;
  requestedDestinationText: string;
  matchedDestinationId?: string;
  matchedDestinationName?: string;
  clearanceDecision: "allowed" | "denied" | "unknown";
  denialReason?: string;
  startedAt: string;
  endedAt?: string;
  finalState:
    | "arrived"
    | "denied"
    | "cancelled"
    | "failed"
    | "in_progress";
  routeSummary?: string;
};
```

## Security Event

```ts
export type SecurityEvent = {
  eventId: string;
  robotId: string;
  type:
    | "ACCESS_DENIED"
    | "UNKNOWN_CARD"
    | "ROBOT_ERROR"
    | "ROBOT_OFFLINE"
    | "MEETING_RECORDING_FAILED"
    | "POSSIBLE_PERSON_WITHOUT_BADGE"
    | "MANUAL_NOTE";
  severity: "info" | "warning" | "critical";
  status: "open" | "acknowledged" | "resolved" | "dismissed";
  title: string;
  description: string;
  createdAt: string;
  locationLabel?: string;
  mapNodeId?: string;
  relatedCardId?: string;
  relatedSessionId?: string;
  imageUri?: string;
  geminiAnalysis?: {
    summary: string;
    confidence: number;
    model: string;
  };
};
```

---

## Backend API Needed By App

The app should consume the same backend used by the robot and dashboard.

Recommended endpoints:

```text
GET  /api/mobile/me
GET  /api/mobile/meetings
GET  /api/mobile/meetings/:meetingId
GET  /api/mobile/robot/status
GET  /api/mobile/navigation-sessions
GET  /api/mobile/security-events
PATCH /api/mobile/security-events/:eventId
```

Admin-only optional endpoints:

```text
GET  /api/admin/cards
GET  /api/admin/destinations
PATCH /api/admin/cards/:cardId
PATCH /api/admin/destinations/:destinationId
```

Future request-robot endpoint:

```text
POST /api/mobile/guide-request
```

That endpoint should only create a high-level request. The Jetson mission controller must still decide when and whether to move.

---

## Firestore Collection Shape

If using Firebase, recommended collections:

```text
users/{userId}
cards/{cardId}
destinations/{destinationId}
robots/{robotId}
robots/{robotId}/heartbeats/{heartbeatId}
meetingSummaries/{meetingId}
guidanceSessions/{sessionId}
securityEvents/{eventId}
```

Suggested security rules:

- Users can read their own user document.
- Users can read meeting summaries where `ownerUserIds` contains their user ID.
- Admin/security users can read guidance sessions and security events.
- Normal users cannot read all card IDs or all guidance sessions.
- Robot service account can write robot status, meeting summaries, guidance sessions, and security events.

---

## Authentication Plan

MVP options, from easiest to more complete:

1. Demo mode user picker

Use hardcoded demo users for hackathon demos.

2. Firebase Auth email/password or magic link

Good enough for a real app prototype.

3. NFC badge linking

Optional stretch. User scans or enters their badge ID and the backend links it to their account after verification.

iPhone NFC note:

Scanning NFC from an iPhone may be possible with native capabilities, but it depends on tag type, app permissions, and setup. Agents should not make this required for the MVP. The robot already reads the hacker badge through the PN532 reader, so the simplest MVP is to associate meetings with card IDs on the backend and map those card IDs to app users.

---

## Security Notifications With Gemini Vision

This is a stretch feature.

Possible future flow:

```text
1. Robot periodically captures a still image in allowed contexts.
2. Image is uploaded to Cloud Storage.
3. Backend sends image to Gemini vision model.
4. Gemini checks for visible people and visible badges.
5. Backend creates a security event if a possible issue is found.
6. App shows the event to security/admin users.
```

Important limitations:

- Do not claim this is perfect badge detection.
- Do not create punitive automated enforcement from this alone.
- Require human review.
- Avoid collecting unnecessary images.
- Respect event privacy rules.

Recommended event type:

```text
POSSIBLE_PERSON_WITHOUT_BADGE
```

Recommended wording:

```text
Possible person without visible badge near Main Hall. Review suggested.
```

Avoid wording:

```text
Unauthorized person detected.
```

---

## App Build Instructions

Initial setup:

```bash
npx create-expo-app mobile --template
cd mobile
npm install
npm install expo-router firebase zod
```

Start development:

```bash
npx expo start
```

Generate iOS project for Xcode:

```bash
npx expo prebuild -p ios
open ios/*.xcworkspace
```

Then use Xcode to select a connected iPhone and run the app.

If agents add native modules for NFC or push notifications, they must verify the Expo/Xcode flow still works.

---

## UI Guidance

The app is an operations tool, not a marketing page.

Design style:

- Phone-first.
- Clear status cards.
- High contrast for robot/security state.
- Compact lists for meetings and sessions.
- Obvious role separation between user and admin screens.
- Avoid decorative complexity.
- Make security events easy to scan.
- Use plain wording.

Suggested tab structure:

```text
Home
Meetings
Robot
Security
Admin
Settings
```

Hide `Security` and `Admin` tabs for users who do not have permission.

---

## Integration Rules For Agents

- Keep this app consistent with `NAVI_CODING_CONTEXT.md`.
- The app reads meeting summaries created by the robot/backend pipeline.
- The app reads guidance sessions created when the robot guides or refuses to guide someone.
- The app reads security events created by the robot/backend.
- The app must respect user roles.
- The app must not expose all guidance logs to normal users.
- Meeting recording type is always `audio_only`.
- The app must not imply video recording exists.
- The app must not claim badge-vision security is complete or reliable.
- iPhone NFC badge scan is optional and not required for MVP.
- Admin views should explain what happened: who/card, destination, clearance decision, time, and robot.
- Use TypeScript shared types matching this README wherever possible.

## MVP Acceptance Checklist

- App can run in iOS simulator or on iPhone through Expo/Xcode.
- User can view their meeting summaries.
- User can open a meeting summary detail screen.
- Robot status screen shows online/offline and current state.
- Admin can see guidance logs.
- Admin/security can see security notifications.
- Data contracts match backend/robot schemas.
- App does not depend on unfinished NFC phone scanning.
- App does not depend on unfinished Gemini vision badge detection.

