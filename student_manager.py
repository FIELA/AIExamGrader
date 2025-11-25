import os
import csv
try:
    import openpyxl
except ImportError:
    openpyxl = None
from typing import List, Dict, Optional, Tuple

class StudentManager:
    def __init__(self):
        self.students: List[Dict[str, str]] = []
        self.student_path: str = ""

    def load_from_file(self, path: str) -> int:
        """
        Load students from an Excel or CSV file.
        Returns the number of students loaded.
        """
        self.students = []
        self.student_path = path
        rows = []
        
        try:
            if path.endswith('.csv'):
                with open(path, 'r', encoding='utf-8-sig') as f:
                    reader = csv.reader(f)
                    rows = list(reader)
            else:
                if openpyxl is None:
                    raise ImportError("openpyxl is not installed. Please install it to read Excel files.")
                wb = openpyxl.load_workbook(path, data_only=True)
                ws = wb.active
                for row in ws.iter_rows(values_only=True):
                    rows.append(list(row))
            
            if not rows:
                return 0

            header = [str(h).strip() for h in rows[0]]
            idx_map = {}
            for i, col_name in enumerate(header):
                if "考号" in col_name or "学号" in col_name or "准考证号" in col_name: idx_map['id'] = i
                elif "姓名" in col_name: idx_map['name'] = i
                elif "班级" in col_name: idx_map['class'] = i
                elif "考场" in col_name: idx_map['room'] = i
                elif "座号" in col_name or "座位" in col_name: idx_map['seat'] = i

            for row in rows[1:]:
                s = {'id': '', 'name': '', 'class': '', 'room': '', 'seat': ''}
                if 'id' in idx_map: s['id'] = str(row[idx_map['id']]).strip()
                if 'name' in idx_map: s['name'] = str(row[idx_map['name']]).strip()
                if 'class' in idx_map: s['class'] = str(row[idx_map['class']]).strip()
                if 'room' in idx_map: s['room'] = str(row[idx_map['room']]).strip()
                if 'seat' in idx_map: s['seat'] = str(row[idx_map['seat']]).strip()
                
                if s['room'] and s['room'].isdigit(): s['room'] = s['room'].zfill(2)
                
                self.students.append(s)
                
            return len(self.students)
        except Exception as e:
            raise Exception(f"Failed to parse student file: {str(e)}")

    def get_student_by_filename(self, filename: str) -> Tuple[Dict[str, str], bool]:
        """
        Parse filename and find student.
        Returns (student_dict, is_absent)
        """
        name_part = os.path.splitext(filename)[0]
        is_absent = "缺" in name_part
        clean_name = name_part.replace("缺", "")
        
        room_no = ""
        seat_no = ""
        
        if "-" in clean_name:
            parts = clean_name.split("-")
            if len(parts) >= 2:
                room_no = parts[0].strip()
                seat_no = parts[1].strip()
        
        found_student = None
        if self.students and room_no and seat_no:
            room_variants = [room_no, room_no.zfill(2)]
            seat_variants = [seat_no, seat_no.zfill(2)]
            
            for s in self.students:
                if str(s['room']) in room_variants and str(s['seat']) in seat_variants:
                    found_student = s
                    break
        
        if not found_student:
            found_student = {
                'id': '未知', 'name': '未知', 'class': '未知',
                'room': room_no, 'seat': seat_no
            }
            
        return found_student, is_absent
