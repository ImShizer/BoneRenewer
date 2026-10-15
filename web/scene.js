import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { STLLoader } from 'three/addons/loaders/STLLoader.js';
import { TransformControls } from 'three/addons/controls/TransformControls.js';

window.BoneApp = window.BoneApp || {};

const container = document.getElementById('canvas-container');
const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf8fafc);

const camera = new THREE.PerspectiveCamera(45, container.clientWidth / container.clientHeight, 0.1, 2000);
camera.position.set(0, 150, 300);

const renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
renderer.setSize(container.clientWidth, container.clientHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
container.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;

const transformControls = new TransformControls(camera, renderer.domElement);
transformControls.addEventListener('dragging-changed', (e) => {
    controls.enabled = !e.value;
});
scene.add(transformControls);

// Lighting and reference grid
scene.add(new THREE.AmbientLight(0xffffff, 0.7));
const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.8);
dirLight1.position.set(120, 220, 120);
scene.add(dirLight1);

const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.4);
dirLight2.position.set(-120, -100, -120);
scene.add(dirLight2);

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

let currentMesh = null;
let defectZoneMesh = null;
let prostheticMesh = null;
let isDefectZoneVisible = true;
let activeLoadToken = 0;

function cleanupMesh() {
    if (transformControls) transformControls.detach();
    if (currentMesh) {
        scene.remove(currentMesh);
        if (currentMesh.geometry) currentMesh.geometry.dispose();
        if (currentMesh.material) currentMesh.material.dispose();
        currentMesh = null;
    }
    if (defectZoneMesh) {
        scene.remove(defectZoneMesh);
        if (defectZoneMesh.geometry) defectZoneMesh.geometry.dispose();
        if (defectZoneMesh.material) defectZoneMesh.material.dispose();
        defectZoneMesh = null;
    }
    if (prostheticMesh) {
        scene.remove(prostheticMesh);
        if (prostheticMesh.geometry) prostheticMesh.geometry.dispose();
        if (prostheticMesh.material) prostheticMesh.material.dispose();
        prostheticMesh = null;
    }
}

function loadSTL(url, onLoaded = null, resetCamera = true, defectZoneUrl = null) {
    const loader = new STLLoader();
    const loadToken = ++activeLoadToken;

    loader.load(
        url,
        (geometry) => {
            if (loadToken !== activeLoadToken) {
                geometry.dispose();
                return;
            }

            cleanupMesh();
            geometry.computeVertexNormals();

            // Compute bounding box center offset of the primary bone mesh
            // so the exact same spatial translation can be applied to the defect zone mesh
            geometry.computeBoundingBox();
            const centerOffset = new THREE.Vector3();
            geometry.boundingBox.getCenter(centerOffset).negate();
            geometry.translate(centerOffset.x, centerOffset.y, centerOffset.z);

            const material = new THREE.MeshStandardMaterial({
                color: 0xf5e6d3,
                roughness: 0.4,
                metalness: 0.1,
                side: THREE.DoubleSide
            });

            currentMesh = new THREE.Mesh(geometry, material);
            currentMesh.rotation.x = -Math.PI / 2;
            scene.add(currentMesh);

            // Load and align the red ground-truth defect zone mesh if provided
            if (defectZoneUrl) {
                loader.load(
                    defectZoneUrl,
                    (defectGeo) => {
                        if (loadToken !== activeLoadToken) {
                            defectGeo.dispose();
                            return;
                        }
                        defectGeo.computeVertexNormals();
                        // Apply identical translation vector for 1:1 coordinate alignment
                        defectGeo.translate(centerOffset.x, centerOffset.y, centerOffset.z);

                        const defectMaterial = new THREE.MeshPhysicalMaterial({
                            color: 0xef4444,
                            emissive: 0x991b1b,
                            emissiveIntensity: 0.35,
                            roughness: 0.25,
                            metalness: 0.05,
                            transparent: true,
                            opacity: 0.65,
                            depthWrite: false,
                            side: THREE.DoubleSide
                        });

                        defectZoneMesh = new THREE.Mesh(defectGeo, defectMaterial);
                        defectZoneMesh.rotation.x = -Math.PI / 2;
                        defectZoneMesh.renderOrder = 1;
                        defectZoneMesh.visible = isDefectZoneVisible;
                        scene.add(defectZoneMesh);
                    },
                    undefined,
                    (err) => {
                        console.warn("[Three.js] Defect highlight zone not loaded:", err);
                    }
                );
            }

            // Reset camera only when explicitly requested (e.g., initial render)
            if (resetCamera) {
                controls.target.set(0, 0, 0);
                camera.position.set(0, 100, 250);
                controls.update();
            }

            if (onLoaded) onLoaded();
            if (window.BoneApp.onModelReady) window.BoneApp.onModelReady();
        },
        undefined,
        (error) => {
            console.error("[Three.js] STL loading failed:", error);
            alert("Failed to load generated 3D model.");
            if (window.BoneApp.setLoading) window.BoneApp.setLoading(false);
        }
    );
}

// Toggle visibility of the red defect zone mesh
function setDefectZoneVisible(visible) {
    isDefectZoneVisible = Boolean(visible);
    if (defectZoneMesh) {
        defectZoneMesh.visible = isDefectZoneVisible;
    }
}

// Exporting to the app context
window.BoneApp.scene = scene;
window.BoneApp.transformControls = transformControls;
window.BoneApp.loadSTL = loadSTL;
window.BoneApp.cleanupMesh = cleanupMesh;
window.BoneApp.getCurrentMesh = () => currentMesh;
window.BoneApp.getDefectZoneMesh = () => defectZoneMesh;
window.BoneApp.setDefectZoneVisible = setDefectZoneVisible;
window.BoneApp.getDefectZoneVisible = () => isDefectZoneVisible;
window.BoneApp.getProstheticMesh = () => prostheticMesh;
window.BoneApp.setProstheticMesh = (m) => { prostheticMesh = m; };