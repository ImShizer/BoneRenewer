import * as THREE from 'three';

window.BoneApp = window.BoneApp || {};

export function overlayProstheticMesh(recommendation) {
    const currentMesh = window.BoneApp.getCurrentMesh();
    const scene = window.BoneApp.scene;
    const transformControls = window.BoneApp.transformControls;

    if (!currentMesh) return;

    // Adding transparency to the current mesh to visualize the prosthetic overlay
    currentMesh.material.transparent = true;
    currentMesh.material.opacity = 0.45;

    if (transformControls) transformControls.detach();
    let oldProsthetic = window.BoneApp.getProstheticMesh();
    if (oldProsthetic) {
        scene.remove(oldProsthetic);
        if (oldProsthetic.geometry) oldProsthetic.geometry.dispose();
        if (oldProsthetic.material) oldProsthetic.material.dispose();
    }

    currentMesh.geometry.computeBoundingBox();
    const bbox = currentMesh.geometry.boundingBox;
    const size = new THREE.Vector3();
    bbox.getSize(size);
    const center = new THREE.Vector3();
    bbox.getCenter(center);

    const metalMaterial = new THREE.MeshStandardMaterial({ color: 0xd1d5db, metalness: 0.95, roughness: 0.15 });
    const porousMaterial = new THREE.MeshStandardMaterial({ color: 0x6b7280, metalness: 0.5, roughness: 0.8 });

    const group = new THREE.Group();
    const type = (recommendation && (recommendation.type || recommendation.id)) ? (recommendation.type || recommendation.id) : "proximal";

    if (type.includes("distal")) {
        const stemRadius = Math.min(size.x, size.z) * 0.06;
        const stemHeight = size.y * 0.35;
        const stem = new THREE.Mesh(new THREE.CylinderGeometry(stemRadius, stemRadius * 0.7, stemHeight, 32), metalMaterial);
        stem.position.y = stemHeight / 2;
        const block = new THREE.Mesh(new THREE.BoxGeometry(size.x * 0.3, size.y * 0.12, size.z * 0.3), metalMaterial);
        group.add(stem);
        group.add(block);
    } else if (type.includes("diaphyseal")) {
        const r = Math.min(size.x, size.z) * 0.14;
        const h = size.y * 0.35;
        group.add(new THREE.Mesh(new THREE.CylinderGeometry(r, r * 0.9, h, 32), porousMaterial));
    } else if (type.includes("plate")) {
        group.add(new THREE.Mesh(new THREE.BoxGeometry(size.x * 0.15, size.y * 0.45, 4), metalMaterial));
    } else {
        const topR = Math.min(size.x, size.z) * 0.05;
        const stemH = size.y * 0.4;
        const stem = new THREE.Mesh(new THREE.CylinderGeometry(topR, topR * 0.5, stemH, 32), metalMaterial);
        stem.position.y = -stemH / 2;
        group.add(stem);

        const neckL = topR * 1.8;
        const neck = new THREE.Mesh(new THREE.CylinderGeometry(topR * 0.56, topR * 0.7, neckL, 32), metalMaterial);
        neck.rotation.z = -Math.PI / 4;
        neck.position.set(neckL * 0.35, neckL * 0.35, 0);
        group.add(neck);

        const head = new THREE.Mesh(new THREE.SphereGeometry(topR * 1.3, 32, 32), metalMaterial);
        head.position.set(neckL * 0.7, neckL * 0.7, 0);
        group.add(head);
    }

    group.position.copy(center);
    scene.add(group);
    window.BoneApp.setProstheticMesh(group);

    transformControls.attach(group);
}

window.BoneApp.overlayProstheticMesh = overlayProstheticMesh;