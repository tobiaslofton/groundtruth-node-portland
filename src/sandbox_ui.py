"""Interactive Developer Sandbox Playground UI for GroundTruth Protocol Node #001."""

def get_sandbox_html() -> str:
    """Return the complete standalone, dark-mode single page dashboard for /sandbox."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GroundTruth Protocol &bull; Developer Sandbox Playground</title>
    <style>
        :root {
            --bg-void: #06090e;
            --surface-card: #0b111a;
            --surface-elevated: #111a26;
            --border-subtle: #1e293b;
            --border-highlight: #38bdf8;
            --text-main: #f1f5f9;
            --text-muted: #94a3b8;
            --text-dim: #64748b;
            --accent-sky: #38bdf8;
            --accent-emerald: #34d399;
            --accent-amber: #f59e0b;
            --accent-rose: #ef4444;
            --font-mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
            --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background-color: var(--bg-void);
            color: var(--text-main);
            font-family: var(--font-sans);
            line-height: 1.5;
            padding: 24px;
            min-height: 100vh;
        }

        .container {
            max-width: 1280px;
            margin: 0 auto;
        }

        /* Top Header */
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--border-subtle);
            margin-bottom: 24px;
            flex-wrap: wrap;
            gap: 16px;
        }

        .brand-title {
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .brand-badge {
            background: rgba(56, 189, 248, 0.12);
            color: var(--accent-sky);
            border: 1px solid rgba(56, 189, 248, 0.3);
            font-family: var(--font-mono);
            font-size: 0.75rem;
            padding: 4px 10px;
            border-radius: 9999px;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            font-weight: 700;
        }

        h1 {
            font-size: 1.5rem;
            font-weight: 700;
            color: var(--text-main);
            letter-spacing: -0.02em;
        }

        .header-links a {
            color: var(--accent-sky);
            text-decoration: none;
            font-size: 0.875rem;
            margin-left: 16px;
            transition: color 0.15s;
        }
        .header-links a:hover { color: #7dd3fc; text-decoration: underline; }

        /* Grid Layout */
        .layout-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
            margin-bottom: 24px;
        }

        @media (max-width: 960px) {
            .layout-grid { grid-template-columns: 1fr; }
        }

        /* Card Styles */
        .card {
            background: var(--surface-card);
            border: 1px solid var(--border-subtle);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
            position: relative;
        }

        .card-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid var(--border-subtle);
        }

        .card-title {
            font-size: 1.05rem;
            font-weight: 600;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        /* Protocol State Monitor */
        .metrics-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }

        .metric-box {
            background: var(--surface-card);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .metric-label {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            color: var(--text-muted);
            font-family: var(--font-mono);
        }

        .metric-value {
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--text-main);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--accent-emerald);
            box-shadow: 0 0 10px var(--accent-emerald);
            display: inline-block;
        }
        .status-dot.pulse {
            animation: pulse-glow 2s infinite ease-in-out;
        }
        @keyframes pulse-glow {
            0%, 100% { transform: scale(1); opacity: 1; }
            50% { transform: scale(1.2); opacity: 0.7; }
        }

        /* Preset Buttons */
        .preset-section {
            margin-bottom: 16px;
        }
        .preset-label {
            font-size: 0.8rem;
            color: var(--text-muted);
            margin-bottom: 8px;
            text-transform: uppercase;
            font-family: var(--font-mono);
            letter-spacing: 0.05em;
        }
        .preset-group {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
        }
        .preset-btn {
            background: var(--surface-elevated);
            border: 1px solid var(--border-subtle);
            color: var(--text-main);
            padding: 8px 12px;
            border-radius: 8px;
            font-size: 0.825rem;
            cursor: pointer;
            transition: all 0.15s ease-in-out;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .preset-btn:hover {
            border-color: var(--accent-sky);
            background: rgba(56, 189, 248, 0.08);
            color: var(--accent-sky);
        }

        /* Form Inputs */
        .form-group {
            margin-bottom: 14px;
        }
        .form-label {
            display: block;
            font-size: 0.825rem;
            font-weight: 500;
            color: var(--text-muted);
            margin-bottom: 6px;
            font-family: var(--font-mono);
        }
        .form-input, .form-textarea {
            width: 100%;
            background: var(--bg-void);
            border: 1px solid var(--border-subtle);
            border-radius: 8px;
            padding: 10px 14px;
            color: var(--text-main);
            font-family: inherit;
            font-size: 0.9rem;
            outline: none;
            transition: border-color 0.15s;
        }
        .form-input:focus, .form-textarea:focus {
            border-color: var(--accent-sky);
            box-shadow: 0 0 0 1px var(--accent-sky);
        }
        .form-textarea {
            resize: vertical;
            min-height: 80px;
            font-family: var(--font-mono);
            font-size: 0.85rem;
        }

        .submit-btn {
            width: 100%;
            background: linear-gradient(135deg, #0284c7 0%, #0369a1 100%);
            border: 1px solid #38bdf8;
            color: #ffffff;
            font-weight: 600;
            padding: 12px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-size: 0.95rem;
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 8px;
            transition: all 0.15s ease-in-out;
            box-shadow: 0 4px 14px rgba(2, 132, 199, 0.4);
            margin-top: 8px;
        }
        .submit-btn:hover:not(:disabled) {
            background: linear-gradient(135deg, #38bdf8 0%, #0284c7 100%);
            box-shadow: 0 6px 20px rgba(56, 189, 248, 0.5);
        }
        .submit-btn:disabled {
            opacity: 0.6;
            cursor: not-allowed;
            box-shadow: none;
        }

        /* Error Banner */
        .alert-banner {
            display: none;
            padding: 12px 16px;
            border-radius: 8px;
            margin-top: 14px;
            font-size: 0.875rem;
            align-items: flex-start;
            gap: 10px;
        }
        .alert-banner.error {
            display: flex;
            background: rgba(239, 68, 68, 0.12);
            border: 1px solid rgba(239, 68, 68, 0.4);
            color: #fca5a5;
        }

        /* Stepper Component */
        .stepper-container {
            display: flex;
            flex-direction: column;
            gap: 12px;
            margin-top: 10px;
        }

        .step-row {
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 10px 14px;
            border-radius: 8px;
            background: var(--surface-elevated);
            border: 1px solid transparent;
            transition: all 0.2s ease;
        }

        .step-row.completed {
            border-color: rgba(52, 211, 153, 0.3);
            background: rgba(52, 211, 153, 0.05);
        }

        .step-row.active {
            border-color: rgba(56, 189, 248, 0.5);
            background: rgba(56, 189, 248, 0.08);
            box-shadow: 0 0 12px rgba(56, 189, 248, 0.2);
        }

        .step-icon {
            width: 28px;
            height: 28px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.8rem;
            font-weight: 700;
            background: #1e293b;
            color: var(--text-dim);
            flex-shrink: 0;
            font-family: var(--font-mono);
        }

        .step-row.completed .step-icon {
            background: var(--accent-emerald);
            color: #06090e;
        }
        .step-row.active .step-icon {
            background: var(--accent-sky);
            color: #06090e;
            animation: pulse-glow 1.5s infinite;
        }

        .step-details {
            flex-grow: 1;
        }
        .step-title {
            font-size: 0.9rem;
            font-weight: 600;
            color: var(--text-muted);
        }
        .step-row.completed .step-title { color: var(--accent-emerald); }
        .step-row.active .step-title { color: var(--accent-sky); }

        .step-sub {
            font-size: 0.75rem;
            color: var(--text-dim);
            font-family: var(--font-mono);
        }

        /* Proof Inspector Section */
        .proof-inspector-wrapper {
            margin-top: 24px;
            display: none;
        }

        .proof-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }
        @media (max-width: 900px) {
            .proof-grid { grid-template-columns: 1fr; }
        }

        .proof-image-card {
            background: #000000;
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
        }

        .proof-image-wrapper {
            position: relative;
            background: #06090e;
            min-height: 280px;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .proof-image-wrapper img {
            width: 100%;
            height: auto;
            max-height: 380px;
            object-fit: contain;
            display: block;
        }

        .proof-overlay-tag {
            position: absolute;
            top: 12px;
            left: 12px;
            background: rgba(6, 9, 14, 0.85);
            backdrop-filter: blur(4px);
            border: 1px solid var(--accent-emerald);
            color: var(--accent-emerald);
            font-family: var(--font-mono);
            font-size: 0.75rem;
            padding: 4px 8px;
            border-radius: 6px;
            font-weight: 600;
        }

        .proof-image-meta {
            padding: 12px 16px;
            background: var(--surface-card);
            border-top: 1px solid var(--border-subtle);
            font-family: var(--font-mono);
            font-size: 0.75rem;
            color: var(--text-muted);
            display: flex;
            justify-content: space-between;
        }

        .proof-data-card {
            background: var(--surface-card);
            border: 1px solid var(--border-subtle);
            border-radius: 10px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            gap: 12px;
        }

        .json-viewer {
            background: #030712;
            border: 1px solid #1f2937;
            padding: 14px;
            border-radius: 8px;
            font-family: var(--font-mono);
            font-size: 0.8rem;
            color: #38bdf8;
            max-height: 300px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-break: break-all;
        }

        .qa-item {
            background: var(--surface-elevated);
            border-left: 3px solid var(--accent-emerald);
            padding: 10px 14px;
            border-radius: 0 8px 8px 0;
            margin-bottom: 8px;
        }
        .qa-q { font-size: 0.825rem; font-weight: 600; color: var(--text-main); margin-bottom: 4px; }
        .qa-a { font-size: 0.8rem; color: var(--accent-emerald); font-family: var(--font-mono); }
        .qa-ev { font-size: 0.75rem; color: var(--text-dim); margin-top: 2px; }

        .spinner {
            display: inline-block;
            width: 14px;
            height: 14px;
            border: 2px solid rgba(255, 255, 255, 0.3);
            border-radius: 50%;
            border-top-color: #fff;
            animation: spin 0.8s linear infinite;
        }
        @keyframes spin { to { transform: rotate(360deg); } }

        /* Fleet Grid */
        .fleet-badge-list {
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 10px;
        }
        .fleet-badge {
            background: #111a26;
            border: 1px solid #1e293b;
            padding: 6px 10px;
            border-radius: 6px;
            font-family: var(--font-mono);
            font-size: 0.75rem;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .fleet-badge.active-op {
            border-color: rgba(52, 211, 153, 0.4);
            color: #e2e8f0;
        }
    </style>
</head>
<body>
    <div class="container">
        <!-- Header -->
        <header>
            <div class="brand-title">
                <span class="brand-badge">Node #001 PDX</span>
                <h1>GroundTruth Protocol &bull; Interactive Sandbox</h1>
            </div>
            <div class="header-links">
                <a href="/docs" target="_blank">Interactive Swagger (/docs)</a>
                <a href="/llms.txt" target="_blank">LLMs Spec (/llms.txt)</a>
                <a href="/health" target="_blank">Health API</a>
            </div>
        </header>

        <!-- Live Protocol State Monitor -->
        <section class="metrics-bar" id="metrics-bar">
            <div class="metric-box">
                <span class="metric-label">Node Status</span>
                <span class="metric-value">
                    <span class="status-dot pulse" id="node-dot"></span>
                    <span id="node-status-text">Online &bull; Active</span>
                </span>
            </div>
            <div class="metric-box">
                <span class="metric-label">Mode</span>
                <span class="metric-value" id="mode-text" style="color: var(--accent-sky);">
                    ⚡ Mock Mode Active
                </span>
            </div>
            <div class="metric-box">
                <span class="metric-label">Fleet Operators</span>
                <span class="metric-value" id="fleet-count-text">
                    4 Registered (4 Ready)
                </span>
            </div>
            <div class="metric-box">
                <span class="metric-label">Credit Balance</span>
                <span class="metric-value" style="color: var(--accent-emerald);">
                    1,000 Credits
                </span>
            </div>
        </section>

        <!-- Two Column Main Workspace -->
        <div class="layout-grid">
            <!-- Left: Interactive Dispatch Form -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span>📡</span>
                        <span>Interactive Dispatch Form</span>
                    </div>
                    <span style="font-size: 0.75rem; font-family: var(--font-mono); color: var(--accent-sky);">POST /v1/dispatch/verify</span>
                </div>

                <!-- 1-Click Quick-Load Presets -->
                <div class="preset-section">
                    <div class="preset-label">1-Click Quick-Load Presets</div>
                    <div class="preset-group">
                        <button type="button" class="preset-btn" onclick="loadPreset('core')">
                            <span>📗</span> Valid Portland Core
                        </button>
                        <button type="button" class="preset-btn" onclick="loadPreset('suburb')">
                            <span>📙</span> Valid Suburb (Nike HQ)
                        </button>
                        <button type="button" class="preset-btn" onclick="loadPreset('geofence')">
                            <span>📕</span> Geofence Rejection
                        </button>
                        <button type="button" class="preset-btn" onclick="loadPreset('safety')">
                            <span>🚫</span> Safety Rejection
                        </button>
                    </div>
                </div>

                <form id="dispatch-form" onsubmit="handleDispatchSubmit(event)">
                    <div class="form-group">
                        <label class="form-label" for="input-location">Location (Portland Metro Bounding Box)</label>
                        <input class="form-input" id="input-location" type="text" required placeholder="e.g. 1005 W Burnside St, Portland, OR" />
                    </div>

                    <div class="form-group">
                        <label class="form-label" for="input-questions">Specific Checklist Questions (1 per line)</label>
                        <textarea class="form-textarea" id="input-questions" rows="3" placeholder="Confirm if main entrance doors are unlocked.&#10;Photograph posted operating hours plaque."></textarea>
                    </div>

                    <div class="form-group">
                        <label class="form-label" for="input-purpose">Stated Agent Purpose</label>
                        <input class="form-input" id="input-purpose" type="text" value="Developer Sandbox Verification" />
                    </div>

                    <div style="display: flex; gap: 12px;">
                        <div class="form-group" style="flex: 1;">
                            <label class="form-label" for="input-client">Client ID</label>
                            <input class="form-input" id="input-client" type="text" value="sandbox_developer" />
                        </div>
                        <div class="form-group" style="flex: 1;">
                            <label class="form-label">Strict Rejection Mode</label>
                            <div style="padding-top: 8px;">
                                <label style="font-size: 0.85rem; color: var(--text-muted); cursor: pointer; display: flex; align-items: center; gap: 6px;">
                                    <input type="checkbox" id="input-strict" checked /> Trigger HTTP 400 on error
                                </label>
                            </div>
                        </div>
                    </div>

                    <button type="submit" class="submit-btn" id="btn-submit">
                        <span id="btn-spinner" class="spinner" style="display: none;"></span>
                        <span id="btn-text">🚀 Dispatch Physical Verification</span>
                    </button>

                    <!-- Alert Banner -->
                    <div class="alert-banner" id="alert-banner">
                        <span id="alert-icon">⚠️</span>
                        <span id="alert-msg"></span>
                    </div>
                </form>

                <!-- Fleet Operators Summary -->
                <div style="margin-top: 20px; border-top: 1px solid var(--border-subtle); padding-top: 14px;">
                    <div class="preset-label">Available Multi-Operator Fleet Registry</div>
                    <div class="fleet-badge-list" id="fleet-badge-list">
                        <div class="fleet-badge active-op"><span>👤</span> Tobias #001 (Central Portland)</div>
                        <div class="fleet-badge active-op"><span>👤</span> Sarah K. (West Washington)</div>
                        <div class="fleet-badge active-op"><span>👤</span> Marcus T. (East Multnomah)</div>
                        <div class="fleet-badge active-op"><span>👤</span> Elena R. (South Clackamas)</div>
                    </div>
                </div>
            </div>

            <!-- Right: Visual Task Lifecycle Stepper -->
            <div class="card">
                <div class="card-header">
                    <div class="card-title">
                        <span>⏱️</span>
                        <span>Visual Task Lifecycle Stepper</span>
                    </div>
                    <span id="active-task-badge" style="font-family: var(--font-mono); font-size: 0.8rem; color: var(--text-dim);">Awaiting Dispatch</span>
                </div>

                <div class="stepper-container" id="stepper">
                    <div class="step-row" id="step-1">
                        <div class="step-icon">1</div>
                        <div class="step-details">
                            <div class="step-title">Dispatched</div>
                            <div class="step-sub" id="step-1-sub">Task received, geofenced & assigned to fleet zone</div>
                        </div>
                    </div>
                    <div class="step-row" id="step-2">
                        <div class="step-icon">2</div>
                        <div class="step-details">
                            <div class="step-title">Operator Review</div>
                            <div class="step-sub" id="step-2-sub">15-minute review window & SLA lock evaluation</div>
                        </div>
                    </div>
                    <div class="step-row" id="step-3">
                        <div class="step-icon">3</div>
                        <div class="step-details">
                            <div class="step-title">Accepted</div>
                            <div class="step-sub" id="step-3-sub">Operator accepted dispatch & locked route</div>
                        </div>
                    </div>
                    <div class="step-row" id="step-4">
                        <div class="step-icon">4</div>
                        <div class="step-details">
                            <div class="step-title">In-Transit</div>
                            <div class="step-sub" id="step-4-sub">Field agent en route to target coordinates</div>
                        </div>
                    </div>
                    <div class="step-row" id="step-5">
                        <div class="step-icon">5</div>
                        <div class="step-details">
                            <div class="step-title">Photo Captured</div>
                            <div class="step-sub" id="step-5-sub">Physical evidence placard photographed on-site</div>
                        </div>
                    </div>
                    <div class="step-row" id="step-6">
                        <div class="step-icon">6</div>
                        <div class="step-details">
                            <div class="step-title">Gemini Vision Inspection</div>
                            <div class="step-sub" id="step-6-sub">Automated multimodal verification of posted signage</div>
                        </div>
                    </div>
                    <div class="step-row" id="step-7">
                        <div class="step-icon">7</div>
                        <div class="step-details">
                            <div class="step-title">Proof Certificate</div>
                            <div class="step-sub" id="step-7-sub">Cryptographic metadata stripped & signed result ready</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- Proof Inspector Section (Visible on Completion) -->
        <section class="card proof-inspector-wrapper" id="proof-inspector-wrapper">
            <div class="card-header">
                <div class="card-title">
                    <span>🔍</span>
                    <span>Proof Inspector & Verifiable Credential</span>
                </div>
                <div style="display: flex; gap: 8px;">
                    <button class="preset-btn" onclick="downloadProofCertificate()">📥 Download Certificate (.json)</button>
                </div>
            </div>

            <div class="proof-grid">
                <!-- Left: Verifiable Photo Proof -->
                <div class="proof-image-card">
                    <div class="proof-image-wrapper">
                        <span class="proof-overlay-tag">✓ GPS & TIME SIGNED</span>
                        <img id="proof-image" src="" alt="Ground Truth Photographic Proof" />
                    </div>
                    <div class="proof-image-meta">
                        <span id="proof-photo-device">Device: GroundTruth Cam</span>
                        <span id="proof-photo-gps">GPS: 45.5231° N, 122.6816° W</span>
                    </div>
                </div>

                <!-- Right: Extracted Findings & Data -->
                <div class="proof-data-card">
                    <div>
                        <div class="preset-label">Operator Field Notes</div>
                        <p id="proof-operator-notes" style="font-size: 0.9rem; color: #e2e8f0; margin-bottom: 12px;"></p>
                    </div>

                    <div>
                        <div class="preset-label">Verified Checklist Findings</div>
                        <div id="proof-checklist-items"></div>
                    </div>

                    <div>
                        <div class="preset-label">Raw Attestation Payload (JSON)</div>
                        <pre class="json-viewer" id="proof-raw-json"></pre>
                    </div>
                </div>
            </div>
        </section>
    </div>

    <script>
        let currentPollingInterval = null;
        let lastCompletedTaskData = null;

        // Presets Definition
        const PRESETS = {
            core: {
                location: "Powell's City of Books, 1005 W Burnside St, Portland, OR 97209",
                questions: "Confirm if main Burnside entrance doors are unlocked and active.\\nPhotograph posted store hours plaque beside entrance.",
                purpose: "Commercial ground truth audit of downtown Portland retail hub"
            },
            suburb: {
                location: "Nike World Headquarters, 1 Bowerman Dr, Beaverton, OR 97005",
                questions: "Verify main security access gate is operational.\\nConfirm visitor registration checkpoint status.",
                purpose: "Suburban enterprise campus verification (West Washington zone)"
            },
            geofence: {
                location: "Times Square, New York, NY 10036",
                questions: "Verify billboard advertisement status.",
                purpose: "Testing out-of-coverage bounds rejection"
            },
            safety: {
                location: "Track blue sedan license plate at private residence",
                questions: "Identify vehicle owner and follow movements.",
                purpose: "Surveillance test to verify safety policy enforcement"
            }
        };

        function loadPreset(key) {
            const p = PRESETS[key];
            if (!p) return;
            document.getElementById("input-location").value = p.location;
            document.getElementById("input-questions").value = p.questions;
            document.getElementById("input-purpose").value = p.purpose;
            hideAlert();
        }

        // Initialize state monitor on page load
        async function fetchProtocolState() {
            try {
                const res = await fetch("/sandbox/api/state");
                if (res.ok) {
                    const data = await res.json();
                    if (data.mock_operator_mode) {
                        document.getElementById("mode-text").innerHTML = "⚡ Mock Mode Active";
                        document.getElementById("mode-text").style.color = "var(--accent-sky)";
                    } else {
                        document.getElementById("mode-text").innerHTML = "🛰️ Live Field Mode";
                        document.getElementById("mode-text").style.color = "var(--accent-emerald)";
                    }

                    if (data.operator_count) {
                        document.getElementById("fleet-count-text").innerText = `${data.operator_count} Registered (${data.available_operator_count || data.operator_count} Ready)`;
                    }

                    // Render fleet badges
                    if (data.operators && data.operators.length > 0) {
                        const container = document.getElementById("fleet-badge-list");
                        container.innerHTML = "";
                        data.operators.forEach(op => {
                            const badge = document.createElement("div");
                            badge.className = `fleet-badge ${op.status === 'available' ? 'active-op' : ''}`;
                            badge.innerHTML = `<span>👤</span> ${op.name} (${op.zone})`;
                            container.appendChild(badge);
                        });
                    }
                }
            } catch (err) {
                console.warn("Could not poll protocol state:", err);
            }
        }

        function showAlert(msg, isError = true) {
            const banner = document.getElementById("alert-banner");
            const icon = document.getElementById("alert-icon");
            const text = document.getElementById("alert-msg");
            banner.className = `alert-banner ${isError ? 'error' : ''}`;
            icon.innerText = isError ? "🚫" : "ℹ️";
            text.innerText = msg;
            banner.style.display = "flex";
        }

        function hideAlert() {
            document.getElementById("alert-banner").style.display = "none";
        }

        function resetStepper() {
            for (let i = 1; i <= 7; i++) {
                const el = document.getElementById(`step-${i}`);
                el.className = "step-row";
            }
            document.getElementById("proof-inspector-wrapper").style.display = "none";
        }

        function setStepState(stepNum, state) {
            // state: 'pending', 'active', 'completed'
            const el = document.getElementById(`step-${stepNum}`);
            if (!el) return;
            el.className = `step-row ${state}`;
        }

        async function handleDispatchSubmit(e) {
            e.preventDefault();
            hideAlert();
            resetStepper();
            if (currentPollingInterval) clearInterval(currentPollingInterval);

            const location = document.getElementById("input-location").value.trim();
            const questionsRaw = document.getElementById("input-questions").value.trim();
            const questions = questionsRaw ? questionsRaw.split("\\n").filter(q => q.trim().length > 0) : ["Verify physical premises status."];
            const stated_purpose = document.getElementById("input-purpose").value.trim();
            const client_id = document.getElementById("input-client").value.trim() || "sandbox_developer";
            const strict = document.getElementById("input-strict").checked;

            const submitBtn = document.getElementById("btn-submit");
            const spinner = document.getElementById("btn-spinner");
            const btnText = document.getElementById("btn-text");

            submitBtn.disabled = true;
            spinner.style.display = "inline-block";
            btnText.innerText = "Dispatching...";

            try {
                const payload = {
                    location: location,
                    specific_questions: questions,
                    stated_purpose: stated_purpose,
                    client_id: client_id,
                    strict: strict
                };

                const res = await fetch("/v1/dispatch/verify?strict=" + strict, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });

                if (!res.ok) {
                    const errorJson = await res.json().catch(() => ({}));
                    const detail = errorJson.detail || `Dispatch Error (HTTP ${res.status})`;
                    showAlert(`HTTP ${res.status}: ${detail}`);
                    document.getElementById("active-task-badge").innerText = `Rejected (HTTP ${res.status})`;
                    document.getElementById("active-task-badge").style.color = "var(--accent-rose)";
                    return;
                }

                const data = await res.json();
                if (data.status === "rejected_out_of_coverage") {
                    showAlert(`Geofence Rejection: ${data.error}`);
                    document.getElementById("active-task-badge").innerText = "Out of Coverage";
                    document.getElementById("active-task-badge").style.color = "var(--accent-rose)";
                    return;
                }
                if (data.status === "rejected_safety_policy") {
                    showAlert(`Safety Policy Rejection: ${data.error}`);
                    document.getElementById("active-task-badge").innerText = "Safety Policy Rejection";
                    document.getElementById("active-task-badge").style.color = "var(--accent-rose)";
                    return;
                }

                // Dispatched successfully!
                const taskId = data.task_id;
                document.getElementById("active-task-badge").innerText = `Task: ${taskId}`;
                document.getElementById("active-task-badge").style.color = "var(--accent-sky)";

                // Start stepper progression and polling
                startTaskPolling(taskId);

            } catch (err) {
                showAlert(`Network / Dispatch Exception: ${err.message}`);
            } finally {
                submitBtn.disabled = false;
                spinner.style.display = "none";
                btnText.innerText = "🚀 Dispatch Physical Verification";
            }
        }

        function startTaskPolling(taskId) {
            setStepState(1, "completed");
            setStepState(2, "active");

            currentPollingInterval = setInterval(async () => {
                try {
                    const res = await fetch(`/v1/tasks/${taskId}`);
                    if (!res.ok) return;
                    const task = await res.json();

                    if (task.status === "pending_operator_review") {
                        setStepState(1, "completed");
                        setStepState(2, "active");
                    } else if (task.status === "accepted_in_progress") {
                        setStepState(1, "completed");
                        setStepState(2, "completed");
                        setStepState(3, "completed");
                        setStepState(4, "active");
                    } else if (task.status === "completed") {
                        clearInterval(currentPollingInterval);
                        currentPollingInterval = null;

                        // Animate all steps to complete
                        for (let i = 1; i <= 7; i++) {
                            setStepState(i, "completed");
                        }

                        document.getElementById("active-task-badge").innerText = `✓ Verified (${taskId})`;
                        document.getElementById("active-task-badge").style.color = "var(--accent-emerald)";

                        // Render proof inspector
                        renderProofInspector(task);
                    } else if (task.status.includes("rejected") || task.status.includes("declined") || task.status.includes("expired")) {
                        clearInterval(currentPollingInterval);
                        currentPollingInterval = null;
                        document.getElementById("active-task-badge").innerText = `Ended (${task.status})`;
                        document.getElementById("active-task-badge").style.color = "var(--accent-rose)";
                        showAlert(`Task status: ${task.status}. Reason: ${task.decline_reason || 'Declined'}`);
                    }
                } catch (err) {
                    console.error("Error polling task:", err);
                }
            }, 800);
        }

        function renderProofInspector(task) {
            lastCompletedTaskData = task;
            const inspector = document.getElementById("proof-inspector-wrapper");
            inspector.style.display = "block";

            // Photo
            const img = document.getElementById("proof-image");
            img.src = task.photo_url || `/v1/tasks/${task.task_id}/photo`;

            // Meta
            if (task.photo_metadata) {
                const meta = task.photo_metadata;
                document.getElementById("proof-photo-device").innerText = `Device: ${meta.device || 'Verified Sensor Node'}`;
                if (meta.gps) {
                    document.getElementById("proof-photo-gps").innerText = `GPS: ${meta.gps.latitude || 45.5231}° N, ${meta.gps.longitude || -122.6816}° W`;
                }
            }

            // Answers
            const answers = task.extracted_answers || {};
            document.getElementById("proof-operator-notes").innerText = answers.operator_notes || "Field inspection confirmed physically on-site.";

            const checklistContainer = document.getElementById("proof-checklist-items");
            checklistContainer.innerHTML = "";

            const vision = answers.vision_analysis || {};
            const items = vision.checklist_results || [];

            if (items.length > 0) {
                items.forEach(item => {
                    const el = document.createElement("div");
                    el.className = "qa-item";
                    el.innerHTML = `
                        <div class="qa-q">✓ ${item.question}</div>
                        <div class="qa-a">${item.answer}</div>
                        <div class="qa-ev">${item.evidence_visible || ''}</div>
                    `;
                    checklistContainer.appendChild(el);
                });
            } else {
                checklistContainer.innerHTML = `<p style="font-size: 0.85rem; color: var(--text-dim);">Physical verification complete.</p>`;
            }

            // Raw JSON
            document.getElementById("proof-raw-json").innerText = JSON.stringify(task, null, 2);

            // Scroll down smoothly to inspector
            inspector.scrollIntoView({ behavior: "smooth" });
        }

        function downloadProofCertificate() {
            if (!lastCompletedTaskData) return;
            const blob = new Blob([JSON.stringify(lastCompletedTaskData, null, 2)], { type: "application/json" });
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `groundtruth_proof_${lastCompletedTaskData.task_id}.json`;
            a.click();
            URL.revokeObjectURL(url);
        }

        // Auto load on start
        window.addEventListener("DOMContentLoaded", () => {
            fetchProtocolState();
            // Default preset
            loadPreset("core");
        });
    </script>
</body>
</html>
"""
