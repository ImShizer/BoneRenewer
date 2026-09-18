import os
import webview
import shutil
from converter import DicomConverter
import sys

# Compilation fix for PyInstaller
if hasattr(sys, '_MEIPASS'):
    os.chdir(sys._MEIPASS)

def get_user_dir():
    if hasattr(sys, 'frozen'):
        return os.path.dirname(sys.executable)
    return os.getcwd()

#######

class Api:
    """Connect JS and Python"""
    
    def ask_folder_path(self):
        """Opens the native folder selection dialog"""
        result = webview.windows[0].create_file_dialog(
            webview.FOLDER_DIALOG, 
            directory=get_user_dir()
        )
        if result and len(result) > 0:
            return result[0]
        return None

    def scan_folder(self, dicom_folder):
        """Get the list of DICOM series by folder"""
        try:
            return DicomConverter.scan_series(dicom_folder)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def run_conversion(self, dicom_folder, series_id,hu_val):
        """Conversion algorithm"""
        try:
            output_dir = os.path.join('web', 'output')
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, 'solid_bone.stl')
            
            converter = DicomConverter(
                dicom_dir=dicom_folder,
                output_path=output_file,
                series_id=series_id,
                hu_threshold=float(hu_val),
                step_size=1
            )
            converter.convert()
            
            # Return the path to JS
            return {"status": "success", "file": "./output/solid_bone.stl"}
        except Exception as e:
            print(f"Error: {e}")
            return {"status": "error", "message": str(e)}

    def export_stl(self):
        result = webview.windows[0].create_file_dialog(
            webview.SAVE_DIALOG, 
            directory=get_user_dir(),
            save_filename='solid_bone.stl',
            file_types=('STL Files (*.stl)', 'All Files (*.*)')
        )
        
        if result and len(result) > 0:
            dest_path = result if isinstance(result, str) else result[0]
            src_path = os.path.join('web', 'output', 'solid_bone.stl')
            
            try:
                shutil.copy(src_path, dest_path)
                return {"status": "success", "path": dest_path}
            except Exception as e:
                return {"status": "error", "message": str(e)}
                
        return {"status": "cancelled"}

if __name__ == '__main__':
    api = Api()
    
    webview.create_window(
        title='DICOM to STL Converter', 
        url='web/index.html', 
        js_api=api,
        width=1200, 
        height=800,
        min_size=(1000, 600),
        background_color='#ffffff',
        maximized=True
    )
    
    webview.start()