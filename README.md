# NAVI — An Embodied Indoor Guide

## Project overview

NAVI is a speech-to-speech, identity-aware indoor robot that helps people move through complex buildings. It combines stereo depth perception, 3D SLAM localization, NFC identification, natural conversation, meeting capture, and robotic interaction into one physical assistant.

The user can tap an NFC badge and ask:

> “Take me to the judging area.”

NAVI verifies the user’s context or permissions, plans a route through its map, drives ahead, waits if the person falls behind, and reroutes when a path is blocked. At the destination, it confirms that the user has arrived.

NAVI’s arm gives it the ability to interact with the building rather than simply drive through it. It could press elevator buttons, operate accessible door controls, point toward a destination, hand over an item, or interact with simple switches and interfaces.

NAVI can also support a consent-based walking-meeting mode. It follows or leads a group, captures audio, video, and useful screenshots, and produces a location-aware summary of decisions and action items. Users can ask NAVI to start or stop recording naturally through speech.

## Pitch lines

### Few-words pitch

**A navigation robot with security and meeting recording.**

### One-line pitch

**After a security check, you can ask NAVI to navigate through the building or ask it to follow you and record a meeting.**

### Elevator pitch

We are building NAVI—a navigation robot you can talk to, and it will navigate you through the building. Think of it as Google Maps for indoors. It also comes with a security feature using an NFC reader, and it can follow you and record meetings that require walking.

### Couple-sentence pitch

NAVI is a robot that can talk with people, check their event badge, and guide them through a building using its depth cameras and 3D map. When a user asks, NAVI can follow a walking meeting, record audio and video with consent, capture useful screenshots, and turn the conversation into notes linked to where it happened.

### Full pitch

We are building NAVI, a physical AI guide for complex indoor events. A visitor can speak naturally to NAVI, tap an NFC badge for identity and access context, and ask to be guided to a meeting room, judging area, or hardware room. NAVI uses the robot’s stereo depth camera and existing 3D SLAM output to understand where it is, navigate through the venue, and communicate through its microphone and speaker. If it reaches an elevator or another simple interface, its arm can interact with a safe mock control panel, with the Meta Quest used to teleoperate the robot and collect demonstrations for a learned manipulation behavior. With explicit consent, NAVI can also follow an onsite walking meeting, capture audio, video, and screenshots, and produce a location-aware summary of decisions and action items. The goal is to use the entire robot as an embodied system—not just as a mobile base or chatbot.

### Sponsor-facing pitch

**NAVI demonstrates the complete embodied-AI loop: teleoperate a robot, collect demonstrations, train useful behaviors, and deploy them in a real indoor environment.**

## The problem

Large indoor spaces are difficult to navigate. Visitors may not know where rooms, elevators, washrooms, labs, or event areas are located. Static signs are easy to miss, floor plans are not always available, and smartphone maps usually stop being useful once someone enters a building.

Robots can solve this problem, but a useful indoor guide must do more than follow a pre-programmed path. It needs to understand the person’s request, localize itself, handle changing obstacles, recognize meaningful places, and interact with the physical environment.

## Core features

### Indoor navigation

- Build a metric 2D map of a building or event area.
- Label important locations such as registration, judging, washrooms, elevators, and hardware rooms.
- Plan routes between locations.
- Wait when the user falls behind.
- Detect blocked paths and reroute.
- Return to a charging or standby location.

### NFC identity and access context

- Let a user tap an NFC badge to identify themselves.
- Use badge context to personalize destinations and interactions.
- Demonstrate simple access rules, such as public areas versus staff-only areas.
- Avoid treating NFC alone as high-security authentication; it is primarily a convenient identity and context signal for the prototype.

### Robotic interaction

The arm could be used to:

- Press elevator buttons.
- Operate accessible door buttons or handles.
- Point toward a route or room.
- Hand an item to a person.
- Press a physical “help” or “confirm” button.
- Learn simple actions from leader-follower demonstrations.

### Walking-meeting mode

With clear participant consent, NAVI could follow or lead a short walking meeting and create:

- A transcript.
- A list of decisions.
- Action items.
- Participants identified through NFC check-in.
- Location and time markers for the discussion.

This turns NAVI’s map into a spatial memory of the building, not just a collection of walls and coordinates.

## Hackathon demo

The demo should focus on a small, reliable environment rather than attempting to map an entire campus.

1. Create a small indoor map with three or four labeled destinations using the robot’s existing 3D SLAM system.
2. A participant speaks to NAVI and taps an NFC badge.
3. NAVI checks the badge context, confirms the request, and begins guiding them.
4. The robot uses its stereo depth cameras to detect people and obstacles, then navigates to the destination.
5. NAVI reaches a safe mock elevator or door panel and uses its arm to interact with it; the Meta Quest provides teleoperation and demonstration data when needed.
6. The participant says, “Start recording this meeting,” and gives consent.
7. NAVI follows the group while capturing audio, video, and screenshots.
8. The participant says, “Stop recording,” and NAVI produces a concise, location-aware summary.

If time is limited, the minimum viable demo is: **NFC check-in → destination selection → mapped navigation → obstacle rerouting → arrival confirmation.**

## Technical direction

The robot’s existing 3D SLAM system is the localization foundation. We will consume its output rather than modify the underlying SLAM implementation. NAVI adds a semantic and interaction layer on top:

```text
stereo depth + robot sensors + existing 3D SLAM
                         ↓
                 localization / map output
                         ↓
              semantic places and routes
                         ↓
                    mission planning
```

The semantic layer stores meaningful places:

```text
occupancy map: walls, free space, obstacles
semantic graph: rooms, doors, elevators, stations
landmarks: NFC tags, AprilTags, visual references
```

The Jetson runs the high-level AI and perception pipeline. The camera and microphone provide perception and interaction, while the navigation system remains grounded in the robot’s live map output. The speaker makes NAVI conversational, and the Meta Quest enables teleoperation and demonstration collection. AI-generated world models may be useful for simulation, visualization, or semantic labeling, but should not be treated as the robot’s only safety map.

## Why the Bracket Bot kit matters

The kit gives the team a complete embodied-AI platform instead of only a software demo: stereo depth cameras, a Jetson computer, speaker and microphone, dual arms, an existing 3D SLAM system, and Meta Quest teleoperation. The leader-follower setup can be used to teleoperate the robot and arms, collect demonstrations, and train or tune manipulation behaviors.

The arm is especially valuable for demonstrating that NAVI can interact with infrastructure and objects. Navigation gets the robot to the right place; speech lets people communicate with it; the arms let it do something useful once it arrives; and meeting mode gives the robot a reason to remain present after navigation is complete.

## Potential sponsor value

NAVI can create a clear, visible demonstration for sponsors working in:

- Robotics and automation.
- AI hardware and edge computing.
- Cameras, LiDAR, and depth sensors.
- Accessibility and assistive technology.
- Smart buildings and facilities management.
- Logistics and indoor delivery.
- Collaboration and workplace software.
- Safety, security, and identity systems.

Sponsors can see their technology in a complete workflow: a person interacts with the robot, the robot perceives the environment, makes a decision, moves through the space, and performs a physical action.

## Future applications

- Hackathon and conference wayfinding.
- Hospital and university navigation.
- Museum and mall assistance.
- Indoor package and equipment delivery.
- Accessibility support for visitors with mobility or vision limitations.
- Emergency guidance around blocked corridors.
- Facilities inspection and maintenance assistance.
- Location-aware meeting and tour documentation.

## Team goal

Our goal is to build a memorable working prototype that shows how mapping, language, identity, manipulation, and learning can come together in one useful robot. NAVI should feel less like a remote-controlled machine and more like a physical guide that understands the space around it and helps people move through it.
