"""Client intake form for commercial real estate analysts and partners."""

def get_intake_html() -> str:
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GroundTruth Protocol // Direct Commercial Verification Intake</title>
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🎯</text></svg>">
    <style>
        :root {
            --bg-void: #05080C;
            --surface-panel: #0B111A;
            --surface-inset: #070B10;
            --cyan-accent: #38BDF8;
            --cyan-dim: #0284C7;
            --text-main: #F1F5F9;
            --text-muted: #94A3B8;
            --border-dim: #1E293B;
            --border-glow: #38BDF8;
            --amber-warn: #F59E0B;
            --emerald-pass: #10B981;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
            background-color: var(--bg-void);
            color: var(--text-main);
            padding: 30px 20px;
            display: flex;
            justify-content: center;
        }

        .container {
            width: 100%;
            max-width: 680px;
            background: var(--surface-panel);
            border: 1px solid var(--border-dim);
            border-radius: 12px;
            padding: 32px;
            box-shadow: 0 12px 30px rgba(0,0,0,0.7);
        }

        .badge {
            display: inline-block;
            background: rgba(56, 189, 248, 0.1);
            color: var(--cyan-accent);
            border: 1px solid rgba(56, 189, 248, 0.3);
            padding: 4px 10px;
            border-radius: 16px;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            margin-bottom: 12px;
        }

        h1 {
            font-size: 1.5rem;
            color: var(--text-main);
            margin-bottom: 6px;
        }

        p.subtitle {
            font-size: 0.9rem;
            color: var(--text-muted);
            margin-bottom: 24px;
            line-height: 1.5;
        }

        .alert-box {
            background: rgba(16, 185, 129, 0.08);
            border-left: 4px solid var(--emerald-pass);
            padding: 12px 16px;
            border-radius: 4px;
            font-size: 0.85rem;
            color: #A7F3D0;
            margin-bottom: 24px;
        }

        .form-group {
            margin-bottom: 20px;
        }

        label {
            display: block;
            font-size: 0.85rem;
            font-weight: 600;
            color: #CBD5E1;
            margin-bottom: 8px;
        }

        label span.req { color: #EF4444; }

        input[type="text"], input[type="email"], textarea {
            width: 100%;
            background: var(--surface-inset);
            border: 1px solid var(--border-dim);
            border-radius: 6px;
            padding: 12px 14px;
            color: var(--text-main);
            font-family: inherit;
            font-size: 0.95rem;
            transition: border-color 0.2s, box-shadow 0.2s;
        }

        input:focus, textarea:focus {
            outline: none;
            border-color: var(--border-glow);
            box-shadow: 0 0 0 2px rgba(56, 189, 248, 0.2);
        }

        .helper-text {
            font-size: 0.75rem;
            color: var(--text-muted);
            margin-top: 5px;
        }

        button.submit-btn {
            width: 100%;
            background: var(--cyan-accent);
            color: #020617;
            border: none;
            border-radius: 6px;
            padding: 14px 20px;
            font-size: 1rem;
            font-weight: 700;
            cursor: pointer;
            transition: background 0.2s, transform 0.1s;
            margin-top: 10px;
        }

        button.submit-btn:hover {
            background: #7DD3FC;
        }

        button.submit-btn:active {
            transform: scale(0.99);
        }

        .result-box {
            display: none;
            margin-top: 24px;
            padding: 18px;
            border-radius: 8px;
            background: var(--surface-inset);
            border: 1px solid var(--border-dim);
            font-size: 0.9rem;
        }

        .sla-pills {
            display: flex;
            gap: 12px;
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid var(--border-dim);
            font-size: 0.8rem;
            color: var(--text-muted);
        }

        .sla-pill {
            display: flex;
            align-items: center;
            gap: 6px;
        }
    </style>
</head>
<body>
    <div class="container">
        <span class="badge">Node #001: Portland Metro</span>
        <h1>Commission Physical Site Verification</h1>
        <p class="subtitle">Dispatches a verified on-foot local operator to photograph the property, inspect exterior tenant notices, and return cryptographically stamped ground truth.</p>

        <div class="alert-box">
            ⚡ <strong>Founder-Fulfilled Testing SLA:</strong> Free pilot verification for Pacific Northwest CRE acquisition analysts & retail underwriters. Sub-2 hour delivery.
        </div>

        <form id="intakeForm" onsubmit="submitIntake(event)">
            <div class="form-group">
                <label>Commercial Address <span class="req">*</span></label>
                <input type="text" id="addressInput" required placeholder="e.g. 1005 W Burnside St, Portland, OR 97209">
                <div class="helper-text">Currently serving Multnomah, Washington, and Clackamas County corridors.</div>
            </div>

            <div class="form-group">
                <label>Questions / What Must Be Verified <span class="req">*</span></label>
                <textarea id="questionsInput" rows="3" required placeholder="1. Is the tenant currently open or dark?&#10;2. Is there a leasing sign or eviction notice taped to the entrance?&#10;3. Does the parking lot appear repaved or damaged?"></textarea>
                <div class="helper-text">List 1 to 3 specific, checkable questions for the operator to photograph and answer.</div>
            </div>

            <div class="form-group">
                <label>Delivery Email Address <span class="req">*</span></label>
                <input type="email" id="emailInput" required placeholder="analyst@firm.com">
                <div class="helper-text">The structured report, high-res photos, and EXIF proof bundle will be sent here upon completion.</div>
            </div>

            <button type="submit" class="submit-btn" id="submitBtn">⚡ Dispatch Field Operator (Free Pilot)</button>
        </form>

        <div class="result-box" id="resultBox"></div>

        <div class="sla-pills">
            <div class="sla-pill">🔒 Cryptographic EXIF Proof</div>
            <div class="sla-pill">⏱️ Sub-2-Hour Delivery</div>
            <div class="sla-pill">🛡️ Strict Privacy Guardrails</div>
        </div>
    </div>

    <script>
        async function submitIntake(e) {
            e.preventDefault();
            const btn = document.getElementById("submitBtn");
            const resBox = document.getElementById("resultBox");
            const address = document.getElementById("addressInput").value.trim();
            const rawQs = document.getElementById("questionsInput").value.trim();
            const email = document.getElementById("emailInput").value.trim();

            const questions = rawQs.split(/\\n+/).map(q => q.replace(/^[0-9]+[.)-]\\s*/, '').trim()).filter(Boolean);

            btn.disabled = true;
            btn.textContent = "Dispatched to LangGraph Orchestrator...";
            resBox.style.display = "none";

            try {
                const response = await fetch("/v1/dispatch/verify", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        location: address,
                        specific_questions: questions.length ? questions : [rawQs],
                        stated_purpose: "CRE Due Diligence Intake (Client: " + email + ")",
                        client_id: "intake_" + email.replace(/[^a-zA-Z0-9]/g, "_")
                    })
                });

                const data = await response.json();
                resBox.style.display = "block";

                if (response.ok) {
                    resBox.style.border = "1px solid #10B981";
                    resBox.innerHTML = `
                        <h3 style="color:#34D399; margin-bottom:8px;">✅ Task Dispatched Successfully</h3>
                        <p><strong>Task ID:</strong> <code>${data.task_id}</code></p>
                        <p><strong>Assigned Fleet Zone:</strong> ${data.zone || 'Portland Central'}</p>
                        <p><strong>Status:</strong> ${data.status}</p>
                        <p style="margin-top:10px; color:#94A3B8;">A local operator has received your request. The verified report will be delivered directly to <strong>${email}</strong> upon completion.</p>
                    `;
                } else {
                    resBox.style.border = "1px solid #EF4444";
                    resBox.innerHTML = `
                        <h3 style="color:#F87171; margin-bottom:8px;">⚠️ Dispatch Failed</h3>
                        <p>${data.detail || data.error || 'Request could not be fulfilled.'}</p>
                    `;
                }
            } catch (err) {
                resBox.style.display = "block";
                resBox.style.border = "1px solid #EF4444";
                resBox.innerHTML = `<h3 style="color:#F87171;">⚠️ Network Error</h3><p>${err.message}</p>`;
            } finally {
                btn.disabled = false;
                btn.textContent = "⚡ Dispatch Field Operator (Free Pilot)";
            }
        }
    </script>
</body>
</html>
"""
