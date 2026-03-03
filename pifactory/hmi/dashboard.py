"""Pi-Factory Demo Dashboard — FALLBACK HMI.

This is a lightweight demo dashboard for the Cookoff submission.
Production HMI runs FUXA (https://github.com/frangoteam/FUXA).

Returns an HTML string rendered by the tag_server's GET / endpoint.
NVIDIA green (#76b900) branding, mobile-responsive, Cosmos <think> panel.
"""

from __future__ import annotations


def render_dashboard() -> str:
    """Return the full HTML dashboard as a string."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pi-Factory — Industrial AI Dashboard</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0a0a0f;
            color: #e0e0e0;
            min-height: 100vh;
        }
        .demo-banner {
            background: #1a1200;
            border-bottom: 2px solid #76b900;
            padding: 10px 20px;
            text-align: center;
            font-size: 13px;
            color: #bba800;
        }
        .demo-banner a { color: #76b900; }
        .header {
            background: linear-gradient(135deg, #0d1a00 0%, #1a2e00 100%);
            padding: 20px;
            border-bottom: 2px solid #76b90040;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .header h1 { font-size: 22px; color: #76b900; }
        .header .subtitle { color: #888; margin-top: 4px; font-size: 13px; }
        .nvidia-badge {
            background: #76b90020;
            border: 1px solid #76b90060;
            padding: 6px 14px;
            border-radius: 6px;
            font-size: 12px;
            color: #76b900;
            font-weight: 600;
        }
        .container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            padding: 16px;
            max-width: 1400px;
            margin: 0 auto;
        }
        @media (max-width: 900px) { .container { grid-template-columns: 1fr; } }
        .panel {
            background: #12121a;
            border: 1px solid #2a2a3a;
            border-radius: 10px;
            overflow: hidden;
        }
        .panel-header {
            background: #1a1a2e;
            padding: 12px 16px;
            border-bottom: 1px solid #2a2a3a;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .panel-header h2 { font-size: 14px; color: #fff; }
        .panel-body { padding: 16px; }
        .tag-grid {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }
        @media (max-width: 600px) { .tag-grid { grid-template-columns: 1fr; } }
        .tag-item {
            background: #1a1a2e;
            padding: 10px 14px;
            border-radius: 8px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .tag-name { color: #888; font-size: 12px; }
        .tag-value { font-weight: 600; font-size: 14px; }
        .tag-value.on { color: #76b900; }
        .tag-value.off { color: #555; }
        .tag-value.warning { color: #ffaa00; }
        .tag-value.critical { color: #ff4444; }
        .badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 600;
        }
        .badge-ok { background: #76b90020; color: #76b900; }
        .badge-warning { background: #ffaa0020; color: #ffaa00; }
        .badge-critical { background: #ff444420; color: #ff4444; }
        .badge-emergency { background: #ff000040; color: #ff0000; }
        .fault-item {
            background: #1a1a2e;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 8px;
            border-left: 4px solid #555;
        }
        .fault-item.warning { border-color: #ffaa00; }
        .fault-item.critical { border-color: #ff4444; }
        .fault-item.emergency { border-color: #ff0000; }
        .fault-title { font-weight: 600; font-size: 13px; margin-bottom: 3px; }
        .fault-desc { color: #888; font-size: 12px; }
        .full-width { grid-column: 1 / -1; }
        .diagnosis-input {
            display: flex;
            gap: 8px;
            margin-bottom: 12px;
        }
        .diagnosis-input input {
            flex: 1;
            background: #0a0a0f;
            border: 1px solid #2a2a3a;
            border-radius: 8px;
            padding: 10px 14px;
            color: #fff;
            font-size: 13px;
        }
        .diagnosis-input input:focus { outline: none; border-color: #76b900; }
        .btn {
            background: linear-gradient(135deg, #76b900 0%, #5a8f00 100%);
            color: #000;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
        }
        .btn:hover { filter: brightness(1.1); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
        .think-panel {
            background: #0d1a00;
            border: 1px solid #76b90030;
            border-radius: 8px;
            padding: 14px;
            margin-bottom: 12px;
            display: none;
        }
        .think-panel h3 {
            color: #76b900;
            font-size: 12px;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .think-panel pre {
            color: #aaa;
            font-size: 12px;
            white-space: pre-wrap;
            line-height: 1.5;
        }
        .result-panel {
            background: #0a0a0f;
            border-radius: 8px;
            padding: 14px;
            font-family: 'SF Mono', Monaco, monospace;
            font-size: 12px;
            line-height: 1.6;
            white-space: pre-wrap;
            max-height: 300px;
            overflow-y: auto;
            display: none;
        }
        .confidence-bar {
            height: 6px;
            background: #1a1a2e;
            border-radius: 3px;
            margin-top: 10px;
            overflow: hidden;
            display: none;
        }
        .confidence-fill {
            height: 100%;
            background: #76b900;
            border-radius: 3px;
            transition: width 0.5s ease;
        }
        .meta-row {
            display: flex;
            gap: 10px;
            margin-top: 8px;
            flex-wrap: wrap;
        }
        .meta-tag {
            background: #1a1a2e;
            padding: 3px 10px;
            border-radius: 4px;
            font-size: 11px;
            color: #888;
        }
        .meta-tag.fast { color: #76b900; }
        .meta-tag.slow { color: #ffaa00; }
        .pulse {
            width: 8px; height: 8px;
            border-radius: 50%;
            background: #76b900;
            animation: pulse 2s infinite;
        }
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
        .footer {
            text-align: center;
            padding: 16px;
            color: #333;
            font-size: 11px;
        }
        .footer a { color: #76b900; text-decoration: none; }
    </style>
</head>
<body>
    <div class="demo-banner">
        Demo view — production HMI runs <a href="https://github.com/frangoteam/FUXA" target="_blank">FUXA</a>.
        See <a href="/docs">API docs</a> or docs/quickstart.md
    </div>

    <div class="header">
        <div>
            <h1>Pi-Factory</h1>
            <div class="subtitle">Industrial AI Diagnostics — Cosmos Reason 2</div>
        </div>
        <div style="display:flex;align-items:center;gap:12px;">
            <a href="/camera" class="nvidia-badge" style="text-decoration:none;">Camera</a>
            <span class="nvidia-badge" id="modelBadge">--</span>
            <div class="pulse"></div>
        </div>
    </div>

    <div class="container">
        <!-- Live I/O -->
        <div class="panel">
            <div class="panel-header">
                <h2>Live I/O Status</h2>
                <span class="meta-tag" id="lastUpdate">--</span>
            </div>
            <div class="panel-body">
                <div class="tag-grid" id="tagGrid">
                    <div class="tag-item"><span class="tag-name">Connecting...</span></div>
                </div>
            </div>
        </div>

        <!-- VFD Live Data -->
        <div class="panel" id="vfdPanel">
            <div class="panel-header">
                <h2>VFD Live Data</h2>
                <span class="meta-tag" id="vfdComms">--</span>
            </div>
            <div class="panel-body">
                <div class="tag-grid" id="vfdGrid">
                    <div class="tag-item"><span class="tag-name">VFD not connected</span></div>
                </div>
            </div>
        </div>

        <!-- Faults -->
        <div class="panel">
            <div class="panel-header">
                <h2>Detected Faults</h2>
                <span class="badge badge-ok" id="faultBadge">0 Active</span>
            </div>
            <div class="panel-body" id="faultList">
                <div class="fault-item"><div class="fault-title">Scanning...</div></div>
            </div>
        </div>

        <!-- AI Diagnosis -->
        <div class="panel full-width">
            <div class="panel-header">
                <h2>Cosmos R2 Diagnosis</h2>
            </div>
            <div class="panel-body">
                <div class="diagnosis-input">
                    <input type="text" id="questionInput"
                           placeholder="Ask: Why is this stopped? What should I check?"
                           value="Why is this equipment stopped?">
                    <button class="btn" id="diagnoseBtn" onclick="runDiagnosis()">Diagnose</button>
                </div>
                <div class="think-panel" id="thinkPanel">
                    <h3>Cosmos Reasoning</h3>
                    <pre id="thinkContent"></pre>
                </div>
                <div class="result-panel" id="resultPanel"></div>
                <div class="confidence-bar" id="confBar">
                    <div class="confidence-fill" id="confFill"></div>
                </div>
                <div class="meta-row" id="metaRow" style="display:none;">
                    <span class="meta-tag" id="latencyTag">--</span>
                    <span class="meta-tag" id="confTag">--</span>
                    <span class="meta-tag" id="modelTag">--</span>
                </div>
            </div>
        </div>
    </div>

    <div class="footer">
        Pi-Factory v2.0 | Powered by <a href="https://build.nvidia.com" target="_blank">NVIDIA Cosmos Reason 2</a>
        | Hardware: <a href="https://www.hms-networks.com/anybus" target="_blank">HMS Anybus CompactCom</a>
    </div>

    <script>
        const TC = {
            motor_running:    {label:'Motor',         type:'bool'},
            motor_speed:      {label:'Motor Speed',   type:'percent'},
            motor_current:    {label:'Motor Current',  type:'amps'},
            temperature:      {label:'Temperature',    type:'temp', warn:65, crit:80},
            pressure:         {label:'Pressure',       type:'psi',  warn:70, crit:60},
            conveyor_running: {label:'Conveyor',       type:'bool'},
            conveyor_speed:   {label:'Conv Speed',     type:'percent'},
            sensor_1:         {label:'Sensor 1',       type:'bool'},
            sensor_2:         {label:'Sensor 2',       type:'bool'},
            fault_alarm:      {label:'Fault Alarm',    type:'alarm'},
            e_stop:           {label:'E-Stop',         type:'estop'},
            error_code:       {label:'Error Code',     type:'int'}
        };

        function fmt(key, val, c) {
            if (!c) return {t:String(val),c:''};
            switch(c.type) {
                case 'bool':    return {t:val?'RUNNING':'STOPPED', c:val?'on':'off'};
                case 'percent': return {t:val+'%', c:''};
                case 'amps':    return {t:parseFloat(val).toFixed(2)+' A', c:val>5?'critical':''};
                case 'temp':    return {t:parseFloat(val).toFixed(1)+' °C', c:val>c.crit?'critical':val>c.warn?'warning':''};
                case 'psi':     return {t:val+' PSI', c:val<c.crit?'critical':val<c.warn?'warning':''};
                case 'alarm':   return {t:val?'ACTIVE':'Clear', c:val?'critical':'on'};
                case 'estop':   return {t:val?'PRESSED':'Clear', c:val?'critical':'on'};
                case 'int':     return {t:val||'None', c:val?'warning':''};
                default:        return {t:String(val), c:''};
            }
        }

        async function fetchTags() {
            try {
                const r = await fetch('/api/tags');
                const tags = await r.json();
                if (tags.error) return;
                const g = document.getElementById('tagGrid');
                g.innerHTML = '';
                for (const [k,c] of Object.entries(TC)) {
                    const v = tags[k];
                    if (v === undefined) continue;
                    const f = fmt(k, v, c);
                    g.innerHTML += '<div class="tag-item"><span class="tag-name">'+c.label+'</span><span class="tag-value '+f.c+'">'+f.t+'</span></div>';
                }
                document.getElementById('lastUpdate').textContent = new Date().toLocaleTimeString();
            } catch(e) { console.error(e); }
        }

        async function fetchFaults() {
            try {
                const r = await fetch('/api/faults');
                const d = await r.json();
                if (d.error) return;
                const list = document.getElementById('faultList');
                const badge = document.getElementById('faultBadge');
                const active = d.faults.filter(f => f.severity !== 'info');
                if (!active.length) {
                    list.innerHTML = '<div class="fault-item" style="border-color:#76b900"><div class="fault-title" style="color:#76b900">No Active Faults</div><div class="fault-desc">System operating normally</div></div>';
                    badge.textContent = 'OK';
                    badge.className = 'badge badge-ok';
                } else {
                    list.innerHTML = active.map(f =>
                        '<div class="fault-item '+f.severity+'"><div class="fault-title">['+f.code+'] '+f.title+'</div><div class="fault-desc">'+f.description+'</div></div>'
                    ).join('');
                    badge.textContent = active.length + ' Active';
                    badge.className = 'badge badge-' + active[0].severity;
                }
            } catch(e) { console.error(e); }
        }

        async function runDiagnosis() {
            const q = document.getElementById('questionInput').value;
            const btn = document.getElementById('diagnoseBtn');
            const result = document.getElementById('resultPanel');
            const think = document.getElementById('thinkPanel');
            const meta = document.getElementById('metaRow');
            btn.disabled = true;
            result.style.display = 'block';
            result.textContent = 'Analyzing with Cosmos R2...';
            think.style.display = 'none';
            try {
                const r = await fetch('/api/diagnose', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({question: q})
                });
                const d = await r.json();
                result.textContent = d.answer;
                if (d.thinking) {
                    think.style.display = 'block';
                    document.getElementById('thinkContent').textContent = d.thinking;
                }
                meta.style.display = 'flex';
                const lt = document.getElementById('latencyTag');
                lt.textContent = d.latency_ms + 'ms';
                lt.className = 'meta-tag ' + (d.latency_ms < 5000 ? 'fast' : 'slow');
                document.getElementById('confTag').textContent = 'Confidence: ' + ((d.confidence||0)*100).toFixed(0) + '%';
                document.getElementById('modelTag').textContent = d.model;
                document.getElementById('modelBadge').textContent = d.model;
                const bar = document.getElementById('confBar');
                bar.style.display = 'block';
                document.getElementById('confFill').style.width = ((d.confidence||0)*100) + '%';
            } catch(e) {
                result.textContent = 'Error: ' + e.message;
            }
            btn.disabled = false;
        }

        const VFD_TC = {
            vfd_output_hz:    {label:'Output Hz',    type:'hz',   warn:30, crit:5},
            vfd_setpoint_hz:  {label:'Setpoint Hz',  type:'hz'},
            vfd_output_amps:  {label:'Current',      type:'amps', crit:5.0},
            vfd_motor_rpm:    {label:'Motor RPM',    type:'int'},
            vfd_torque_pct:   {label:'Torque',       type:'pct',  warn:80, crit:110},
            vfd_drive_temp_c: {label:'Drive Temp',   type:'temp', warn:60, crit:70},
            vfd_dc_bus_volts: {label:'volts',        type:'int'},
            vfd_run_status:   {label:'Run Status',   type:'bool'},
            vfd_fault_code:   {label:'Fault',        type:'fault'},
        };
        function fmtVfd(key, val, c) {
            if (!c) return {t:String(val),c:''};
            switch(c.type) {
                case 'hz':     return {t:parseFloat(val).toFixed(1)+' Hz', c:c.crit!==undefined&&val<c.crit?'critical':c.warn!==undefined&&val<c.warn?'warning':''};
                case 'amps':   return {t:parseFloat(val).toFixed(1)+' A',  c:c.crit&&val>c.crit?'critical':''};
                case 'pct':    return {t:parseFloat(val).toFixed(0)+'%',   c:c.crit&&val>c.crit?'critical':c.warn&&val>c.warn?'warning':''};
                case 'temp':   return {t:parseFloat(val).toFixed(1)+' °C', c:c.crit&&val>c.crit?'critical':c.warn&&val>c.warn?'warning':''};
                case 'bool':   return {t:val?'RUNNING':'STOPPED',          c:val?'on':'off'};
                case 'fault':  return {t:val?'FAULT '+val:'No Fault',      c:val?'critical':'on'};
                case 'int':    return {t:String(val), c:''};
                default:       return {t:String(val), c:''};
            }
        }
        async function fetchVFD() {
            try {
                const r = await fetch('/api/vfd/status');
                const comms = document.getElementById('vfdComms');
                if (r.status === 503) {
                    comms.textContent = 'Not connected';
                    comms.style.color = '#555';
                    return;
                }
                const tags = await r.json();
                const g = document.getElementById('vfdGrid');
                g.innerHTML = '';
                for (const [k,c] of Object.entries(VFD_TC)) {
                    const v = tags[k];
                    if (v === undefined) continue;
                    const f = fmtVfd(k, v, c);
                    g.innerHTML += '<div class="tag-item"><span class="tag-name">'+c.label+'</span><span class="tag-value '+f.c+'">'+f.t+'</span></div>';
                }
                if (tags.vfd_comms_ok) {
                    comms.textContent = 'Connected';
                    comms.style.color = '#76b900';
                } else {
                    comms.textContent = 'Comms Lost';
                    comms.style.color = '#ff4444';
                }
            } catch(e) { console.error(e); }
        }

        fetchTags(); fetchFaults(); fetchVFD();
        setInterval(fetchTags, 2000);
        setInterval(fetchFaults, 3000);
        setInterval(fetchVFD, 1000);
        document.getElementById('questionInput').addEventListener('keypress', e => {
            if (e.key === 'Enter') runDiagnosis();
        });
    </script>
</body>
</html>'''
