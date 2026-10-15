window.BoneApp = window.BoneApp || {};

// Memory polyfill for Linux
(function() {
    try {
        if (typeof window.localStorage !== 'undefined') {
            window.localStorage.setItem('__test', '1');
            window.localStorage.removeItem('__test');
            return;
        }
    } catch (e) {}
    const mem = {};
    window.localStorage = {
        getItem: k => mem[k] || null,
        setItem: (k, v) => { mem[k] = String(v); },
        removeItem: k => { delete mem[k]; },
        clear: () => { for (let k in mem) delete mem[k]; }
    };
})();

// DOM elements
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

window.BoneApp.setAllButtonsDisabled = (disabled) => {
    renderBtn.disabled = disabled;
    exportBtn.disabled = disabled;
    exportNiftiBtn.disabled = disabled;
    if (btnDiagnostics) btnDiagnostics.disabled = disabled;
    if (window.BoneApp.enableDefectButton) window.BoneApp.enableDefectButton(!disabled);
};

function setLoading(active, message = "Processing...") {
    loadingText.innerText = message;
    if (active) loadingOverlay.classList.add('active');
    else loadingOverlay.classList.remove('active');
}
window.BoneApp.setLoading = setLoading;

// Callback after model rendering is complete
window.BoneApp.onModelReady = () => {
    renderBtn.disabled = false;
    exportBtn.disabled = false;
    exportNiftiBtn.disabled = false;
    if (btnDiagnostics) btnDiagnostics.disabled = false;
    if (window.BoneApp.enableDefectButton) window.BoneApp.enableDefectButton(true);
    setLoading(false);
};

function setUIMode(mode) {
    currentMode = mode;
    const isNifti = (mode === "nifti");
    huInput.disabled = isNifti;
    lowHuInput.disabled = isNifti;
    iterationsInput.disabled = isNifti;
    seriesSelect.disabled = isNifti;
    if (isNifti) seriesSelect.innerHTML = `<option value="nifti" selected>NIfTI Data</option>`;
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
    const nextState = !btnAdvanced.classList.contains('active');
    localStorage.setItem('bone_advanced_mode', nextState);
    applyAdvancedMode(nextState);
});

// PyWebView event listeners
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
            scanResult.series.forEach((s, idx) => {
                const opt = document.createElement('option');
                opt.value = s.id;
                opt.innerText = `Series ${idx + 1} (${s.count} slices)`;
                seriesSelect.appendChild(opt);
            });
            seriesSelect.disabled = false;
            huInput.disabled = false;
            lowHuInput.disabled = false;
            iterationsInput.disabled = false;
            renderBtn.disabled = false;
        } else {
            alert("Помилка сканування DICOM: " + scanResult.message);
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
        }
    });

    renderBtn.addEventListener('click', async () => {
        renderBtn.disabled = true;
        exportBtn.disabled = true;
        exportNiftiBtn.disabled = true;
        if (btnDiagnostics) btnDiagnostics.disabled = true;
        if (window.BoneApp.enableDefectButton) window.BoneApp.enableDefectButton(false);

        let res;
        if (currentMode === "dicom") {
            setLoading(true, "Converting DICOM to STL...");
            res = await window.pywebview.api.run_conversion(
                currentDicomPath, seriesSelect.value, huInput.value, lowHuInput.value, iterationsInput.value
            );
        } else {
            setLoading(true, "Rendering NIfTI to 3D...");
            res = await window.pywebview.api.run_nifti_conversion(currentNiftiPath);
        }

        if (res && res.status === "success") {
            window.BoneApp.loadSTL(res.file + '?v=' + Date.now());
        } else {
            alert("Помилка рендерингу: " + (res ? res.message : "Невідома помилка"));
            renderBtn.disabled = false;
            setLoading(false);
        }
    });

    if (btnDiagnostics) {
        btnDiagnostics.addEventListener('click', async () => {
            btnDiagnostics.disabled = true;
            setLoading(true, "Виконання ML-діагностики...");
            try {
                const res = await window.pywebview.api.start_diagnostics();
                if (res.status === "success") {
                    window.BoneApp.overlayProstheticMesh(res.recommendation);
                    alert(`=== РЕЗУЛЬТАТ ДІАГНОСТИКИ ===\n\nПротез: ${res.recommendation.name}\nТочність: ${Math.round(res.recommendation.confidence * 100)}%\n\n${res.recommendation.reasoning}`);
                }
            } finally {
                setLoading(false);
                btnDiagnostics.disabled = false;
            }
        });
    }

    exportBtn.addEventListener('click', async () => {
        const res = await window.pywebview.api.export_stl();
        if (res.status === "success") alert("STL збережено:\n" + res.path);
    });

    exportNiftiBtn.addEventListener('click', async () => {
        const res = await window.pywebview.api.export_nifti();
        if (res.status === "success") alert("NIfTI збережено:\n" + res.path);
    });
});