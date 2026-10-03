import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';

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
    2000
);
camera.position.set(0, 150, 300);

const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setSize(container.clientWidth, container.clientHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
container.appendChild(renderer.domElement);

// Основной OrbitControls для вращения всей сцены
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;

// Интерактивный TransformControls для ручной точной подгонки протеза
const transformControls = new TransformControls(camera, renderer.domElement);
transformControls.addEventListener('dragging-changed', (event) => {
    controls.enabled = !event.value; // Отключаем вращение сцены при перетаскивании протеза
});
scene.add(transformControls);

// Illumination
scene.add(new THREE.AmbientLight(0xffffff, 0.7));
const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
dirLight1.position.set(120, 220, 120);
scene.add(dirLight1);

const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.4);
dirLight2.position.set(-120, -100, -120);
scene.add(dirLight2);

// Ground plane
const grid = new THREE.GridHelper(300, 30, 0xd1d5db, 0xe5e7eb);
grid.position.y = -60;
scene.add(grid);

window.addEventListener('resize', () => {
    if (!container.clientWidth || !container.clientHeight) return;
    camera.aspect = container.clientWidth / container.clientHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(container.clientWidth, container.clientHeight);
});

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
const btnDiagnostics = document.getElementById('btn-diagnostics');
const loadingOverlay = document.getElementById('loading-overlay');
const loadingText = document.getElementById('loading-text');

let currentMode = "dicom";
let currentDicomPath = "";
let currentNiftiPath = "";
let currentMesh = null;
let prostheticMesh = null;


// ==========================================
// 3. Helpers & Cleanup
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
    if (transformControls) {
        transformControls.detach();
    }
    if (currentMesh) {
        scene.remove(currentMesh);
        if (currentMesh.geometry) currentMesh.geometry.dispose();
        if (currentMesh.material) currentMesh.material.dispose();
        currentMesh = null;
    }
    if (prostheticMesh) {
        scene.remove(prostheticMesh);
        if (prostheticMesh.geometry) prostheticMesh.geometry.dispose();
        if (prostheticMesh.material) prostheticMesh.material.dispose();
        prostheticMesh = null;
    }
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

applyAdvancedMode(localStorage.getItem('bone_advanced_mode') === 'true');

btnAdvanced.addEventListener('click', () => {
    const isCurrentlyActive = btnAdvanced.classList.contains('active');
    const nextState = !isCurrentlyActive;
    localStorage.setItem('bone_advanced_mode', nextState);
    applyAdvancedMode(nextState);
});


// ==========================================
// 4. Анатомически точная визуализация протезов
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
                color: 0xf5e6d3,
                roughness: 0.4,
                metalness: 0.1,
                side: THREE.DoubleSide
            });

            currentMesh = new THREE.Mesh(geometry, material);
            currentMesh.rotation.x = -Math.PI / 2;
            scene.add(currentMesh);

            controls.target.set(0, 0, 0);
            camera.position.set(0, 100, 250);
            controls.update();

            renderBtn.disabled = false;
            exportBtn.disabled = false;
            exportNiftiBtn.disabled = false;
            if (btnDiagnostics) btnDiagnostics.disabled = false;

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

function overlayProstheticMesh(recommendation) {
    if (!currentMesh) return;

    // 1. Делаем кость полупрозрачной
    currentMesh.material.transparent = true;
    currentMesh.material.opacity = 0.45;

    // 2. Очищаем прошлый протез и отсоединяем гизмо
    if (transformControls) transformControls.detach();
    if (prostheticMesh) {
        scene.remove(prostheticMesh);
        if (prostheticMesh.geometry) prostheticMesh.geometry.dispose();
        if (prostheticMesh.material) prostheticMesh.material.dispose();
        prostheticMesh = null;
    }

    // 3. Вычисляем Bounding Box и геометрический центр кости
    currentMesh.geometry.computeBoundingBox();
    const bbox = currentMesh.geometry.boundingBox;
    const size = new THREE.Vector3();
    bbox.getSize(size);
    const center = new THREE.Vector3();
    bbox.getCenter(center);

    const metalMaterial = new THREE.MeshStandardMaterial({
        color: 0xd1d5db,
        metalness: 0.95,
        roughness: 0.15
    });

    const porousMaterial = new THREE.MeshStandardMaterial({
        color: 0x6b7280,
        metalness: 0.5,
        roughness: 0.8
    });

    const group = new THREE.Group();
    const type = (recommendation && (recommendation.type || recommendation.id)) ? (recommendation.type || recommendation.id) : "proximal";

    // ==========================================
    // Генерация различных видов конструкций
    // ==========================================
    if (type.includes("distal")) {
        // --- 1. ДИСТАЛЬНЫЙ КОЛЕННЫЙ ПРОТЕЗ ---
        const stemRadius = Math.min(size.x, size.z) * 0.06;
        const stemHeight = size.y * 0.35;

        const stemGeo = new THREE.CylinderGeometry(stemRadius, stemRadius * 0.7, stemHeight, 32);
        const stemMesh = new THREE.Mesh(stemGeo, metalMaterial);
        stemMesh.position.y = stemHeight / 2;

        const blockGeo = new THREE.BoxGeometry(size.x * 0.3, size.y * 0.12, size.z * 0.3);
        const blockMesh = new THREE.Mesh(blockGeo, metalMaterial);
        blockMesh.position.y = 0;

        group.add(stemMesh);
        group.add(blockMesh);

    } else if (type.includes("diaphyseal")) {
        // --- 2. ДИАФИЗАРНАЯ МУФТА (SLEEVE) ---
        const sleeveRadius = Math.min(size.x, size.z) * 0.14;
        const sleeveHeight = size.y * 0.35;

        const sleeveGeo = new THREE.CylinderGeometry(sleeveRadius, sleeveRadius * 0.9, sleeveHeight, 32);
        const sleeveMesh = new THREE.Mesh(sleeveGeo, porousMaterial);
        group.add(sleeveMesh);

    } else if (type.includes("plate")) {
        // --- 3. РЕКОНСТРУКТИВНАЯ ОСТЕОСИНТЕЗНАЯ ПЛАСТИНА ---
        const plateWidth = size.x * 0.15;
        const plateHeight = size.y * 0.45;
        const plateThickness = 4;

        const plateGeo = new THREE.BoxGeometry(plateWidth, plateHeight, plateThickness);
        const plateMesh = new THREE.Mesh(plateGeo, metalMaterial);
        group.add(plateMesh);

    } else {
        // --- 4. ПРОКСИМАЛЬНЫЙ ТАЗОБЕДРЕННЫЙ ПРОТЕЗ ---
        const stemRadiusTop = Math.min(size.x, size.z) * 0.05;
        const stemRadiusBottom = stemRadiusTop * 0.5;
        const stemHeight = size.y * 0.4;

        // Конический ножечный штифт
        const stemGeo = new THREE.CylinderGeometry(stemRadiusTop, stemRadiusBottom, stemHeight, 32);
        const stemMesh = new THREE.Mesh(stemGeo, metalMaterial);
        stemMesh.position.y = -stemHeight / 2;
        group.add(stemMesh);

        // Анатомическая шейка
        const neckRadius = stemRadiusTop * 0.7;
        const neckLength = stemRadiusTop * 1.8;
        const neckGeo = new THREE.CylinderGeometry(neckRadius * 0.8, neckRadius, neckLength, 32);
        const neckMesh = new THREE.Mesh(neckGeo, metalMaterial);
        neckMesh.rotation.z = -Math.PI / 4;
        neckMesh.position.set(neckLength * 0.35, neckLength * 0.35, 0);
        group.add(neckMesh);

        // Головка
        const headRadius = stemRadiusTop * 1.3;
        const headGeo = new THREE.SphereGeometry(headRadius, 32, 32);
        const headMesh = new THREE.Mesh(headGeo, metalMaterial);
        headMesh.position.set(neckLength * 0.7, neckLength * 0.7, 0);
        group.add(headMesh);
    }

    prostheticMesh = group;

    // Автоматически центрируем протез в геометрическом центре кости
    prostheticMesh.position.copy(center);
    scene.add(prostheticMesh);

    // Подключаем интерактивные хирургические оси для тонкой ручной настройки позиционирования
    transformControls.attach(prostheticMesh);
}


// ==========================================
// 5. PyWebView Bridge Events
// ==========================================
window.addEventListener('pywebviewready', () => {

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

    importNiftiBtn.addEventListener('click', async () => {
        const result = await window.pywebview.api.ask_nifti_path();
        if (!result || result.status === "cancelled") return;

        if (result.status === "success") {
            setUIMode("nifti");
            currentNiftiPath = result.path;
            scanTitle.innerText = "NIfTI:\n" + result.filename;

            renderBtn.disabled = false;
            exportBtn.disabled = true;
            exportNiftiBtn.disabled = true;
        } else if (result.status === "error") {
            alert("NIfTI Picker Error:\n" + result.message);
        }
    });

    renderBtn.addEventListener('click', async () => {
        renderBtn.disabled = true;
        exportBtn.disabled = true;
        exportNiftiBtn.disabled = true;
        if (btnDiagnostics) btnDiagnostics.disabled = true;

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
            loadSTL(result.file + '?v=' + Date.now());
        } else {
            alert("Render Error:\n" + (result ? result.message : "Unknown error"));
            renderBtn.disabled = false;
            setLoading(false);
        }
    });

    // Обработка кнопки Start Diagnostics
    if (btnDiagnostics) {
        btnDiagnostics.addEventListener('click', async () => {
            btnDiagnostics.disabled = true;
            setLoading(true, "Виконання ML-діагностики...");

            try {
                const result = await window.pywebview.api.start_diagnostics();

                if (result.status === "success") {
                    const rec = result.recommendation;

                    // ПЕРЕДАЕМ ML-РЕКОМЕНДАЦИЮ В ФУНКЦИЮ ОТРИСОВКИ
                    overlayProstheticMesh(rec);

                    const infoText =
                        `=== РЕЗУЛЬТАТ ДІАГНОСТИКИ ===\n\n` +
                        `Рекомендований протез:\n${rec.name}\n\n` +
                        `Точність підбору (ML): ${Math.round(rec.confidence * 100)}%\n\n` +
                        `Опис:\n${rec.description}\n\n` +
                        `Обґрунтування:\n${rec.reasoning}\n\n` +
                        `Параметри дефекту:\n` +
                        `• Довжина: ${rec.features[1]} мм\n` +
                        `• Діаметр: ${rec.features[2]} мм`;

                    alert(infoText);
                } else {
                    alert("Помилка діагностики:\n" + result.message);
                }
            } catch (e) {
                alert("Помилка з'єднання з ML-модулем: " + e);
            } finally {
                setLoading(false);
                btnDiagnostics.disabled = false;
            }
        });
    }

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