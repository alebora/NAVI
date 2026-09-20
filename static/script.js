const input = document.getElementById("navi-input");
const askButton = document.getElementById("navi-button");
const statusBox = document.getElementById("navi-status");
const statusText = document.getElementById("navi-status-text");
const resultBox = document.getElementById("navi-result");
const chips = document.querySelectorAll(".example-chip");

const THINKING_LINES = [
    "Reading the schedule...",
    "Matching your question to an event...",
    "Checking the details...",
];

let thinkingTimer = null;

function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value ?? "";
    return div.innerHTML;
}

function startThinking() {
    let i = 0;
    statusText.textContent = THINKING_LINES[0];
    statusBox.hidden = false;

    thinkingTimer = setInterval(() => {
        i = (i + 1) % THINKING_LINES.length;
        statusText.textContent = THINKING_LINES[i];
    }, 750);
}

function stopThinking() {
    clearInterval(thinkingTimer);
    statusBox.hidden = true;
}

function renderMatch(data) {
    const event = data.event;

    resultBox.innerHTML = `
        <div class="event-card">
            <div class="event-top">
                <div>
                    <div class="result-label">NAVI FOUND A MATCH</div>
                    <h3>${escapeHtml(event.name)}</h3>
                </div>
            </div>

            <p class="event-response">${escapeHtml(data.response)}</p>

            <div class="event-details">
                <div class="event-detail">
                    <span>TIME</span>
                    <strong>${escapeHtml(event.time)}</strong>
                </div>
                <div class="event-detail">
                    <span>LOCATION</span>
                    <strong>${escapeHtml(event.location)}</strong>
                </div>
                <div class="event-detail">
                    <span>ROOM</span>
                    <strong>${escapeHtml(event.room)}</strong>
                </div>
            </div>

            <button class="navigate-button" id="navigate-btn" type="button">
                Take me there <span>→</span>
            </button>
        </div>
    `;

    document.getElementById("navigate-btn").addEventListener("click", () => {
        renderRoute(event);
    });
}

function renderRoute(event) {
    const existing = document.getElementById("navigation-card");
    if (existing) {
        existing.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
    }

    const card = document.createElement("div");
    card.className = "navigation-card";
    card.id = "navigation-card";

    card.innerHTML = `
        <div class="navigation-header">
            <div>
                <div class="navigation-label">ROUTE PREVIEW</div>
                <h3>${escapeHtml(event.name)}</h3>
            </div>
            <div class="navigation-arrow">→</div>
        </div>

        <div class="navigation-route">
            <div class="route-point">
                <div class="route-marker">A</div>
                <div>
                    <span>YOU ARE HERE</span>
                    <strong>Main Entrance</strong>
                </div>
            </div>

            <div class="route-line"></div>

            <div class="route-point">
                <div class="route-marker destination">B</div>
                <div>
                    <span>DESTINATION</span>
                    <strong>${escapeHtml(event.location)}</strong>
                    <small>${escapeHtml(event.room)}</small>
                </div>
            </div>
        </div>

        <div class="navigation-instruction">
            <div class="instruction-number">01</div>
            <div>
                <span>NEXT STEP</span>
                <strong>Head toward ${escapeHtml(event.location)}, then look for ${escapeHtml(event.room)}.</strong>
            </div>
        </div>

        <p class="demo-note">
            This is a simulated preview. Find the physical NAVI robot
            on the floor and it will guide you there using its own
            cameras and mapping.
        </p>
    `;

    resultBox.appendChild(card);
    card.scrollIntoView({ behavior: "smooth", block: "center" });
}

function renderEmpty(message) {
    resultBox.innerHTML = `
        <div class="empty-result">
            ${escapeHtml(message)}
            <br>
            Try asking about a topic, a company, or what to do right now.
        </div>
    `;
}

async function askNavi() {
    const question = input.value.trim();

    if (!question) {
        input.focus();
        return;
    }

    askButton.disabled = true;
    resultBox.innerHTML = "";
    startThinking();

    try {
        const res = await fetch("/ask", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question }),
        });

        const data = await res.json();

        if (data.event) {
            renderMatch(data);
        } else {
            renderEmpty(data.response);
        }
    } catch (error) {
        renderEmpty("I'm having trouble connecting right now. Please try again.");
    } finally {
        stopThinking();
        askButton.disabled = false;
    }
}

askButton.addEventListener("click", askNavi);

input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        askNavi();
    }
});

chips.forEach((chip) => {
    chip.addEventListener("click", () => {
        input.value = chip.textContent;
        askNavi();
    });
});

const revealTargets = document.querySelectorAll(".reveal");

if ("IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
        (entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add("is-visible");
                    observer.unobserve(entry.target);
                }
            });
        },
        { threshold: 0.15 }
    );

    revealTargets.forEach((el) => observer.observe(el));
} else {
    revealTargets.forEach((el) => el.classList.add("is-visible"));
}
