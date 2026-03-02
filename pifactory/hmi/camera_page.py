"""Pi-Factory Live Camera Page — webcam feed + live tag sidebar.

Same dark theme / NVIDIA green as the main dashboard.
The camera feed uses MJPEG streaming (natively supported by browsers).
Tag sidebar polls /api/tags every 2s.
"""

from __future__ import annotations


def render_camera_page() -> str:
    """Return the full HTML camera page as a string."""
    return '''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pi-Factory — Live Camera</title>
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
            text-decoration: none;
        }
        .nvidia-badge:hover { background: #76b90030; }
        .container {
            display: grid;
            grid-template-columns: 1fr 320px;
            gap: 16px;
            padding: 16px;
            max-width: 1400px;
            margin: 0 auto;
        }
        @media (max-width: 900px) {
            .container { grid-template-columns: 1fr; }
        }
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
        .cam-feed {
            width: 100%;
            border-radius: 8px;
            background: #0a0a0f;
            display: block;
        }
        .no-camera {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 400px;
            background: #0a0a0f;
            border-radius: 8px;
            color: #555;
            font-size: 15px;
            flex-direction: column;
            gap: 12px;
        }
        .no-camera svg { opacity: 0.3; }
        .tag-list { display: flex; flex-direction: column; gap: 8px; }
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
        .fault-badge {
            display: inline-block;
            padding: 3px 10px;
            border-radius: 20px;
            font-size: 11px;
            font-weight: 600;
        }
        .fault-badge.ok { background: #76b90020; color: #76b900; }
        .fault-badge.active { background: #ff444420; color: #ff4444; }
        .btn {
            background: linear-gradient(135deg, #76b900 0%, #5a8f00 100%);
            color: #000;
            border: none;
            padding: 10px 20px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 13px;
            cursor: pointer;
            width: 100%;
            margin-top: 12px;
        }
        .btn:hover { filter: brightness(1.1); }
        .btn:disabled { opacity: 0.5; cursor: not-allowed; }
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
            <h1>Pi-Factory — Live Camera</h1>
            <div class="subtitle">Webcam feed for Cosmos R2 multimodal analysis</div>
        </div>
        <div style="display:flex;align-items:center;gap:12px;">
            <a href="/" class="nvidia-badge">Dashboard</a>
            <div class="pulse"></div>
        </div>
    </div>

    <div class="container">
        <!-- Camera Feed -->
        <div class="panel">
            <div class="panel-header">
                <h2>Camera Feed</h2>
                <span class="fault-badge ok" id="camStatus">Live</span>
            </div>
            <div class="panel-body" id="camBody">
                <img id="camFeed" class="cam-feed" src="/api/camera/stream"
                     alt="Live camera feed"
                     onerror="showNoCamera()">
            </div>
        </div>

        <!-- Tag Sidebar -->
        <div class="panel">
            <div class="panel-header">
                <h2>Live I/O</h2>
                <span class="fault-badge ok" id="faultBadge">0 Faults</span>
            </div>
            <div class="panel-body">
                <div class="tag-list" id="tagList">
                    <div class="tag-item"><span class="tag-name">Connecting...</span></div>
                </div>
                <button class="btn" id="diagnoseBtn" onclick="diagnoseCamera()">
                    Diagnose What You See
                </button>
            </div>
        </div>
    </div>

    <div class="footer">
        Pi-Factory v1.0 | Powered by <a href="https://build.nvidia.com" target="_blank">NVIDIA Cosmos Reason 2</a>
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
                case 'temp':    return {t:parseFloat(val).toFixed(1)+' C', c:val>c.crit?'critical':val>c.warn?'warning':''};
                case 'psi':     return {t:val+' PSI', c:val<c.crit?'critical':val<c.warn?'warning':''};
                case 'alarm':   return {t:val?'ACTIVE':'Clear', c:val?'critical':'on'};
                case 'estop':   return {t:val?'PRESSED':'Clear', c:val?'critical':'on'};
                case 'int':     return {t:val||'None', c:val?'warning':''};
                default:        return {t:String(val), c:''};
            }
        }

        function showNoCamera() {
            document.getElementById('camBody').innerHTML =
                '<div class="no-camera">' +
                '<svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">' +
                '<path d="M23 19a2 2 0 01-2 2H3a2 2 0 01-2-2V8a2 2 0 012-2h4l2-3h6l2 3h4a2 2 0 012 2z"/>' +
                '<circle cx="12" cy="13" r="4"/>' +
                '</svg>' +
                '<span>No camera configured</span>' +
                '<span style="font-size:12px;color:#444">Set VIDEO_SOURCE env var to enable</span>' +
                '</div>';
            var s = document.getElementById('camStatus');
            s.textContent = 'Offline';
            s.className = 'fault-badge active';
        }

        async function fetchTags() {
            try {
                var r = await fetch('/api/tags');
                var tags = await r.json();
                if (tags.error) return;
                var list = document.getElementById('tagList');
                list.innerHTML = '';
                for (var entry of Object.entries(TC)) {
                    var k = entry[0], c = entry[1];
                    var v = tags[k];
                    if (v === undefined) continue;
                    var f = fmt(k, v, c);
                    list.innerHTML += '<div class="tag-item"><span class="tag-name">' +
                        c.label + '</span><span class="tag-value ' + f.c + '">' +
                        f.t + '</span></div>';
                }
            } catch(e) { console.error(e); }
        }

        async function fetchFaultCount() {
            try {
                var r = await fetch('/api/faults');
                var d = await r.json();
                var active = d.faults.filter(function(f) { return f.severity !== 'info'; });
                var badge = document.getElementById('faultBadge');
                if (!active.length) {
                    badge.textContent = 'OK';
                    badge.className = 'fault-badge ok';
                } else {
                    badge.textContent = active.length + ' Fault' + (active.length > 1 ? 's' : '');
                    badge.className = 'fault-badge active';
                }
            } catch(e) { console.error(e); }
        }

        async function diagnoseCamera() {
            var btn = document.getElementById('diagnoseBtn');
            btn.disabled = true;
            btn.textContent = 'Analyzing...';
            try {
                var r = await fetch('/api/diagnose', {
                    method: 'POST',
                    headers: {'Content-Type':'application/json'},
                    body: JSON.stringify({question: 'What do you see in the camera feed?'})
                });
                var d = await r.json();
                alert(d.answer);
            } catch(e) {
                alert('Diagnosis error: ' + e.message);
            }
            btn.disabled = false;
            btn.textContent = 'Diagnose What You See';
        }

        fetchTags();
        fetchFaultCount();
        setInterval(fetchTags, 2000);
        setInterval(fetchFaultCount, 3000);
    </script>
</body>
</html>'''
