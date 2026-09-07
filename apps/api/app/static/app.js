const API_BASE = '/api/v1';
const activeTasks = {}; // contentId -> { title: string, label: string, step: string }

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
    } else if (tabName === 'settings') {
        // Settings view is ready
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
        textEl.innerText = `${task.title ? `"${task.title}"` : 'Video'}: ${task.step || 'Processing...'}`;
        banner.style.display = 'inline-flex';
    } else {
        banner.style.display = 'none';
    }
}

function toggleModal(id) {
    const modal = document.getElementById(id);
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
        document.getElementById('stat-production').innerText = contents.filter(c => c.status !== 'completed').length;
        document.getElementById('stat-completed').innerText = contents.filter(c => c.status === 'completed').length;
        
        renderKanban(contents);
    } catch (e) {
        console.error("Failed to fetch pipeline", e);
    }
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
        const s = content.status || 'planning';
        
        if (s === 'researching' || s === 'scripting') colId = 'scripting';
        if (s === 'scenes' || s === 'media') colId = 'media';
        if (s === 'assembly' || s === 'completed') colId = 'assembly';
        
        const card = document.createElement('div');
        card.className = 'task-card';
        
        const taskState = activeTasks[content.id];
        let actionBtn = '';
        
        if (taskState) {
            actionBtn = `<button class="btn-sm btn-action" disabled style="background: rgba(108, 92, 231, 0.4); border: 1px solid rgba(162, 155, 254, 0.5); font-weight: 600;"><i class="ri-loader-4-line spin" style="color: #00b894;"></i> ${taskState.label || 'Processing'}</button>`;
        } else if (s === 'planning') {
            actionBtn = `<button class="btn-sm btn-action" onclick="triggerAction(this, '${content.id}', 'research')"><i class="ri-search-eye-line"></i> Research</button>`;
        } else if (s === 'researching') {
            actionBtn = `<button class="btn-sm btn-action" onclick="triggerAction(this, '${content.id}', 'script')"><i class="ri-edit-line"></i> Write Script</button>`;
        } else if (s === 'scripting') {
            actionBtn = `<button class="btn-sm btn-action" onclick="triggerAction(this, '${content.id}', 'scenes')"><i class="ri-film-line"></i> Plan Scenes</button>`;
        } else if (s === 'scenes') {
            actionBtn = `<button class="btn-sm btn-action" onclick="triggerAction(this, '${content.id}', 'media')"><i class="ri-image-edit-line"></i> Gen Media</button>`;
        } else if (s === 'media') {
            actionBtn = `<button class="btn-sm btn-action" onclick="triggerAction(this, '${content.id}', 'assemble')"><i class="ri-movie-line"></i> Assemble Video</button>`;
        } else if (s === 'completed') {
            actionBtn = `<button class="btn-sm btn-action" style="background:#00b894;" onclick="playVideo('${content.id}')"><i class="ri-play-fill"></i> Play Video</button>`;
        }

        card.innerHTML = `
            <div class="card-tags">
                <span class="tag tag-platform">${content.platform}</span>
            </div>
            <div class="card-title">${content.title}</div>
            <div class="card-desc">${content.description || 'No description provided.'}</div>
            <div class="card-actions">
                ${actionBtn}
            </div>
        `;
        
        if(cols[colId]) {
            cols[colId].appendChild(card);
        }
    });
    
    Object.keys(cols).forEach(k => {
        const countEl = document.getElementById(`count-${k}`);
        if(countEl && cols[k]) countEl.innerText = cols[k].children.length;
    });

    updateBannerStatus();
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
                <h3 style="font-size: 16px; font-weight: 600; margin-bottom: 8px;">${idea.title}</h3>
                <p style="font-size: 13px; color: var(--text-muted); margin-bottom: 20px; line-height: 1.5;">${idea.description || 'No description provided.'}</p>
                <div style="display: flex; gap: 10px;">
                    <button class="btn-sm btn-action" style="flex: 1;" onclick="launchIdeaE2E('${idea.id}', '${escapeHtml(idea.title)}', '${escapeHtml(idea.description)}', '${idea.platform}')">
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
        
        activeTasks[content.id] = { title: content.title, label: 'Researching', step: 'Researching topic & audience...' };
        updateBannerStatus();
        await fetchPipeline();

        await triggerAction(content.id, 'research', 'Researching');
        await triggerAction(content.id, 'script', 'Writing Script');
        await triggerAction(content.id, 'scenes', 'Planning Scenes');
        await triggerAction(content.id, 'media', 'Generating Media');
        await triggerAction(content.id, 'assemble', 'Assembling Video');
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

        const completed = contents.filter(c => c.status === 'completed');

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

            let videoUrl = videoAsset.path.replace(/\\/g, '/').replace(/.*data\/assets\//, '/assets/');
            if (!videoUrl.startsWith('/')) videoUrl = '/' + videoUrl;

            const card = document.createElement('div');
            card.className = 'glass';
            card.style.padding = '20px';
            card.style.borderRadius = '18px';
            card.innerHTML = `
                <div style="position: relative; border-radius: 12px; overflow: hidden; margin-bottom: 16px; background: #000; height: 240px; display: flex; align-items: center; justify-content: center;">
                    <video src="${videoUrl}#t=0.5" style="width: 100%; height: 100%; object-fit: cover;" preload="metadata"></video>
                    <button onclick="playVideo('${content.id}')" style="position: absolute; width: 54px; height: 54px; border-radius: 50%; background: linear-gradient(135deg, #00b894, #00cec9); color: white; border: none; font-size: 24px; cursor: pointer; display: flex; align-items: center; justify-content: center; box-shadow: 0 6px 20px rgba(0, 184, 148, 0.6);">
                        <i class="ri-play-fill" style="margin-left: 3px;"></i>
                    </button>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span class="tag tag-platform">${content.platform || 'Shorts'}</span>
                    <span style="font-size: 11px; color: #00b894; font-weight: 600;">Ready</span>
                </div>
                <h3 style="font-size: 15px; font-weight: 600; margin-bottom: 14px;">${content.title}</h3>
                <div style="display: flex; gap: 10px;">
                    <button class="btn-sm btn-action" style="flex: 1;" onclick="playVideo('${content.id}')">
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
            // Fallback reset loop
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

async function triggerAction(btnEl, contentId, action, customLabel = null, modelOverride = null) {
    if (typeof btnEl === 'string') {
        modelOverride = customLabel;
        customLabel = action;
        action = contentId;
        contentId = btnEl;
        btnEl = null;
    }

    const actionLabels = {
        'research': 'Researching',
        'script': 'Writing Script',
        'scenes': 'Planning Scenes',
        'media': 'Generating Media',
        'assemble': 'Assembling Video'
    };

    const label = customLabel || actionLabels[action] || 'Processing';
    activeTasks[contentId] = { label: label, step: `${label}...` };
    updateBannerStatus();
    fetchPipeline();

    try {
        let res;
        if (action === 'research') {
            const m = modelOverride || document.getElementById('modelResearch')?.value;
            const q = m ? `?model=${encodeURIComponent(m)}` : '';
            res = await fetch(`${API_BASE}/content/${contentId}/research/${q}`, { method: 'POST' });
        } else if (action === 'script') {
            const m = modelOverride || document.getElementById('modelScript')?.value;
            const q = m ? `?model=${encodeURIComponent(m)}` : '';
            res = await fetch(`${API_BASE}/content/${contentId}/scripts/generate${q}`, { method: 'POST' });
        } else if (action === 'scenes') {
            const m = modelOverride || document.getElementById('modelScene')?.value;
            const q = m ? `?model=${encodeURIComponent(m)}` : '';
            res = await fetch(`${API_BASE}/content/${contentId}/scenes/generate${q}`, { method: 'POST' });
        } else if (action === 'media') {
            res = await fetch(`${API_BASE}/content/${contentId}/scenes/`);
            if (res.ok) {
                const scenes = await res.json();
                for (let s of scenes) {
                    try { await fetch(`${API_BASE}/scenes/${s.id}/image`, {method:'POST'}); } catch(e){}
                    try { await fetch(`${API_BASE}/scenes/${s.id}/voice`, {method:'POST'}); } catch(e){}
                }
                await fetch(`${API_BASE}/content/${contentId}`, {
                    method: 'PUT',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({status: 'media'})
                });
            }
        } else if (action === 'assemble') {
            res = await fetch(`${API_BASE}/content/${contentId}/video/generate`, { method: 'POST' });
            if (res.ok) {
                delete activeTasks[contentId];
                updateBannerStatus();
                await fetchPipeline();
                playVideo(contentId);
                return;
            }
        }
        
        if (res && !res.ok) {
            const errBody = await res.json().catch(() => ({}));
            throw new Error(`Server returned ${res.status}: ${JSON.stringify(errBody)}`);
        }
    } finally {
        delete activeTasks[contentId];
        updateBannerStatus();
        await fetchPipeline();
    }
}

async function submitEndToEnd() {
    const title = document.getElementById('ideaTitle').value;
    const desc = document.getElementById('ideaDesc').value;
    const platform = document.getElementById('ideaPlatform').value;
    const type = document.getElementById('ideaType').value;

    const mResearch = document.getElementById('modelResearch')?.value;
    const mScript = document.getElementById('modelScript')?.value;
    const mScene = document.getElementById('modelScene')?.value;
    
    if (!title) {
        document.getElementById('ideaTitle').focus();
        document.getElementById('ideaTitle').style.borderColor = '#ff7675';
        setTimeout(() => { document.getElementById('ideaTitle').style.borderColor = ''; }, 2000);
        return;
    }
    
    const btn = document.getElementById('e2eCreateBtn');
    const origText = btn ? btn.innerHTML : '';
    if (btn) {
        btn.innerHTML = `<i class="ri-loader-4-line spin"></i> Launching E2E...`;
        btn.disabled = true;
    }

    try {
        // 1. Create Idea & Content
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
        
        // 2. Close modal & update pipeline
        toggleModal('ideaModal');
        document.getElementById('ideaForm').reset();
        
        // 3. Register active task state so circular spinner shows immediately on card and banner!
        activeTasks[content.id] = { title: content.title, label: 'Researching', step: 'Researching topic & audience...' };
        updateBannerStatus();
        await fetchPipeline();

        // 4. Run pipeline steps passing selected LLMs per task!
        activeTasks[content.id] = { title: content.title, label: 'Researching', step: `Researching (${mResearch || 'LLM'})...` };
        updateBannerStatus();
        await triggerAction(content.id, 'research', 'Researching', mResearch);

        activeTasks[content.id] = { title: content.title, label: 'Writing Script', step: `Writing script (${mScript || 'LLM'})...` };
        updateBannerStatus();
        await triggerAction(content.id, 'script', 'Writing Script', mScript);

        activeTasks[content.id] = { title: content.title, label: 'Planning Scenes', step: `Planning scenes (${mScene || 'LLM'})...` };
        updateBannerStatus();
        await triggerAction(content.id, 'scenes', 'Planning Scenes', mScene);

        activeTasks[content.id] = { title: content.title, label: 'Gen Media', step: 'Generating AI images & voice audio...' };
        updateBannerStatus();
        await triggerAction(content.id, 'media', 'Generating Media');

        activeTasks[content.id] = { title: content.title, label: 'Assembling Video', step: 'Assembling video clips & sound...' };
        updateBannerStatus();
        await triggerAction(content.id, 'assemble', 'Assembling Video');
        
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

ws.onmessage = function(event) {
    const logs = document.getElementById('terminal-logs');
    try {
        const data = JSON.parse(event.data);
        const line = document.createElement('div');
        line.className = 'log-line';
        if (data.agent === 'System') line.classList.add('system');
        if (data.agent === 'LLMService' || data.agent === 'Llama3.1') line.classList.add('llm');
        
        line.innerHTML = `<span class="time">[${data.time || new Date().toLocaleTimeString()}]</span> <span class="agent">[${data.agent || 'System'}]</span> <span class="text">${escapeHtml(data.message)}</span>`;
        
        logs.appendChild(line);
        logs.scrollTop = logs.scrollHeight;
    } catch (e) {
        console.error("Failed to parse log message:", event.data);
    }
};

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
        
        let url = videoAsset.path.replace(/\\/g, '/').replace(/.*data\/assets\//, '/assets/');
        if (!url.startsWith('/')) url = '/' + url;
        
        url += (url.includes('?') ? '&' : '?') + 't=' + Date.now();
        
        const player = document.getElementById('videoPlayer');
        const bigPlayBtn = document.getElementById('bigPlayBtn');

        player.pause();
        player.src = url;
        player.muted = false;
        player.volume = 1.0;
        player.load();
        
        if (bigPlayBtn) {
            bigPlayBtn.style.display = 'flex';
        }

        toggleModal('videoModal');
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
