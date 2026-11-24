# BoneRenewer

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![SimpleITK](https://img.shields.io/badge/SimpleITK-2.5%2B-blue)](https://simpleitk.org/)
[![scikit-learn](https://img.shields.io/badge/scikit--learn-1.0%2B-F7931E?logo=scikit-learn&logoColor=white)](https://scikit-learn.org/)
[![pywebview](https://img.shields.io/badge/pywebview-6.2%2B-2E8B57)](https://pywebview.flowrl.com/)
[![Three.js](https://img.shields.io/badge/Three.js-r160-black?logo=three.js&logoColor=white)](https://threejs.org/)
[![WebGL](https://img.shields.io/badge/WebGL-2.0-990000?logo=webgl&logoColor=white)](https://www.khronos.org/webgl/)

**BoneRenewer** – спеціалізований десктопний комплекс для локальної 3D-реконструкції кісткових структур за даними комп'ютерної томографії (КТ), процедурного моделювання ушкоджень та автоматизованого передопераційного підбору ендопротезів. Застосунок поєднує інструменти воксельної сегментації томографічних об'ємів, алгоритми процедурної генерації дефектів з еталонними масками кісткової втрати та метричну класифікацію для рекомендації модульних імплантатів. Усі обчислення та візуалізація виконуються повністю локально на робочій станції без передавання медичних даних у зовнішні мережі.

---

## Основний функціонал

- **Імпорт КТ-досліджень:** завантаження серій DICOM з автоматичним виявленням об'ємних серій, фільтрацією поодиноких зрізів та орієнтацією за анатомічним стандартом LPS, 
а також прямий імпорт файлів NIfTI (`.nii` та `.nii.gz`).
- **Двоетапна адаптивна сегментація:** порогове виділення кортикального ядра кістки за шкалою Хаунсфілда (HU) з відсіканням дрібних шумів, 
покісткове відновлення губчастої речовини через просторове розширення та заповнення внутрішніх порожнин із захистом суглобових щілин від випадкового злиття.
- **Процедурна генерація дефектів кістки:** моделювання 3 клінічних типів синтетичних ушкоджень кісткової тканини:
  - *Spherical Cavity (Cyst/Resection)* – сферична кавітарна порожнина кортикальної та губчастої зони;
  - *Wedge Cortical Fracture* – крайовий клиноподібний дефект діафіза зі стохастичною лінією зламу;
  - *Partial Segmental Resection (22mm)* – часткова гемісегментарна резекція зі збереженням опорного кортикального містка.
  Усі типи дефектів модулюються багатомасштабним 3D-шумом Гаусса для імітації природного трабекулярного рельєфу та нерівностей перелому.
- **Візуалізація еталонної маски (Red Zone):** автоматичний розрахунок і просторове накладання напівпрозорої 3D-моделі видаленого фрагмента (Ground Truth) для наочної оцінки дефіциту кістки.
- **Автоматизований підбір ендопротезів:** морфометричний аналіз воксельної маски (визначення довжини дефекту, еквівалентного діаметра кістки та коефіцієнта заповнення) 
із вибором оптимального ревізійного або модульного імплантату з каталогу (ревізійні колінні системи, проксимальні стегнові протези, діафізарні титанові муфти) за алгоритмом $k$-найближчих сусідів ($k$-NN) 
зі стандартизацією ознак та оцінкою достовірності.
- **Інтерактивна 3D-візуалізація та експорт:** рендеринг у Three.js на базі WebGL, напівавтоматичне переведення кістки в прозорий режим при позиціонуванні протеза, 
вбудований 3D-маніпулятор (TransformControls) для просторової корекції імплантату та експорт результатів у полігональні сітки `.stl` і томографічні маски `.nii.gz`.

---

## Стек технологій та структура проєкту

### Стек технологій

| Компонент | Технології та бібліотеки |
| :--- | :--- |
| **Мова програмування** | Python 3.10+ |
| **Обробка медичних даних** | SimpleITK, NumPy, SciPy, scikit-image, trimesh |
| **Машинне навчання / ML** | scikit-learn (NearestNeighbors, StandardScaler) |
| **Десктопний контейнер** | pywebview |
| **Графічний інтерфейс та 3D** | HTML5, CSS3, JavaScript (ES6+), Three.js (r160), WebGL |
| **Збірка виконуваного файлу** | PyInstaller |

### Структура репозиторію

```text
BoneRenewer/
├── assets/
│   └── icon.ico
├── web/
│   ├── index.html
│   ├── styles.css
│   ├── app.js
│   ├── scene.js
│   ├── defects.js
│   ├── prosthetics.js
│   ├── output/
│   └── vendor/fonts/
├── converter.py
├── defect_generator.py
├── diagnostics.py
├── main.py
├── main.spec
├── requirements.txt
└── README.md
```

---

## Встановлення та запуск із вихідного коду

### Системні вимоги

- **Операційна система:** Windows 10/11 (x64) або Ubuntu Linux 20.04+ (x64)
- **Інтерпретатор Python:** версія 3.10 – 3.13
- **Відеоадаптер:** з підтримкою WebGL 2.0 та актуальними графічними драйверами
- **Оперативна пам'ять:** не менше 8 ГБ (рекомендовано 16 ГБ для комфортної обробки КТ високої роздільної здатності)

### Покрокова інструкція

1. **Клонування репозиторію:**
   ```bash
   git clone https://github.com:ImShizer/BoneRenewer.git
   cd BoneRenewer
   ```

2. **Створення та активація віртуального середовища (`venv`):**
   - Windows (PowerShell):
     ```powershell
     python -m venv .venv
     .\.venv\Scripts\Activate.ps1
     ```
   - Windows (Command Prompt):
     ```cmd
     python -m venv .venv
     .\.venv\Scripts\activate.bat
     ```
   - Linux / macOS:
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```

3. **Встановлення залежностей:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

4. **Запуск застосунку:**
   ```bash
   python main.py
   ```

---

## Збірка та компіляція (Build)

Пакування проєкту в автономний виконуваний файл здійснюється за допомогою **PyInstaller**.

### Компіляція за наявним конфігураційним файлом `main.spec` (рекомендовано)

У репозиторії наявна готова конфігурація `main.spec`, яка автоматично включає каталог `web/` у виконуваний файл, вимикає консольне вікно та виключає невикористовувані сторонні бібліотеки (`matplotlib`, `pandas`, `PyQt5`, `PySide6`):

```bash
pip install pyinstaller
pyinstaller main.spec
```

Після завершення збірки готовий бінарний файл буде збережено у папці `dist/`:
- Windows: `dist/main.exe`
- Linux: `dist/main`

### Компіляція прямою командою CLI PyInstaller

За потреби ручного перепакування або зміни параметрів можна використати пряму команду термінала з обов'язковим прокиданням директорії фронтенду через прапорець `--add-data`:

**Windows:**
  ```powershell
  pyinstaller --noconsole --name "BoneRenewer" --icon="assets/icon.ico" --add-data "web;web" --exclude-module matplotlib --exclude-module tkinter --exclude-module pandas --exclude-module PyQt5 --exclude-module PySide6 main.py
  ```

**Linux:**
  ```bash
  pyinstaller --noconsole --name "BoneRenewer" --add-data "web:web" --exclude-module matplotlib --exclude-module tkinter --exclude-module pandas --exclude-module PyQt5 --exclude-module PySide6 main.py
  ```
