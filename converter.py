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
        solid_mask = self._fill_cavities(clean_mask)
        
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
        """Removes small noise objects."""
        raw_mask = volume >= self.hu_threshold
        labeled_mask, num_features = measure.label(raw_mask, return_num=True)
        clean_mask = np.zeros_like(raw_mask)

        if num_features > 0:
            # Keep only large components
            for region in measure.regionprops(labeled_mask):
                if region.area > self.min_volume:
                    clean_mask[labeled_mask == region.label] = True
                    
        return clean_mask

    def _fill_cavities(self, mask: np.ndarray) -> np.ndarray:
        """Closes micro-cracks and fills internal bone cavities."""
        # Inflate slightly to seal external micro-cracks
        closed_mask = ndi.binary_closing(mask, iterations=2)
        solid_mask = np.zeros_like(closed_mask)
        
        # 2D Fill holes along the Z axis (axial slices)
        for z in range(closed_mask.shape[0]):
            solid_mask[z] = ndi.binary_fill_holes(closed_mask[z])
            
        return solid_mask

    def _generate_mesh(self, mask: np.ndarray, spacing: tuple):
        """Marching Cubes algorithm to extract surface geometry."""
        verts, faces, normals, _ = measure.marching_cubes(
            volume=mask.astype(float),
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