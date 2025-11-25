import unittest
import os
import json
from config_manager import ConfigManager
from student_manager import StudentManager
from utils import clean_json_string, sort_csv_headers

class TestCore(unittest.TestCase):
    def test_clean_json_string(self):
        raw = "```json\n{\"key\": \"value\"}\n```"
        cleaned = clean_json_string(raw)
        self.assertEqual(cleaned, "{\"key\": \"value\"}")
        
        raw_dirty = "some text {\"key\": \"value\"} some other text"
        cleaned_dirty = clean_json_string(raw_dirty)
        self.assertEqual(cleaned_dirty, "{\"key\": \"value\"}")

    def test_config_manager(self):
        # Create a dummy config
        with open("test_config.json", "w") as f:
            json.dump({"api_key": "123"}, f)
            
        cm = ConfigManager("test_config.json")
        self.assertEqual(cm.get("api_key"), "123")
        
        cm.set("base_url", "http://test.com")
        self.assertEqual(cm.get("base_url"), "http://test.com")
        
        # Verify save
        with open("test_config.json", "r") as f:
            data = json.load(f)
            self.assertEqual(data["base_url"], "http://test.com")
            
        os.remove("test_config.json")

    def test_student_manager(self):
        # Create a dummy CSV
        with open("test_students.csv", "w", encoding="utf-8-sig") as f:
            f.write("姓名,考号,班级,考场,座号\n")
            f.write("张三,1001,1,01,01\n")
            
        sm = StudentManager()
        count = sm.load_from_file("test_students.csv")
        self.assertEqual(count, 1)
        
        student, is_absent = sm.get_student_by_filename("01-01.jpg")
        self.assertEqual(student['name'], "张三")
        self.assertFalse(is_absent)
        
        student, is_absent = sm.get_student_by_filename("01-01缺.jpg")
        self.assertEqual(student['name'], "张三")
        self.assertTrue(is_absent)
        
        os.remove("test_students.csv")
        
    def test_csv_header_order(self):
        # Test input with mixed order and unknown fields
        headers = [
            'OCR姓名', '17', '总分', '姓名', '复审状态', 
            '信息一致性', '考场', '18', '确认缺考'
        ]
        
        sorted_headers = sort_csv_headers(headers)
        
        # Expected order:
        # 1. Basic: 考场, 姓名
        # 2. Status: 复审状态, 确认缺考
        # 3. Scores: 总分
        # 4. Questions: 17, 18
        # 5. Details: 信息一致性
        # 6. OCR: OCR姓名
        
        expected = [
            '考场', '姓名', 
            '复审状态', '确认缺考', 
            '总分', 
            '17', '18', 
            '信息一致性', 
            'OCR姓名'
        ]
        
        self.assertEqual(sorted_headers, expected)

if __name__ == '__main__':
    unittest.main()
