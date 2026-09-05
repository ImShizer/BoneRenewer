import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';

// --- Three.js Setup ---
const container = document.getElementById('canvas-container');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf8fafc);

const camera = new THREE.PerspectiveCamera(45, (window.innerWidth - 320) / window.innerHeight, 0.1, 1000);
camera.position.set(200, 150, 250);

const renderer = new THREE.WebGLRenderer({ antialias: true });

// Initial sizing based on assumed panel widths 
renderer.setSize(window.innerWidth - 320, window.innerHeight - 70);
container.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

// Lighting setup
scene.add(new THREE.AmbientLight(0xffffff, 0.6));
const dirLight = new THREE.DirectionalLight(0xffffff, 1.0);
dirLight.position.set(100, 200, 100);
scene.add(dirLight);

// Base grid
const grid = new THREE.GridHelper(300, 30, 0xd1d5db, 0xe5e7eb);
grid.position.y = -60;
scene.add(grid);

function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
}
animate();

// Handle window resize
window.addEventListener('resize', () => {
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
});

// UI Logic
const folderBtn = document.getElementById('btn-select-folder');
const scanTitle = document.getElementById('scan-title');
const seriesSelect = document.getElementById('series-select');
const huInput = document.getElementById('hu-input');
const renderBtn = document.getElementById('render-btn');
const exportBtn = document.getElementById('export-btn');
const loadingOverlay = document.getElementById('loading-overlay');

let currentDicomPath = "";
let currentMesh = null;

// Wait for pywebview API to be ready before attaching Python calls
window.addEventListener('pywebviewready', function () {

    // Folder selection
    folderBtn.addEventListener('click', async () => {
        const folderPath = await window.pywebview.api.ask_folder_path();

        if (folderPath) {
            currentDicomPath = folderPath;
            scanTitle.innerText = "Directory:\n" + folderPath.split(/[\\/]/).pop();

            seriesSelect.disabled = true;
            seriesSelect.innerHTML = `<option value="">Scanning series...</option>`;

            const scanResult = await window.pywebview.api.scan_folder(folderPath);

            if (scanResult.status === "success") {
                seriesSelect.innerHTML = "";

                scanResult.series.forEach((series, index) => {
                    const opt = document.createElement('option');
                    opt.value = series.id;
                    opt.innerText = `Series ${index + 1} (${series.count} slices)`;
                    seriesSelect.appendChild(opt);
                });

                seriesSelect.disabled = false;
                huInput.disabled = false;
                renderBtn.disabled = false;
            } else {
                seriesSelect.innerHTML = `<option value="">Error: ${scanResult.message}</option>`;
            }
        }
    });

    // Render execution
    renderBtn.addEventListener('click', async () => {
        renderBtn.disabled = true;
        exportBtn.disabled = true;
        loadingOverlay.classList.add('active');

        const selectedSeries = seriesSelect.value;
        const selectedHU = huInput.value;

        const result = await window.pywebview.api.run_conversion(currentDicomPath, selectedSeries, selectedHU);

        if (result.status === "success") {
            loadSTL(result.file + '?v=' + new Date().getTime());
        } else {
            alert('Render Error:\n' + result.message);
            renderBtn.disabled = false;
            loadingOverlay.classList.remove('active');
        }
    });

    exportBtn.addEventListener('click', async () => {
        const result = await window.pywebview.api.export_stl();

        if (result.status === "success") {
            alert("Saved successfully to:\n" + result.path);
        } else if (result.status === "error") {
            alert("Export Error:\n" + result.message);
        }
    });
});

// STL Loader function
function loadSTL(url) {
    const loader = new STLLoader();
    loader.load(url,
        (geometry) => {
            if (currentMesh) scene.remove(currentMesh);

            geometry.computeVertexNormals();
            geometry.center();

            const material = new THREE.MeshStandardMaterial({
                color: 0xffffff, roughness: 0.3, metalness: 0.1, side: THREE.DoubleSide
            });

            currentMesh = new THREE.Mesh(geometry, material);
            currentMesh.rotation.x = -Math.PI / 2;
            scene.add(currentMesh);

            renderBtn.disabled = false;
            exportBtn.disabled = false;
            loadingOverlay.classList.remove('active');
        },
        undefined,
        (error) => {
            alert('Failed to load 3D model.');
            renderBtn.disabled = false;
            loadingOverlay.classList.remove('active');
        }
    );
}