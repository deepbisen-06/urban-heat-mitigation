// -------------------------------------------------------------
// GeoHeat - Frontend Controller, Canvas GIS & Microclimate Canyon
// -------------------------------------------------------------

// Backend API Base URL
const API_URL = "http://localhost:8000";

// App State
let appState = {
    metadata: {},
    cells: [],
    weather: {},
    selectedCellId: null,
    activeLayer: 'temp_surface',
    activeProfile: 'dense_highrise',
    budget: 2000000,
    strategy: 'balanced',
    gridSize: 40,
    playbackTime: 12,      // Default 12 PM (Noon)
    playbackInterval: null, // For 24h play cycle
    
    // Advanced Real-world features
    activeTool: 'inspect', // 'inspect', 'paint_green', 'paint_cool'
    isPainting: false,
    showWindParticles: false,
    particles: []
};

// Canvas references
const canvas = document.getElementById("gis-grid-canvas");
const ctx = canvas.getContext("2d");
let hoveredCellId = null;

// Chart references
let driverChart = null;
let paretoChart = null;
let diurnalChart = null;

// Initialization
document.addEventListener("DOMContentLoaded", () => {
    setupCanvas();
    setupEventListeners();
    loadCityArchetype(appState.activeProfile);
});

// Setup canvas bounds
function setupCanvas() {
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width;
    canvas.height = rect.height || 420;
}

// Load default city data
async function loadCityArchetype(profile) {
    showLoading(true);
    try {
        const response = await fetch(`${API_URL}/api/city-data?profile=${profile}`);
        if (!response.ok) throw new Error("Network error loading archetype");
        
        const data = await response.json();
        
        appState.metadata = data.metadata;
        appState.cells = data.cells;
        appState.weather = data.metadata.weather;
        appState.gridSize = data.metadata.grid_size;
        appState.activeProfile = profile;
        appState.playbackTime = 12; // Reset to Noon
        
        // Sync diurnal controls
        document.getElementById("diurnal-time-slider").value = 12;
        document.getElementById("current-playback-time").textContent = "12:00 PM";
        updateTickHighlight(12);
        
        // Update weather sliders
        updateWeatherUI();
        
        // Reset selection
        appState.selectedCellId = null;
        document.getElementById("inspector-content").classList.add("hidden");
        document.getElementById("inspector-placeholder").classList.remove("hidden");
        
        // Draw grid
        drawGrid();
        
        // Trigger Pareto curve load in background
        fetchParetoFrontier();
        
        // Reset ROI metrics
        updateROIMetrics({
            total_capital_cost: 0,
            annual_energy_saved_kwh: 0,
            annual_energy_savings: 0,
            annual_carbon_saved_tons: 0,
            annual_carbon_savings: 0,
            annual_stormwater_retained_m3: 0,
            annual_stormwater_savings: 0,
            total_annual_savings: 0,
            payback_years: 0,
            roi_percentage: 0
        });

    } catch (err) {
        console.error("Failed to load archetype:", err);
        alert("Failed to connect to the backend server. Make sure main.py is running!");
    } finally {
        showLoading(false);
    }
}

// Draw cells on Canvas Grid
function drawGrid() {
    if (!appState.cells.length) return;
    
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    const cellW = canvas.width / appState.gridSize;
    const cellH = canvas.height / appState.gridSize;
    
    appState.cells.forEach(cell => {
        const x = cell.x * cellW;
        const y = cell.y * cellH;
        
        ctx.fillStyle = getCellColor(cell);
        ctx.fillRect(x, y, cellW, cellH);
        
        // Grid lines
        ctx.strokeStyle = "rgba(255, 255, 255, 0.03)";
        ctx.lineWidth = 0.5;
        ctx.strokeRect(x, y, cellW, cellH);
        
        // Highlight if hovered
        if (cell.id === hoveredCellId) {
            ctx.strokeStyle = "rgba(0, 225, 255, 0.8)";
            ctx.lineWidth = 2;
            ctx.strokeRect(x + 1, y + 1, cellW - 2, cellH - 2);
        }
        
        // Highlight if selected
        if (cell.id === appState.selectedCellId) {
            ctx.strokeStyle = "#00ffaa";
            ctx.lineWidth = 2.5;
            ctx.strokeRect(x + 1, y + 1, cellW - 2, cellH - 2);
        }
    });
}

// Particle simulation functions for Wind Corridors
function updateAndDrawParticles() {
    if (!appState.showWindParticles || !appState.cells.length) return;
    
    const cellW = canvas.width / appState.gridSize;
    const cellH = canvas.height / appState.gridSize;
    
    // Initialize particles if empty
    if (appState.particles.length === 0) {
        for (let i = 0; i < 200; i++) {
            appState.particles.push(createRandomParticle());
        }
    }
    
    appState.particles.forEach(p => {
        // Look up grid cell under particle
        const col = Math.floor(p.x / cellW);
        const row = Math.floor(p.y / cellH);
        
        let localDensity = 0.4;
        let isFlowChannel = false;
        
        if (col >= 0 && col < appState.gridSize && row >= 0 && row < appState.gridSize) {
            const cell = appState.cells[row * appState.gridSize + col];
            if (cell) {
                localDensity = cell.building_density;
                isFlowChannel = (cell.land_use === 'water' || cell.land_use === 'park');
            }
        }
        
        // Update velocity (wind flow channels speed up particle, high concrete slows it)
        let windBase = appState.weather.wind_speed || 1.5;
        let speedFactor = isFlowChannel ? 1.5 : (1.0 - localDensity * 0.85);
        
        p.vx = windBase * 1.5 * speedFactor * p.speedMultiplier;
        
        // Minor horizontal/vertical weave
        p.vy += (Math.random() - 0.5) * 0.15;
        p.vy = Math.max(-0.4, Math.min(0.4, p.vy));
        
        p.x += p.vx;
        p.y += p.vy;
        
        // Reset when particle flows off-screen
        if (p.x > canvas.width) {
            p.x = 0;
            p.y = Math.random() * canvas.height;
            p.alpha = 0.2 + Math.random() * 0.6;
        }
        
        // Render particle with glowing trace
        ctx.fillStyle = `rgba(0, 225, 255, ${p.alpha})`;
        ctx.beginPath();
        ctx.arc(p.x, p.y, p.radius, 0, 2 * Math.PI);
        ctx.fill();
    });
}

function createRandomParticle() {
    return {
        x: Math.random() * canvas.width,
        y: Math.random() * canvas.height,
        vx: 1,
        vy: 0,
        radius: 1.0 + Math.random() * 1.8,
        alpha: 0.15 + Math.random() * 0.6,
        speedMultiplier: 0.7 + Math.random() * 0.6
    };
}

// Continuous animation loop hook
function runAnimationLoop() {
    if (!appState.showWindParticles) return;
    drawGrid();
    updateAndDrawParticles();
    requestAnimationFrame(runAnimationLoop);
}

// Convert cell attribute to color based on active layer & diurnal time
function getCellColor(cell) {
    const layer = appState.activeLayer;
    const hour = appState.playbackTime;
    
    // Calculate client-side diurnal adjustments for smooth animating maps!
    const hourFactor = Math.sin((hour - 9) * Math.PI / 12); // -1 to +1
    
    // Physical parameters shift
    const baseAirTemp = appState.weather.air_temp_noon || 33;
    const localTaNoon = cell.temp_air || baseAirTemp;
    const localTsNoon = cell.temp_surface || (localTaNoon + 8);
    
    // Simulate diurnal thermal cycles
    const surfaceAmplitude = 14 + 10 * cell.building_density - 6 * cell.albedo;
    const currentTs = localTsNoon + (surfaceAmplitude * hourFactor - surfaceAmplitude);
    
    const airAmplitude = 6;
    const currentTa = localTaNoon + (airAmplitude * hourFactor - airAmplitude);
    
    // Water behaves differently (low thermal diurnal shift)
    let finalTs = currentTs;
    let finalTa = currentTa;
    if (cell.land_use === 'water') {
        finalTs = localTsNoon - 2 + (2 * hourFactor - 2);
        finalTa = localTaNoon - 1 + (1.5 * hourFactor - 1.5);
    }

    if (cell.land_use === 'water' && layer !== 'temp_surface' && layer !== 'temp_air' && layer !== 'wbgt') {
        return "rgba(22, 53, 110, 0.85)"; 
    }
    
    switch (layer) {
        case 'temp_surface':
            return getTemperatureColor(finalTs);
        case 'temp_air':
            return getTemperatureColor(finalTa, 28, 45);
        case 'wbgt':
            // Calculate on-the-fly WBGT:
            const rhNoon = appState.weather.relative_humidity || 0.6;
            const currentRh = Math.min(0.95, Math.max(0.1, rhNoon + 0.20 * (1.0 - hourFactor)));
            
            // Stull wet bulb formula
            const RH_pct = currentRh * 100;
            const T_nw = finalTa * Math.atan(0.151977 * Math.pow(RH_pct + 8.313659, 0.5)) + Math.atan(finalTa + RH_pct) - Math.atan(RH_pct - 1.676331) + 0.00391838 * Math.pow(RH_pct, 1.5) * Math.atan(0.023101 * RH_pct) - 4.686035;
            
            // Globe temp
            const solarNoon = appState.weather.solar_radiation || 800;
            const currentSolar = hour >= 6 && hour <= 18 ? solarNoon * Math.sin((hour - 6) * Math.PI / 12) : 0;
            const T_g = 0.6 * finalTa + 0.3 * finalTs + 0.1 * (currentSolar / 100);
            
            const wbgt = 0.7 * T_nw + 0.2 * T_g + 0.1 * finalTa;
            return getTemperatureColor(wbgt, 18, 38);
            
        case 'ndvi':
            const nd = Math.max(0, cell.ndvi);
            return `rgba(0, ${Math.floor(100 + nd * 155)}, ${Math.floor(60 + nd * 50)}, 0.85)`;
        case 'albedo':
            const alb = Math.floor(cell.albedo * 255);
            return `rgba(${alb}, ${alb}, ${alb}, 0.85)`;
        case 'svi':
            const sv = Math.floor(cell.svi * 200);
            return `rgba(${100 + sv}, 50, ${150 + sv / 2}, 0.85)`;
        case 'risk':
            // Risk expands dynamically with time of day temperature shifts
            const tempAnomaly = Math.max(0, finalTs - 25);
            const riskVal = Math.min(1.0, (tempAnomaly / 25.0) * cell.svi);
            const rColor = Math.floor(riskVal * 255);
            return `rgba(${rColor}, ${40}, ${100 - rColor / 3}, 0.85)`;
        default:
            return "rgba(255,255,255,0.1)";
    }
}

// Interpolate temperature colors
function getTemperatureColor(temp, minT = 22, maxT = 52) {
    const norm = Math.min(1.0, Math.max(0.0, (temp - minT) / (maxT - minT)));
    const hue = (1.0 - norm) * 240; 
    return `hsla(${hue}, 85%, 50%, 0.85)`;
}

// Setup listeners and control inputs
function setupEventListeners() {
    window.addEventListener("resize", () => {
        setupCanvas();
        drawGrid();
    });
    
    // Archetype selection
    document.querySelectorAll(".btn-tab[data-profile]").forEach(btn => {
        btn.addEventListener("click", (e) => {
            document.querySelectorAll(".btn-tab[data-profile]").forEach(b => b.classList.remove("active"));
            e.currentTarget.classList.add("active");
            const profile = e.currentTarget.getAttribute("data-profile");
            
            document.getElementById("current-profile-badge").textContent = e.currentTarget.textContent.trim();
            loadCityArchetype(profile);
        });
    });
    
    // Layer toggles
    document.querySelectorAll(".btn-layer").forEach(btn => {
        btn.addEventListener("click", (e) => {
            document.querySelectorAll(".btn-layer").forEach(b => b.classList.remove("active"));
            e.currentTarget.classList.add("active");
            appState.activeLayer = e.currentTarget.getAttribute("data-layer");
            
            updateLegendLabels();
            drawGrid();
        });
    });

    // Brush Tool Selector
    document.querySelectorAll(".btn-tool[id]").forEach(btn => {
        btn.addEventListener("click", (e) => {
            document.querySelectorAll(".btn-tool").forEach(b => b.classList.remove("active"));
            e.currentTarget.classList.add("active");
            
            const toolId = e.currentTarget.id;
            if (toolId === "btn-tool-inspect") appState.activeTool = "inspect";
            else if (toolId === "btn-tool-paint-green") appState.activeTool = "paint_green";
            else if (toolId === "btn-tool-paint-cool") appState.activeTool = "paint_cool";
        });
    });

    // Toggle Wind Flow Corridors Particle Layer
    const windToggle = document.getElementById("btn-toggle-wind");
    windToggle.addEventListener("click", () => {
        appState.showWindParticles = !appState.showWindParticles;
        if (appState.showWindParticles) {
            windToggle.classList.add("active");
            appState.particles = []; // rebuild particles
            runAnimationLoop();
        } else {
            windToggle.classList.remove("active");
            drawGrid(); // redraw static grid
        }
    });

    // Climate inputs change
    const weatherInputs = ["air-temp", "humidity", "wind", "solar"];
    weatherInputs.forEach(id => {
        const slider = document.getElementById(`input-${id}`);
        slider.addEventListener("input", (e) => {
            let val = parseFloat(e.target.value);
            let displayVal = val;
            if (id === "air-temp") displayVal += " °C";
            else if (id === "humidity") displayVal = Math.round(val * 100) + " %";
            else if (id === "wind") displayVal += " m/s";
            else if (id === "solar") displayVal += " W/m²";
            
            document.getElementById(`val-${id}`).textContent = displayVal;
            
            if (id === "air-temp") appState.weather.air_temp_noon = val;
            else if (id === "humidity") appState.weather.relative_humidity = val;
            else if (id === "wind") appState.weather.wind_speed = val;
            else if (id === "solar") appState.weather.solar_radiation = val;
            
            triggerRecalculation();
        });
    });

    // Reset weather
    document.getElementById("reset-weather-btn").addEventListener("click", () => {
        const weather_defaults = data_manager_defaults_for_weather();
        appState.weather = { ...weather_defaults };
        updateWeatherUI();
        triggerRecalculation();
    });

    // Budget slider
    const budgetSlider = document.getElementById("input-budget");
    budgetSlider.addEventListener("input", (e) => {
        const val = parseFloat(e.target.value);
        appState.budget = val;
        document.getElementById("val-budget").textContent = `$${(val / 1000000).toFixed(1)}M`;
    });

    // Strategy Selection
    document.querySelectorAll("input[name='opt-strategy']").forEach(radio => {
        radio.addEventListener("change", (e) => {
            appState.strategy = e.target.value;
        });
    });

    // Optimize trigger
    document.getElementById("btn-run-optimization").addEventListener("click", () => {
        runOptimizer();
    });

    // Playback Time Slider
    const timeSlider = document.getElementById("diurnal-time-slider");
    timeSlider.addEventListener("input", (e) => {
        const hour = parseInt(e.target.value);
        updatePlaybackHour(hour);
    });

    // Play/Pause Diurnal Cycle
    const playBtn = document.getElementById("btn-play-diurnal");
    playBtn.addEventListener("click", () => {
        if (appState.playbackInterval) {
            clearInterval(appState.playbackInterval);
            appState.playbackInterval = null;
            playBtn.innerHTML = '<i class="fa-solid fa-play"></i> Play 24h Cycle';
        } else {
            playBtn.innerHTML = '<i class="fa-solid fa-pause"></i> Pause Cycle';
            appState.playbackInterval = setInterval(() => {
                let currentH = (appState.playbackTime + 1) % 24;
                timeSlider.value = currentH;
                updatePlaybackHour(currentH);
            }, 350);
        }
    });

    // Canvas Mouse Click/Paint Actions
    canvas.addEventListener("mousedown", (e) => {
        if (appState.activeTool === "inspect") return;
        appState.isPainting = true;
        paintCellAtCoordinates(e);
    });

    canvas.addEventListener("mousemove", (e) => {
        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        
        const cellW = canvas.width / appState.gridSize;
        const cellH = canvas.height / appState.gridSize;
        
        const col = Math.floor(mouseX / cellW);
        const row = Math.floor(mouseY / cellH);
        
        if (col >= 0 && col < appState.gridSize && row >= 0 && row < appState.gridSize) {
            const cellId = row * appState.gridSize + col;
            if (hoveredCellId !== cellId) {
                hoveredCellId = cellId;
                if (!appState.showWindParticles) drawGrid();
            }
            if (appState.isPainting) {
                paintCellAtCoordinates(e);
            }
        } else {
            if (hoveredCellId !== null) {
                hoveredCellId = null;
                if (!appState.showWindParticles) drawGrid();
            }
        }
    });

    window.addEventListener("mouseup", () => {
        if (appState.isPainting) {
            appState.isPainting = false;
            // Sync final values back to thermodynamic server for full ROI recalcs
            triggerRecalculation();
        }
    });

    canvas.addEventListener("click", () => {
        if (appState.activeTool !== "inspect") return;
        if (hoveredCellId !== null) {
            appState.selectedCellId = hoveredCellId;
            drawGrid();
            inspectCell(hoveredCellId);
            
            canvas.classList.add("grid-highlight-animation");
            setTimeout(() => canvas.classList.remove("grid-highlight-animation"), 500);
        }
    });

    // Cell Inspector Sliders
    const insAlbedo = document.getElementById("slider-cell-albedo");
    const insNdvi = document.getElementById("slider-cell-ndvi");

    insAlbedo.addEventListener("input", (e) => {
        const val = parseFloat(e.target.value);
        document.getElementById("val-cell-albedo").textContent = val.toFixed(2);
        updateSelectedCellParameters(val, parseFloat(insNdvi.value));
    });

    insNdvi.addEventListener("input", (e) => {
        const val = parseFloat(e.target.value);
        document.getElementById("val-cell-ndvi").textContent = val.toFixed(2);
        updateSelectedCellParameters(parseFloat(insAlbedo.value), val);
    });

    // GIS Upload drag and drop
    const dropZone = document.getElementById("upload-zone");
    
    dropZone.addEventListener("dragover", (e) => {
        e.preventDefault();
        dropZone.style.borderColor = "#00ffaa";
    });
    
    dropZone.preventDefault = (e) => e.preventDefault();

    dropZone.addEventListener("dragleave", () => {
        dropZone.style.borderColor = "rgba(255, 255, 255, 0.12)";
    });

    dropZone.addEventListener("drop", (e) => {
        e.preventDefault();
        dropZone.style.borderColor = "rgba(255, 255, 255, 0.12)";
        if (e.dataTransfer.files.length) {
            handleGISUpload(e.dataTransfer.files[0]);
        }
    });

    dropZone.addEventListener("click", () => {
        document.getElementById("gis-file-input").click();
    });

    document.getElementById("gis-file-input").addEventListener("change", (e) => {
        if (e.target.files.length) {
            handleGISUpload(e.target.files[0]);
        }
    });
}

// Painting brush operation
function paintCellAtCoordinates(e) {
    const rect = canvas.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const mouseY = e.clientY - rect.top;
    
    const cellW = canvas.width / appState.gridSize;
    const cellH = canvas.height / appState.gridSize;
    
    const col = Math.floor(mouseX / cellW);
    const row = Math.floor(mouseY / cellH);
    
    if (col >= 0 && col < appState.gridSize && row >= 0 && row < appState.gridSize) {
        const cell = appState.cells[row * appState.gridSize + col];
        if (cell && cell.land_use !== 'water') {
            if (appState.activeTool === 'paint_green') {
                cell.ndvi = Math.min(0.85, cell.ndvi + 0.08); // Add vegetation
            } else if (appState.activeTool === 'paint_cool') {
                cell.albedo = Math.min(0.70, cell.albedo + 0.06); // Add albedo
            }
            // Draw grid in real-time
            if (!appState.showWindParticles) drawGrid();
        }
    }
}

// Update Playback Hour
function updatePlaybackHour(hour) {
    appState.playbackTime = hour;
    
    let suffix = hour >= 12 ? "PM" : "AM";
    let formattedHour = hour % 12;
    if (formattedHour === 0) formattedHour = 12;
    document.getElementById("current-playback-time").textContent = `${formattedHour}:00 ${suffix}`;
    
    updateTickHighlight(hour);
    if (!appState.showWindParticles) drawGrid();
    
    if (appState.selectedCellId !== null) {
        const cell = appState.cells.find(c => c.id === appState.selectedCellId);
        if (cell) updateStreetCanyonView(cell);
    }
}

// Highlights tick text in bottom slider
function updateTickHighlight(hour) {
    document.querySelectorAll(".time-ticks span").forEach(s => s.className = "");
    const tickNoon = document.getElementById("tick-noon");
    
    if (hour === 12) {
        tickNoon.className = "active-tick";
    }
}

// UI canyon 3D visualization updates
function updateStreetCanyonView(cell) {
    const hour = appState.playbackTime;
    
    const leftB = document.getElementById("canyon-left-b");
    const rightB = document.getElementById("canyon-right-b");
    const leftRoof = document.getElementById("canyon-left-roof");
    const rightRoof = document.getElementById("canyon-right-roof");
    const ground = document.getElementById("canyon-ground");
    const tree1 = document.getElementById("c-tree-1");
    const tree2 = document.getElementById("c-tree-2");
    const wind = document.getElementById("canyon-wind");
    const sun = document.getElementById("canyon-sun");
    const skyBg = document.getElementById("canyon-sky-bg");

    // 1. Adjust building height representing urban density
    const heightPercent = Math.min(90, Math.max(15, cell.building_height * 2.5));
    leftB.style.height = `${heightPercent}%`;
    rightB.style.height = `${heightPercent * 0.9}%`; 

    // 2. Adjust building and ground roof color based on albedo
    const roofColor = Math.round(cell.albedo * 255);
    leftRoof.style.backgroundColor = `rgb(${roofColor}, ${roofColor}, ${roofColor})`;
    rightRoof.style.backgroundColor = `rgb(${roofColor}, ${roofColor}, ${roofColor})`;
    
    const groundColor = Math.round(cell.albedo * 180);
    ground.style.backgroundColor = `rgb(${groundColor}, ${groundColor}, ${groundColor})`;

    // 3. Show trees representing NDVI (greening)
    if (cell.ndvi > 0.45) {
        tree1.style.opacity = "1";
        tree2.style.opacity = "1";
    } else if (cell.ndvi > 0.15) {
        tree1.style.opacity = "1";
        tree2.style.opacity = "0.15";
    } else {
        tree1.style.opacity = "0";
        tree2.style.opacity = "0";
    }

    // 4. Set wind duration speed arrow
    const windSpeed = appState.weather.wind_speed || 1.5;
    const duration = Math.max(0.5, 6.0 / windSpeed);
    wind.style.animationDuration = `${duration}s`;

    // 5. Shift sky gradient and sun positioning based on diurnal time
    if (hour >= 6 && hour <= 18) {
        // Daytime
        const sunProgress = (hour - 6) / 12; // 0 to 1
        sun.style.left = `${10 + sunProgress * 80}%`;
        sun.style.display = "block";
        
        if (hour < 9) {
            skyBg.style.background = "linear-gradient(#f97316, #bae6fd)"; 
        } else if (hour > 15) {
            skyBg.style.background = "linear-gradient(#ea580c, #fed7aa)"; 
        } else {
            skyBg.style.background = "linear-gradient(#0ea5e9, #bae6fd)"; 
        }
    } else {
        // Nighttime
        sun.style.display = "none";
        skyBg.style.background = "linear-gradient(#0f172a, #020617)"; 
    }
}

// Reset climate limits based on profile
function data_manager_defaults_for_weather() {
    const prof = appState.activeProfile;
    if (prof === "arid_inland") {
        return { air_temp_noon: 42.0, relative_humidity: 0.15, wind_speed: 3.0, solar_radiation: 950.0, sky_temp: 12.0 };
    } else if (prof === "dense_highrise") {
        return { air_temp_noon: 33.0, relative_humidity: 0.75, wind_speed: 1.5, solar_radiation: 800.0, sky_temp: 22.0 };
    } else {
        return { air_temp_noon: 35.0, relative_humidity: 0.65, wind_speed: 4.5, solar_radiation: 850.0, sky_temp: 20.0 };
    }
}

// Synchronize UI elements with current weather variables
function updateWeatherUI() {
    const w = appState.weather;
    document.getElementById("input-air-temp").value = w.air_temp_noon;
    document.getElementById("val-air-temp").textContent = `${w.air_temp_noon} °C`;

    document.getElementById("input-humidity").value = w.relative_humidity;
    document.getElementById("val-humidity").textContent = `${Math.round(w.relative_humidity * 100)} %`;

    document.getElementById("input-wind").value = w.wind_speed;
    document.getElementById("val-wind").textContent = `${w.wind_speed} m/s`;

    document.getElementById("input-solar").value = w.solar_radiation;
    document.getElementById("val-solar").textContent = `${w.solar_radiation} W/m²`;
}

// Adjust labels on map layer toggles
function updateLegendLabels() {
    const labelMin = document.getElementById("legend-label-min");
    const labelMax = document.getElementById("legend-label-max");
    const colorBar = document.getElementById("legend-color-bar");
    
    colorBar.className = "legend-gradient";
    
    switch (appState.activeLayer) {
        case 'temp_surface':
            labelMin.textContent = "Cool (22°C)";
            labelMax.textContent = "Hot (52°C)";
            colorBar.style.background = "linear-gradient(90deg, #002bff, #00d2ff, #00ffaa, #ffaa00, #ff0000)";
            break;
        case 'temp_air':
            labelMin.textContent = "Cool (28°C)";
            labelMax.textContent = "Hot (45°C)";
            colorBar.style.background = "linear-gradient(90deg, #002bff, #00d2ff, #00ffaa, #ffaa00, #ff0000)";
            break;
        case 'wbgt':
            labelMin.textContent = "Safe (18°C)";
            labelMax.textContent = "Extreme (38°C)";
            colorBar.style.background = "linear-gradient(90deg, #00ffaa, #ffaa00, #ff3c3c, #8b5cf6)";
            break;
        case 'ndvi':
            labelMin.textContent = "Concrete (0.0)";
            labelMax.textContent = "Lush Cover (0.8)";
            colorBar.style.background = "linear-gradient(90deg, #7c5226, #a1d77a, #00aa66, #005f33)";
            break;
        case 'albedo':
            labelMin.textContent = "Dark (0.05)";
            labelMax.textContent = "Reflective (0.65)";
            colorBar.style.background = "linear-gradient(90deg, #0a0a0a, #777777, #cccccc, #ffffff)";
            break;
        case 'svi':
            labelMin.textContent = "Low Vulnerability";
            labelMax.textContent = "High Vulnerability";
            colorBar.style.background = "linear-gradient(90deg, #0f172a, #6366f1, #d946ef)";
            break;
        case 'risk':
            labelMin.textContent = "Low risk";
            labelMax.textContent = "Extreme Risk";
            colorBar.style.background = "linear-gradient(90deg, #060913, #a855f7, #ef4444, #ff007f)";
            break;
    }
}

// Display/Hide Loading State overlay
function showLoading(show) {
    const loader = document.getElementById("map-loading");
    if (show) {
        loader.classList.remove("hidden");
    } else {
        loader.classList.add("hidden");
    }
}

// API trigger to simulate full layout recalculation
async function triggerRecalculation() {
    showLoading(true);
    try {
        const response = await fetch(`${API_URL}/api/simulate`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                cells: appState.cells,
                weather: appState.weather
            })
        });
        
        if (!response.ok) throw new Error("Recalculation failed");
        const data = await response.json();
        appState.cells = data.cells;
        
        if (!appState.showWindParticles) drawGrid();
        updateROIMetrics(data.roi);
        
        if (appState.selectedCellId !== null) {
            inspectCell(appState.selectedCellId);
        }
    } catch (err) {
        console.error(err);
    } finally {
        showLoading(false);
    }
}

// Inspector Cell function
function inspectCell(cellId) {
    const cell = appState.cells.find(c => c.id === cellId);
    if (!cell) return;
    
    document.getElementById("inspector-placeholder").classList.add("hidden");
    const contentPanel = document.getElementById("inspector-content");
    contentPanel.classList.remove("hidden");
    
    // Core parameters text
    document.getElementById("cell-coords").textContent = `${cell.lat.toFixed(4)}°N, ${cell.lon.toFixed(4)}°E`;
    document.getElementById("cell-landuse").textContent = `${cell.land_use} (Density: ${Math.round(cell.building_density*100)}%)`;
    
    // Set inspector input sliders values
    const insAlbedo = document.getElementById("slider-cell-albedo");
    const insNdvi = document.getElementById("slider-cell-ndvi");
    
    insAlbedo.value = cell.albedo;
    document.getElementById("val-cell-albedo").textContent = cell.albedo.toFixed(2);
    
    insNdvi.value = cell.ndvi;
    document.getElementById("val-cell-ndvi").textContent = cell.ndvi.toFixed(2);
    
    // Show local thermodynamic energy balance values
    const fluxes = cell.fluxes || { Rn: 0, H: 0, LE: 0, G: 0, residual: 0 };
    document.getElementById("flux-rn").textContent = Math.round(fluxes.Rn);
    document.getElementById("flux-h").textContent = Math.round(fluxes.H);
    document.getElementById("flux-le").textContent = Math.round(fluxes.LE);
    document.getElementById("flux-g").textContent = Math.round(fluxes.G);
    
    const closureDiv = document.getElementById("flux-closure");
    closureDiv.textContent = `Residual error: ${fluxes.residual.toFixed(2)} W/m²`;
    
    if (Math.abs(fluxes.residual) < 0.1) {
        closureDiv.style.color = "var(--accent-emerald)";
    } else {
        closureDiv.style.color = "var(--accent-amber)";
    }
    
    // Render the 3D street canyon animation
    updateStreetCanyonView(cell);
    
    // Plot the explainable AI drivers
    renderDriverAttributionChart(cell.drivers);
    
    // Plot diurnal line graphs
    fetchDiurnalProfile(cell);
}

// Update specific cell values from inspector sliders
function updateSelectedCellParameters(albedo, ndvi) {
    if (appState.selectedCellId === null) return;
    
    const cell = appState.cells.find(c => c.id === appState.selectedCellId);
    if (cell) {
        cell.albedo = albedo;
        cell.ndvi = ndvi;
        
        // Debounce API triggers
        if (this.simTimeout) clearTimeout(this.simTimeout);
        this.simTimeout = setTimeout(() => {
            triggerRecalculation();
        }, 300);
    }
}

// Generate driver explainability chart
function renderDriverAttributionChart(drivers) {
    const ctxChart = document.getElementById("driver-chart").getContext("2d");
    
    if (driverChart) {
        driverChart.destroy();
    }
    
    if (!drivers) return;
    
    const labels = ["Albedo (Low Reflectivity)", "NDVI (Lack of Vegetation)", "Density (Building trapping)"];
    const dataVals = [
        drivers.albedo_attribution_celsius,
        drivers.ndvi_attribution_celsius,
        drivers.density_attribution_celsius
    ];
    
    driverChart = new Chart(ctxChart, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Heat driver contribution (°C)',
                data: dataVals,
                backgroundColor: [
                    'rgba(0, 225, 255, 0.45)', 
                    'rgba(0, 255, 170, 0.45)', 
                    'rgba(255, 60, 60, 0.45)'   
                ],
                borderColor: [
                    '#00e1ff',
                    '#00ffaa',
                    '#ff3c3c'
                ],
                borderWidth: 1.5,
                borderRadius: 4
            }]
        },
        options: {
            indexAxis: 'y',
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#90a0be', font: { family: 'Outfit', size: 10 } },
                    title: { display: true, text: 'Warming Impact Anomaly (°C)', color: '#90a0be', font: { family: 'Outfit', size: 10 } }
                },
                y: {
                    grid: { display: false },
                    ticks: { color: '#f0f4f9', font: { family: 'Outfit', size: 10 } }
                }
            }
        }
    });
}

// Fetch 24 hours diurnal cycle
async function fetchDiurnalProfile(cell) {
    try {
        const response = await fetch(`${API_URL}/api/diurnal`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                cell: cell,
                weather: appState.weather
            })
        });
        
        if (!response.ok) throw new Error("Failed to fetch diurnal curves");
        const data = await response.json();
        
        plotDiurnalChart(data);
    } catch (err) {
        console.error(err);
    }
}

// Draw diurnal line chart
function plotDiurnalChart(diurnalData) {
    const ctxChart = document.getElementById("diurnal-chart").getContext("2d");
    
    if (diurnalChart) {
        diurnalChart.destroy();
    }
    
    const hours = diurnalData.baseline.hours.map(h => `${Math.floor(h)}:00`);
    const baselineTemp = diurnalData.baseline.surface_temp;
    const modifiedTemp = diurnalData.modified.surface_temp;
    
    diurnalChart = new Chart(ctxChart, {
        type: 'line',
        data: {
            labels: hours,
            datasets: [
                {
                    label: 'Baseline LST',
                    data: baselineTemp,
                    borderColor: '#ff3c3c',
                    backgroundColor: 'rgba(255, 60, 60, 0.05)',
                    borderWidth: 2,
                    tension: 0.3,
                    pointRadius: 1
                },
                {
                    label: 'Mitigated LST',
                    data: modifiedTemp,
                    borderColor: '#00ffaa',
                    backgroundColor: 'rgba(0, 255, 170, 0.05)',
                    borderWidth: 2,
                    tension: 0.3,
                    pointRadius: 1,
                    fill: true
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    labels: { color: '#f0f4f9', font: { family: 'Outfit', size: 9 } }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)' },
                    ticks: { color: '#90a0be', font: { family: 'Outfit', size: 9 } }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#90a0be', font: { family: 'Outfit', size: 9 } },
                    title: { display: true, text: 'Temp (°C)', color: '#90a0be', font: { family: 'Outfit', size: 9 } }
                }
            }
        }
    });
}

// Fetch the trade-off points for the Pareto frontier curve
async function fetchParetoFrontier() {
    try {
        const response = await fetch(`${API_URL}/api/pareto`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                cells: appState.cells,
                weather: appState.weather,
                budget: appState.budget,
                strategy: appState.strategy
            })
        });
        
        if (!response.ok) throw new Error("Failed to fetch Pareto points");
        const data = await response.json();
        
        plotParetoChart(data.frontier);
    } catch (err) {
        console.error(err);
    }
}

// Render Pareto Scatter Chart
function plotParetoChart(frontierData) {
    const ctxChart = document.getElementById("pareto-chart").getContext("2d");
    
    if (paretoChart) {
        paretoChart.destroy();
    }
    
    const datasets = {
        efficiency_focused: [],
        equity_focused: [],
        balanced: []
    };
    
    frontierData.forEach(p => {
        datasets[p.strategy].push({
            x: p.cost_allocated / 1000000, 
            y: p.energy_saved_kwh / 1000,    
            payback: p.payback_years,
            budget: p.budget_limit
        });
    });
    
    Object.keys(datasets).forEach(k => {
        datasets[k].sort((a,b) => a.x - b.x);
    });
    
    paretoChart = new Chart(ctxChart, {
        type: 'scatter',
        data: {
            datasets: [
                {
                    label: 'Cooling Efficiency Max',
                    data: datasets.efficiency_focused,
                    borderColor: '#00e1ff',
                    backgroundColor: 'rgba(0, 225, 255, 0.8)',
                    showLine: true,
                    tension: 0.2
                },
                {
                    label: 'Social Heat Equity',
                    data: datasets.equity_focused,
                    borderColor: '#ffaa00',
                    backgroundColor: 'rgba(255, 170, 0, 0.8)',
                    showLine: true,
                    tension: 0.2
                },
                {
                    label: 'Balanced Strategy',
                    data: datasets.balanced,
                    borderColor: '#00ffaa',
                    backgroundColor: 'rgba(0, 255, 170, 0.8)',
                    showLine: true,
                    tension: 0.2
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const p = context.raw;
                            return `Cost: $${p.x.toFixed(2)}M, Savings: ${p.y.toFixed(0)} MWh/yr, Payback: ${p.payback} yrs`;
                        }
                    }
                },
                legend: {
                    labels: { color: '#f0f4f9', font: { family: 'Outfit', size: 9 } }
                }
            },
            scales: {
                x: {
                    grid: { color: 'rgba(255, 255, 255, 0.03)' },
                    ticks: { color: '#90a0be', font: { family: 'Outfit', size: 9 } },
                    title: { display: true, text: 'Budget ($ Millions)', color: '#90a0be', font: { family: 'Outfit', size: 9 } }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#90a0be', font: { family: 'Outfit', size: 9 } },
                    title: { display: true, text: 'Energy Savings (MWh/yr)', color: '#90a0be', font: { family: 'Outfit', size: 9 } }
                }
            },
            onClick: (e, elements) => {
                if (elements.length > 0) {
                    const datasetIdx = elements[0].datasetIndex;
                    const index = elements[0].index;
                    const clickedPoint = paretoChart.data.datasets[datasetIdx].data[index];
                    
                    const stratMap = ['efficiency_focused', 'equity_focused', 'balanced'];
                    appState.strategy = stratMap[datasetIdx];
                    appState.budget = clickedPoint.budget;
                    
                    document.getElementById("input-budget").value = clickedPoint.budget;
                    document.getElementById("val-budget").textContent = `$${(clickedPoint.budget / 1000000).toFixed(1)}M`;
                    
                    const radio = document.querySelector(`input[name='opt-strategy'][value='${appState.strategy}']`);
                    if (radio) radio.checked = true;
                    
                    runOptimizer();
                }
            }
        }
    });
}

// Run AI optimization
async function runOptimizer() {
    showLoading(true);
    try {
        const response = await fetch(`${API_URL}/api/optimize`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                cells: appState.cells,
                weather: appState.weather,
                budget: appState.budget,
                strategy: appState.strategy
            })
        });
        
        if (!response.ok) throw new Error("Optimization solver error");
        const data = await response.json();
        
        appState.cells = data.cells;
        if (!appState.showWindParticles) drawGrid();
        updateROIMetrics(data.roi);
        
        if (appState.selectedCellId !== null) {
            inspectCell(appState.selectedCellId);
        }
        
    } catch (err) {
        console.error(err);
        alert("Optimization solver failed to compile results.");
    } finally {
        showLoading(false);
    }
}

// Update bottom ROI statistics panel
function updateROIMetrics(roi) {
    const currency = roi.currency_symbol || "$";
    
    document.getElementById("roi-capital-cost").textContent = `${currency}${formatNumber(roi.total_capital_cost)}`;
    document.getElementById("roi-energy-savings").textContent = `${currency}${formatNumber(roi.annual_energy_savings)} / yr`;
    document.getElementById("roi-energy-kwh").textContent = `${formatNumber(roi.annual_energy_saved_kwh)} kWh saved / yr`;
    
    document.getElementById("roi-carbon-saved").textContent = `${roi.annual_carbon_saved_tons.toFixed(1)} Tons / yr`;
    document.getElementById("roi-carbon-value").textContent = `${currency}${formatNumber(roi.annual_carbon_savings)} offset value`;
    
    document.getElementById("roi-payback").textContent = `${roi.payback_years} Years`;
    document.getElementById("roi-percentage").textContent = `ROI: ${roi.roi_percentage}% / yr`;
    
    document.getElementById("roi-stormwater").textContent = `${formatNumber(roi.annual_stormwater_retained_m3)} m³`;
    document.getElementById("roi-stormwater-value").textContent = `${currency}${formatNumber(roi.annual_stormwater_savings)} treating savings`;
}

// Format numbers nicely
function formatNumber(num) {
    if (num >= 1000000) return (num / 1000000).toFixed(2) + "M";
    if (num >= 1000) return (num / 1000).toFixed(1) + "k";
    return Math.round(num).toString();
}

// Upload GIS custom files
async function handleGISUpload(file) {
    const statusMsg = document.getElementById("upload-status");
    statusMsg.style.color = "var(--text-secondary)";
    statusMsg.textContent = "Processing GIS layers...";
    
    const formData = new FormData();
    formData.append("file", file);
    
    showLoading(true);
    try {
        const response = await fetch(`${API_URL}/api/upload-gis`, {
            method: "POST",
            body: formData
        });
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(errorText || "Invalid GIS layout");
        }
        
        const data = await response.json();
        
        appState.metadata = data.metadata;
        appState.cells = data.cells;
        appState.weather = data.metadata.weather;
        appState.gridSize = data.metadata.grid_size;
        appState.activeProfile = "custom_upload";
        
        document.getElementById("current-profile-badge").textContent = "Custom GIS Upload";
        
        updateWeatherUI();
        
        appState.selectedCellId = null;
        document.getElementById("inspector-content").classList.add("hidden");
        document.getElementById("inspector-placeholder").classList.remove("hidden");
        
        drawGrid();
        fetchParetoFrontier();
        
        statusMsg.style.color = "var(--accent-emerald)";
        statusMsg.textContent = "GIS data loaded successfully!";
        
        setTimeout(() => {
            statusMsg.textContent = "";
        }, 5000);
        
    } catch (err) {
        console.error(err);
        statusMsg.style.color = "var(--accent-red)";
        statusMsg.textContent = `Upload failed: ${err.message}`;
    } finally {
        showLoading(false);
    }
}
