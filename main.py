import os
import sys
import shutil
import webview
import numpy as np
from converter import DicomConverter, STLExporter, NiftiHandler

# PyInstaller compatibility
if hasattr(sys, '_MEIPASS'):
    os.chdir(sys._MEIPASS)

def get_user_dir():
    if hasattr(sys, 'frozen'):
        return os.path.dirname(sys.executable)
    return os.getcwd()


class Api:
    """Bridges Three.js frontend with Python processing pipelines."""

    def __init__(self):
        self.output_dir = os.path.join('web', 'output')
        os.makedirs(self.output_dir, exist_ok=True)
        self.cached_stl = os.path.join(self.output_dir, 'solid_bone.stl')
        self.cached_nii = os.path.join(self.output_dir, 'solid_bone.nii.gz')

    def ask_folder_path(self):
        """Native DICOM folder picker."""
        result = webview.windows[0].create_file_dialog(
            webview.FOLDER_DIALOG,
            directory=get_user_dir()
        )
        return result[0] if result and len(result) > 0 else None

    def scan_folder(self, dicom_folder):
        """Scans selected folder for valid series."""
        try:
            return DicomConverter.scan_series(dicom_folder)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def run_conversion(self, dicom_folder, series_id, hu_val, low_hu_val=220, iterations_val=6):
        """Runs segmentation and caches both STL and NIfTI volumes."""
        try:
            converter = DicomConverter(
                dicom_dir=dicom_folder,
                output_stl_path=self.cached_stl,
                series_id=series_id,
                hu_threshold=float(hu_val),
                low_threshold=float(low_hu_val),
                bone_search_iters=int(iterations_val),
                step_size=1
            )
            # Generates STL and caches paired .nii.gz simultaneously
            converter.convert(export_nifti_path=self.cached_nii)

            return {"status": "success", "file": "./output/solid_bone.stl"}
        except Exception as e:
            print(f"[Conversion Error]: {e}")
            return {"status": "error", "message": str(e)}

    def ask_nifti_path(self):
        """Opens native file picker for NIfTI without processing."""
        try:
            result = webview.windows[0].create_file_dialog(
                webview.OPEN_DIALOG,
                directory=get_user_dir(),
                file_types=('NIfTI Files (*.nii;*.gz)', 'All Files (*.*)')
            )

            if not result or len(result) == 0:
                return {"status": "cancelled"}

            file_path = result if isinstance(result, str) else result[0]

            if not (file_path.endswith('.nii') or file_path.endswith('.nii.gz')):
                return {"status": "error", "message": "Selected file is not a valid .nii or .nii.gz archive"}

            return {
                "status": "success",
                "path": file_path,
                "filename": os.path.basename(file_path)
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def run_nifti_conversion(self, nifti_path):
        """Processes NIfTI volume, generates surface mesh, and caches files."""
        try:
            if not os.path.exists(nifti_path):
                return {"status": "error", "message": "NIfTI file does not exist."}

            volume, spacing, sitk_img = NiftiHandler.load(nifti_path)

            # Real density values
            if volume.dtype == bool or np.max(volume) <= 1:
                mask = volume > 0
            else:
                mask = volume >= 450.0

            # Build mesh and cache STL
            verts, faces, normals = STLExporter.generate_mesh(mask, spacing)
            STLExporter.export(verts, faces, normals, self.cached_stl)

            # Nifti cache
            shutil.copy(nifti_path, self.cached_nii)

            return {"status": "success", "file": "./output/solid_bone.stl"}
        except Exception as e:
            print(f"[NIfTI Render Error]: {e}")
            return {"status": "error", "message": str(e)}

    def export_nifti(self):
        """Saves current volume to user-selected NIfTI path."""
        if not os.path.exists(self.cached_nii):
            return {"status": "error", "message": "No NIfTI data available for export."}

        # Valid file types for NIfTI export
        result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG,
            directory=get_user_dir(),
            save_filename='solid_bone.nii.gz',
            file_types=('Compressed Archive (*.gz)', 'NIfTI (*.nii)', 'All Files (*.*)')
        )

        if result and len(result) > 0:
            dest_path = result if isinstance(result, str) else result[0]
            
            # Saving nii.gz directly
            if not dest_path.endswith('.nii.gz') and not dest_path.endswith('.nii'):
                dest_path += '.nii.gz'

            try:
                shutil.copy(self.cached_nii, dest_path)
                return {"status": "success", "path": dest_path}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        return {"status": "cancelled"}

    def export_stl(self):
        """Saves current mesh to user-selected STL path."""
        if not os.path.exists(self.cached_stl):
            return {"status": "error", "message": "No model has been rendered yet."}

        result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG,
            directory=get_user_dir(),
            save_filename='solid_bone.stl',
            file_types=('STL Files (*.stl)', 'All Files (*.*)')
        )

        if result and len(result) > 0:
            dest_path = result if isinstance(result, str) else result[0]
            try:
                shutil.copy(self.cached_stl, dest_path)
                return {"status": "success", "path": dest_path}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        return {"status": "cancelled"}

    def export_nifti(self):
        """Saves current volume to user-selected NIfTI path."""
        if not os.path.exists(self.cached_nii):
            return {"status": "error", "message": "No NIfTI data available for export."}

        result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG,
            directory=get_user_dir(),
            save_filename='solid_bone.nii.gz',
            file_types=('NIfTI Compressed (*.nii.gz)', 'NIfTI (*.nii)', 'All Files (*.*)')
        )

        if result and len(result) > 0:
            dest_path = result if isinstance(result, str) else result[0]
            try:
                shutil.copy(self.cached_nii, dest_path)
                return {"status": "success", "path": dest_path}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        return {"status": "cancelled"}


if __name__ == '__main__':
    api = Api()

    webview.create_window(
        title='DICOM to STL & NIfTI Studio',
        url='web/index.html',
        js_api=api,
        width=1200,
        height=800,
        min_size=(1000, 600),
        background_color='#ffffff',
        maximized=True
    )

    webview.start()