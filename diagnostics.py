import os
import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler
from converter import NiftiHandler


class ProstheticRecommender:
    """Високоточний ML-модуль оцінки анатомічного дефекту та підбору ендопротезів."""

    def __init__(self):
        # Повний каталог модульних ендопротезів під усі типи суглобів та розмірні ряди
        self.catalog = [
            {
                "id": "distal_knee_xl",
                "type": "distal",
                "name": "Ревізійний колінний ендопротез (Distal Knee XL)",
                "features": [0.85, 188.0, 59.0],  # [Defect Ratio, Length mm, Diameter mm]
                "description": "Модульний ревізійний протез колінного суглоба з мищелковим блоком та інтрамедулярним штифтом.",
                "reasoning": "Виявлено масивний дефект у ділянці колінного суглоба (>180 мм). Забезпечує відновлення суглобової поверхні та надійну всерединіканальну фіксацію."
            },
            {
                "id": "proximal_femur_xl",
                "type": "proximal",
                "name": "Ревізійний проксимальний ендопротез стегна (Розмір XL)",
                "features": [0.85, 190.0, 58.0],
                "description": "Подовжений модульний протез для масивних сегментарних дефектів проксимального відділу стегна.",
                "reasoning": "Обрано через критичну довжину дефекту проксимальної ділянки (>180 мм) та діаметр кістки."
            },
            {
                "id": "proximal_femur_m",
                "type": "proximal",
                "name": "Проксимальний ендопротез стегна (Розмір M)",
                "features": [0.85, 120.0, 42.0],
                "description": "Модульний ендопротез для помірних дефектів проксимального відділу стегнової кістки.",
                "reasoning": "Показаний при стандартних дефектах проксимальної зони (довжина ~120 мм)."
            },
            {
                "id": "distal_knee_m",
                "type": "distal",
                "name": "Дистальний ревізійний протез коліна (Розмір M)",
                "features": [0.45, 95.0, 40.0],
                "description": "Анатомічний блочний імплант для заміщення колінного суглоба середнього розміру.",
                "reasoning": "Локалізація дефекту в дистальному метаепіфізі середнього розміру."
            },
            {
                "id": "diaphyseal_sleeve",
                "type": "diaphyseal",
                "name": "Діафізарна титанова муфта (Sleeve XL)",
                "features": [0.25, 160.0, 32.0],
                "description": "Пориста остеоінтегрована муфта для перекриття сегментарних діафізарних дефектів.",
                "reasoning": "Виявлено сегментарний діафізарний дефект без ураження суглобових поверхонь."
            }
        ]

        # 1. Матриця ознак
        X = np.array([item["features"] for item in self.catalog])

        # 2. Нормалізація ознак (StandardScaler)
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # 3. k-NN модель
        self.model = NearestNeighbors(n_neighbors=1, metric='euclidean')
        self.model.fit(X_scaled)

    def extract_features(self, solid_mask: np.ndarray, spacing: tuple) -> list:
        """Витягує геометричні параметри дефекту з маски кістки."""
        voxel_vol = spacing[0] * spacing[1] * spacing[2]
        total_vol = solid_mask.sum() * voxel_vol

        z_indices = np.where(solid_mask.any(axis=(1, 2)))[0]
        if len(z_indices) == 0:
            return [0.0, 0.0, 0.0]

        length_mm = (z_indices[-1] - z_indices[0]) * spacing[2]
        area_per_slice = solid_mask.sum(axis=(1, 2)) * (spacing[0] * spacing[1])
        valid_areas = area_per_slice[area_per_slice > 0]
        mean_area = np.mean(valid_areas) if len(valid_areas) > 0 else 1e-5
        eq_diameter_mm = 2 * np.sqrt(mean_area / np.pi)

        bbox_volume = length_mm * mean_area
        defect_ratio = float(total_vol / bbox_volume) if bbox_volume > 0 else 0.5

        return [round(defect_ratio, 2), round(length_mm, 1), round(eq_diameter_mm, 1)]

    def predict(self, solid_mask: np.ndarray, spacing: tuple) -> dict:
        """Підбирає протез та розраховує нормалізовану точність совпадіння."""
        features = self.extract_features(solid_mask, spacing)

        # Масштабуємо отримані фічі
        features_scaled = self.scaler.transform([features])
        distances, indices = self.model.kneighbors(features_scaled)

        match = self.catalog[indices[0][0]]
        dist = float(distances[0][0])

        # Розрахунок точності (Гауссове затухання)
        confidence = float(np.exp(-0.15 * (dist ** 2)))

        return {
            "id": match["id"],
            "type": match["type"],
            "name": match["name"],
            "description": match["description"],
            "reasoning": match["reasoning"],
            "confidence": round(confidence, 2),
            "features": features
        }


class DiagnosticEngine:
    """Інтерфейс для запуску ML-діагностики з main.py."""

    def __init__(self):
        self.recommender = ProstheticRecommender()

    def run_diagnostics(self, cached_stl_path: str, cached_nii_path: str, last_mask=None, last_spacing=None):
        if last_mask is None or last_spacing is None:
            if os.path.exists(cached_nii_path):
                last_mask, last_spacing, _ = NiftiHandler.load(cached_nii_path)
            else:
                return {
                    "status": "error",
                    "message": "Спочатку завантажте та обробіть файл (DICOM/NIfTI)."
                }

        rec = self.recommender.predict(last_mask, last_spacing)
        return {"status": "success", "recommendation": rec}