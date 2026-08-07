/**
 * app.js — Browser STT + WebSocket client for Nova voice assistant.
 *
 * Handles:
 *  - Web Speech API (SpeechRecognition / webkitSpeechRecognition)
 *  - Continuous listening with interim results
 *  - WebSocket connection to Python backend with auto-reconnect
 *  - Wake word state machine: IDLE → LISTENING → WAKE_DETECTED → COMMAND
 *  - Browser SpeechSynthesis for TTS
 *  - Mic permission handling and browser compatibility checks
 *  - Auto-restart STT on visibility change, errors, and page focus
 */

(function () {
    "use strict";

    // ─── State ─────────────────────────────────────────────────────────
    const State = {
        IDLE: "idle",
        LISTENING: "listening",
        WAKE_DETECTED: "wake_detected",
        PROCESSING: "processing",
    };

    let currentState = State.IDLE;
    let recognition = null;
    let ws = null;
    let wsReconnectTimer = null;
    let wsReconnectDelay = 1000;
    const WS_MAX_DELAY = 15000;
    let isListening = false;
    let commandHistory = [];
    let sttHealthTimer = null;
    const STT_RESTART_DELAY = 500;  // faster restart

    // ─── DOM Elements ──────────────────────────────────────────────────
    const $ = (id) => document.getElementById(id);
    const dom = {
        micButton: $("micButton"),
        micLabel: $("micLabel"),
        micPulse: $("micPulse"),
        statusCard: $("statusCard"),
        statusRing: $("statusRing"),
        statusLabel: $("statusLabel"),
        statusHint: $("statusHint"),
        connectionDot: $("connectionDot"),
        connectionText: $("connectionText"),
        interimText: $("interimText"),
        transcriptLog: $("transcriptLog"),
        transcriptCard: $("transcriptCard"),
        transcriptLang: $("transcriptLang"),
        resultCard: $("resultCard"),
        resultIcon: $("resultIcon"),
        resultTitle: $("resultTitle"),
        resultTool: $("resultTool"),
        resultAction: $("resultAction"),
        resultDuration: $("resultDuration"),
        resultMessage: $("resultMessage"),
        historyList: $("historyList"),
        clearHistory: $("clearHistory"),
        errorBanner: $("errorBanner"),
        errorText: $("errorText"),
        errorClose: $("errorClose"),
    };

    // ─── Browser Compatibility Check ───────────────────────────────────

    function checkBrowserSupport() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) {
            showError(
                "Your browser does not support Speech Recognition. " +
                "Please use Google Chrome or Microsoft Edge for the best experience."
            );
            dom.micButton.disabled = true;
            dom.micButton.style.opacity = "0.4";
            dom.micLabel.textContent = "Browser not supported";
            return false;
        }
        return true;
    }

    // ─── Speech Recognition Setup ──────────────────────────────────────

    function initSpeechRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) return;

        recognition = new SpeechRecognition();
        recognition.continuous = true;
        recognition.interimResults = true;
        recognition.lang = "en-US";
        recognition.maxAlternatives = 1;

        dom.transcriptLang.textContent = recognition.lang;

        recognition.onstart = () => {
            isListening = true;
            if (currentState === State.IDLE) {
                setState(State.LISTENING);
            }
        };

        recognition.onresult = (event) => {
            let interimTranscript = "";
            let finalTranscript = "";

            for (let i = event.resultIndex; i < event.results.length; i++) {
                const transcript = event.results[i][0].transcript;
                if (event.results[i].isFinal) {
                    finalTranscript += transcript;
                } else {
                    interimTranscript += transcript;
                }
            }

            // Show interim results (live, updating in place)
            if (interimTranscript) {
                dom.interimText.textContent = interimTranscript;
                dom.transcriptCard.classList.add("active");
                scrollToBottom(dom.transcriptLog);
            }

            // Process final results — add to log and send to backend
            if (finalTranscript) {
                dom.interimText.textContent = "";
                addToTranscriptLog(finalTranscript.trim());
                dom.transcriptCard.classList.remove("active");

                // Send to backend via WebSocket
                sendTranscript(finalTranscript.trim());
            }
        };

        let restartTimer = null;

        recognition.onerror = (event) => {
            if (event.error === "aborted") {
                // Aborted — try to restart immediately
                console.log("Speech recognition aborted, restarting...");
                isListening = false;
                // Don't stop — just restart
                if (currentState !== State.PROCESSING) {
                    scheduleRestart();
                }
                return;
            }

            switch (event.error) {
                case "not-allowed":
                    showError(
                        "Microphone access was denied or requires user permission. Please click the microphone button to start."
                    );
                    stopListening();
                    break;
                case "no-speech":
                    // Normal — just silence, keep listening
                    break;
                case "audio-capture":
                    showError("No microphone detected. Please connect a microphone and try again.");
                    stopListening();
                    break;
                case "network":
                    console.warn("Network error in speech recognition, will retry...");
                    break;
                default:
                    console.warn("Speech recognition error:", event.error);
            }
        };

        recognition.onend = () => {
            // Auto-restart with fast delay if we should still be listening
            if (isListening) {
                scheduleRestart();
            }
        };

        function scheduleRestart() {
            if (restartTimer) clearTimeout(restartTimer);
            restartTimer = setTimeout(() => {
                if (isListening && currentState !== State.PROCESSING) {
                    try {
                        recognition.start();
                    } catch (e) {
                        console.warn("Failed to restart recognition:", e.message);
                        // Retry again after longer delay
                        setTimeout(() => {
                            if (isListening) {
                                try { recognition.start(); } catch (e2) { /* give up */ }
                            }
                        }, 2000);
                    }
                }
            }, STT_RESTART_DELAY);
        }
    }

    // ─── Listening Control ─────────────────────────────────────────────

    function startListening() {
        if (!recognition) return;
        isListening = true;
        try {
            recognition.start();
        } catch (e) {
            // Already started — that's fine
            console.warn("Recognition start:", e.message);
        }
        setState(State.LISTENING);
    }

    function stopListening() {
        isListening = false;
        if (recognition) {
            try {
                recognition.stop();
            } catch (e) {
                // Not started — that's fine
            }
        }
        setState(State.IDLE);
    }

    function toggleListening() {
        if (isListening) {
            stopListening();
        } else {
            startListening();
        }
    }

    // ─── WebSocket Connection ──────────────────────────────────────────

    function connectWebSocket() {
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        console.log("Connecting to WebSocket:", wsUrl);
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            console.log("WebSocket connected.");
            wsReconnectDelay = 1000;  // reset backoff
            setConnectionStatus(true);
        };

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleServerMessage(data);
            } catch (e) {
                console.error("Failed to parse WebSocket message:", e);
            }
        };

        ws.onclose = (event) => {
            console.warn("WebSocket closed:", event.code, event.reason);
            setConnectionStatus(false);
            scheduleReconnect();
        };

        ws.onerror = (error) => {
            console.error("WebSocket error:", error);
            setConnectionStatus(false);
        };
    }

    function scheduleReconnect() {
        if (wsReconnectTimer) clearTimeout(wsReconnectTimer);
        console.log(`Reconnecting in ${wsReconnectDelay}ms...`);
        wsReconnectTimer = setTimeout(() => {
            connectWebSocket();
            wsReconnectDelay = Math.min(wsReconnectDelay * 1.5, WS_MAX_DELAY);
        }, wsReconnectDelay);
    }

    function sendTranscript(text) {
        if (!text) return;

        // Sanitize: limit length, trim
        text = text.trim().substring(0, 500);
        if (!text) return;

        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                type: "transcript",
                text: text,
                is_final: true,
            }));
            console.log("Sent transcript:", text);
        } else {
            console.warn("WebSocket not connected. Buffering:", text);
            showError("Connection lost. Reconnecting...");
        }
    }

    // ─── Handle Server Responses ───────────────────────────────────────

    function handleServerMessage(data) {
        console.log("Server message:", data);

        switch (data.type) {
            case "wake_detected":
                setState(State.WAKE_DETECTED);
                speak("Yes?");
                break;

            case "result":
                showResult(data);
                addToHistory(data);
                if (data.speak) {
                    speak(data.speak);
                }
                // Return to listening after showing result
                setTimeout(() => setState(State.LISTENING), 1500);
                break;

            case "waiting_wake":
                setState(State.LISTENING);
                dom.statusHint.textContent = 'Say "Hey Nova" to activate';
                break;

            case "error":
                showError(data.message || "An error occurred.");
                setState(State.LISTENING);
                break;

            case "info":
                dom.statusHint.textContent = data.message || "";
                break;

            default:
                console.warn("Unknown message type:", data.type);
        }
    }

    // ─── UI State Management ───────────────────────────────────────────

    function setState(newState) {
        currentState = newState;

        // Reset classes
        dom.micButton.classList.remove("listening", "wake-detected", "processing");
        dom.statusCard.classList.remove("listening", "wake-detected", "processing");
        dom.statusRing.classList.remove("listening", "wake-detected", "processing");

        switch (newState) {
            case State.IDLE:
                dom.statusLabel.textContent = "Ready";
                dom.statusHint.textContent = "Click the microphone to start listening";
                dom.micLabel.textContent = "Tap to listen";
                break;

            case State.LISTENING:
                dom.micButton.classList.add("listening");
                dom.statusCard.classList.add("listening");
                dom.statusRing.classList.add("listening");
                dom.statusLabel.textContent = "Listening";
                dom.statusHint.textContent = 'Say "Hey Nova" followed by your command';
                dom.micLabel.textContent = "Listening...";
                break;

            case State.WAKE_DETECTED:
                dom.micButton.classList.add("wake-detected");
                dom.statusCard.classList.add("wake-detected");
                dom.statusRing.classList.add("wake-detected");
                dom.statusLabel.textContent = "Wake Word Detected";
                dom.statusHint.textContent = "Listening for your command...";
                dom.micLabel.textContent = "Speak your command";
                break;

            case State.PROCESSING:
                dom.micButton.classList.add("processing");
                dom.statusCard.classList.add("processing");
                dom.statusRing.classList.add("processing");
                dom.statusLabel.textContent = "Processing";
                dom.statusHint.textContent = "Executing your command...";
                dom.micLabel.textContent = "Processing...";
                break;
        }
    }

    function setConnectionStatus(connected) {
        dom.connectionDot.classList.toggle("connected", connected);
        dom.connectionDot.classList.toggle("error", !connected);
        dom.connectionText.textContent = connected ? "Connected" : "Disconnected";
    }

    // ─── Result Display ────────────────────────────────────────────────

    function showResult(data) {
        setState(State.PROCESSING);

        dom.resultCard.classList.remove("hidden", "success", "error");
        dom.resultCard.classList.add(data.success ? "success" : "error");

        dom.resultIcon.textContent = data.success ? "✅" : "❌";
        dom.resultTitle.textContent = data.success ? "Success" : "Error";
        dom.resultTool.textContent = data.tool || "—";
        dom.resultAction.textContent = data.action || "—";
        dom.resultDuration.textContent = data.duration_ms ? `${data.duration_ms}ms` : "";
        dom.resultMessage.textContent = data.message || "";

        // Re-trigger animation
        dom.resultCard.style.animation = "none";
        dom.resultCard.offsetHeight; // force reflow
        dom.resultCard.style.animation = "";
    }

    // ─── History ───────────────────────────────────────────────────────

    function addToHistory(data) {
        const entry = {
            text: data.original_text || data.message?.substring(0, 50) || "...",
            result: data.message?.substring(0, 80) || "",
            success: data.success,
            tool: data.tool,
            time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        };
        commandHistory.unshift(entry);
        if (commandHistory.length > 20) commandHistory.pop();
        renderHistory();
    }

    function renderHistory() {
        if (commandHistory.length === 0) {
            dom.historyList.innerHTML = '<p class="history-empty">No commands yet. Say "Hey Nova" to start!</p>';
            return;
        }

        dom.historyList.innerHTML = commandHistory.map((entry) => `
            <div class="history-item">
                <span class="history-item-icon">${entry.success ? "✅" : "❌"}</span>
                <div class="history-item-content">
                    <div class="history-item-text">${escapeHtml(entry.text)}</div>
                    <div class="history-item-result">${escapeHtml(entry.result)}</div>
                </div>
                <span class="history-item-time">${entry.time}</span>
            </div>
        `).join("");
    }

    function clearHistoryUI() {
        commandHistory = [];
        renderHistory();
    }

    // ─── Transcript Log (ChatGPT Voice style) ─────────────────────────

    let transcriptEntries = [];

    function addToTranscriptLog(text) {
        transcriptEntries.push(text);

        const log = dom.transcriptLog;
        if (!log) return;

        // Clear "Waiting for speech..." placeholder
        if (transcriptEntries.length === 1) {
            log.innerHTML = "";
        }

        const entry = document.createElement("div");
        entry.className = "transcript-entry";
        entry.innerHTML = `<span class="transcript-label">You:</span> ${escapeHtml(text)}`;
        log.appendChild(entry);

        // Keep max 50 entries
        while (log.children.length > 50) {
            log.removeChild(log.firstChild);
        }

        scrollToBottom(log);
    }

    function scrollToBottom(element) {
        if (element) {
            element.scrollTop = element.scrollHeight;
        }
    }

    function clearTranscriptLog() {
        transcriptEntries = [];
        if (dom.transcriptLog) {
            dom.transcriptLog.innerHTML = '<p class="transcript-empty">Waiting for speech...</p>';
        }
    }

    // ─── Browser TTS ───────────────────────────────────────────────────

    function speak(text) {
        if (!text || !window.speechSynthesis) return;

        // Cancel any ongoing speech
        window.speechSynthesis.cancel();

        const utterance = new SpeechSynthesisUtterance(text);
        utterance.rate = 1.0;
        utterance.pitch = 1.0;
        utterance.volume = 0.9;
        utterance.lang = "en-US";

        // Try to pick a good voice
        const voices = window.speechSynthesis.getVoices();
        const preferred = voices.find(v =>
            v.lang.startsWith("en") && (v.name.includes("Google") || v.name.includes("Microsoft"))
        );
        if (preferred) utterance.voice = preferred;

        window.speechSynthesis.speak(utterance);
    }

    // Load voices (some browsers need this async)
    if (window.speechSynthesis) {
        window.speechSynthesis.onvoiceschanged = () => {
            window.speechSynthesis.getVoices();
        };
    }

    // ─── Error Handling ────────────────────────────────────────────────

    function showError(message) {
        dom.errorText.textContent = message;
        dom.errorBanner.classList.remove("hidden");

        // Auto-hide after 8 seconds
        setTimeout(() => {
            dom.errorBanner.classList.add("hidden");
        }, 8000);
    }

    function hideError() {
        dom.errorBanner.classList.add("hidden");
    }

    // ─── Utility ───────────────────────────────────────────────────────

    function escapeHtml(text) {
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
    }

    // ─── Health Check ──────────────────────────────────────────────────

    function startSttHealthCheck() {
        // Periodically ensure STT is running when it should be
        if (sttHealthTimer) clearInterval(sttHealthTimer);
        sttHealthTimer = setInterval(() => {
            if (isListening && currentState !== State.PROCESSING) {
                // Check if recognition is actually running
                try {
                    // Try to start — if it throws "already started", that's fine
                    recognition.start();
                } catch (e) {
                    // Already running — that's good
                }
            }
        }, 5000);  // check every 5 seconds
    }

    function stopSttHealthCheck() {
        if (sttHealthTimer) {
            clearInterval(sttHealthTimer);
            sttHealthTimer = null;
        }
    }

    // ─── Visibility Change Handler ─────────────────────────────────────

    function setupVisibilityHandler() {
        document.addEventListener("visibilitychange", () => {
            if (!isListening) return;

            if (document.hidden) {
                // Tab went to background — STT may be paused by browser
                console.log("Tab hidden — STT may pause, will auto-resume.");
            } else {
                // Tab became visible — restart STT to ensure it's running
                console.log("Tab visible — restarting STT.");
                setTimeout(() => {
                    if (isListening) {
                        try {
                            recognition.start();
                        } catch (e) {
                            // Already started
                        }
                    }
                }, 200);
            }
        });

        // Also handle page focus/blur
        window.addEventListener("focus", () => {
            if (isListening) {
                setTimeout(() => {
                    try { recognition.start(); } catch (e) { /* ok */ }
                }, 200);
            }
        });
    }

    // ─── Event Listeners ───────────────────────────────────────────────

    dom.micButton.addEventListener("click", toggleListening);
    dom.clearHistory.addEventListener("click", clearHistoryUI);
    dom.errorClose.addEventListener("click", hideError);

    // Keyboard shortcut: spacebar to toggle
    document.addEventListener("keydown", (e) => {
        if (e.code === "Space" && e.target === document.body) {
            e.preventDefault();
            toggleListening();
        }
    });

    // ─── Initialize ────────────────────────────────────────────────────

    function init() {
        console.log("Nova Voice Assistant — initializing...");

        if (!checkBrowserSupport()) return;

        initSpeechRecognition();
        connectWebSocket();
        setupVisibilityHandler();

        // Attempt background start on load (active if mic permission previously granted)
        try {
            startListening();
            startSttHealthCheck();
            console.log("Nova Voice Assistant — active and listening in background.");
        } catch (e) {
            console.log("Waiting for user permission / microphone tap.");
            stopListening();
        }
    }

    // Start when DOM is ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
