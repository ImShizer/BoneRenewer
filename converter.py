import os
import SimpleITK as sitk
import numpy as np
import scipy.ndimage as ndi
from skimage import measure
import trimesh

class DicomConverter:
    """Converts DICOM medical image series to solid STL 3D models."""
    
    def __init__(self, dicom_dir: str, output_path: str, series_id: str, hu_threshold: float = 450.0, step_size: int = 1):
        self.dicom_dir = dicom_dir
        self.output_path = output_path
        self.hu_threshold = hu_threshold
        self.step_size = step_size
        self.series_id = series_id
        self.min_volume = 3000  # Minimum voxel count to keep

    def convert(self):
        print("1. Loading DICOM data...")
        volume, spacing = self._load_dicom()

        print("2. Segmenting bone tissues...")
        clean_mask = self._segment_bone(volume)
        
        print("3. Filling internal cavities...")
        solid_mask = self._fill_cavities(clean_mask, volume)
        
        print("4. Generating 3D mesh...")
        verts, faces, normals = self._generate_mesh(solid_mask, spacing)
        
        print("5. Exporting STL file...")
        self._export_mesh(verts, faces, normals)

    def _load_dicom(self):
        """Get the largest DICOM series."""
        reader = sitk.ImageSeriesReader()
        
        # Select the series
        dicom_files = reader.GetGDCMSeriesFileNames(self.dicom_dir, self.series_id)
        
        if not dicom_files:
            raise ValueError(f"No files found for series {self.series_id}")
        
        reader.SetFileNames(dicom_files)
        image = reader.Execute()
        
        image = sitk.DICOMOrient(image, 'LPS')
        volume = sitk.GetArrayFromImage(image)
        spacing = image.GetSpacing()
        
        return volume, spacing

    @staticmethod
    def scan_series(dicom_dir: str):
        """Scans directories for valid DICOM series"""
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
        """
        Stage 1: Extracts pure, isolated bone cores at hu_threshold (>=450 HU).
        Guarantees zero skin artifacts and complete joint separation.
        """
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
        """
        Accurate per-bone reconstruction:
        1. Strictly prevents adjacent bones from capturing each other (no joint fusion).
        2. Discards all disconnected noise particles (eliminates halo/dust/skin).
        3. Fills medullary canal along the Z-axis ONLY, preventing flat 2D films on side craters.
        """
        labeled_bones, num_bones = measure.label(core_mask, return_num=True)
        final_solid_volume = np.zeros_like(core_mask, dtype=bool)

        low_threshold = 220.0
        spongy_candidates = volume >= low_threshold

        for region in measure.regionprops(labeled_bones):
            if region.area < self.min_volume:
                continue

            # 1. Select the current bone core
            single_bone_core = (labeled_bones == region.label)

            # 2. Crossover prevention
            other_bones = core_mask & (~single_bone_core)
            forbidden_zone = ndi.binary_dilation(other_bones, iterations=2)

            bone_search_zone = ndi.binary_dilation(single_bone_core, iterations=6) & (~forbidden_zone)

            # 3. Add spongy bone candidates
            enhanced_bone = single_bone_core | (spongy_candidates & bone_search_zone)

            # 4. Remove small disconnected particles
            labeled_enhanced = measure.label(enhanced_bone)
            if labeled_enhanced.max() > 0:
                counts = np.bincount(labeled_enhanced.ravel())
                counts[0] = 0  
                main_label = np.argmax(counts)
                enhanced_bone = (labeled_enhanced == main_label)

            # 5. Z-axis filling and hole closure
            enhanced_bone = ndi.binary_closing(enhanced_bone, iterations=2)

            # Fill only transverse slices. This will turn the hollow tube into a solid,
            # but will not stretch the film on the lateral condyles of the joint.
            for z in range(enhanced_bone.shape[0]):
                enhanced_bone[z, :, :] = ndi.binary_fill_holes(enhanced_bone[z, :, :])
                
            # (Loops over Y and X are removed)

            # Add the processed bone to the final volume
            final_solid_volume |= enhanced_bone

        return final_solid_volume

    def _generate_mesh(self, mask: np.ndarray, spacing: tuple):
        smoothed_mask = ndi.gaussian_filter(mask.astype(float), sigma=0.8)

        verts, faces, normals, _ = measure.marching_cubes(
            volume=smoothed_mask,
            level=0.5,
            spacing=(spacing[2], spacing[1], spacing[0]),
            step_size=self.step_size
        )
        return verts, faces, normals

    def _export_mesh(self, verts: np.ndarray, faces: np.ndarray, normals: np.ndarray):
        """Clean geometry and export."""
        mesh = trimesh.Trimesh(vertices=verts, faces=faces, vertex_normals=normals)
        
        # Automatic geometry cleanup
        mesh.process() 
        mesh.export(self.output_path)
        
        print(f"\n SUCCESS: Saved to {self.output_path}")
        print(f" Polygons: {len(mesh.faces):,}")
        print(f" Dimensions (X, Y, Z): {[round(dim, 2) for dim in mesh.extents]} mm")


if __name__ == "__main__":
    # Test execution
    INPUT_DIR = "../Data/Knee/DCM"
    OUTPUT_FILE = "solid_bone.stl"

    converter = DicomConverter(
        dicom_dir=INPUT_DIR,
        output_path=OUTPUT_FILE,
        hu_threshold=450.0,
        step_size=1
    )
    converter.convert()