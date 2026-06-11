// State Management
const state = {
    selectedMetric: 'shots',
    filters: {
        league: '',
        team: '',
        player: '',
        season: '',
        situation: '',
        shot_type: ''
    },
    rawFiltersData: null, // Initial response from /api/filters
    currentData: null,    // Response from /api/data
    xBins: 12,
    yBins: 8
};

// Grid Configuration
const pitchConfig = {
    xStart: 50,
    xEnd: 950,
    yStart: 30,
    yEnd: 620,
    width: 900,
    height: 590
};

// DOM Elements
const dom = {
    leagueSelect: document.getElementById('filter-league'),
    teamSelect: document.getElementById('filter-team'),
    playerSelect: document.getElementById('filter-player'),
    seasonSelect: document.getElementById('filter-season'),
    situationSelect: document.getElementById('filter-situation'),
    shotTypeSelect: document.getElementById('filter-shot-type'),
    btnReset: document.getElementById('btn-reset'),
    
    metricButtons: document.querySelectorAll('.metric-btn'),
    
    statShots: document.getElementById('stat-shots'),
    statGoals: document.getElementById('stat-goals'),
    statXg: document.getElementById('stat-xg'),
    statGoalRate: document.getElementById('stat-goal-rate'),
    statAvgXg: document.getElementById('stat-avg-xg'),
    
    heatmapGrid: document.getElementById('heatmap-grid'),
    footballPitch: document.getElementById('football-pitch'),
    pitchContainer: document.getElementById('pitch-container'),
    zoneTooltip: document.getElementById('zone-tooltip'),
    
    topPlayersList: document.getElementById('top-players-list'),
    bodypartBreakdown: document.getElementById('bodypart-breakdown'),
    situationBreakdown: document.getElementById('situation-breakdown'),
    
    // Tooltip subfields
    ttShots: document.getElementById('tt-shots'),
    ttGoals: document.getElementById('tt-goals'),
    ttXg: document.getElementById('tt-xg'),
    ttConversion: document.getElementById('tt-conversion'),
    ttAvgXg: document.getElementById('tt-avg-xg'),
    
    // Cluster Monitor
    btnStartJob: document.getElementById('btn-start-job'),
    mrStateBadge: document.getElementById('mr-state-badge'),
    mrMessage: document.getElementById('mr-message'),
    mrProgressFill: document.getElementById('mr-progress-fill'),
    workersGrid: document.getElementById('workers-grid')
};

// Initialize Application
async function init() {
    setupEventListeners();
    await fetchInitialFilters();
    // Do not call updateDashboardData() initially, let user trigger it.
}

// Event Listeners setup
function setupEventListeners() {
    // Dropdown filters
    dom.leagueSelect.addEventListener('change', handleLeagueChange);
    dom.teamSelect.addEventListener('change', handleTeamChange);
    dom.playerSelect.addEventListener('input', handlePlayerChange);
    dom.seasonSelect.addEventListener('change', (e) => {
        state.filters.season = e.target.value;
    });
    dom.situationSelect.addEventListener('change', (e) => {
        state.filters.situation = e.target.value;
    });
    dom.shotTypeSelect.addEventListener('change', (e) => {
        state.filters.shot_type = e.target.value;
    });

    // Reset button
    dom.btnReset.addEventListener('click', resetFilters);

    // Metric selector buttons
    dom.metricButtons.forEach(btn => {
        btn.addEventListener('click', (e) => {
            const button = e.currentTarget;
            dom.metricButtons.forEach(b => b.classList.remove('active'));
            button.classList.add('active');
            
            state.selectedMetric = button.dataset.metric;
            renderHeatmap();
        });
    });

    // MapReduce Job Start
    dom.btnStartJob.addEventListener('click', startMapReduceJob);
}

// Fetch Initial Dropdowns (Leagues, Seasons, Situations, Bodyparts)
async function fetchInitialFilters() {
    try {
        const response = await fetch('/api/filters');
        if (!response.ok) throw new Error("Error fetching filters");
        
        const data = await response.json();
        state.rawFiltersData = data;
        
        // Populate leagues
        data.leagues.forEach(league => {
            const opt = document.createElement('option');
            opt.value = league;
            opt.textContent = league;
            dom.leagueSelect.appendChild(opt);
        });

        // Populate seasons
        data.seasons.forEach(season => {
            const opt = document.createElement('option');
            opt.value = season;
            opt.textContent = season;
            dom.seasonSelect.appendChild(opt);
        });

        // Populate situations
        data.situations.forEach(situation => {
            const opt = document.createElement('option');
            opt.value = situation;
            opt.textContent = situation;
            dom.situationSelect.appendChild(opt);
        });

        // Populate body parts (shot types)
        data.shot_types.forEach(type => {
            const opt = document.createElement('option');
            opt.value = type;
            opt.textContent = type;
            dom.shotTypeSelect.appendChild(opt);
        });

        // Populate players datalist
        await populatePlayersDatalist();

    } catch (err) {
        console.error("Failed to load initial filters:", err);
    }
}

// Handle League Dropdown Change (Cascades to Teams)
async function handleLeagueChange(e) {
    const league = e.target.value;
    state.filters.league = league;
    state.filters.team = '';
    state.filters.player = '';
    
    // Clear search player input
    dom.playerSelect.value = '';
    
    // Reset dependant dropdowns
    dom.teamSelect.innerHTML = '<option value="">Cargando equipos...</option>';
    dom.teamSelect.disabled = true;
    
    if (league) {
        try {
            const response = await fetch(`/api/teams?league=${encodeURIComponent(league)}`);
            const data = await response.json();
            
            dom.teamSelect.innerHTML = '<option value="">Todos los equipos</option>';
            data.teams.forEach(team => {
                const opt = document.createElement('option');
                opt.value = team;
                opt.textContent = team;
                dom.teamSelect.appendChild(opt);
            });
            dom.teamSelect.disabled = false;
        } catch (err) {
            console.error("Failed to fetch teams:", err);
            dom.teamSelect.innerHTML = '<option value="">Error cargando equipos</option>';
        }
    } else {
        dom.teamSelect.innerHTML = '<option value="">Selecciona una liga primero</option>';
        dom.teamSelect.disabled = true;
    }
    
    // Refresh players datalist for the selected league
    await populatePlayersDatalist();
}

// Handle Team Dropdown Change (Cascades to Players)
async function handleTeamChange(e) {
    const team = e.target.value;
    state.filters.team = team;
    state.filters.player = '';
    
    // Clear search player input
    dom.playerSelect.value = '';
    
    // Refresh players datalist for the selected team/league
    await populatePlayersDatalist();
}

// Handle Player Input Search Change
function handlePlayerChange(e) {
    state.filters.player = e.target.value;
}

// Populates players autocomplete list based on league/team selections
async function populatePlayersDatalist() {
    try {
        const league = state.filters.league;
        const team = state.filters.team;
        
        let url = '/api/players';
        const params = new URLSearchParams();
        if (league) params.append('league', league);
        if (team) params.append('team', team);
        
        const queryString = params.toString();
        if (queryString) url += '?' + queryString;
        
        const response = await fetch(url);
        const data = await response.json();
        
        const datalist = document.getElementById('players-datalist');
        datalist.innerHTML = '';
        
        data.players.forEach(player => {
            const opt = document.createElement('option');
            opt.value = player;
            datalist.appendChild(opt);
        });
    } catch (err) {
        console.error("Failed to populate players datalist:", err);
    }
}

// Reset all filters to default
async function resetFilters() {
    dom.leagueSelect.value = '';
    dom.teamSelect.innerHTML = '<option value="">Selecciona una liga primero</option>';
    dom.teamSelect.disabled = true;
    dom.playerSelect.value = '';
    dom.seasonSelect.value = '';
    dom.situationSelect.value = '';
    dom.shotTypeSelect.value = '';
    
    state.filters = {
        league: '',
        team: '',
        player: '',
        season: '',
        situation: '',
        shot_type: ''
    };
    
    await populatePlayersDatalist();
    
    state.currentData = null;
    renderStatsSummary();
    renderHeatmap();
    renderTopPlayers();
    renderBreakdowns();
}

// Query main dashboard data from server
async function updateDashboardData() {
    try {
        // Build query string
        const params = new URLSearchParams();
        for (const [k, v] of Object.entries(state.filters)) {
            if (v) params.append(k, v);
        }
        
        const response = await fetch(`/api/data?${params.toString()}`);
        if (!response.ok) throw new Error("Error fetching data");
        
        const data = await response.json();
        state.currentData = data;
        
        renderStatsSummary();
        renderHeatmap();
        renderTopPlayers();
        renderBreakdowns();
        
    } catch (err) {
        console.error("Failed to fetch dashboard data:", err);
    }
}

// Render overall stats summary cards
function renderStatsSummary() {
    if (!state.currentData) return;
    const summary = state.currentData.summary;
    
    dom.statShots.textContent = summary.total_shots.toLocaleString();
    dom.statGoals.textContent = summary.total_goals.toLocaleString();
    dom.statXg.textContent = summary.total_xg.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    dom.statGoalRate.textContent = (summary.goal_rate * 100).toFixed(1) + '%';
    dom.statAvgXg.textContent = summary.avg_xg.toFixed(3);
}

// Render tactical pitch heatmap grid using SVG
function renderHeatmap() {
    if (!state.currentData) return;
    
    const grid = state.currentData.grid;
    const metric = state.selectedMetric;
    
    // Clear current grid
    dom.heatmapGrid.innerHTML = '';
    
    // Create a 2D map for easy lookup: (x, y) -> cell data
    const gridMap = {};
    grid.forEach(cell => {
        gridMap[`${cell.zone_x},${cell.zone_y}`] = cell;
    });
    
    // Find maximum value of selected metric in current dataset for color scale sizing
    let maxMetricVal = 0;
    grid.forEach(cell => {
        const val = cell[metric] || 0;
        if (val > maxMetricVal) maxMetricVal = val;
    });
    
    if (maxMetricVal === 0) maxMetricVal = 1; // Prevent division by zero
    
    // Dimensions of each cell in SVG coordinates
    const cellWidth = pitchConfig.width / state.xBins;
    const cellHeight = pitchConfig.height / state.yBins;
    
    // Draw cells
    for (let y = 0; y < state.yBins; y++) {
        for (let x = 0; x < state.xBins; x++) {
            const key = `${x},${y}`;
            const cellData = gridMap[key] || {
                zone_x: x,
                zone_y: y,
                shots: 0,
                goals: 0,
                misses: 0,
                xg_sum: 0.0,
                goal_rate: 0.0,
                avg_xg: 0.0
            };
            
            const val = cellData[metric] || 0;
            const ratio = val / maxMetricVal;
            
            // Calculate coordinates on SVG
            const xPos = pitchConfig.xStart + x * cellWidth;
            const yPos = pitchConfig.yStart + y * cellHeight;
            
            // Create SVG rect
            const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            rect.setAttribute('x', xPos);
            rect.setAttribute('y', yPos);
            rect.setAttribute('width', cellWidth);
            rect.setAttribute('height', cellHeight);
            rect.setAttribute('class', 'heatmap-cell');
            
            // Colors: HSL transition from Green (130) -> Orange (40) -> Red (0)
            // Low values have low opacity, high values are solid
            let fillColor = 'transparent';
            if (val > 0) {
                // Map ratio linearly from hue 130 to 0
                const hue = 130 - ratio * 130;
                // Scale opacity: higher ratio = higher opacity
                const opacity = 0.15 + ratio * 0.75;
                fillColor = `hsla(${hue}, 85%, 50%, ${opacity})`;
            }
            rect.setAttribute('fill', fillColor);
            
            // Attach mouse events
            rect.addEventListener('mouseover', (e) => showTooltip(e, cellData));
            rect.addEventListener('mousemove', moveTooltip);
            rect.addEventListener('mouseout', hideTooltip);
            
            dom.heatmapGrid.appendChild(rect);
        }
    }
}

// Tooltip Helpers
function showTooltip(e, cell) {
    dom.ttShots.textContent = cell.shots.toLocaleString();
    dom.ttGoals.textContent = cell.goals.toLocaleString();
    dom.ttXg.textContent = cell.xg_sum.toFixed(3);
    dom.ttConversion.textContent = (cell.goal_rate * 100).toFixed(1) + '%';
    dom.ttAvgXg.textContent = cell.avg_xg.toFixed(3);
    
    // Set header with field context (e.g. Attacking / Defensive zone)
    let areaDesc = "";
    if (cell.zone_x >= 9) areaDesc = "Área de Ataque";
    else if (cell.zone_x >= 6) areaDesc = "Mitad Ofensiva";
    else if (cell.zone_x >= 3) areaDesc = "Mitad Defensiva";
    else areaDesc = "Área de Salida";
    
    dom.zoneTooltip.querySelector('.tooltip-header').textContent = `${areaDesc} [${cell.zone_x}, ${cell.zone_y}]`;
    
    // Remove hidden class
    dom.zoneTooltip.classList.remove('hidden');
    moveTooltip(e);
}

function moveTooltip(e) {
    const containerRect = dom.pitchContainer.getBoundingClientRect();
    
    // Calculate position relative to container
    let x = e.clientX - containerRect.left + 15;
    let y = e.clientY - containerRect.top + 15;
    
    // Boundary check so tooltip stays inside container
    const tooltipWidth = 180;
    const tooltipHeight = 130;
    
    if (x + tooltipWidth > containerRect.width) {
        x = e.clientX - containerRect.left - tooltipWidth - 15;
    }
    
    if (y + tooltipHeight > containerRect.height) {
        y = e.clientY - containerRect.top - tooltipHeight - 15;
    }
    
    dom.zoneTooltip.style.left = `${x}px`;
    dom.zoneTooltip.style.top = `${y}px`;
}

function hideTooltip() {
    dom.zoneTooltip.classList.add('hidden');
}

// Render Top Players Table
function renderTopPlayers() {
    if (!state.currentData) return;
    const players = state.currentData.top_players;
    
    dom.topPlayersList.innerHTML = '';
    
    if (players.length === 0) {
        dom.topPlayersList.innerHTML = `
            <tr>
                <td colspan="4" class="loading-cell">No se encontraron goleadores con estos filtros.</td>
            </tr>
        `;
        return;
    }
    
    players.forEach(p => {
        const tr = document.createElement('tr');
        
        const tdName = document.createElement('td');
        tdName.textContent = p.player;
        
        const tdShots = document.createElement('td');
        tdShots.className = 'num-col';
        tdShots.textContent = p.shots.toLocaleString();
        
        const tdGoals = document.createElement('td');
        tdGoals.className = 'num-col';
        tdGoals.textContent = p.goals.toLocaleString();
        
        const tdXg = document.createElement('td');
        tdXg.className = 'num-col';
        tdXg.textContent = p.xg.toFixed(2);
        
        tr.appendChild(tdName);
        tr.appendChild(tdShots);
        tr.appendChild(tdGoals);
        tr.appendChild(tdXg);
        
        dom.topPlayersList.appendChild(tr);
    });
}

// Render horizontal bar chart breakdowns (Body part & Situations)
function renderBreakdowns() {
    if (!state.currentData) return;
    const breakdowns = state.currentData.breakdowns;
    const totalShots = state.currentData.summary.total_shots || 1;
    
    // 1. Body Part (Shot types)
    dom.bodypartBreakdown.innerHTML = '';
    const bodyparts = breakdowns.shot_types;
    
    // Spanish mapping for labels
    const bodypartLabels = {
        'LeftFoot': 'Pie Izquierdo',
        'RightFoot': 'Pie Derecho',
        'Head': 'Cabeza',
        'OtherBodyPart': 'Otro'
    };
    
    Object.entries(bodyparts).forEach(([type, count]) => {
        const pct = (count / totalShots * 100).toFixed(1);
        const label = bodypartLabels[type] || type;
        dom.bodypartBreakdown.appendChild(createChartRow(label, count, pct));
    });
    
    // 2. Situations
    dom.situationBreakdown.innerHTML = '';
    const situations = breakdowns.situations;
    
    const situationLabels = {
        'OpenPlay': 'Jugada Abierta',
        'FromCorner': 'Tiro de Esquina',
        'DirectFreekick': 'Tiro Libre Directo',
        'Penalty': 'Penal',
        'SetPiece': 'Balón Parado'
    };
    
    Object.entries(situations).forEach(([sit, count]) => {
        const pct = (count / totalShots * 100).toFixed(1);
        const label = situationLabels[sit] || sit;
        dom.situationBreakdown.appendChild(createChartRow(label, count, pct));
    });
    
    // Trigger transition animation in next tick
    setTimeout(() => {
        document.querySelectorAll('.bar-fill').forEach(fill => {
            fill.style.width = fill.dataset.pct + '%';
        });
    }, 50);
}

// Helper to create horizontal bar chart elements
function createChartRow(label, count, pct) {
    const row = document.createElement('div');
    row.className = 'chart-bar-row';
    
    row.innerHTML = `
        <div class="bar-labels">
            <span class="bar-name">${label}</span>
            <span class="bar-val">${count.toLocaleString()} (${pct}%)</span>
        </div>
        <div class="bar-track">
            <div class="bar-fill" data-pct="${pct}"></div>
        </div>
    `;
    
    return row;
}

// ==========================================
// Distributed MapReduce Logic
// ==========================================

let statusInterval = null;

async function startMapReduceJob() {
    try {
        dom.btnStartJob.disabled = true;
        
        // Build query string
        const params = new URLSearchParams();
        for (const [k, v] of Object.entries(state.filters)) {
            if (v) params.append(k, v);
        }
        
        const response = await fetch(`/api/start_job?${params.toString()}`);
        if (!response.ok) throw new Error("Failed to start job");
        
        // Start polling status
        if (statusInterval) clearInterval(statusInterval);
        statusInterval = setInterval(pollJobStatus, 500);
        pollJobStatus(); // fetch immediately
    } catch (err) {
        console.error(err);
        dom.btnStartJob.disabled = false;
        alert("Error starting MapReduce job");
    }
}

async function pollJobStatus() {
    try {
        const response = await fetch('/api/job_status');
        const data = await response.json();
        
        renderJobStatus(data);
        
        if (data.state === 'finished' || data.state === 'error') {
            clearInterval(statusInterval);
            dom.btnStartJob.disabled = false;
            
            if (data.state === 'finished') {
                // Fetch the final result!
                const res = await fetch('/api/job_result');
                const finalData = await res.json();
                state.currentData = finalData;
                
                renderStatsSummary();
                renderHeatmap();
                renderTopPlayers();
                renderBreakdowns();
            }
        }
    } catch (err) {
        console.error("Error polling status", err);
    }
}

function renderJobStatus(data) {
    // Update badge
    dom.mrStateBadge.className = `state-badge ${data.state}`;
    let stateText = data.state.toUpperCase();
    if (data.state === 'mapping') stateText = 'MAP';
    else if (data.state === 'reducing') stateText = 'REDUCE';
    else if (data.state === 'shuffling') stateText = 'SHUFFLE';
    dom.mrStateBadge.textContent = stateText;
    
    // Update message and progress
    dom.mrMessage.textContent = data.message;
    dom.mrProgressFill.style.width = `${data.progress}%`;
    
    // Render workers
    dom.workersGrid.innerHTML = '';
    
    Object.entries(data.worker_status).forEach(([url, status], i) => {
        const isActive = status !== 'idle' && status !== 'error';
        const iconClass = isActive ? 'fa-solid fa-gear active worker-icon' : 'fa-solid fa-server worker-icon';
        const colorStyle = isActive ? 'color: #3b82f6;' : 'color: var(--text-secondary);';
        
        const name = `Worker ${i+1}`;
        
        const card = document.createElement('div');
        card.className = 'worker-card';
        card.innerHTML = `
            <div class="worker-header">
                <i class="${iconClass}" style="${colorStyle}"></i> ${name}
            </div>
            <div class="worker-status" title="${status}">
                ${status}
            </div>
        `;
        dom.workersGrid.appendChild(card);
    });
}

// Start application
window.addEventListener('DOMContentLoaded', init);
