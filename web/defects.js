window.BoneApp = window.BoneApp || {};

const btnDeform = document.getElementById('btn-deform');
const defectNav = document.getElementById('defect-nav');
const defectPrevBtn = document.getElementById('defect-prev-btn');
const defectNextBtn = document.getElementById('defect-next-btn');
const defectTitle = document.getElementById('defect-title');
const defectBadge = document.getElementById('defect-badge');
const defectZoneBtn = document.getElementById('defect-zone-btn');

let defectsList = [];
let currentDefectIndex = 0;

function updateZoneButtonUI(isBaseline = false) {
    if (!defectZoneBtn) return;
    const isVisible = window.BoneApp.getDefectZoneVisible
        ? window.BoneApp.getDefectZoneVisible()
        : true;

    defectZoneBtn.disabled = isBaseline;
    if (isVisible && !isBaseline) {
        defectZoneBtn.classList.add('active');
    } else {
        defectZoneBtn.classList.remove('active');
    }
}

async function showDefect(index) {
    if (!defectsList || defectsList.length === 0) return;
    const def = defectsList[index];
    const isBaseline = (index === 0 || def.id === 'baseline');

    defectTitle.innerText = def.title;
    // Format badge: 0 is Baseline, 1-3 are synthetic lesions
    defectBadge.innerText = isBaseline
        ? `0 / ${defectsList.length - 1} (Baseline)`
        : `${index} / ${defectsList.length - 1}`;

    updateZoneButtonUI(isBaseline);

    // Notify backend which model is active for diagnostics
    if (window.pywebview && window.pywebview.api && window.pywebview.api.select_defect) {
        await window.pywebview.api.select_defect(def.id);
    }

    const cacheBuster = '?v=' + Date.now();
    const boneUrl = def.file + cacheBuster;

    // Resolve path to the excised red defect zone STL (with automatic naming fallback)
    let zoneFile = def.defect_file;
    if (!zoneFile && !isBaseline && def.file) {
        zoneFile = def.file.replace(/\.stl$/i, '_zone.stl');
    }
    const zoneUrl = (!isBaseline && zoneFile) ? (zoneFile + cacheBuster) : null;

    // Load bone STL and red defect zone STL without resetting camera position
    window.BoneApp.loadSTL(boneUrl, null, false, zoneUrl);
}

if (btnDeform) {
    btnDeform.addEventListener('click', async () => {
        // Gray out all action buttons during calculation
        if (window.BoneApp.setAllButtonsDisabled) {
            window.BoneApp.setAllButtonsDisabled(true);
        }
        if (window.BoneApp.setLoading) {
            window.BoneApp.setLoading(true, "Generating defect models...");
        }

        try {
            const result = await window.pywebview.api.generate_defects();
            if (result.status === "success") {
                defectsList = result.defects;
                currentDefectIndex = 0; // Starts at Baseline
                defectNav.classList.remove('hidden');
                await showDefect(currentDefectIndex);
            } else {
                alert("Defect Generation Error:\n" + result.message);
            }
        } catch (e) {
            alert("Bridge Error: " + e);
        } finally {
            if (window.BoneApp.setLoading) {
                window.BoneApp.setLoading(false);
            }
            // Restore button states
            if (window.BoneApp.setAllButtonsDisabled) {
                window.BoneApp.setAllButtonsDisabled(false);
            }
        }
    });
}

if (defectPrevBtn) {
    defectPrevBtn.addEventListener('click', () => {
        if (!defectsList || defectsList.length === 0) return;
        currentDefectIndex = (currentDefectIndex - 1 + defectsList.length) % defectsList.length;
        showDefect(currentDefectIndex);
    });
}

if (defectNextBtn) {
    defectNextBtn.addEventListener('click', () => {
        if (!defectsList || defectsList.length === 0) return;
        currentDefectIndex = (currentDefectIndex + 1) % defectsList.length;
        showDefect(currentDefectIndex);
    });
}

if (defectZoneBtn) {
    defectZoneBtn.addEventListener('click', () => {
        if (!window.BoneApp.getDefectZoneVisible || !window.BoneApp.setDefectZoneVisible) return;
        const nextState = !window.BoneApp.getDefectZoneVisible();
        window.BoneApp.setDefectZoneVisible(nextState);
        updateZoneButtonUI(currentDefectIndex === 0);
    });
}

window.BoneApp.enableDefectButton = (state = true) => {
    if (btnDeform) btnDeform.disabled = !state;
};