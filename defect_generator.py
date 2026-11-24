import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
import numpy as np
import scipy.ndimage as ndi
from skimage import measure
from converter import STLExporter


@dataclass
class AnatomicalContext:
    """Stores pre-calculated anatomical metadata and masks for reference during defect generation."""
    mask_bool: np.ndarray
    main_bone_mask: np.ndarray
    spacing: tuple
    z_min: int
    z_max: int
    y_min: int
    y_max: int
    x_min: int
    x_max: int
    slice_areas: np.ndarray


class BaseDefect(ABC):
    """Abstract Base Class for procedural bone defect generation strategies."""

    # --- Multi-scale Gaussian Noise Parameters ---
    SIGMA_COARSE: float = 2.2
    SIGMA_FINE: float = 0.85
    WEIGHT_COARSE: float = 0.65
    WEIGHT_FINE: float = 0.35
    EPSILON: float = 1e-8

    # --- Cleanup & Mesh Processing Parameters ---
    DEFAULT_MIN_VOXELS: int = 60
    EXCISED_MIN_VOXELS: int = 25
    BOUNDING_BOX_PAD: int = 4

    def __init__(self, defect_id: str, title: str, description: str):
        self.defect_id = defect_id
        self.title = title
        self.description = description

    @classmethod
    def _multi_scale_noise(cls, shape: tuple, seed: int = 42) -> np.ndarray:
        """
        Multi-scale 3D Gaussian noise normalized to [-1, 1],
        combining coarse fracture waves and fine trabecular roughness.
        """
        rng = np.random.default_rng(seed)
        
        coarse = ndi.gaussian_filter(rng.normal(0.0, 1.0, size=shape), sigma=cls.SIGMA_COARSE)
        coarse /= (np.max(np.abs(coarse)) + cls.EPSILON)

        fine = ndi.gaussian_filter(rng.normal(0.0, 1.0, size=shape), sigma=cls.SIGMA_FINE)
        fine /= (np.max(np.abs(fine)) + cls.EPSILON)

        combined = cls.WEIGHT_COARSE * coarse + cls.WEIGHT_FINE * fine
        return combined / (np.max(np.abs(combined)) + cls.EPSILON)

    @classmethod
    def _clean_small_fragments(cls, mask: np.ndarray, min_voxels: int = None) -> np.ndarray:
        """Removes tiny disconnected voxel islands ('floating dust') caused by stochastic boundary erosion."""
        if min_voxels is None:
            min_voxels = cls.DEFAULT_MIN_VOXELS

        labeled, num = measure.label(mask, return_num=True)
        if num <= 1:
            return mask
        counts = np.bincount(labeled.ravel())
        counts[0] = 0  # Ignore background label
        keep = counts >= min_voxels
        return keep[labeled]

    @classmethod
    def export_pair(cls, mask_intact: np.ndarray, mask_damaged: np.ndarray, spacing: tuple,
                    stl_bone_path: str, stl_zone_path: str):
        """Exports both the damaged bone mesh and the excised ground-truth defect mesh."""
        # 1. Export damaged bone model
        verts, faces, normals = STLExporter.generate_mesh(mask_damaged, spacing)
        STLExporter.export(verts, faces, normals, stl_bone_path)

        # 2. Compute and export the excised volume (Ground Truth Defect Zone)
        excised_mask = mask_intact & (~mask_damaged)
        excised_mask = cls._clean_small_fragments(excised_mask, min_voxels=cls.EXCISED_MIN_VOXELS)

        if np.any(excised_mask):
            v_z, f_z, n_z = STLExporter.generate_mesh(excised_mask, spacing)
            STLExporter.export(v_z, f_z, n_z, stl_zone_path)

    @abstractmethod
    def apply(self, ctx: AnatomicalContext, config: dict) -> np.ndarray:
        """Applies defect carving logic onto the bone mask and returns the modified mask."""
        pass


class SphericalCavityDefect(BaseDefect):
    """Generates a spherical cavity with irregular margins."""

    # Mathematical / Geometric Constants
    Y_OFFSET_RATIO: float = 0.4  # Shifts sphere center slightly inwards from anterior cortex

    def __init__(self):
        super().__init__(
            defect_id="cavity",
            title="Spherical Cavity (Cyst/Resection)",
            description="Spherical cavity with irregular margins."
        )

    def apply(self, ctx: AnatomicalContext, config: dict) -> np.ndarray:
        mask_cavity = ctx.mask_bool.copy()
        target_z = int(ctx.z_min + (ctx.z_max - ctx.z_min) * config["target_z_ratio"])
        target_z = np.clip(target_z, ctx.z_min, ctx.z_max)

        y_profile = np.where(ctx.main_bone_mask[target_z, :, :])
        if len(y_profile[0]) == 0:
            return mask_cavity

        y_front = y_profile[0].max()
        x_front = int(np.mean(y_profile[1][y_profile[0] == y_front]))

        r_mm = config["radius_mm"]
        rz = int(r_mm / ctx.spacing[2])
        ry = int(r_mm / ctx.spacing[1])
        rx = int(r_mm / ctx.spacing[0])

        pad = self.BOUNDING_BOX_PAD
        cz, cy, cx = target_z, int(y_front - ry * self.Y_OFFSET_RATIO), x_front
        z1, z2 = max(0, cz - rz - pad), min(ctx.mask_bool.shape[0], cz + rz + pad + 1)
        y1, y2 = max(0, cy - ry - pad), min(ctx.mask_bool.shape[1], cy + ry + pad + 1)
        x1, x2 = max(0, cx - rx - pad), min(ctx.mask_bool.shape[2], cx + rx + pad + 1)

        zz, yy, xx = np.ogrid[z1:z2, y1:y2, x1:x2]
        sphere_dist = np.sqrt(
            ((zz - cz) / max(rz, 1)) ** 2 +
            ((yy - cy) / max(ry, 1)) ** 2 +
            ((xx - cx) / max(rx, 1)) ** 2
        )

        noise_cav = self._multi_scale_noise((z2 - z1, y2 - y1, x2 - x1), seed=config["seed"])
        cavity_body = (sphere_dist + config["noise_scale"] * noise_cav) <= 1.0

        mask_cavity[z1:z2, y1:y2, x1:x2] &= ~cavity_body
        return self._clean_small_fragments(mask_cavity)


class WedgeFractureDefect(BaseDefect):
    """Generates a wedge fracture with irregular fracture margins."""

    # Mathematical Noise-Weighting Constants
    NOISE_MARGIN_WEIGHT_Z: float = 0.15
    NOISE_DEPTH_WEIGHT: float = 0.22
    NOISE_MARGIN_WEIGHT_Y: float = 0.16
    Z_FACTOR_MIN_THRESHOLD: float = 0.03

    def __init__(self):
        super().__init__(
            defect_id="wedge",
            title="Wedge Cortical Fracture",
            description="Diaphyseal cortical wedge deficit with stochastic fracture margins."
        )

    def apply(self, ctx: AnatomicalContext, config: dict) -> np.ndarray:
        mask_wedge = ctx.mask_bool.copy()
        wedge_z = int(ctx.z_min + (ctx.z_max - ctx.z_min) * config["target_z_ratio"])
        wedge_hz = int((config["height_mm"] / 2.0) / ctx.spacing[2])

        x_profile = np.where(ctx.main_bone_mask[wedge_z, :, :])
        if len(x_profile[1]) == 0:
            return mask_wedge

        x_edge = x_profile[1].max()
        y_edge = int(np.mean(x_profile[0][x_profile[1] == x_edge]))

        cut_depth_vox = int(config["depth_mm"] / ctx.spacing[0])
        width_y_vox = int(config["width_mm"] / ctx.spacing[1])

        pad = self.BOUNDING_BOX_PAD
        z1 = max(0, wedge_z - wedge_hz - pad)
        z2 = min(ctx.mask_bool.shape[0], wedge_z + wedge_hz + pad + 1)
        x1 = max(0, x_edge - cut_depth_vox - pad)
        x2 = min(ctx.mask_bool.shape[2], x_edge + 1)
        y1 = max(0, y_edge - width_y_vox - pad)
        y2 = min(ctx.mask_bool.shape[1], y_edge + width_y_vox + pad + 1)

        sub_shape = (z2 - z1, y2 - y1, x2 - x1)
        zz, yy, xx = np.ogrid[z1:z2, y1:y2, x1:x2]

        noise_depth = self._multi_scale_noise(sub_shape, seed=config["noise_seed_depth"])
        noise_margin = self._multi_scale_noise(sub_shape, seed=config["noise_seed_margin"])

        z_norm = (np.abs(zz - wedge_z) / max(wedge_hz, 1)) + self.NOISE_MARGIN_WEIGHT_Z * noise_margin
        z_factor = np.clip(1.0 - z_norm, 0.0, 1.0)

        fracture_depth = cut_depth_vox * (z_factor + self.NOISE_DEPTH_WEIGHT * noise_depth)
        wedge_dist_x = (x_edge - xx)
        wedge_dist_y = (np.abs(yy - y_edge) / max(width_y_vox, 1)) + self.NOISE_MARGIN_WEIGHT_Y * noise_margin

        wedge_body = (wedge_dist_x <= fracture_depth) & \
                     (wedge_dist_y <= z_factor) & \
                     (z_factor > self.Z_FACTOR_MIN_THRESHOLD)

        mask_wedge[z1:z2, y1:y2, x1:x2] &= ~wedge_body
        return self._clean_small_fragments(mask_wedge)


class PartialSegmentalResectionDefect(BaseDefect):
    """Generates a partial hemi-diaphyseal resection preserving a cortical bridge."""

    # Mathematical & Morphological Constants
    DEFAULT_DIAPHYSIS_RATIO: float = 0.45
    CUT_CENTER_OFFSET_X: float = 0.15
    CUT_CENTER_OFFSET_Y: float = 0.35
    MIN_CUT_RADIUS_VOXELS: float = 4.0

    # Taper Profile Parameters: 1.15 - 0.35 * (z_rel ** 2)
    TAPER_BASE: float = 1.15
    TAPER_QUADRATIC_COEFF: float = 0.35
    TAPER_MIN_CLIP: float = 0.5
    TAPER_MAX_CLIP: float = 1.0

    def __init__(self):
        super().__init__(
            defect_id="segmental",
            title="Partial Segmental Resection (22mm)",
            description="Hemi-diaphyseal structural resection preserving a cortical bridge."
        )

    def apply(self, ctx: AnatomicalContext, config: dict) -> np.ndarray:
        mask_segmental = ctx.mask_bool.copy()
        search_z_start = int(ctx.z_min + (ctx.z_max - ctx.z_min) * config["search_z_start_ratio"])
        search_z_end = int(ctx.z_min + (ctx.z_max - ctx.z_min) * config["search_z_end_ratio"])
        middle_areas = ctx.slice_areas[search_z_start:search_z_end]
        valid_indices = np.where(middle_areas > 0)[0]

        if len(valid_indices) > 0:
            diaphysis_center_z = search_z_start + valid_indices[np.argmin(middle_areas[valid_indices])]
        else:
            diaphysis_center_z = int(ctx.z_min + (ctx.z_max - ctx.z_min) * self.DEFAULT_DIAPHYSIS_RATIO)

        gap_half_vox = int((config["height_mm"] / 2.0) / ctx.spacing[2])
        pad_z = self.BOUNDING_BOX_PAD
        z_s1 = max(0, diaphysis_center_z - gap_half_vox - pad_z)
        z_s2 = min(ctx.mask_bool.shape[0], diaphysis_center_z + gap_half_vox + pad_z + 1)

        local_bone = ctx.main_bone_mask[z_s1:z_s2, :, :]
        local_coords = np.argwhere(local_bone)

        if len(local_coords) == 0:
            return mask_segmental

        ly_min, lx_min = local_coords[:, 1].min(), local_coords[:, 2].min()
        ly_max, lx_max = local_coords[:, 1].max(), local_coords[:, 2].max()

        by1 = max(0, ly_min - 2)
        by2 = min(ctx.mask_bool.shape[1], ly_max + 3)
        bx1 = max(0, lx_min - 2)
        bx2 = min(ctx.mask_bool.shape[2], lx_max + 3)

        sub_shape_seg = (z_s2 - z_s1, by2 - by1, bx2 - bx1)
        zz, yy, xx = np.ogrid[z_s1:z_s2, by1:by2, bx1:bx2]

        bone_span_x = max(lx_max - lx_min, 1)
        bone_span_y = max(ly_max - ly_min, 1)
        cut_center_x = lx_min + self.CUT_CENTER_OFFSET_X * bone_span_x
        cut_center_y = ly_min + self.CUT_CENTER_OFFSET_Y * bone_span_y

        rx_cut = max(config["cross_section_ratio_x"] * bone_span_x, self.MIN_CUT_RADIUS_VOXELS)
        ry_cut = max(config["cross_section_ratio_y"] * bone_span_y, self.MIN_CUT_RADIUS_VOXELS)

        z_rel = (zz - diaphysis_center_z) / max(gap_half_vox, 1)

        noise_axial = self._multi_scale_noise(sub_shape_seg, seed=config["seed"])
        noise_radial = self._multi_scale_noise(sub_shape_seg, seed=config["seed"] + 1)

        xy_dist = np.sqrt(
            ((xx - cut_center_x) / rx_cut) ** 2 +
            ((yy - cut_center_y) / ry_cut) ** 2
        )

        in_axial_bounds = (np.abs(z_rel) + config["noise_scale_axial"] * noise_axial) <= 1.0
        taper_profile = np.clip(
            self.TAPER_BASE - self.TAPER_QUADRATIC_COEFF * (z_rel ** 2),
            self.TAPER_MIN_CLIP,
            self.TAPER_MAX_CLIP
        )
        in_radial_bounds = (xy_dist + config["noise_scale_radial"] * noise_radial) <= taper_profile

        seg_cut_body = in_axial_bounds & in_radial_bounds & ctx.main_bone_mask[z_s1:z_s2, by1:by2, bx1:bx2]
        mask_segmental[z_s1:z_s2, by1:by2, bx1:bx2] &= ~seg_cut_body
        return self._clean_small_fragments(mask_segmental)


class DefectGenerator:
    """Orchestrates procedural defect generation pipelines."""

    CONFIG = {
        "cavity": {
            "radius_mm": 13.0,
            "target_z_ratio": 0.72,
            "noise_scale": 0.18,
            "seed": 101
        },
        "wedge": {
            "height_mm": 32.0,
            "depth_mm": 16.0,
            "width_mm": 18.0,
            "target_z_ratio": 0.45,
            "noise_seed_depth": 42,
            "noise_seed_margin": 43
        },
        "segmental": {
            "height_mm": 22.0,
            "cross_section_ratio_x": 0.55,
            "cross_section_ratio_y": 0.65,
            "search_z_start_ratio": 0.25,
            "search_z_end_ratio": 0.70,
            "noise_scale_axial": 0.18,
            "noise_scale_radial": 0.22,
            "seed": 304
        }
    }

    STRATEGIES = [
        SphericalCavityDefect(),
        WedgeFractureDefect(),
        PartialSegmentalResectionDefect()
    ]

    @classmethod
    def _build_anatomical_context(cls, mask: np.ndarray, spacing: tuple) -> AnatomicalContext:
        """Isolates the primary bone component and extracts geometric bounds."""
        mask_bool = mask.astype(bool)
        labeled_bones, num_features = measure.label(mask_bool, return_num=True)
        if num_features == 0:
            raise ValueError("Bone mask is empty!")

        props = measure.regionprops(labeled_bones)
        props.sort(key=lambda x: x.area, reverse=True)
        main_bone_mask = (labeled_bones == props[0].label)

        indices = np.argwhere(main_bone_mask)
        z_min, y_min, x_min = indices.min(axis=0)
        z_max, y_max, x_max = indices.max(axis=0)
        slice_areas = np.sum(main_bone_mask, axis=(1, 2))

        return AnatomicalContext(
            mask_bool=mask_bool,
            main_bone_mask=main_bone_mask,
            spacing=spacing,
            z_min=z_min, z_max=z_max,
            y_min=y_min, y_max=y_max,
            x_min=x_min, x_max=x_max,
            slice_areas=slice_areas
        )

    @classmethod
    def generate_all_defects(cls, mask: np.ndarray, spacing: tuple, output_dir: str, baseline_stl_path: str) -> list:
        """Executes full defect generation pipeline across all registered strategies."""
        os.makedirs(output_dir, exist_ok=True)
        ctx = cls._build_anatomical_context(mask, spacing)

        defects = [{
            "id": "baseline",
            "title": "Baseline (Intact Bone)",
            "description": "Original intact solid bone model without synthetic defects.",
            "file": "./output/solid_bone.stl",
            "defect_file": None,
            "mask": ctx.mask_bool
        }]

        for strategy in cls.STRATEGIES:
            cfg = cls.CONFIG.get(strategy.defect_id, {})
            damaged_mask = strategy.apply(ctx, cfg)

            stl_bone_path = os.path.join(output_dir, f"defect_{strategy.defect_id}.stl")
            stl_zone_path = os.path.join(output_dir, f"defect_{strategy.defect_id}_zone.stl")

            BaseDefect.export_pair(ctx.mask_bool, damaged_mask, spacing, stl_bone_path, stl_zone_path)

            defects.append({
                "id": strategy.defect_id,
                "title": strategy.title,
                "description": strategy.description,
                "file": f"./output/defect_{strategy.defect_id}.stl",
                "defect_file": f"./output/defect_{strategy.defect_id}_zone.stl",
                "mask": damaged_mask
            })

        return defects