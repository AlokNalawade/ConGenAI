const API_BASE = '/api/v1';
const activeTasks = {}; // contentId -> { title: string, label: string, step: string }

function getAssetUrl(path) {
    if (!path) return '';
    let clean = path.replace(/\\/g, '/');
    if (clean.includes('data/assets/')) {
        clean = clean.split('data/assets/')[1];
    } else if (clean.includes('assets/')) {
        clean = clean.split('assets/')[1];
    } else if (clean.startsWith('/')) {
        clean = clean.substring(1);
    }
    return '/assets/' + clean;
}

function switchTab(linkEl, tabName) {
    document.querySelectorAll('.sidebar nav a').forEach(a => a.classList.remove('active'));
    if (linkEl) {
        linkEl.classList.add('active');
    } else {
        const navEl = document.getElementById(`nav-${tabName}`);
        if (navEl) navEl.classList.add('active');
    }

    const views = ['dashboard', 'ideas', 'pipeline', 'videos', 'settings'];
    views.forEach(v => {
        const el = document.getElementById(`view-${v}`);
        if (el) {
            el.style.display = (v === tabName) ? 'block' : 'none';
        }
    });

    if (tabName === 'dashboard' || tabName === 'pipeline') {
        fetchPipeline();
    } else if (tabName === 'ideas') {
        loadIdeasView();
    } else if (tabName === 'videos') {
        loadVideosView();
    }
}

async function loadAvailableModels() {
    try {
        const res = await fetch(`${API_BASE}/ideas/available-models`);
        if (!res.ok) return;
        const models = await res.json();
        
        ['modelResearch', 'modelScript', 'modelScene'].forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            el.innerHTML = '';
            models.forEach(m => {
                const opt = document.createElement('option');
                opt.value = m;
                opt.innerText = m;
                el.appendChild(opt);
            });
        });
    } catch(e) {
        console.error("Failed to load available models", e);
    }
}
loadAvailableModels();

function updateBannerStatus() {
    const banner = document.getElementById('pipeline-status-banner');
    const textEl = document.getElementById('pipeline-status-text');
    if (!banner || !textEl) return;

    const activeKeys = Object.keys(activeTasks);
    if (activeKeys.length > 0) {
        const firstKey = activeKeys[0];
        const task = activeTasks[firstKey];
        textEl.innerText = `${task.title ? `"${task.title}"` : 'Video'}: ${task.step || 'Processing via Durable Worker...'}`;
        banner.style.display = 'inline-flex';
    } else {
        banner.style.display = 'none';
    }
}

function toggleModal(id) {
    const modal = document.getElementById(id);
    if (!modal) return;
    if (modal.classList.contains('active')) {
        modal.classList.remove('active');
        setTimeout(() => { modal.style.display = 'none'; }, 300);
    } else {
        modal.style.display = 'flex';
        void modal.offsetWidth; // force reflow
        modal.classList.add('active');
    }
}

async function fetchPipeline() {
    try {
        const res = await fetch(`${API_BASE}/content/`);
        const contents = await res.json();
        
        document.getElementById('stat-ideas').innerText = contents.length;
        document.getElementById('stat-production').innerText = contents.filter(c => !['completed', 'approved', 'failed', 'idea'].includes(c.status)).length;
        document.getElementById('stat-completed').innerText = contents.filter(c => ['completed', 'approved', 'awaiting_approval'].includes(c.status)).length;
        
        renderKanban(contents);
    } catch (e) {
        console.error("Failed to fetch pipeline", e);
    }
}

function getStageBadge(status) {
    const map = {
        'idea': { label: '💡 Idea', color: 'rgba(255,255,255,0.1)', text: '#a0a5b5' },
        'planning': { label: '💡 Planning', color: 'rgba(255,255,255,0.1)', text: '#a0a5b5' },
        'researching': { label: '🔬 Researching', color: 'rgba(108, 92, 231, 0.2)', text: '#a29bfe', spin: true, percent: 15 },
        'strategizing': { label: '🎯 Strategizing', color: 'rgba(108, 92, 231, 0.2)', text: '#a29bfe', spin: true, percent: 30 },
        'scripting': { label: '📝 Scriptwriting', color: 'rgba(108, 92, 231, 0.2)', text: '#a29bfe', spin: true, percent: 45 },
        'planning_scenes': { label: '🎬 Scene Planning', color: 'rgba(162, 155, 254, 0.2)', text: '#a29bfe', spin: true, percent: 60 },
        'generating_assets': { label: '🎨 Generating Media', color: 'rgba(253, 203, 110, 0.2)', text: '#fdcb6e', spin: true, percent: 75 },
        'media': { label: '🎨 Media Assets', color: 'rgba(253, 203, 110, 0.2)', text: '#fdcb6e', spin: true, percent: 75 },
        'rendering_video': { label: '⚡ Rendering Video', color: 'rgba(253, 203, 110, 0.25)', text: '#fdcb6e', spin: true, percent: 90 },
        'assembly': { label: '⚡ Assembling Video', color: 'rgba(253, 203, 110, 0.25)', text: '#fdcb6e', spin: true, percent: 90 },
        'quality_check': { label: '🔍 Quality Scoring', color: 'rgba(0, 206, 201, 0.2)', text: '#00cec9', spin: true, percent: 95 },
        'awaiting_approval': { label: '👁️ Ready for Review', color: 'rgba(0, 184, 148, 0.25)', text: '#00b894', percent: 100 },
        'approved': { label: '✅ Approved', color: 'rgba(0, 184, 148, 0.25)', text: '#00b894', percent: 100 },
        'completed': { label: '✅ Completed', color: 'rgba(0, 184, 148, 0.25)', text: '#00b894', percent: 100 },
        'failed': { label: '❌ Failed', color: 'rgba(214, 48, 49, 0.25)', text: '#ff7675', percent: 0 }
    };
    return map[status] || { label: status || 'Pending', color: 'rgba(255,255,255,0.1)', text: '#fff' };
}

function renderKanban(contents) {
    const cols = {
        'planning': document.getElementById('col-planning'),
        'scripting': document.getElementById('col-scripting'),
        'media': document.getElementById('col-media'),
        'assembly': document.getElementById('col-assembly')
    };
    
    Object.values(cols).forEach(col => { if(col) col.innerHTML = ''; });
    
    contents.forEach(content => {
        let colId = 'planning';
        const s = content.status || 'idea';
        
        if (['researching', 'strategizing', 'scripting', 'planning_scenes'].includes(s)) colId = 'scripting';
        if (['generating_assets', 'media', 'rendering_video', 'assembly'].includes(s)) colId = 'media';
        if (['quality_check', 'awaiting_approval', 'approved', 'completed'].includes(s)) colId = 'assembly';
        if (s === 'failed') colId = 'planning'; // Keep failed in column 1 for easy retry
        
        const card = document.createElement('div');
        card.className = 'task-card';
        card.style.position = 'relative';
        
        const taskState = activeTasks[content.id];
        const badge = getStageBadge(s);

        let actionBtn = '';
        if (taskState) {
            actionBtn = `<button class="btn-sm btn-action" disabled style="background: rgba(108, 92, 231, 0.3); border: 1px solid rgba(162, 155, 254, 0.4); font-weight: 600;"><i class="ri-loader-4-line spin" style="color: #00b894;"></i> ${taskState.label || 'Processing'}</button>`;
        } else if (['idea', 'planning'].includes(s)) {
            actionBtn = `<button class="btn-sm btn-action" style="background: linear-gradient(135deg, #6c5ce7, #a29bfe);" onclick="runPipelineWorker('${content.id}')"><i class="ri-play-circle-fill"></i> Run Pipeline</button>`;
        } else if (s === 'failed') {
            actionBtn = `<button class="btn-sm btn-action" style="background: rgba(214, 48, 49, 0.8);" onclick="resumePipelineWorker('${content.id}')"><i class="ri-refresh-line"></i> Retry / Resume</button>`;
        } else if (['awaiting_approval', 'approved', 'completed'].includes(s)) {
            actionBtn = `<button class="btn-sm btn-action" style="background: linear-gradient(135deg, #00b894, #00cec9);" onclick="openHitlInspector('${content.id}')"><i class="ri-eye-line"></i> Inspect & Review</button>`;
        } else {
            // Actively processing in worker queue
            actionBtn = `<button class="btn-sm btn-action" disabled style="background: rgba(108, 92, 231, 0.25); color: #a29bfe;"><i class="ri-loader-4-line spin"></i> Processing...</button>`;
        }

        let progressBar = '';
        if (badge.percent !== undefined && badge.percent > 0 && badge.percent < 100) {
            progressBar = `
                <div style="width: 100%; background: rgba(255,255,255,0.06); height: 4px; border-radius: 2px; margin-bottom: 12px; overflow: hidden;">
                    <div style="width: ${badge.percent}%; background: linear-gradient(90deg, #6c5ce7, #00b894); height: 100%; transition: width 0.4s ease;"></div>
                </div>
            `;
        }

        card.innerHTML = `
            <div class="card-tags" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
                <span class="tag tag-platform">${content.platform || 'Shorts'}</span>
                <span class="tag" style="background: ${badge.color}; color: ${badge.text}; display: inline-flex; align-items: center; gap: 4px;">
                    ${badge.spin ? '<i class="ri-loader-4-line spin"></i>' : ''} ${badge.label}
                </span>
            </div>
            ${progressBar}
            <div class="card-title">${escapeHtml(content.title)}</div>
            <div class="card-desc">${escapeHtml(content.description || 'No description provided.')}</div>
            <div class="card-actions" style="margin-top: 12px;">
                ${actionBtn}
            </div>
        `;
        
        if (cols[colId]) {
            cols[colId].appendChild(card);
        }
    });
    
    Object.keys(cols).forEach(k => {
        const countEl = document.getElementById(`count-${k}`);
        if(countEl && cols[k]) countEl.innerText = cols[k].children.length;
    });

    updateBannerStatus();
}

async function runPipelineWorker(contentId) {
    activeTasks[contentId] = { label: 'Queued', step: 'Enqueued to Redis worker queue...' };
    updateBannerStatus();
    try {
        const res = await fetch(`${API_BASE}/content/${contentId}/pipeline`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content_id: contentId, resume: true })
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        await fetchPipeline();
    } catch (e) {
        console.error("Failed to enqueue pipeline job:", e);
        delete activeTasks[contentId];
        updateBannerStatus();
    }
}

async function resumePipelineWorker(contentId) {
    activeTasks[contentId] = { label: 'Resuming', step: 'Resuming pipeline execution...' };
    updateBannerStatus();
    try {
        const res = await fetch(`${API_BASE}/content/${contentId}/resume`, { method: 'POST' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        await fetchPipeline();
    } catch (e) {
        console.error("Failed to resume pipeline job:", e);
        delete activeTasks[contentId];
        updateBannerStatus();
    }
}

async function loadIdeasView() {
    const grid = document.getElementById('ideas-grid');
    if (!grid) return;
    grid.innerHTML = `<div style="grid-column: 1/-1; color: var(--text-muted); padding: 20px;"><i class="ri-loader-4-line spin"></i> Loading ideas library...</div>`;

    try {
        const res = await fetch(`${API_BASE}/ideas/`);
        const ideas = await res.json();
        grid.innerHTML = '';

        if (ideas.length === 0) {
            grid.innerHTML = `
                <div class="glass" style="grid-column: 1/-1; padding: 40px; text-align: center;">
                    <i class="ri-lightbulb-line" style="font-size: 48px; color: #a29bfe; margin-bottom: 12px; display: block;"></i>
                    <h3 style="margin-bottom: 8px;">No Content Ideas Yet</h3>
                    <p style="color: var(--text-muted); font-size: 14px; margin-bottom: 20px;">Create your first content idea to start generating automated videos.</p>
                    <button class="btn btn-primary" onclick="toggleModal('ideaModal')"><i class="ri-add-line"></i> Create New Idea</button>
                </div>
            `;
            return;
        }

        ideas.forEach(idea => {
            const card = document.createElement('div');
            card.className = 'glass';
            card.style.padding = '24px';
            card.style.borderRadius = '16px';
            card.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <span class="tag tag-platform">${idea.platform || 'Shorts'}</span>
                    <span style="font-size: 11px; color: var(--text-muted);">${idea.content_type || 'General'}</span>
                </div>
                <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 8px;">${escapeHtml(idea.title)}</h3>
                <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 20px; line-height: 1.5;">${escapeHtml(idea.description || 'No description provided.')}</p>
                <div style="display: flex; gap: 10px;">
                    <button class="btn-sm btn-action" style="flex: 1; background: linear-gradient(135deg, #00b894, #00cec9);" onclick="launchIdeaE2E('${idea.id}', '${escapeHtml(idea.title)}', '${escapeHtml(idea.description)}', '${idea.platform}')">
                        <i class="ri-rocket-line"></i> Launch Video E2E
                    </button>
                </div>
            `;
            grid.appendChild(card);
        });
    } catch (e) {
        grid.innerHTML = `<div style="color: #ff7675; padding: 20px;">Failed to load ideas library: ${e}</div>`;
    }
}

async function launchIdeaE2E(ideaId, title, description, platform) {
    try {
        const contentRes = await fetch(`${API_BASE}/content/`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({idea_id: ideaId, title: title, description: description, platform: platform})
        });
        if (!contentRes.ok) throw new Error("Failed to create content from idea");
        const content = await contentRes.json();
        
        switchTab(document.getElementById('nav-dashboard'), 'dashboard');
        await runPipelineWorker(content.id);
    } catch (e) {
        console.error("Launch E2E from Idea error:", e);
    }
}

async function loadVideosView() {
    const grid = document.getElementById('videos-grid');
    if (!grid) return;
    grid.innerHTML = `<div style="grid-column: 1/-1; color: var(--text-muted); padding: 20px;"><i class="ri-loader-4-line spin"></i> Loading videos gallery...</div>`;

    try {
        const res = await fetch(`${API_BASE}/content/`);
        const contents = await res.json();
        grid.innerHTML = '';

        const completed = contents.filter(c => ['completed', 'approved', 'awaiting_approval'].includes(c.status));

        if (completed.length === 0) {
            grid.innerHTML = `
                <div class="glass" style="grid-column: 1/-1; padding: 40px; text-align: center;">
                    <i class="ri-video-line" style="font-size: 48px; color: #a29bfe; margin-bottom: 12px; display: block;"></i>
                    <h3 style="margin-bottom: 8px;">No Generated Videos Yet</h3>
                    <p style="color: var(--text-muted); font-size: 14px; margin-bottom: 20px;">Use the Auto-Create button on any idea to generate vertical short videos.</p>
                    <button class="btn btn-primary" onclick="switchTab(document.getElementById('nav-dashboard'), 'dashboard')"><i class="ri-rocket-fill"></i> Go to Dashboard</button>
                </div>
            `;
            return;
        }

        for (let content of completed) {
            const assetsRes = await fetch(`${API_BASE}/content/${content.id}/assets`);
            const assets = await assetsRes.json();
            const videoAsset = assets.find(a => a.asset_type === 'video');

            if (!videoAsset) continue;

            const videoUrl = getAssetUrl(videoAsset.path);

            const card = document.createElement('div');
            card.className = 'glass';
            card.style.padding = '20px';
            card.style.borderRadius = '18px';
            card.innerHTML = `
                <div style="position: relative; border-radius: 12px; overflow: hidden; margin-bottom: 16px; background: #000; height: 240px; display: flex; align-items: center; justify-content: center;">
                    <video src="${videoUrl}#t=0.5" style="width: 100%; height: 100%; object-fit: cover;" preload="metadata"></video>
                    <button onclick="playVideoDirect('${videoUrl}', '${escapeHtml(content.title)}')" style="position: absolute; width: 54px; height: 54px; border-radius: 50%; background: linear-gradient(135deg, #00b894, #00cec9); color: white; border: none; font-size: 24px; cursor: pointer; display: flex; align-items: center; justify-content: center; box-shadow: 0 6px 20px rgba(0, 184, 148, 0.6);">
                        <i class="ri-play-fill" style="margin-left: 3px;"></i>
                    </button>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span class="tag tag-platform">${content.platform || 'Shorts'}</span>
                    <span style="font-size: 11px; color: #00b894; font-weight: 600;">Ready</span>
                </div>
                <h3 style="font-size: 15px; font-weight: 600; margin-bottom: 14px;">${escapeHtml(content.title)}</h3>
                <div style="display: flex; gap: 10px;">
                    <button class="btn-sm btn-action" style="flex: 1;" onclick="playVideoDirect('${videoUrl}', '${escapeHtml(content.title)}')">
                        <i class="ri-play-fill"></i> Play Video
                    </button>
                    <a href="${videoUrl}" download="${content.title.replace(/[^a-zA-Z0-9]/g, '_')}.mp4" class="btn-sm" style="background: rgba(255,255,255,0.08); color: white; text-decoration: none; display: inline-flex; align-items: center; gap: 4px;">
                        <i class="ri-download-line"></i> MP4
                    </a>
                </div>
            `;
            grid.appendChild(card);
        }
    } catch (e) {
        grid.innerHTML = `<div style="color: #ff7675; padding: 20px;">Failed to load videos gallery: ${e}</div>`;
    }
}

async function resetAllData() {
    if (!confirm("Are you sure you want to clear all database entries and generated video assets?")) return;
    try {
        const res = await fetch(`${API_BASE}/ideas/reset/`, { method: 'DELETE' });
        if (!res.ok) {
            const contents = await (await fetch(`${API_BASE}/content/`)).json();
            for (let c of contents) {
                await fetch(`${API_BASE}/content/${c.id}`, { method: 'DELETE' });
            }
        }
        alert("All data cleared successfully!");
        fetchPipeline();
        switchTab(document.getElementById('nav-dashboard'), 'dashboard');
    } catch (e) {
        alert("Reset failed: " + e);
    }
}

document.getElementById('ideaForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const title = document.getElementById('ideaTitle').value;
    const desc = document.getElementById('ideaDesc').value;
    const platform = document.getElementById('ideaPlatform').value;
    const type = document.getElementById('ideaType').value;
    
    try {
        const ideaRes = await fetch(`${API_BASE}/ideas/`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title, description: desc, platform, content_type: type})
        });
        const idea = await ideaRes.json();
        
        await fetch(`${API_BASE}/content/`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({idea_id: idea.id, title: idea.title, description: idea.description, platform: idea.platform})
        });
        
        toggleModal('ideaModal');
        document.getElementById('ideaForm').reset();
        fetchPipeline();
    } catch (e) {
        console.error("Error creating idea:", e);
    }
});

async function submitEndToEnd() {
    const title = document.getElementById('ideaTitle').value;
    const desc = document.getElementById('ideaDesc').value;
    const platform = document.getElementById('ideaPlatform').value;
    const type = document.getElementById('ideaType').value;
    
    if (!title) {
        document.getElementById('ideaTitle').focus();
        document.getElementById('ideaTitle').style.borderColor = '#ff7675';
        setTimeout(() => { document.getElementById('ideaTitle').style.borderColor = ''; }, 2000);
        return;
    }
    
    const btn = document.getElementById('e2eCreateBtn');
    const origText = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = `<i class="ri-loader-4-line spin"></i> Enqueueing...`;
        btn.disabled = true;
    }

    try {
        const ideaRes = await fetch(`${API_BASE}/ideas/`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({title, description: desc, platform, content_type: type})
        });
        if (!ideaRes.ok) throw new Error("Failed to create idea");
        const idea = await ideaRes.json();
        
        const contentRes = await fetch(`${API_BASE}/content/`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({idea_id: idea.id, title: idea.title, description: idea.description, platform: idea.platform})
        });
        if (!contentRes.ok) throw new Error("Failed to create content");
        const content = await contentRes.json();
        
        toggleModal('ideaModal');
        document.getElementById('ideaForm').reset();
        
        switchTab(document.getElementById('nav-dashboard'), 'dashboard');
        await runPipelineWorker(content.id);
        
    } catch (e) {
        console.error("End-to-end process error:", e);
    } finally {
        if (btn) {
            btn.innerHTML = origText;
            btn.disabled = false;
        }
    }
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, "&amp;")
              .replace(/</g, "&lt;")
              .replace(/>/g, "&gt;")
              .replace(/"/g, "&quot;")
              .replace(/'/g, "&#039;");
}

function onSearchInput(query) {
    query = (query || '').toLowerCase().trim();
    document.querySelectorAll('.task-card').forEach(card => {
        const title = card.querySelector('.card-title')?.innerText.toLowerCase() || '';
        const desc = card.querySelector('.card-desc')?.innerText.toLowerCase() || '';
        if (title.includes(query) || desc.includes(query)) {
            card.style.display = 'block';
        } else {
            card.style.display = 'none';
        }
    });
}

// WebSocket for Terminal
const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
const ws = new WebSocket(`${wsProtocol}//${window.location.host}/api/ws/logs`);

let unreadLogCount = 0;
let isTerminalMinimized = false;

ws.onmessage = function(event) {
    const logs = document.getElementById('terminal-logs');
    try {
        const data = JSON.parse(event.data);
        const line = document.createElement('div');
        line.className = 'log-line';
        if (data.agent === 'System') line.classList.add('system');
        if (data.agent === 'Worker' || data.agent === 'JobWorker') line.classList.add('llm');
        
        line.innerHTML = `<span class="time">[${data.time || new Date().toLocaleTimeString()}]</span> <span class="agent">[${data.agent || 'System'}]</span> <span class="text">${escapeHtml(data.message)}</span>`;
        
        if (logs) {
            logs.appendChild(line);
            logs.scrollTop = logs.scrollHeight;
        }

        if (isTerminalMinimized) {
            unreadLogCount++;
            const unreadBadge = document.getElementById('terminal-unread-badge');
            if (unreadBadge) {
                unreadBadge.innerText = unreadLogCount;
                unreadBadge.style.display = 'inline-block';
            }
        }
        
        // Auto-refresh pipeline view on any incoming agent log event
        fetchPipeline();
    } catch (e) {
        console.error("Failed to parse log message:", event.data);
    }
};

// Polling interval every 3 seconds to keep dashboard & cards 100% in sync
setInterval(fetchPipeline, 3000);

function playVideoDirect(url, title = "Video Preview") {
    const player = document.getElementById('videoPlayer');
    const bigPlayBtn = document.getElementById('bigPlayBtn');
    if (!player) return;

    player.pause();
    player.src = url + (url.includes('?') ? '&' : '?') + 't=' + Date.now();
    player.muted = false;
    player.volume = 1.0;
    player.load();

    if (bigPlayBtn) bigPlayBtn.style.display = 'flex';
    toggleModal('videoModal');
}

async function playVideo(contentId) {
    try {
        const res = await fetch(`${API_BASE}/content/${contentId}/assets`);
        if (!res.ok) throw new Error("Could not fetch assets");
        const assets = await res.json();
        const videoAsset = assets.find(a => a.asset_type === 'video');
        if (!videoAsset) {
            console.warn("No video asset found.");
            return;
        }
        
        const url = getAssetUrl(videoAsset.path);
        playVideoDirect(url);
    } catch (e) {
        console.error("Error playing video:", e);
    }
}

function userStartPlay() {
    const player = document.getElementById('videoPlayer');
    const bigPlayBtn = document.getElementById('bigPlayBtn');

    if (player) {
        player.muted = false;
        player.volume = 1.0;
        const playPromise = player.play();
        if (playPromise !== undefined) {
            playPromise.then(() => {
                if (bigPlayBtn) bigPlayBtn.style.display = 'none';
            }).catch(err => {
                console.warn("Play with sound error:", err);
                player.muted = false;
                player.play();
                if (bigPlayBtn) bigPlayBtn.style.display = 'none';
            });
        }
    }
}

function closeVideoModal() {
    const player = document.getElementById('videoPlayer');
    const bigPlayBtn = document.getElementById('bigPlayBtn');
    if (player) {
        player.pause();
        player.removeAttribute('src');
        player.load();
    }
    if (bigPlayBtn) {
        bigPlayBtn.style.display = 'flex';
    }
    toggleModal('videoModal');
}

fetchPipeline();

// --- Terminal Controls & Draggable Window ---
let isDraggingTerminal = false;
let dragOffsetX = 0;
let dragOffsetY = 0;

function setupDraggableTerminal() {
    const container = document.getElementById('terminal-floating-container');
    const dragHandle = document.getElementById('terminal-drag-handle');
    if (!container || !dragHandle) return;

    const minBtn = document.getElementById('terminal-min-btn');
    const maxBtn = document.getElementById('terminal-max-btn');
    const badge = document.getElementById('terminal-badge');
    const redDot = dragHandle.querySelector('.dot.red');
    const yellowDot = dragHandle.querySelector('.dot.yellow');
    const greenDot = dragHandle.querySelector('.dot.green');

    if (minBtn) minBtn.onclick = (e) => { e.stopPropagation(); minimizeTerminalWindow(); };
    if (maxBtn) maxBtn.onclick = (e) => { e.stopPropagation(); maximizeTerminalWindow(); };
    if (badge) badge.onclick = (e) => { e.stopPropagation(); restoreTerminalWindow(); };
    if (redDot) redDot.onclick = (e) => { e.stopPropagation(); minimizeTerminalWindow(); };
    if (yellowDot) yellowDot.onclick = (e) => { e.stopPropagation(); minimizeTerminalWindow(); };
    if (greenDot) greenDot.onclick = (e) => { e.stopPropagation(); maximizeTerminalWindow(); };

    dragHandle.addEventListener('mousedown', (e) => {
        if (e.target.closest('button') || e.target.closest('.dot')) return;
        if (container.classList.contains('maximized')) return;

        isDraggingTerminal = true;
        const rect = container.getBoundingClientRect();
        dragOffsetX = e.clientX - rect.left;
        dragOffsetY = e.clientY - rect.top;

        container.style.left = rect.left + 'px';
        container.style.top = rect.top + 'px';
        container.style.bottom = 'auto';
        container.style.right = 'auto';

        document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', (e) => {
        if (!isDraggingTerminal || container.classList.contains('maximized')) return;

        let left = e.clientX - dragOffsetX;
        let top = e.clientY - dragOffsetY;

        const maxLeft = window.innerWidth - container.offsetWidth;
        const maxTop = window.innerHeight - 40;

        left = Math.max(0, Math.min(left, maxLeft));
        top = Math.max(0, Math.min(top, maxTop));

        container.style.left = left + 'px';
        container.style.top = top + 'px';
    });

    document.addEventListener('mouseup', () => {
        if (isDraggingTerminal) {
            isDraggingTerminal = false;
            document.body.style.userSelect = '';
        }
    });
}

function minimizeTerminalWindow() {
    const container = document.getElementById('terminal-floating-container');
    const badge = document.getElementById('terminal-badge');
    if (!container) return;

    isTerminalMinimized = true;
    container.classList.add('minimized');
    container.style.display = 'none';
    if (badge) {
        badge.style.display = 'flex';
    }
}

function restoreTerminalWindow() {
    const container = document.getElementById('terminal-floating-container');
    const badge = document.getElementById('terminal-badge');
    const unreadBadge = document.getElementById('terminal-unread-badge');
    if (!container) return;

    isTerminalMinimized = false;
    container.classList.remove('minimized');
    container.style.display = 'block';
    if (badge) {
        badge.style.display = 'none';
    }
    unreadLogCount = 0;
    if (unreadBadge) {
        unreadBadge.style.display = 'none';
        unreadBadge.innerText = '0';
    }
}

function maximizeTerminalWindow() {
    const container = document.getElementById('terminal-floating-container');
    const maxIcon = document.getElementById('terminal-max-icon');
    const maxText = document.getElementById('terminal-max-text');
    if (!container) return;

    if (container.classList.contains('maximized')) {
        container.classList.remove('maximized');
        if (container.dataset.prevLeft !== undefined && container.dataset.prevLeft !== '') {
            container.style.left = container.dataset.prevLeft;
            container.style.top = container.dataset.prevTop;
            container.style.bottom = 'auto';
            container.style.right = 'auto';
        } else {
            container.style.left = '';
            container.style.top = '';
            container.style.bottom = '24px';
            container.style.right = '24px';
        }
        if (maxIcon) maxIcon.className = 'ri-checkbox-blank-line';
        if (maxText) maxText.innerText = 'Maximize';
    } else {
        container.dataset.prevLeft = container.style.left || '';
        container.dataset.prevTop = container.style.top || '';
        container.classList.add('maximized');
        if (maxIcon) maxIcon.className = 'ri-aspect-ratio-line';
        if (maxText) maxText.innerText = 'Restore';
    }
}

function clearTerminalLogs() {
    const body = document.getElementById('terminal-logs');
    if (body) {
        body.innerHTML = '<div class="log-line system"><span class="time"></span><span class="agent">[System]</span><span class="text"> Log console cleared.</span></div>';
    }
}

// --- HITL Inspector & Action Handlers ---
let currentHitlContentId = null;

async function openHitlInspector(contentId) {
    currentHitlContentId = contentId;
    toggleModal('hitlModal');

    const titleEl = document.getElementById('hitlTitle');
    const scoreEl = document.getElementById('hitlScore');
    const hookEl = document.getElementById('hitlHookText');
    const bodyEl = document.getElementById('hitlBodyText');
    const ctaEl = document.getElementById('hitlCtaText');
    const player = document.getElementById('hitlVideoPlayer');

    if (titleEl) titleEl.innerText = "Content Inspector";
    if (scoreEl) scoreEl.innerText = "--";
    if (hookEl) hookEl.innerText = "Loading script...";
    if (bodyEl) bodyEl.innerText = "Loading...";
    if (ctaEl) ctaEl.innerText = "Loading...";

    try {
        const res = await fetch(`${API_BASE}/content/${contentId}/pipeline`);
        if (res.ok) {
            const data = await res.json();
            if (titleEl) titleEl.innerText = data.title || "Content Inspector";
            if (scoreEl) scoreEl.innerText = data.quality_score !== null && data.quality_score !== undefined ? data.quality_score : "--";

            if (data.video_asset_path && player) {
                const url = getAssetUrl(data.video_asset_path);
                player.src = url + '?t=' + Date.now();
                player.load();
            }
        }

        // Fetch script details
        const scriptRes = await fetch(`${API_BASE}/content/${contentId}/scripts/latest`);
        if (scriptRes.ok) {
            const scriptData = await scriptRes.json();
            if (hookEl) hookEl.innerText = scriptData.hook || "(No hook generated)";
            if (bodyEl) bodyEl.innerText = scriptData.body || "(No body generated)";
            if (ctaEl) ctaEl.innerText = scriptData.cta || "(No CTA generated)";
        }

        // Fetch scenes details
        const scenesRes = await fetch(`${API_BASE}/content/${contentId}/scenes/`);
        if (scenesRes.ok) {
            const scenesData = await scenesRes.json();
            const scenesListEl = document.getElementById('hitlScenesList');
            if (scenesListEl) {
                scenesListEl.innerHTML = scenesData.map(sc => `
                    <div style="padding: 10px; background: rgba(0,0,0,0.3); border-radius: 8px; border: 1px solid rgba(255,255,255,0.06);">
                        <div style="display: flex; justify-content: space-between; font-size: 12px; font-weight: 700; color: #a29bfe; margin-bottom: 4px;">
                            <span>Scene ${sc.scene_number} (${sc.duration}s)</span>
                            <span>${sc.transition || 'fade'}</span>
                        </div>
                        <div style="font-size: 12px; color: #fff; margin-bottom: 4px;">🗣️ ${escapeHtml(sc.narration || '')}</div>
                        <div style="font-size: 11px; color: var(--text-muted);">🎨 Visual: ${escapeHtml(sc.visual_prompt || sc.visual_description || '')}</div>
                    </div>
                `).join('');
            }
        }
    } catch (e) {
        console.error("Error opening HITL inspector:", e);
    }
}

function switchHitlTab(tabName) {
    ['script', 'scenes', 'telemetry'].forEach(t => {
        const tabEl = document.getElementById(`hitlTab${t.charAt(0).toUpperCase() + t.slice(1)}`);
        const btnEl = document.getElementById(`hitlTab${t.charAt(0).toUpperCase() + t.slice(1)}Btn`);
        if (tabEl) tabEl.style.display = (t === tabName) ? 'block' : 'none';
        if (btnEl) btnEl.classList.toggle('active', t === tabName);
    });
}

async function hitlApprove() {
    if (!currentHitlContentId) return;
    try {
        const res = await fetch(`${API_BASE}/content/${currentHitlContentId}/approve`, { method: 'POST' });
        if (res.ok) {
            alert("Content approved for publishing!");
            toggleModal('hitlModal');
            fetchPipeline();
        }
    } catch (e) {
        console.error("Failed to approve content:", e);
    }
}

async function hitlResume() {
    if (!currentHitlContentId) return;
    try {
        await resumePipelineWorker(currentHitlContentId);
        toggleModal('hitlModal');
    } catch (e) {
        console.error("Failed to resume content:", e);
    }
}

async function hitlRegenerate(mode = 'full') {
    if (!currentHitlContentId) return;

    const labels = {
        visuals: {
            confirm: 'Regenerate visuals only?\n\nYour script and scene plan will be kept.\nOnly images, audio, and video will be re-generated.\n\nThis is ~4× faster than a full regeneration.',
            toast: 'Regenerating visuals — script preserved. Images, audio & video will be re-generated.',
        },
        full: {
            confirm: 'Start a full regeneration?\n\nEverything will be re-generated from scratch:\nresearch, script, scenes, images, audio, and video.\n\nThis will take the full pipeline time.',
            toast: 'Full regeneration triggered. All stages will re-run from scratch.',
        },
    };

    const label = labels[mode] || labels.full;
    if (!confirm(label.confirm)) return;

    // Disable both regen buttons while the request is in flight
    const visBtnEl = document.getElementById('hitlRegenVisualsBtn');
    const fullBtnEl = document.getElementById('hitlRegenBtn');
    if (visBtnEl) visBtnEl.disabled = true;
    if (fullBtnEl) fullBtnEl.disabled = true;

    try {
        const res = await fetch(`${API_BASE}/content/${currentHitlContentId}/regenerate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode }),
        });

        if (res.ok) {
            const data = await res.json();
            alert(label.toast);
            toggleModal('hitlModal');
            fetchPipeline();
        } else {
            const err = await res.json().catch(() => ({}));
            alert(`Regeneration failed: ${err.detail || res.statusText}`);
        }
    } catch (e) {
        console.error('Failed to regenerate content:', e);
        alert('Network error — could not trigger regeneration.');
    } finally {
        if (visBtnEl) visBtnEl.disabled = false;
        if (fullBtnEl) fullBtnEl.disabled = false;
    }
}

// Initialize terminal handlers
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupDraggableTerminal);
} else {
    setupDraggableTerminal();
}
