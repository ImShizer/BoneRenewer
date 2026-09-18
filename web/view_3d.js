import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

// ==========================================
// 1. Three.js Scene Setup & Initialization
// ==========================================
const container = document.getElementById('canvas-container');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf8fafc);

const camera = new THREE.PerspectiveCamera(
    45, 
    container.clientWidth / container.clientHeight, 
    0.1, 
    1000
);
camera.position.set(200, 150, 250);

const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setSize(container.clientWidth, container.clientHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
container.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;

// Scene illumination
scene.add(new THREE.AmbientLight(0xffffff, 0.65));
const dirLight = new THREE.DirectionalLight(0xffffff, 1.0);
dirLight.position.set(120, 220, 120);
scene.add(dirLight);

// Reference ground plane
const grid = new THREE.GridHelper(300, 30, 0xd1d5db, 0xe5e7eb);
grid.position.y = -60;
scene.add(grid);

// Responsive canvas resizing
window.addEventListener('resize', () => {
    if (!container.clientWidth || !container.clientHeight) return;
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
});

// Render cycle
function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}
animate();


// ==========================================
// 2. DOM Elements & State Management
// ==========================================
const folderBtn = document.getElementById('btn-select-folder');
const importNiftiBtn = document.getElementById('btn-import-nifti');
const btnAdvanced = document.getElementById('btn-advanced');
const advancedSettings = document.getElementById('advanced-settings');

const scanTitle = document.getElementById('scan-title');
const seriesSelect = document.getElementById('series-select');
const huInput = document.getElementById('hu-input');
const lowHuInput = document.getElementById('low-hu-input');
const iterationsInput = document.getElementById('iterations-input');

const renderBtn = document.getElementById('render-btn');
const exportBtn = document.getElementById('export-btn');
const exportNiftiBtn = document.getElementById('export-nifti-btn');
const loadingOverlay = document.getElementById('loading-overlay');
const loadingText = document.getElementById('loading-text');

let currentMode = "dicom"; // Pipeline mode: "dicom" or "nifti"
let currentDicomPath = "";
let currentNiftiPath = "";
let currentMesh = null;


// ==========================================
// 3. UI Helpers & Resource Cleanup
// ==========================================
function setLoading(active, message = "Processing...") {
    loadingText.innerText = message;
    if (active) {
        loadingOverlay.classList.add('active');
    } else {
        loadingOverlay.classList.remove('active');
    }
}

function cleanupMesh() {
    if (!currentMesh) return;
    scene.remove(currentMesh);
    if (currentMesh.geometry) currentMesh.geometry.dispose();
    if (currentMesh.material) {
        if (Array.isArray(currentMesh.material)) {
            currentMesh.material.forEach(mat => mat.dispose());
        } else {
            currentMesh.material.dispose();
        }
    }
    currentMesh = null;
}

function setUIMode(mode) {
    currentMode = mode;
    const isNifti = (mode === "nifti");

    huInput.disabled = isNifti;
    lowHuInput.disabled = isNifti;
    iterationsInput.disabled = isNifti;
    seriesSelect.disabled = isNifti;

    if (isNifti) {
        seriesSelect.innerHTML = `<option value="nifti" selected>NIfTI Data</option>`;
    }
}

function applyAdvancedMode(active) {
    if (active) {
        advancedSettings.classList.remove('hidden');
        btnAdvanced.classList.add('active');
    } else {
        advancedSettings.classList.add('hidden');
        btnAdvanced.classList.remove('active');
    }
}

// Initialize persisted Advanced Mode toggle
applyAdvancedMode(localStorage.getItem('bone_advanced_mode') === 'true');

btnAdvanced.addEventListener('click', () => {
    const isCurrentlyActive = btnAdvanced.classList.contains('active');
    const nextState = !isCurrentlyActive;
    localStorage.setItem('bone_advanced_mode', nextState);
    applyAdvancedMode(nextState);
});


// ==========================================
// 4. Mesh Loader Pipeline
// ==========================================
function loadSTL(url) {
    const loader = new STLLoader();
    loader.load(
        url,
        (geometry) => {
            cleanupMesh();

            geometry.computeVertexNormals();
            geometry.center();

            const material = new THREE.MeshStandardMaterial({
                color: 0xffffff,
                roughness: 0.35,
                metalness: 0.1,
                side: THREE.DoubleSide
            });

            currentMesh = new THREE.Mesh(geometry, material);
            // Reorient medical axial coordinates to Three.js world space
            currentMesh.rotation.x = -Math.PI / 2;
            scene.add(currentMesh);

            renderBtn.disabled = false;
            exportBtn.disabled = false;
            exportNiftiBtn.disabled = false;
            setLoading(false);
        },
        undefined,
        (error) => {
            console.error("[Three.js] STL loading failed:", error);
            alert("Failed to render generated 3D model.");
            renderBtn.disabled = false;
            setLoading(false);
        }
    );
}


// ==========================================
// 5. PyWebView Bridge Events
// ==========================================
window.addEventListener('pywebviewready', () => {

    // Step 1: Select DICOM Directory
    folderBtn.addEventListener('click', async () => {
        const folderPath = await window.pywebview.api.ask_folder_path();
        if (!folderPath) return;

        setUIMode("dicom");
        currentDicomPath = folderPath;
        scanTitle.innerText = "Directory:\n" + folderPath.split(/[\\/]/).pop();

        seriesSelect.disabled = true;
        seriesSelect.innerHTML = `<option value="">Scanning series...</option>`;
        renderBtn.disabled = true;

        const scanResult = await window.pywebview.api.scan_folder(folderPath);

        if (scanResult.status === "success") {
            seriesSelect.innerHTML = "";
            scanResult.series.forEach((series, idx) => {
                const opt = document.createElement('option');
                opt.value = series.id;
                opt.innerText = `Series ${idx + 1} (${series.count} slices)`;
                seriesSelect.appendChild(opt);
            });

            seriesSelect.disabled = false;
            huInput.disabled = false;
            lowHuInput.disabled = false;
            iterationsInput.disabled = false;
            renderBtn.disabled = false;
        } else {
            seriesSelect.innerHTML = `<option value="">Error scanning folder</option>`;
            alert("DICOM Scan Error: " + scanResult.message);
        }
    });

    // Step 2: Select NIfTI File without blocking overlay
    importNiftiBtn.addEventListener('click', async () => {
        const result = await window.pywebview.api.ask_nifti_path();
        if (!result || result.status === "cancelled") return;

        if (result.status === "success") {
            setUIMode("nifti");
            currentNiftiPath = result.path;
            scanTitle.innerText = "NIfTI:\n" + result.filename;

            // Prepare render actions
            renderBtn.disabled = false;
            exportBtn.disabled = true;
            exportNiftiBtn.disabled = true;
        } else if (result.status === "error") {
            alert("NIfTI Picker Error:\n" + result.message);
        }
    });

    // Step 3: Central Execution Handler (Render 3D)
    renderBtn.addEventListener('click', async () => {
        renderBtn.disabled = true;
        exportBtn.disabled = true;
        exportNiftiBtn.disabled = true;

        let result;

        if (currentMode === "dicom") {
            setLoading(true, "Converting DICOM to STL...");
            result = await window.pywebview.api.run_conversion(
                currentDicomPath,
                seriesSelect.value,
                huInput.value,
                lowHuInput.value,
                iterationsInput.value
            );
        } else if (currentMode === "nifti") {
            setLoading(true, "Rendering NIfTI to 3D...");
            result = await window.pywebview.api.run_nifti_conversion(currentNiftiPath);
        }

        if (result && result.status === "success") {
            // Append timestamp to bypass local browser cache
            loadSTL(result.file + '?v=' + Date.now());
        } else {
            alert("Render Error:\n" + (result ? result.message : "Unknown error"));
            renderBtn.disabled = false;
            setLoading(false);
        }
    });

    // Step 4: Export Handlers
    exportBtn.addEventListener('click', async () => {
        const result = await window.pywebview.api.export_stl();
        if (result.status === "success") {
            alert("STL saved successfully to:\n" + result.path);
        } else if (result.status === "error") {
            alert("Export STL Error:\n" + result.message);
        }
    });

    exportNiftiBtn.addEventListener('click', async () => {
        const result = await window.pywebview.api.export_nifti();
        if (result.status === "success") {
            alert("NIfTI saved successfully to:\n" + result.path);
        } else if (result.status === "error") {
            alert("Export NIfTI Error:\n" + result.message);
        }
    });
});