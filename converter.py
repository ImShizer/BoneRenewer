import os
import SimpleITK as sitk
import numpy as np
import scipy.ndimage as ndi
from skimage import measure
import trimesh


class STLExporter:
    """Handles 3D surface generation via Marching Cubes and STL file export."""

    @staticmethod
    def generate_mesh(mask: np.ndarray, spacing: tuple, step_size: int = 1, sigma: float = 0.8):
        """Generates smoothed surface mesh from a 3D boolean volume."""
        smoothed_mask = ndi.gaussian_filter(mask.astype(float), sigma=sigma)

        # SimpleITK spacing is (X, Y, Z); marching_cubes takes (Z, Y, X)
        verts, faces, normals, _ = measure.marching_cubes(
            volume=smoothed_mask,
            level=0.5,
            spacing=(spacing[2], spacing[1], spacing[0]),
            step_size=step_size
        )
        return verts, faces, normals

    @staticmethod
    def export(verts: np.ndarray, faces: np.ndarray, normals: np.ndarray, output_path: str):
        """Cleans mesh topology and saves binary STL."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, vertex_normals=normals)
        mesh.process()
        mesh.export(output_path)

        print(f"[STLExporter] Saved: {output_path} | Polygons: {len(mesh.faces):,}")


class NiftiHandler:
    """Handles NIfTI (.nii.gz) input/output with spatial metadata preservation."""

    @staticmethod
    def export(volume_or_mask: np.ndarray, output_path: str, reference_image: sitk.Image = None, spacing: tuple = None):
        """
        Exports a NumPy volume to compressed NIfTI (.nii.gz).
        Preserves physical coordinates, origin, and spacing.
        """
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        data = volume_or_mask.astype(np.uint8) if volume_or_mask.dtype == bool else volume_or_mask.astype(np.int16)
        itk_image = sitk.GetImageFromArray(data)

        if reference_image is not None:
            itk_image.CopyInformation(reference_image)
        elif spacing is not None:
            itk_image.SetSpacing(spacing)

        sitk.WriteImage(itk_image, output_path)
        print(f"[NiftiHandler] Exported NIfTI to: {output_path}")

    @staticmethod
    def load(nifti_path: str):
        """
        Loads NIfTI image, enforces LPS orientation, and returns raw volume + spacing.
        """
        if not os.path.exists(nifti_path):
            raise FileNotFoundError(f"File not found: {nifti_path}")

        image = sitk.ReadImage(nifti_path)
        image = sitk.DICOMOrient(image, 'LPS')
        volume = sitk.GetArrayFromImage(image)
        spacing = image.GetSpacing()

        return volume, spacing, image


class DicomConverter:
    """Orchestrates DICOM loading, advanced bone reconstruction, and pipelines export."""

    def __init__(
        self,
        dicom_dir: str,
        output_stl_path: str,
        series_id: str,
        hu_threshold: float = 450.0,
        low_threshold: float = 220.0,
        bone_search_iters: int = 6,
        step_size: int = 1
    ):
        self.dicom_dir = dicom_dir
        self.output_stl_path = output_stl_path
        self.series_id = series_id
        self.hu_threshold = hu_threshold
        self.low_threshold = low_threshold
        self.bone_search_iters = bone_search_iters
        self.step_size = step_size
        self.min_volume = 3000

        self.sitk_image = None
        self.spacing = None

    def convert(self, export_nifti_path: str = None):
        """Executes full reconstruction pipeline."""
        print("1. Loading DICOM series...")
        volume, spacing = self._load_dicom()

        print(f"2. Segmenting bone tissues (Core >= {self.hu_threshold} HU)...")
        clean_mask = self._segment_bone(volume)

        print(f"3. Filling internal cavities (Spongy >= {self.low_threshold} HU, iters={self.bone_search_iters})...")
        solid_mask = self._fill_cavities(clean_mask, volume)

        print("4. Generating surface mesh...")
        verts, faces, normals = STLExporter.generate_mesh(solid_mask, spacing, self.step_size)

        print("5. Exporting STL file...")
        STLExporter.export(verts, faces, normals, self.output_stl_path)

        if export_nifti_path:
            print("6. Exporting paired NIfTI mask...")
            NiftiHandler.export(solid_mask, export_nifti_path, reference_image=self.sitk_image)

        return solid_mask, spacing

    def _load_dicom(self):
        """Loads and sorts DICOM series with continuity verification."""
        reader = sitk.ImageSeriesReader()
        dicom_files = reader.GetGDCMSeriesFileNames(self.dicom_dir, self.series_id)

        if not dicom_files:
            raise ValueError(f"No files found for series {self.series_id}")

        reader.SetFileNames(dicom_files)
        image = reader.Execute()
        image = sitk.DICOMOrient(image, 'LPS')

        self.sitk_image = image
        self.spacing = image.GetSpacing()
        volume = sitk.GetArrayFromImage(image)

        return volume, self.spacing

    @staticmethod
    def scan_series(dicom_dir: str):
        """Scans directories for valid DICOM series."""
        reader = sitk.ImageSeriesReader()
        series_ids = reader.GetGDCMSeriesIDs(dicom_dir)

        if not series_ids:
            return {"status": "error", "message": "No DICOM series found."}

        valid_series = []
        for s_id in series_ids:
            files = reader.GetGDCMSeriesFileNames(dicom_dir, s_id)
            if len(files) > 1:
                valid_series.append({
                    "id": s_id,
                    "count": len(files)
                })

        if not valid_series:
            return {"status": "error", "message": "No 3D series (>1 slice) found."}

        valid_series.sort(key=lambda x: x["count"], reverse=True)
        return {"status": "success", "series": valid_series}

    def _segment_bone(self, volume: np.ndarray) -> np.ndarray:
        """Stage 1: Core isolation >= hu_threshold."""
        core_mask = volume >= self.hu_threshold
        labeled_core, num_features = measure.label(core_mask, return_num=True)

        if num_features == 0:
            return np.zeros_like(core_mask, dtype=bool)

        clean_core = np.zeros_like(core_mask, dtype=bool)
        for region in measure.regionprops(labeled_core):
            if region.area >= self.min_volume:
                clean_core[labeled_core == region.label] = True

        return clean_core

    def _fill_cavities(self, core_mask: np.ndarray, volume: np.ndarray) -> np.ndarray:
        """Stage 2: Per-bone reconstruction with Z-axis channel filling and DMZ protection."""
        labeled_bones, num_bones = measure.label(core_mask, return_num=True)
        final_solid_volume = np.zeros_like(core_mask, dtype=bool)

        spongy_candidates = volume >= self.low_threshold

        for region in measure.regionprops(labeled_bones):
            if region.area < self.min_volume:
                continue

            single_bone_core = (labeled_bones == region.label)

            # Joint crossover protection
            other_bones = core_mask & (~single_bone_core)
            forbidden_zone = ndi.binary_dilation(other_bones, iterations=2)

            bone_search_zone = ndi.binary_dilation(
                single_bone_core, iterations=self.bone_search_iters
            ) & (~forbidden_zone)

            # Add spongy candidates
            enhanced_bone = single_bone_core | (spongy_candidates & bone_search_zone)

            # Halo and noise filtering
            labeled_enhanced = measure.label(enhanced_bone)
            if labeled_enhanced.max() > 0:
                counts = np.bincount(labeled_enhanced.ravel())
                counts[0] = 0
                main_label = np.argmax(counts)
                enhanced_bone = (labeled_enhanced == main_label)

            # Transverse cavity filling
            enhanced_bone = ndi.binary_closing(enhanced_bone, iterations=2)
            for z in range(enhanced_bone.shape[0]):
                enhanced_bone[z, :, :] = ndi.binary_fill_holes(enhanced_bone[z, :, :])

            final_solid_volume |= enhanced_bone

        return final_solid_volume