// Global Variables
let chatSocket = null;
let telemetrySocket = null;
let tempChart = null;
let currentSessionId = 's1';

const maxChartDataPoints = 30;
const nozzleTempData = [];
const bedTempData = [];
const chartLabels = [];

// Initialize Chart.js with beautiful Stitch styles
function initChart() {
    const ctx = document.getElementById('tempChart').getContext('2d');
    tempChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: chartLabels,
            datasets: [
                {
                    label: 'Nozzle (°C)',
                    data: nozzleTempData,
                    borderColor: '#f43f5e', // red-500
                    backgroundColor: 'rgba(244, 63, 94, 0.05)',
                    borderWidth: 2,
                    tension: 0.3,
                    fill: true,
                    pointRadius: 0
                },
                {
                    label: 'Bed (°C)',
                    data: bedTempData,
                    borderColor: '#ffb95f', // tertiary/amber
                    backgroundColor: 'rgba(255, 185, 95, 0.05)',
                    borderWidth: 2,
                    tension: 0.3,
                    fill: true,
                    pointRadius: 0
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: { display: false },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.04)' },
                    ticks: { color: '#c5c6cd', font: { size: 9 } }
                }
            }
        }
    });
}

// Update Temperature Chart with live readings
function updateChart(nozzle, bed) {
    const now = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    chartLabels.push(now);
    nozzleTempData.push(nozzle);
    bedTempData.push(bed);

    if (chartLabels.length > maxChartDataPoints) {
        chartLabels.shift();
        nozzleTempData.shift();
        bedTempData.shift();
    }
    if (tempChart) {
        tempChart.update();
    }
}

// Establish WebSockets connections
function connectSockets() {
    const loc = window.location;
    const wsProto = loc.protocol === "https:" ? "wss:" : "ws:";
    
    // Clean up existing socket references before reconnecting to prevent leaks
    if (chatSocket) {
        try {
            chatSocket.onclose = null;
            chatSocket.onerror = null;
            chatSocket.close();
        } catch(e) {}
    }
    if (telemetrySocket) {
        try {
            telemetrySocket.onclose = null;
            telemetrySocket.onerror = null;
            telemetrySocket.close();
        } catch(e) {}
    }
    
    let reconnectTimeout = null;
    const triggerReconnect = () => {
        updateStatusBadge(false);
        if (!reconnectTimeout) {
            reconnectTimeout = setTimeout(() => {
                reconnectTimeout = null;
                connectSockets();
            }, 3000);
        }
    };
    
    // 1. Chat Connection
    chatSocket = new WebSocket(`${wsProto}//${loc.host}/ws/chat?session_id=${currentSessionId}`);
    
    chatSocket.onopen = () => {
        updateStatusBadge(true);
        // Refresh data on reconnect so dashboard/telemetry isn't stale
        fetchAndRenderFleetMatrix();
        fetchSpoolmanInventory();
    };
    
    chatSocket.onclose = () => {
        triggerReconnect();
    };
    
    chatSocket.onerror = () => {
        triggerReconnect();
    };
    
    chatSocket.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        handleChatMessage(payload);
    };

    // 2. Telemetry Connection
    telemetrySocket = new WebSocket(`${wsProto}//${loc.host}/ws/telemetry`);
    
    telemetrySocket.onclose = () => {
        triggerReconnect();
    };
    
    telemetrySocket.onerror = () => {
        triggerReconnect();
    };
    
    telemetrySocket.onmessage = (event) => {
        const payload = JSON.parse(event.data);
        if (payload.type === "telemetry") {
            handleTelemetry(payload.data);
        } else if (payload.type === "telemetry_error") {
            showErrorToast(payload.message);
        }
    };
}

// Update Header Connection Badge
function updateStatusBadge(connected) {
    const badge = document.getElementById('status-badge');
    if (!badge) return;
    if (connected) {
        badge.className = "badge badge-connected";
        badge.innerHTML = `<i class="fa-solid fa-check"></i> Connected`;
    } else {
        badge.className = "badge badge-disconnected";
        badge.innerHTML = `<i class="fa-solid fa-circle-xmark animate-pulse"></i> Reconnecting...`;
    }
}

// Handle real-time telemetry streaming
let amsStatus = []; // Keep track of current AMS slots for the safety confirmation card
function handleTelemetry(data) {
    amsStatus = data.ams_slots || [];
    
    // Update active printer card in the fleet matrix
    const activeCard = document.querySelector('#fleet-matrix .border-secondary');
    if (activeCard) {
        const badge = activeCard.querySelector('.state-badge');
        if (badge) {
            badge.innerText = data.state;
            badge.className = `state-badge px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                data.state === 'printing' ? 'bg-secondary/10 text-secondary' : 
                (data.state === 'idle' ? 'bg-surface-container-highest text-on-surface-variant' : 'bg-error-container/10 text-error')
            }`;
        }
        const temps = activeCard.querySelector('.text-xs.font-mono-label');
        if (temps) {
            temps.innerHTML = `
                <span>Nozzle: ${Math.round(data.nozzle_temp)}°C</span>
                <span>Bed: ${Math.round(data.bed_temp)}°C</span>
            `;
        }
    }

    // 1. Update Right Sidebar Telemetry elements
    const stateEl = document.getElementById('printer-state');
    if (stateEl) {
        stateEl.innerText = data.state;
        updateStateColor(stateEl, data.state);
    }
    const fileEl = document.getElementById('active-file');
    if (fileEl) fileEl.innerText = data.active_file || "None";
    
    const progressTextEl = document.getElementById('progress-text');
    if (progressTextEl) progressTextEl.innerText = `${Math.round(data.percent_complete)}%`;
    
    const progressBarEl = document.getElementById('progress-bar');
    if (progressBarEl) progressBarEl.style.width = `${data.percent_complete}%`;

    const nozzleTempEl = document.getElementById('nozzle-temp');
    if (nozzleTempEl) nozzleTempEl.innerText = data.nozzle_temp.toFixed(1);
    
    const targetNozzleTempEl = document.getElementById('target-nozzle-temp');
    if (targetNozzleTempEl) targetNozzleTempEl.innerText = data.target_nozzle_temp.toFixed(0);

    const bedTempEl = document.getElementById('bed-temp');
    if (bedTempEl) bedTempEl.innerText = data.bed_temp.toFixed(1);
    
    const targetBedTempEl = document.getElementById('target-bed-temp');
    if (targetBedTempEl) targetBedTempEl.innerText = data.target_bed_temp.toFixed(0);

    // 2. Update Dashboard view elements
    const dashStateEl = document.getElementById('dashboard-state');
    if (dashStateEl) {
        dashStateEl.innerText = data.state;
        updateStateColor(dashStateEl, data.state);
    }
    
    const dashStateBadgeEl = document.getElementById('dashboard-state-badge');
    if (dashStateBadgeEl) {
        dashStateBadgeEl.innerText = data.state;
        updateBadgeStateColor(dashStateBadgeEl, data.state);
    }

    const dashFileEl = document.getElementById('dashboard-active-file');
    if (dashFileEl) dashFileEl.innerText = data.active_file || "No active print job";

    const dashProgressTextEl = document.getElementById('dashboard-progress-text');
    if (dashProgressTextEl) dashProgressTextEl.innerText = `${Math.round(data.percent_complete)}%`;
    
    const dashProgressBarEl = document.getElementById('dashboard-progress-bar');
    if (dashProgressBarEl) dashProgressBarEl.style.width = `${data.percent_complete}%`;

    const dashNozzleEl = document.getElementById('dashboard-nozzle');
    if (dashNozzleEl) dashNozzleEl.innerText = data.nozzle_temp.toFixed(1);

    const dashBedEl = document.getElementById('dashboard-bed');
    if (dashBedEl) dashBedEl.innerText = data.bed_temp.toFixed(1);

    // 3. Update Chart
    updateChart(data.nozzle_temp, data.bed_temp);

    // 4. Update AMS Grid
    const amsGrid = document.getElementById('ams-slots-grid');
    if (amsGrid) {
        amsGrid.innerHTML = '';
        (data.ams_slots || []).forEach(slot => {
            const hasSpool = slot.material !== "";
            const colorCircle = hasSpool ? `<span class="spool-indicator" style="background-color: ${slot.color}"></span>` : `<span class="spool-indicator" style="background-color: #1e293b; border-style: dashed; border-width: 1px;"></span>`;
            const material = hasSpool ? slot.material : "Empty";
            const weight = hasSpool ? `${slot.weight_g.toFixed(0)}g` : "N/A";
            
            const card = document.createElement('div');
            card.className = "flex flex-col items-center justify-center bg-surface-container/60 p-2 rounded-xl border border-outline-variant/30 text-center";
            card.innerHTML = `
                <span class="text-[9px] font-mono-label text-on-surface-variant">S${slot.slot}</span>
                ${colorCircle}
                <span class="text-[10px] font-bold text-on-surface mt-1 truncate max-w-full">${material}</span>
                <span class="text-[9px] text-on-surface-variant font-mono-label">${weight}</span>
            `;
            amsGrid.appendChild(card);
        });
    }
}

// State color helper (Text element)
function updateStateColor(element, state) {
    state = (state || "").toLowerCase();
    if (state === "printing") {
        element.style.color = "#6bd8cb"; // teal
    } else if (state === "paused" || state.includes("heating") || state === "cooldown") {
        element.style.color = "#ffb95f"; // amber
    } else if (state === "error" || state === "offline") {
        element.style.color = "#ffb4ab"; // red
    } else {
        element.style.color = "#bcc7de"; // slate
    }
}

// State color helper (Badge element)
function updateBadgeStateColor(element, state) {
    state = (state || "").toLowerCase();
    element.className = "px-3 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ";
    if (state === "printing") {
        element.className += "bg-secondary/20 text-secondary border border-secondary/30";
    } else if (state === "paused" || state.includes("heating") || state === "cooldown") {
        element.className += "bg-tertiary/20 text-tertiary border border-tertiary/30";
    } else if (state === "error" || state === "offline") {
        element.className += "bg-error/20 text-error border border-error/30";
    } else {
        element.className += "bg-surface-container-highest text-on-surface-variant border border-outline-variant/30";
    }
}

// Render styled cards for agent status and file-list responses
function renderStyledChatContent(text) {
    if (!text) return null;
    
    // Detect Printer Status response
    const statusMatch = text.match(/Printer Status:\s*\nState:\s*(.+)\s*\nNozzle:\s*([\d.]+)°C\s*\(Target:\s*([\d.]+)°C\)\s*\nBed:\s*([\d.]+)°C\s*\(Target:\s*([\d.]+)°C\)\s*\nProgress:\s*([\d.]+)%\s*\nActive File:\s*(.*)/);
    if (statusMatch) {
        const [, state, nozzle, nozzleTarget, bed, bedTarget, progress, activeFile] = statusMatch;
        const stateNorm = (state || "").trim().toLowerCase();
        
        let stateColor = "#bcc7de";
        let stateBg = "rgba(188,199,222,0.12)";
        if (stateNorm === "printing") { stateColor = "#6bd8cb"; stateBg = "rgba(107,216,203,0.12)"; }
        else if (stateNorm === "pause" || stateNorm === "paused") { stateColor = "#ffb95f"; stateBg = "rgba(255,185,95,0.12)"; }
        else if (stateNorm === "error") { stateColor = "#ffb4ab"; stateBg = "rgba(255,180,171,0.12)"; }

        return `
            <div class="chat-status-card">
                <div class="status-header">
                    <div style="display:flex;align-items:center;gap:6px;">
                        <span class="material-symbols-outlined" style="font-size:16px;color:${stateColor}">print</span>
                        <span style="font-size:11px;font-weight:800;letter-spacing:0.06em;text-transform:uppercase;color:var(--md-sys-color-primary,#bcc7de)">Printer Status</span>
                    </div>
                    <span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:6px;text-transform:uppercase;background:${stateBg};color:${stateColor};letter-spacing:0.05em">${state.trim()}</span>
                </div>
                <div style="display:flex;gap:8px;justify-content:center;">
                    <div class="temp-gauge">
                        <span class="temp-label">Nozzle</span>
                        <span class="temp-value" style="color:#f43f5e">${parseFloat(nozzle).toFixed(0)}°</span>
                        <span class="temp-target">Target ${parseFloat(nozzleTarget).toFixed(0)}°C</span>
                    </div>
                    <div class="temp-gauge">
                        <span class="temp-label">Bed</span>
                        <span class="temp-value" style="color:#ffb95f">${parseFloat(bed).toFixed(0)}°</span>
                        <span class="temp-target">Target ${parseFloat(bedTarget).toFixed(0)}°C</span>
                    </div>
                </div>
                <div class="progress-section">
                    <div style="display:flex;justify-content:space-between;align-items:baseline;">
                        <span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:0.06em;opacity:0.6">Progress</span>
                        <span style="font-size:16px;font-weight:800;color:#6bd8cb">${parseFloat(progress).toFixed(0)}%</span>
                    </div>
                    <div class="progress-track">
                        <div class="progress-fill" style="width:${progress}%"></div>
                    </div>
                    ${activeFile && activeFile.trim() ? `<div style="margin-top:6px;font-size:10px;opacity:0.5;word-break:break-all">📄 ${activeFile.trim()}</div>` : ''}
                </div>
            </div>
        `;
    }

    // Detect file listing response
    const filesMatch = text.match(/Available G-code files on server:\n([\s\S]+)/);
    if (filesMatch) {
        const filesBlock = filesMatch[1].trim();
        const lines = filesBlock.split('\n').filter(l => l.trim().startsWith('-'));
        
        if (lines.length === 0 || (lines.length === 1 && lines[0].includes("No files found"))) {
            return `
                <div class="chat-files-card">
                    <div style="display:flex;align-items:center;gap:6px;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid rgba(196,199,207,0.1)">
                        <span class="material-symbols-outlined" style="font-size:16px;color:var(--md-sys-color-secondary,#6bd8cb)">folder_open</span>
                        <span style="font-size:11px;font-weight:800;letter-spacing:0.06em;text-transform:uppercase;color:var(--md-sys-color-primary,#bcc7de)">G-code Files</span>
                    </div>
                    <div style="font-size:12px;opacity:0.5;font-style:italic">No files found on the server.</div>
                </div>
            `;
        }
        
        let fileItemsHtml = '';
        lines.forEach(line => {
            const name = line.replace(/^-\s*/, '').trim();
            fileItemsHtml += `
                <div class="file-item">
                    <span class="material-symbols-outlined" style="font-size:16px;color:var(--md-sys-color-secondary,#6bd8cb);flex-shrink:0">description</span>
                    <span style="font-size:11px;font-weight:600;color:var(--md-sys-color-on-surface,#e3e2e6);overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${name}</span>
                </div>
            `;
        });
        
        return `
            <div class="chat-files-card">
                <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid rgba(196,199,207,0.1)">
                    <div style="display:flex;align-items:center;gap:6px;">
                        <span class="material-symbols-outlined" style="font-size:16px;color:var(--md-sys-color-secondary,#6bd8cb)">folder</span>
                        <span style="font-size:11px;font-weight:800;letter-spacing:0.06em;text-transform:uppercase;color:var(--md-sys-color-primary,#bcc7de)">G-code Files</span>
                    </div>
                    <span style="font-size:10px;font-weight:700;padding:2px 8px;border-radius:6px;background:rgba(107,216,203,0.1);color:#6bd8cb">${lines.length} file${lines.length !== 1 ? 's' : ''}</span>
                </div>
                <div style="display:flex;flex-direction:column;gap:4px;">
                    ${fileItemsHtml}
                </div>
            </div>
        `;
    }

    return null;
}

// Append messages to Chat Container
function handleChatMessage(payload) {
    const chatHistory = document.getElementById('chat-history');
    if (!chatHistory) return;
    
    if (payload.type === "status") {
        const indicator = document.getElementById('typing-indicator');
        if (indicator) {
            indicator.style.display = payload.status === "thinking" ? "flex" : "none";
        }
        chatHistory.scrollTop = chatHistory.scrollHeight;
        return;
    }

    if (payload.type === "hitl_request") {
        const msgDiv = document.createElement('div');
        msgDiv.className = "chat-msg agent";
        const interrupt_id = payload.interrupt_id;
        
        let msgData = null;
        let isJson = false;
        
        if (payload.payload) {
            if (typeof payload.payload === 'string') {
                try {
                    msgData = JSON.parse(payload.payload);
                    isJson = true;
                } catch(e) {
                    msgData = {};
                }
            } else {
                msgData = payload.payload;
                isJson = true;
            }
        }
        
        if (!isJson && payload.message) {
            const trimmed = payload.message.trim();
            if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
                try {
                    msgData = JSON.parse(trimmed);
                    isJson = true;
                } catch (e) {
                    // Ignore, not valid json
                }
            }
        }
        
        if (!msgData) {
            msgData = { prompt: payload.message };
        }
        
        const promptText = msgData.prompt || payload.message || "Safety verification required.";

        let amsListHtml = '';
        let checkboxHtml = '';
        
        // Formatted print job details section
        let jobDetailsHtml = '';
        if (msgData.filename) {
            jobDetailsHtml += `
                <div class="mb-3 pb-2 border-b border-outline-variant/30 text-on-surface-variant font-mono-label text-[11px] space-y-1">
                    <div class="flex justify-between items-center">
                        <span class="text-[9px] uppercase font-bold tracking-wider text-secondary">File to Print:</span>
                        <span class="text-[11px] font-semibold text-on-surface select-all truncate max-w-[200px]" title="${msgData.filename}">${msgData.filename}</span>
                    </div>
            `;
            if (msgData.print_time) {
                jobDetailsHtml += `
                    <div class="flex justify-between items-center">
                        <span class="text-[9px] uppercase font-bold tracking-wider text-secondary">Est. Print Time:</span>
                        <span class="text-[11px] font-semibold text-on-surface">${msgData.print_time}</span>
                    </div>
                `;
            }
            if (msgData.filament_weight) {
                jobDetailsHtml += `
                    <div class="flex justify-between items-center">
                        <span class="text-[9px] uppercase font-bold tracking-wider text-secondary">Filament Required:</span>
                        <span class="text-[11px] font-semibold text-on-surface">${msgData.filament_weight}g</span>
                    </div>
                `;
            }
            if (msgData.plate_name) {
                jobDetailsHtml += `
                    <div class="flex justify-between items-center">
                        <span class="text-[9px] uppercase font-bold tracking-wider text-secondary">Plate Details:</span>
                        <span class="text-[11px] font-semibold text-on-surface">${msgData.plate_name} (Plate #${msgData.plate_id || 1})</span>
                    </div>
                `;
            }
            if (msgData.requested_bed_plate) {
                jobDetailsHtml += `
                    <div class="flex justify-between items-center">
                        <span class="text-[9px] uppercase font-bold tracking-wider text-secondary">Target Bed Plate:</span>
                        <span class="text-[11px] font-semibold text-primary">${msgData.requested_bed_plate}</span>
                    </div>
                `;
            }
            jobDetailsHtml += `</div>`;
        }
        
        amsListHtml += jobDetailsHtml;
        
        if (interrupt_id === "confirm_bed_cleared") {
            if (msgData.requested_filaments && msgData.requested_filaments.length > 0) {
                amsListHtml += `<div class="font-bold text-primary mb-2 text-[10px] uppercase tracking-wider">Sliced Filaments Mapping:</div>`;
                msgData.requested_filaments.forEach((req, idx) => {
                    let optionsHtml = '';
                    amsStatus.forEach(slot => {
                        if (slot.material) {
                            const isMatch = slot.material.toLowerCase() === req.type.toLowerCase();
                            optionsHtml += `<option value="${slot.slot - 1}" ${isMatch ? 'selected' : ''}>Slot ${slot.slot}: ${slot.material} (${slot.weight_g.toFixed(0)}g)</option>`;
                        }
                    });
                    optionsHtml += `<option value="-1">External Spool (No AMS)</option>`;
                    
                    amsListHtml += `
                        <div class="mb-2">
                            <div class="flex items-center gap-1.5 mb-1 text-[11px]">
                                <span class="spool-indicator" style="background-color: ${req.color}"></span>
                                <span>Virtual Slot ${req.slot_id}: <strong>${req.type}</strong> (${req.used_grams.toFixed(1)}g)</span>
                            </div>
                            <select class="chat-ams-select bg-surface-container-highest border border-outline-variant rounded p-1 text-[11px] text-on-surface w-full focus:ring-secondary" data-slot-id="${req.slot_id}">
                                ${optionsHtml}
                            </select>
                        </div>
                    `;
                });
            } else {
                amsStatus.forEach(slot => {
                    if (slot.material) {
                        amsListHtml += `<div><span class="spool-indicator" style="background-color: ${slot.color}"></span> Slot ${slot.slot}: ${slot.material} (${slot.weight_g.toFixed(0)}g)</div>`;
                    }
                });
                if (!amsListHtml) {
                    amsListHtml = '<div>No active AMS slots detected. Spool holder check required.</div>';
                }
            }
            
            checkboxHtml = `
                <label class="hitl-item flex items-center gap-2 select-none cursor-pointer">
                    <input type="checkbox" id="chk-bed" class="rounded border-outline-variant bg-surface-container-high focus:ring-secondary text-secondary">
                    <span>Confirm print bed is fully cleared.</span>
                </label>
                <label class="hitl-item flex items-center gap-2 select-none cursor-pointer">
                    <input type="checkbox" id="chk-filament" class="rounded border-outline-variant bg-surface-container-high focus:ring-secondary text-secondary">
                    <span>Confirm materials/AMS map match requirements.</span>
                </label>
            `;
        } else if (interrupt_id === "confirm_door_closed") {
            checkboxHtml = `
                <label class="hitl-item flex items-center gap-2 select-none cursor-pointer">
                    <input type="checkbox" id="chk-door" class="rounded border-outline-variant bg-surface-container-high focus:ring-secondary text-secondary">
                    <span>Confirm door / lid is closed (for ABS/ASA prints).</span>
                </label>
            `;
        } else {
            checkboxHtml = `
                <label class="hitl-item flex items-center gap-2 select-none cursor-pointer">
                    <input type="checkbox" id="chk-generic" class="rounded border-outline-variant bg-surface-container-high focus:ring-secondary text-secondary">
                    <span>Confirm request: ${msgData.prompt || payload.message}</span>
                </label>
            `;
        }

        msgDiv.innerHTML = `
            <span class="sender-label">BamBot AI (Safety Required)</span>
            <div class="bubble">
                <div class="font-bold text-tertiary mb-2 flex items-center gap-1">
                    <span class="material-symbols-outlined text-sm">warning</span> Safety Verification Required
                </div>
                <div class="mb-3 text-xs leading-relaxed text-on-surface-variant">${promptText}</div>
                <div class="hitl-checklist-card text-xs font-mono-label space-y-3" data-interrupt-id="${interrupt_id}" data-payload='${JSON.stringify(msgData).replace(/'/g, "&apos;")}'>
                    <div class="bg-surface-container-low p-2.5 rounded-lg border border-outline-variant/30 space-y-1.5">
                        ${amsListHtml}
                    </div>
                    <div class="flex flex-col gap-2 pt-1">
                        ${checkboxHtml}
                    </div>
                    <button class="btn-confirm-hitl uppercase tracking-wider" onclick="submitSafetyCheck(this)">Confirm & Resume Workflow</button>
                </div>
            </div>
        `;
        
        chatHistory.appendChild(msgDiv);
        chatHistory.scrollTop = chatHistory.scrollHeight;
        
        const indicator = document.getElementById('typing-indicator');
        if (indicator) indicator.style.display = "none";
        return;
    }

    const msgDiv = document.createElement('div');
    msgDiv.className = `chat-msg ${payload.sender}`;
    
    const senderLabelName = payload.sender === "user" ? "You" : "BamBot AI";
    let thoughtsHtml = '';
    
    if (payload.thoughts) {
        thoughtsHtml = `
            <div class="agent-thoughts">
                <div class="font-bold text-[10px] text-secondary tracking-widest uppercase mb-1 flex items-center gap-1">
                    <span class="material-symbols-outlined text-xs">psychology</span> Cognitive Monologue
                </div>
                <div>${payload.thoughts}</div>
            </div>
        `;
    }

    // Detect and render styled status card
    const styledContent = renderStyledChatContent(payload.text);

    // Process structured tool calls into beautiful execution accordions if present in logs
    let logsHtml = '';
    if (payload.metrics && payload.metrics.trajectory) {
        // We'll optionally show the last tool calls directly nested in the bubble for high transparency
    }

    msgDiv.innerHTML = `
        <span class="sender-label">${senderLabelName}</span>
        <div class="bubble shadow-md">
            ${thoughtsHtml}
            ${styledContent || `<div class="leading-relaxed text-sm whitespace-pre-wrap">${payload.text}</div>`}
        </div>
    `;
    
    chatHistory.appendChild(msgDiv);
    chatHistory.scrollTop = chatHistory.scrollHeight;

    // Update Observability panel
    if (payload.metrics) {
        updateObservability(payload.metrics);
    }
}

// Helper to locally append a chat message (e.g. for uploads or status info)
function appendChatMessage(sender, text) {
    handleChatMessage({
        type: "message",
        sender: sender,
        text: text,
        thoughts: ""
    });
}

// POST Safety verification to backend
async function submitSafetyCheck(btn) {
    const card = btn.closest('.hitl-checklist-card');
    const interrupt_id = card.getAttribute('data-interrupt-id');
    const rawPayload = card.getAttribute('data-payload');
    let msgData = {};
    try {
        if (rawPayload) msgData = JSON.parse(rawPayload);
    } catch(e) {}
    
    const chkBed = card.querySelector('#chk-bed');
    const chkDoor = card.querySelector('#chk-door');
    const chkFilament = card.querySelector('#chk-filament');
    const chkGeneric = card.querySelector('#chk-generic');
    
    if (chkBed && !chkBed.checked) {
        showCustomAlert("Verification Failed", "Please confirm the print bed is fully cleared.", "warning");
        return;
    }
    if (chkDoor && !chkDoor.checked) {
        showCustomAlert("Verification Failed", "Please confirm the door/lid is closed.", "warning");
        return;
    }
    if (chkFilament && !chkFilament.checked) {
        showCustomAlert("Verification Failed", "Please confirm the filament requirements.", "warning");
        return;
    }
    if (chkGeneric && !chkGeneric.checked) {
        showCustomAlert("Verification Failed", "Please confirm the request to proceed.", "warning");
        return;
    }

    try {
        const bedVal = chkBed ? chkBed.checked : true;
        const doorVal = chkDoor ? chkDoor.checked : true;
        const filamentVal = chkFilament ? chkFilament.checked : true;
        
        // Collect custom AMS mapping from chat dropdowns
        const chatSelects = card.querySelectorAll('.chat-ams-select');
        const mappings = [];
        chatSelects.forEach(select => {
            mappings.push(parseInt(select.value));
        });
        
        await fetch('/api/safety/confirm', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ bed_cleared: bedVal, door_closed: doorVal, filament_verified: filamentVal })
        });
        
        card.innerHTML = `<div class="text-secondary font-bold flex items-center gap-1.5 py-1.5"><span class="material-symbols-outlined">check_circle</span> Checked & approved. Resuming...</div>`;
        
        if (chatSocket) {
            chatSocket.send(JSON.stringify({
                type: "hitl_response",
                interrupt_id: interrupt_id,
                response: { 
                    result: true,
                    ams_mapping: mappings.length > 0 ? mappings : null,
                    plate_id: msgData.plate_id || null,
                    plate_name: msgData.plate_name || null
                }
            }));
        }
    } catch (e) {
        showErrorToast("Failed to submit safety checklist. Check API connection.");
    }
}

// Update Observability Panel
function updateObservability(metrics) {
    if (document.getElementById('metric-prompt')) {
        document.getElementById('metric-prompt').innerText = metrics.prompt_tokens;
        document.getElementById('metric-candidates').innerText = metrics.candidates_tokens;
        document.getElementById('metric-thinking').innerText = metrics.thinking_tokens;
        document.getElementById('metric-total').innerText = metrics.total_tokens;
        document.getElementById('metric-cost').innerText = metrics.estimated_cost_usd.toFixed(6);
    }

    const logDiv = document.getElementById('trajectory-log');
    if (logDiv) {
        logDiv.innerHTML = '';
        if (!metrics.trajectory || metrics.trajectory.length === 0) {
            logDiv.innerHTML = '<p class="text-on-surface-variant italic">No tools have been executed in this session.</p>';
            return;
        }

        metrics.trajectory.forEach(step => {
            const item = document.createElement('div');
            item.className = "p-2 rounded border border-outline-variant/20 bg-surface-container-low/40 border-l-2";
            
            let isAttempt = step.type === "tool_call_attempt";
            item.style.borderLeftColor = isAttempt ? "#ffb95f" : "#6bd8cb";
            
            let timeStr = new Date().toLocaleTimeString();
            let content = isAttempt 
                ? `<span class="text-tertiary">[CALL]</span> ${step.tool} with args: <pre class="text-[9px] mt-1 text-on-surface-variant max-w-full overflow-x-auto">${JSON.stringify(step.args, null, 2)}</pre>`
                : `<span class="text-secondary">[RESULT]</span> <pre class="text-[9px] mt-1 text-on-surface-variant max-w-full overflow-x-auto">${typeof step.result === 'string' ? step.result : JSON.stringify(step.result, null, 2)}</pre>`;
            
            item.innerHTML = `
                <div class="text-[8px] text-on-surface-variant font-semibold flex justify-between items-center">
                    <span>${step.tool}</span>
                    <span>${timeStr}</span>
                </div>
                <div class="mt-1 leading-relaxed whitespace-pre-wrap">${content}</div>
            `;
            logDiv.appendChild(item);
        });
        logDiv.scrollTop = logDiv.scrollHeight;
    }
}

// Switch Navigation Tabs
function switchTab(tabId) {
    // 1. Update Header tab indicators
    document.querySelectorAll('.nav-tab-btn').forEach(btn => {
        if (btn.getAttribute('data-tab') === tabId) {
            btn.className = "nav-tab-btn active bg-secondary/10 text-secondary font-bold p-stack-sm flex items-center gap-stack-md rounded-lg font-mono-label text-xs text-left w-full border-l-4 border-secondary pl-2";
        } else {
            btn.className = "nav-tab-btn text-on-surface-variant p-stack-sm flex items-center gap-stack-md hover:bg-secondary/5 transition-all duration-200 rounded-lg font-mono-label text-xs text-left w-full border-l-4 border-transparent pl-2";
        }
    });

    // 2. Update visible panels
    document.querySelectorAll('.tab-view').forEach(view => {
        if (view.id === tabId) {
            view.classList.add('active');
        } else {
            view.classList.remove('active');
        }
    });

    // 3. Perform tab-specific data refreshes
    if (tabId === 'files-view') {
        fetchPrinterFiles();
    } else if (tabId === 'dashboard-view') {
        fetchSpoolmanInventory();
    }
}

// Fetch Spoolman Inventory from Backend API
async function fetchSpoolmanInventory() {
    const listContainer = document.getElementById('dashboard-spoolman-list');
    if (!listContainer) return;
    try {
        const resp = await fetch('/api/inventory');
        const spools = await resp.json();
        listContainer.innerHTML = '';
        if (!spools || spools.length === 0) {
            listContainer.innerHTML = '<p class="text-xs text-on-surface-variant italic">Spoolman not configured on this BamBot instance.</p>';
            return;
        }

        spools.forEach(spool => {
            const hasSpool = spool.material !== "";
            const colorCircle = hasSpool ? `<span class="spool-indicator" style="background-color: ${spool.color || '#45474c'}"></span>` : `<span class="spool-indicator" style="background-color: #1e293b; border-style: dashed;"></span>`;
            const name = spool.name || "Generic Spool";
            const material = spool.material || "PLA";
            const weight = spool.remaining_g || 0;
            const percent = Math.min(100, Math.round((weight / 1000) * 100));
            
            const item = document.createElement('div');
            item.className = "space-y-1 bg-surface-container-low p-2.5 rounded-xl border border-outline-variant/30";
            item.innerHTML = `
                <div class="flex justify-between items-center mb-1 text-xs">
                    <div class="flex items-center gap-stack-sm truncate">
                        ${colorCircle}
                        <span class="text-on-surface font-bold truncate max-w-[140px]">${name}</span>
                        <span class="bg-surface-container-highest text-[10px] text-on-surface-variant px-1 rounded font-mono-label font-semibold">${material}</span>
                    </div>
                    <span class="text-on-surface font-mono-label text-[11px] font-semibold">${Math.round(weight)}g</span>
                </div>
                <div class="h-1.5 w-full bg-surface-container-highest rounded-full overflow-hidden">
                    <div class="h-full bg-secondary shadow-[0_0_6px_rgba(107,216,203,0.3)]" style="width: ${percent}%;"></div>
                </div>
            `;
            listContainer.appendChild(item);
        });
    } catch (e) {
        listContainer.innerHTML = '<p class="text-xs text-error font-semibold">Failed to retrieve Spoolman inventory.</p>';
    }
}

// Fetch Gcode Files from Backend API
let pendingFilename = "";
let pendingPlateId = null;
let pendingPlateName = "";

function closeManualPrintModal() {
    const modal = document.getElementById('manual-print-modal');
    const card = document.getElementById('manual-print-modal-card');
    if (modal && card) {
        card.classList.add('scale-95', 'opacity-0');
        setTimeout(() => {
            modal.classList.add('hidden');
        }, 150);
    }
}

async function triggerPrintFile(filename, timeStr) {
    pendingFilename = filename;
    pendingPlateId = 1;
    pendingPlateName = "Plate 1";

    const modal = document.getElementById('manual-print-modal');
    const card = document.getElementById('manual-print-modal-card');
    const filenameEl = document.getElementById('modal-filename');
    const timeEl = document.getElementById('modal-print-time');
    const bedPlateEl = document.getElementById('modal-bed-plate');
    const filamentList = document.getElementById('modal-filament-list');
    const chkBed = document.getElementById('modal-chk-bed');
    const chkDoor = document.getElementById('modal-chk-door');
    const chkDoorWrapper = document.getElementById('modal-chk-door-wrapper');

    if (!modal || !card) return;

    if (chkBed) chkBed.checked = false;
    if (chkDoor) chkDoor.checked = false;
    if (chkDoorWrapper) chkDoorWrapper.style.display = 'none';

    filenameEl.innerText = filename;
    timeEl.innerText = timeStr || "Unknown";

    if (filename.toLowerCase().includes('abs') || filename.toLowerCase().includes('asa')) {
        if (chkDoorWrapper) chkDoorWrapper.style.display = 'flex';
    }

    filamentList.innerHTML = '<div class="text-xs text-on-surface-variant italic">Loading print requirements...</div>';

    modal.classList.remove('hidden');
    setTimeout(() => {
        card.classList.remove('scale-95', 'opacity-0');
    }, 10);

    try {
        const resp = await fetch(`/api/files/${encodeURIComponent(filename)}/requirements`);
        const reqs = await resp.json();

        if (reqs.requested_bed_plate) {
            bedPlateEl.innerText = reqs.requested_bed_plate;
        }
        if (reqs.plate_id) pendingPlateId = reqs.plate_id;
        if (reqs.plate_name) pendingPlateName = reqs.plate_name;

        filamentList.innerHTML = '';
        const reqFils = reqs.requested_filaments || [];
        if (reqFils.length === 0) {
            filamentList.innerHTML = '<div class="text-xs text-on-surface-variant italic">No filament mapping requirements.</div>';
            return;
        }

        reqFils.forEach((req, idx) => {
            const container = document.createElement('div');
            container.className = "flex flex-col gap-1.5";
            
            let optionsHtml = '';
            amsStatus.forEach(slot => {
                if (slot.material) {
                    const isMatch = slot.material.toLowerCase() === req.type.toLowerCase();
                    optionsHtml += `<option value="${slot.slot - 1}" ${isMatch ? 'selected' : ''}>Slot ${slot.slot}: ${slot.material} (${slot.weight_g.toFixed(0)}g)</option>`;
                }
            });
            optionsHtml += `<option value="-1">External Spool (No AMS)</option>`;

            container.innerHTML = `
                <div class="flex items-center justify-between text-[11px] mb-0.5">
                    <div class="flex items-center gap-1.5">
                        <span class="spool-indicator" style="background-color: ${req.color}"></span>
                        <span>Virtual Slot ${req.slot_id}: <strong class="text-secondary">${req.type}</strong> (${req.used_grams.toFixed(1)}g)</span>
                    </div>
                </div>
                <select class="modal-ams-select bg-surface-container-highest border border-outline-variant/40 rounded p-1.5 text-xs text-on-surface w-full focus:ring-secondary" data-slot-id="${req.slot_id}">
                    ${optionsHtml}
                </select>
            `;
            filamentList.appendChild(container);
        });

    } catch (e) {
        filamentList.innerHTML = '<div class="text-xs text-error font-semibold">Failed to fetch requirements. Custom spool mapping unavailable.</div>';
    }
}

async function submitManualPrintJob() {
    const chkBed = document.getElementById('modal-chk-bed');
    const chkDoor = document.getElementById('modal-chk-door');
    const chkDoorWrapper = document.getElementById('modal-chk-door-wrapper');

    if (chkBed && !chkBed.checked) {
        showCustomAlert("Verification Failed", "Please confirm the print bed is fully cleared.", "warning");
        return;
    }
    if (chkDoorWrapper && chkDoorWrapper.style.display !== 'none' && chkDoor && !chkDoor.checked) {
        showCustomAlert("Verification Failed", "Closed chamber door/lid is required for ABS/ASA filaments. Please close the door and confirm.", "warning");
        return;
    }

    const mappings = [];
    const selectElements = document.querySelectorAll('.modal-ams-select');
    selectElements.forEach(select => {
        mappings.push(parseInt(select.value));
    });

    try {
        const resp = await fetch('/api/printer/command', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                action: 'start_print',
                value: pendingFilename,
                ams_mapping: mappings.length > 0 ? mappings : null,
                plate_id: pendingPlateId,
                plate_name: pendingPlateName
            })
        });
        const res = await resp.json();
        if (resp.status >= 400 || res.error) {
            showErrorToast(res.error || "Failed to start print.");
        } else {
            showCustomAlert("Print Job Started", `Print successfully started for: ${pendingFilename}`, "success");
            closeManualPrintModal();
            switchTab('dashboard-view');
        }
    } catch (e) {
        showErrorToast("Failed to connect to backend command API.");
    }
}

async function fetchPrinterFiles() {
    const listContainer = document.getElementById('files-list-container');
    if (!listContainer) return;
    try {
        const resp = await fetch('/api/files');
        const files = await resp.json();
        listContainer.innerHTML = '';
        if (!files || files.length === 0) {
            listContainer.innerHTML = '<p class="text-xs text-on-surface-variant italic">No print library G-code files found.</p>';
            return;
        }

        files.forEach(file => {
            const card = document.createElement('div');
            card.className = "bg-surface-container border border-outline-variant/60 p-4 rounded-xl flex items-center justify-between hover:border-secondary/50 transition-all duration-200 shadow-sm";
            card.innerHTML = `
                <div class="flex items-center gap-3 min-w-0">
                    <span class="material-symbols-outlined text-secondary shrink-0">description</span>
                    <div class="min-w-0">
                        <h3 class="font-bold text-on-surface text-sm truncate" title="${file.name}">${file.name}</h3>
                        <div class="flex gap-4 mt-0.5 text-[10px] text-on-surface-variant font-mono-label">
                            <span>Size: <strong class="text-on-surface">${file.size || "Unknown"}</strong></span>
                            <span>Time: <strong class="text-on-surface">${file.estimated_time || "Unknown"}</strong></span>
                            <span>Filament: <strong class="text-on-surface">${file.filament_required_g || 0.0}g</strong></span>
                        </div>
                    </div>
                </div>
                <button class="bg-secondary text-on-secondary font-mono-label text-xs font-bold px-4 py-2 rounded-lg active:scale-95 transition-all hover:brightness-105 shrink-0" onclick="triggerPrintFile('${file.name}', '${file.estimated_time || 'Unknown'}')">
                    START PRINT
                </button>
            `;
            listContainer.appendChild(card);
        });
    } catch (e) {
        listContainer.innerHTML = '<p class="text-xs text-error font-semibold">Failed to retrieve file list from printer.</p>';
    }
}

// Trigger control commands via API
async function sendPrinterAction(action) {
    try {
        const resp = await fetch('/api/printer/command', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: action })
        });
        const res = await resp.json();
        if (resp.status_code >= 400 || res.error) {
            showErrorToast(res.error || `Command ${action} failed.`);
        }
    } catch (e) {
        showErrorToast(`Connection failed when pausing/resuming.`);
    }
}

// Trigger Calibration command
async function triggerCalibrate() {
    if (confirm("Calibrate the printer bed leveling and resonance? This will home all axes.")) {
        await sendPrinterAction("calibrate");
    }
}

// Emergency stop handler
async function triggerHardStop() {
    try {
        await fetch('/api/printer/command', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'cancel' })
        });
        showErrorToast("EMERGENCY HARD STOP COMMAND BROADCASTED!");
    } catch (e) {
        showErrorToast("Failed to send Hard Stop request. Verify local API server!");
    }
}

// Observability drawer toggle
function toggleObservabilityDrawer() {
    const drawer = document.getElementById('observability-drawer');
    if (drawer) {
        drawer.classList.toggle('hidden');
        if (!drawer.classList.contains('hidden')) {
            drawer.classList.remove('translate-x-full');
        } else {
            drawer.classList.add('translate-x-full');
        }
    }
}

// Toast warning
function showErrorToast(msg) {
    const toast = document.getElementById('toast-error');
    const msgEl = document.getElementById('toast-message');
    if (toast && msgEl) {
        msgEl.innerText = msg;
        toast.style.display = 'flex';
        setTimeout(() => {
            toast.style.display = 'none';
        }, 4000);
    }
}

// Load and manage multiple chat sessions
async function loadChatSessions() {
    try {
        const response = await fetch('/api/chat/sessions');
        const sessions = await response.json();
        
        // If currentSessionId is not in list (deleted), switch to 's1'
        const exists = sessions.some(s => s.session_id === currentSessionId);
        if (!exists && sessions.length > 0) {
            currentSessionId = sessions[0].session_id;
        }
        
        renderChatSessionsList(sessions);
    } catch (error) {
        console.error("Failed to load chat sessions:", error);
    }
}

function renderChatSessionsList(sessions) {
    const listEl = document.getElementById('chat-sessions-list');
    if (!listEl) return;
    
    listEl.innerHTML = '';
    sessions.forEach(session => {
        const btn = document.createElement('button');
        btn.className = `chat-session-btn text-on-surface-variant p-3 flex items-center justify-between hover:bg-secondary/5 transition-all duration-200 rounded-lg text-xs w-full mb-1 text-left`;
        if (session.session_id === currentSessionId) {
            btn.classList.add('active');
        }
        btn.setAttribute('data-session-id', session.session_id);
        btn.addEventListener('click', () => switchSession(session.session_id));
        
        const titleSpan = document.createElement('span');
        titleSpan.className = 'truncate font-semibold flex-1';
        titleSpan.innerText = session.title;
        btn.appendChild(titleSpan);
        
        // Only allow deleting non-default sessions
        if (session.session_id !== 's1') {
            const delBtn = document.createElement('span');
            delBtn.className = 'material-symbols-outlined text-[16px] text-error opacity-0 hover:opacity-100 ml-2 delete-session-btn';
            delBtn.innerText = 'delete';
            delBtn.title = 'Delete Chat';
            delBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                deleteChatSession(session.session_id);
            });
            btn.appendChild(delBtn);
        }
        
        listEl.appendChild(btn);
    });
}

async function createNewChatSession() {
    try {
        const response = await fetch('/api/chat/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ title: `Chat ${Math.random().toString(36).substring(2, 6).toUpperCase()}` })
        });
        const data = await response.json();
        if (data.status === 'success') {
            await loadChatSessions();
            switchSession(data.session_id);
        }
    } catch (error) {
        console.error("Failed to create new chat session:", error);
    }
}

async function deleteChatSession(sessionId) {
    if (confirm("Are you sure you want to delete this chat session? All message history will be deleted.")) {
        try {
            const response = await fetch(`/api/chat/sessions/${sessionId}`, {
                method: 'DELETE'
            });
            const data = await response.json();
            if (data.status === 'success') {
                if (currentSessionId === sessionId) {
                    currentSessionId = 's1';
                }
                await loadChatSessions();
                switchSession(currentSessionId);
            }
        } catch (error) {
            console.error("Failed to delete chat session:", error);
        }
    }
}

function switchSession(sessionId) {
    currentSessionId = sessionId;
    // Clear chat history UI
    const chatHistory = document.getElementById('chat-history');
    if (chatHistory) {
        chatHistory.innerHTML = '';
    }
    // Reload and re-render sessions list
    loadChatSessions();
    // Reconnect socket
    connectSockets();
}

// Send user message
function sendChatMessage() {
    const input = document.getElementById('chat-input');
    if (!input) return;
    const text = input.value.trim();
    if (!text || !chatSocket) return;

    chatSocket.send(JSON.stringify({ text: text }));
    input.value = '';
    
    // reset textarea height
    input.style.height = 'auto';
}

// Fetch and Render Fleet Matrix
async function fetchAndRenderFleetMatrix() {
    const matrix = document.getElementById('fleet-matrix');
    if (!matrix) return;
    try {
        const resp = await fetch('/api/printers');
        const data = await resp.json();
        const printers = data.printers || [];
        const isReal = data.is_real;
        
        matrix.innerHTML = '';
        if (printers.length === 0) {
            matrix.innerHTML = '<div class="col-span-3 text-xs font-mono-label text-on-surface-variant italic">No printers found.</div>';
            return;
        }
        
        // Find active printer
        const activePrinter = printers.find(p => p.is_active) || printers[0];
        if (activePrinter) {
            // Update active printer info in the Active Print Job section
            const infoEl = document.getElementById('dashboard-active-printer-info');
            if (infoEl) {
                infoEl.innerText = `${activePrinter.name} (${activePrinter.model})`;
            }
            
            // Set camera feed to active printer
            const liveCamImg = document.getElementById('live-cam-feed');
            if (liveCamImg) {
                const targetSrc = `/api/printers/${activePrinter.id}/camera/stream`;
                
                const absoluteTarget = new URL(targetSrc, window.location.href).href;
                if (liveCamImg.src !== absoluteTarget) {
                    liveCamImg.src = absoluteTarget;
                }
            }
        }

        printers.forEach(p => {
            const isActive = p.is_active;
            const borderClass = isActive ? 'border-secondary bg-secondary/5 ring-1 ring-secondary/30' : 'border-outline-variant bg-surface-container';
            const stateClass = p.state === 'printing' ? 'bg-secondary/10 text-secondary' : 
                               (p.state === 'idle' ? 'bg-surface-container-highest text-on-surface-variant' : 'bg-error-container/10 text-error');
            
            const card = document.createElement('div');
            card.className = `p-stack-md rounded-2xl border ${borderClass} hover:border-secondary transition-all duration-300 cursor-pointer transform active:scale-98`;
            card.innerHTML = `
                <div class="flex justify-between items-start mb-stack-md">
                    <div>
                        <p class="font-mono-label text-xs font-bold text-on-surface">${p.name}</p>
                        <p class="font-mono-label text-[10px] text-on-surface-variant">${p.model}</p>
                    </div>
                    <span class="state-badge px-2 py-0.5 rounded text-[10px] font-bold uppercase ${stateClass}">${p.state}</span>
                </div>
                <div class="flex justify-between items-center text-xs font-mono-label">
                    <span>Nozzle: ${Math.round(p.nozzle_temp)}°C</span>
                    <span>Bed: ${Math.round(p.bed_temp)}°C</span>
                </div>
            `;
            
            card.addEventListener('click', async () => {
                card.classList.add('scale-95');
                setTimeout(() => card.classList.remove('scale-95'), 100);
                await selectPrinter(p.id, isReal);
            });
            
            matrix.appendChild(card);
        });
    } catch (err) {
        console.error("Failed to render fleet matrix:", err);
    }
}

// Select/enlarge a specific printer
async function selectPrinter(printerId, isReal) {
    try {
        const resp = await fetch(`/api/printers/${printerId}/select`, {
            method: 'POST'
        });
        if (resp.ok) {
            // Trigger animation on active print job section
            const activeJobCard = document.querySelector('.bg-surface-container-low');
            if (activeJobCard) {
                activeJobCard.classList.add('scale-[1.01]', 'border-secondary');
                setTimeout(() => activeJobCard.classList.remove('scale-[1.01]', 'border-secondary'), 300);
            }
            
            // Re-render fleet matrix to update selection styling and camera/info
            await fetchAndRenderFleetMatrix();
        }
    } catch (err) {
        console.error("Error selecting printer:", err);
    }
}

document.addEventListener('DOMContentLoaded', () => {
    initChart();
    loadChatSessions();
    connectSockets();
    fetchSpoolmanInventory();
    fetchAndRenderFleetMatrix();

    // Bind new chat button
    const btnNewChat = document.getElementById('btn-new-chat');
    if (btnNewChat) btnNewChat.addEventListener('click', createNewChatSession);

    // Bind tab clicks
    document.querySelectorAll('.nav-tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            switchTab(btn.getAttribute('data-tab'));
        });
    });

    // Chat triggers
    const btnSend = document.getElementById('btn-send');
    if (btnSend) btnSend.addEventListener('click', sendChatMessage);
    
    const chatInput = document.getElementById('chat-input');
    if (chatInput) {
        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                sendChatMessage();
            }
        });

        // Auto-resize chat input textarea
        chatInput.addEventListener('input', function() {
            this.style.height = 'auto';
            this.style.height = (this.scrollHeight) + 'px';
        });
    }

    // Attach File Trigger
    const chatAttachBtn = document.getElementById('chat-attach-btn');
    const chatFileInput = document.getElementById('chat-file-input');
    if (chatAttachBtn && chatFileInput) {
        chatAttachBtn.addEventListener('click', () => {
            chatFileInput.click();
        });

        chatFileInput.addEventListener('change', async () => {
            if (chatFileInput.files.length === 0) return;
            const file = chatFileInput.files[0];

            appendChatMessage("user", `Uploading file to library: ${file.name}...`);

            const formData = new FormData();
            formData.append('file', file);

            try {
                const resp = await fetch('/api/library/upload', {
                    method: 'POST',
                    body: formData
                });
                const res = await resp.json();
                if (resp.ok) {
                    appendChatMessage("agent", `Successfully uploaded ${file.name} to the print library! You can find and trigger it in the Files view.`);
                } else {
                    appendChatMessage("agent", `Error uploading file: ${res.detail || 'Unknown error'}`);
                }
            } catch (err) {
                appendChatMessage("agent", `Failed to upload file: ${err.message}`);
            }
            chatFileInput.value = '';
        });
    }
});

function showCustomAlert(title, message, type = "success") {
    const modal = document.getElementById('custom-alert-modal');
    const card = document.getElementById('custom-alert-card');
    const icon = document.getElementById('custom-alert-icon');
    const titleEl = document.getElementById('custom-alert-title');
    const msgEl = document.getElementById('custom-alert-message');
    
    if (!modal || !card) return;
    
    titleEl.innerText = title;
    msgEl.innerText = message;
    
    if (type === "success") {
        icon.innerText = "check_circle";
        icon.className = "material-symbols-outlined text-4xl text-secondary";
    } else if (type === "warning") {
        icon.innerText = "warning";
        icon.className = "material-symbols-outlined text-4xl text-amber-400";
    } else {
        icon.innerText = "error";
        icon.className = "material-symbols-outlined text-4xl text-error";
    }
    
    modal.classList.remove('hidden');
    setTimeout(() => {
        card.classList.remove('scale-95', 'opacity-0');
    }, 10);
}

function closeCustomAlert() {
    const modal = document.getElementById('custom-alert-modal');
    const card = document.getElementById('custom-alert-card');
    if (modal && card) {
        card.classList.add('scale-95', 'opacity-0');
        setTimeout(() => {
            modal.classList.add('hidden');
        }, 150);
    }
}
