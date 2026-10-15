import os
import numpy as np
import scipy.ndimage as ndi
from skimage import measure
from converter import STLExporter


class DefectGenerator:
    """Procedural generation of realistic bone lesions and ground-truth defect volumes."""

    # Centralized configuration dictionary for all defect parameters
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
            "noise_scale_radial": 0.22, # Added radial noise to prevent flat 'popsicle' cuts
            "seed": 304
        }
    }

    @staticmethod
    def _multi_scale_noise(shape: tuple, seed: int = 42) -> np.ndarray:
        """
        Generates multi-scale 3D Gaussian noise normalized to [-1, 1],
        combining coarse fracture waves and fine trabecular roughness.
        """
        rng = np.random.default_rng(seed)
        coarse = ndi.gaussian_filter(rng.normal(0.0, 1.0, size=shape), sigma=2.2)
        coarse /= (np.max(np.abs(coarse)) + 1e-8)

        fine = ndi.gaussian_filter(rng.normal(0.0, 1.0, size=shape), sigma=0.85)
        fine /= (np.max(np.abs(fine)) + 1e-8)

        combined = 0.65 * coarse + 0.35 * fine
        return combined / (np.max(np.abs(combined)) + 1e-8)

    @staticmethod
    def _clean_small_fragments(mask: np.ndarray, min_voxels: int = 60) -> np.ndarray:
        """
        Removes tiny disconnected voxel islands ('floating dust')
        caused by stochastic boundary erosion.
        """
        labeled, num = measure.label(mask, return_num=True)
        if num <= 1:
            return mask
        counts = np.bincount(labeled.ravel())
        counts[0] = 0  # Ignore background label
        keep = counts >= min_voxels
        return keep[labeled]

    @staticmethod
    def _export_pair(mask_intact: np.ndarray, mask_damaged: np.ndarray, spacing: tuple,
                     stl_bone_path: str, stl_zone_path: str):
        """Exports both the damaged bone mesh and the excised ground-truth defect mesh."""
        # 1. Export damaged bone model
        verts, faces, normals = STLExporter.generate_mesh(mask_damaged, spacing)
        STLExporter.export(verts, faces, normals, stl_bone_path)

        # 2. Compute and export the excised volume (Ground Truth Defect Zone)
        excised_mask = mask_intact & (~mask_damaged)
        excised_mask = DefectGenerator._clean_small_fragments(excised_mask, min_voxels=25)

        if np.any(excised_mask):
            v_z, f_z, n_z = STLExporter.generate_mesh(excised_mask, spacing)
            STLExporter.export(v_z, f_z, n_z, stl_zone_path)

    @classmethod
    def generate_all_defects(cls, mask: np.ndarray, spacing: tuple, output_dir: str, baseline_stl_path: str):
        os.makedirs(output_dir, exist_ok=True)
        mask_bool = mask.astype(bool)

        # 1. Isolate the primary bone component for anatomical reference
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

        # Position 0: Original intact bone baseline
        defects = [{
            "id": "baseline",
            "title": "Baseline (Intact Bone)",
            "description": "Original intact solid bone model without synthetic defects.",
            "file": "./output/solid_bone.stl",
            "defect_file": None,
            "mask": mask_bool
        }]

        # =========================================================================
        # 1. Spherical Cavity (Subchondral Cyst / Tumor Resection Bed)
        # =========================================================================
        cfg_cavity = cls.CONFIG["cavity"]
        mask_cavity = mask_bool.copy()
        target_z = int(z_min + (z_max - z_min) * cfg_cavity["target_z_ratio"])
        target_z = np.clip(target_z, z_min, z_max)

        y_profile = np.where(main_bone_mask[target_z, :, :])
        if len(y_profile[0]) > 0:
            y_front = y_profile[0].max()
            x_front = int(np.mean(y_profile[1][y_profile[0] == y_front]))

            r_mm = cfg_cavity["radius_mm"]
            rz = int(r_mm / spacing[2])
            ry = int(r_mm / spacing[1])
            rx = int(r_mm / spacing[0])

            pad = 4
            cz, cy, cx = target_z, int(y_front - ry * 0.4), x_front
            z1, z2 = max(0, cz - rz - pad), min(mask.shape[0], cz + rz + pad + 1)
            y1, y2 = max(0, cy - ry - pad), min(mask.shape[1], cy + ry + pad + 1)
            x1, x2 = max(0, cx - rx - pad), min(mask.shape[2], cx + rx + pad + 1)

            zz, yy, xx = np.ogrid[z1:z2, y1:y2, x1:x2]
            sphere_dist = np.sqrt(
                ((zz - cz) / max(rz, 1))**2 +
                ((yy - cy) / max(ry, 1))**2 +
                ((xx - cx) / max(rx, 1))**2
            )

            noise_cav = cls._multi_scale_noise((z2 - z1, y2 - y1, x2 - x1), seed=cfg_cavity["seed"])
            cavity_body = (sphere_dist + cfg_cavity["noise_scale"] * noise_cav) <= 1.0

            mask_cavity[z1:z2, y1:y2, x1:x2] &= ~cavity_body
            mask_cavity = cls._clean_small_fragments(mask_cavity, min_voxels=60)

        stl_cavity = os.path.join(output_dir, 'defect_cavity.stl')
        stl_cavity_zone = os.path.join(output_dir, 'defect_cavity_zone.stl')
        cls._export_pair(mask_bool, mask_cavity, spacing, stl_cavity, stl_cavity_zone)

        defects.append({
            "id": "cavity",
            "title": "Spherical Cavity (Cyst/Resection)",
            "description": "Subchondral cortical cavity with irregular trabecular margins.",
            "file": "./output/defect_cavity.stl",
            "defect_file": "./output/defect_cavity_zone.stl",
            "mask": mask_cavity
        })

        # =========================================================================
        # 2. Wedge Fracture (Blast Injury / Cortical Spall)
        # =========================================================================
        cfg_wedge = cls.CONFIG["wedge"]
        mask_wedge = mask_bool.copy()
        wedge_z = int(z_min + (z_max - z_min) * cfg_wedge["target_z_ratio"])
        wedge_hz = int((cfg_wedge["height_mm"] / 2.0) / spacing[2])

        x_profile = np.where(main_bone_mask[wedge_z, :, :])
        if len(x_profile[1]) > 0:
            x_edge = x_profile[1].max()
            y_edge = int(np.mean(x_profile[0][x_profile[1] == x_edge]))

            cut_depth_vox = int(cfg_wedge["depth_mm"] / spacing[0])
            width_y_vox = int(cfg_wedge["width_mm"] / spacing[1])

            pad = 4
            z1 = max(0, wedge_z - wedge_hz - pad)
            z2 = min(mask.shape[0], wedge_z + wedge_hz + pad + 1)
            x1 = max(0, x_edge - cut_depth_vox - pad)
            x2 = min(mask.shape[2], x_edge + 1)
            y1 = max(0, y_edge - width_y_vox - pad)
            y2 = min(mask.shape[1], y_edge + width_y_vox + pad + 1)

            sub_shape = (z2 - z1, y2 - y1, x2 - x1)
            zz, yy, xx = np.ogrid[z1:z2, y1:y2, x1:x2]

            noise_depth = cls._multi_scale_noise(sub_shape, seed=cfg_wedge["noise_seed_depth"])
            noise_margin = cls._multi_scale_noise(sub_shape, seed=cfg_wedge["noise_seed_margin"])

            z_norm = (np.abs(zz - wedge_z) / max(wedge_hz, 1)) + 0.15 * noise_margin
            z_factor = np.clip(1.0 - z_norm, 0.0, 1.0)

            fracture_depth = cut_depth_vox * (z_factor + 0.22 * noise_depth)
            wedge_dist_x = (x_edge - xx)
            wedge_dist_y = (np.abs(yy - y_edge) / max(width_y_vox, 1)) + 0.16 * noise_margin

            wedge_body = (wedge_dist_x <= fracture_depth) & \
                         (wedge_dist_y <= z_factor) & \
                         (z_factor > 0.03)

            mask_wedge[z1:z2, y1:y2, x1:x2] &= ~wedge_body
            mask_wedge = cls._clean_small_fragments(mask_wedge, min_voxels=60)

        stl_wedge = os.path.join(output_dir, 'defect_wedge.stl')
        stl_wedge_zone = os.path.join(output_dir, 'defect_wedge_zone.stl')
        cls._export_pair(mask_bool, mask_wedge, spacing, stl_wedge, stl_wedge_zone)

        defects.append({
            "id": "wedge",
            "title": "Wedge Cortical Fracture",
            "description": "Diaphyseal cortical wedge deficit with stochastic fracture margins.",
            "file": "./output/defect_wedge.stl",
            "defect_file": "./output/defect_wedge_zone.stl",
            "mask": mask_wedge
        })

        # =========================================================================
        # 3. Partial Hemi-Diaphyseal Resection (22 mm Lateral-Cortical Defect)
        # =========================================================================
        cfg_seg = cls.CONFIG["segmental"]
        mask_segmental = mask_bool.copy()
        search_z_start = int(z_min + (z_max - z_min) * cfg_seg["search_z_start_ratio"])
        search_z_end = int(z_min + (z_max - z_min) * cfg_seg["search_z_end_ratio"])
        middle_areas = slice_areas[search_z_start:search_z_end]
        valid_indices = np.where(middle_areas > 0)[0]

        if len(valid_indices) > 0:
            diaphysis_center_z = search_z_start + valid_indices[np.argmin(middle_areas[valid_indices])]
        else:
            diaphysis_center_z = int(z_min + (z_max - z_min) * 0.45)

        gap_half_vox = int((cfg_seg["height_mm"] / 2.0) / spacing[2])
        pad_z = 4
        z_s1 = max(0, diaphysis_center_z - gap_half_vox - pad_z)
        z_s2 = min(mask.shape[0], diaphysis_center_z + gap_half_vox + pad_z + 1)

        local_bone = main_bone_mask[z_s1:z_s2, :, :]
        local_coords = np.argwhere(local_bone)

        if len(local_coords) > 0:
            ly_min, lx_min = local_coords[:, 1].min(), local_coords[:, 2].min()
            ly_max, lx_max = local_coords[:, 1].max(), local_coords[:, 2].max()

            by1 = max(0, ly_min - 2)
            by2 = min(mask.shape[1], ly_max + 3)
            bx1 = max(0, lx_min - 2)
            bx2 = min(mask.shape[2], lx_max + 3)

            sub_shape_seg = (z_s2 - z_s1, by2 - by1, bx2 - bx1)
            zz, yy, xx = np.ogrid[z_s1:z_s2, by1:by2, bx1:bx2]

            bone_span_x = max(lx_max - lx_min, 1)
            bone_span_y = max(ly_max - ly_min, 1)
            cut_center_x = lx_min + 0.15 * bone_span_x
            cut_center_y = ly_min + 0.35 * bone_span_y

            rx_cut = max(cfg_seg["cross_section_ratio_x"] * bone_span_x, 4.0)
            ry_cut = max(cfg_seg["cross_section_ratio_y"] * bone_span_y, 4.0)

            z_rel = (zz - diaphysis_center_z) / max(gap_half_vox, 1)
            
            # Generate multi-scale noise fields for both axial and radial boundaries
            noise_axial = cls._multi_scale_noise(sub_shape_seg, seed=cfg_seg["seed"])
            noise_radial = cls._multi_scale_noise(sub_shape_seg, seed=cfg_seg["seed"] + 1)

            xy_dist = np.sqrt(
                ((xx - cut_center_x) / rx_cut)**2 +
                ((yy - cut_center_y) / ry_cut)**2
            )

            # Apply stochastic perturbation to radial distance to eliminate flat 'popsicle' cuts
            in_axial_bounds = (np.abs(z_rel) + cfg_seg["noise_scale_axial"] * noise_axial) <= 1.0
            taper_profile = np.clip(1.15 - 0.35 * (z_rel**2), 0.5, 1.0)
            in_radial_bounds = (xy_dist + cfg_seg["noise_scale_radial"] * noise_radial) <= taper_profile

            seg_cut_body = in_axial_bounds & in_radial_bounds & main_bone_mask[z_s1:z_s2, by1:by2, bx1:bx2]
            mask_segmental[z_s1:z_s2, by1:by2, bx1:bx2] &= ~seg_cut_body
            mask_segmental = cls._clean_small_fragments(mask_segmental, min_voxels=60)

        stl_segmental = os.path.join(output_dir, 'defect_segmental.stl')
        stl_segmental_zone = os.path.join(output_dir, 'defect_segmental_zone.stl')
        cls._export_pair(mask_bool, mask_segmental, spacing, stl_segmental, stl_segmental_zone)

        defects.append({
            "id": "segmental",
            "title": "Partial Segmental Resection (22mm)",
            "description": "Hemi-diaphyseal structural resection preserving a cortical bridge.",
            "file": "./output/defect_segmental.stl",
            "defect_file": "./output/defect_segmental_zone.stl",
            "mask": mask_segmental
        })

        return defects