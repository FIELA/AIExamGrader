import base64
import json
import time
from typing import List, Dict, Any, Optional
from PIL import Image
import google.generativeai as genai
from openai import OpenAI
from utils import clean_json_string

class AIGraderEngine:
    def __init__(self, provider, api_key, base_url=None, model_name=None):
        self.api_key = api_key
        self.base_url = base_url.strip() if base_url else None
        
        if self.base_url:
            if self.base_url.startswith("http://") and "localhost" not in self.base_url and "127.0.0.1" not in self.base_url:
                self.base_url = self.base_url.replace("http://", "https://", 1)
            self.base_url = self.base_url.rstrip('/')
            if "chat/completions" not in self.base_url:
                if not self.base_url.endswith("/v1") and "googleapis.com" not in self.base_url:
                    self.base_url += "/v1"

        if provider == "Gemini" and self.base_url:
            self.provider = "OpenAI"
        else:
            self.provider = provider

        if not model_name or model_name.strip() == "":
            self.model_name = "gemini-2.5-pro-maxthinking" 
        else:
            self.model_name = model_name.strip()

        if self.provider == "OpenAI":
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        elif self.provider == "Gemini":
            genai.configure(api_key=self.api_key)
            self.gemini_model = genai.GenerativeModel(self.model_name)

    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
            
    def get_available_models(self):
        model_list = []
        try:
            if self.provider == "OpenAI":
                models = self.client.models.list()
                model_list = [m.id for m in models.data]
                model_list.sort()
                priority = [m for m in model_list if any(x in m for x in ["gemini", "gpt", "claude", "qwen", "deepseek"])]
                other = [m for m in model_list if m not in priority]
                model_list = priority + other
            elif self.provider == "Gemini":
                for m in genai.list_models():
                    if 'generateContent' in m.supported_generation_methods:
                        name = m.name.replace('models/', '')
                        model_list.append(name)
                model_list.sort(reverse=True)
            return model_list
        except Exception as e:
            raise Exception(str(e))

    def grade_exam(self, rubric_text, image_path, layout_description=None):
        # --- Prompt 针对特定版式优化 ---
        default_layout = """
        ### ⚠️ 答题卡布局说明 (务必遵守)
        该答题卡分为 **左栏** 和 **右栏**：
        
        **1. 基本信息区 (左栏顶部)**
           - 左侧：考生手写信息（班级、姓名、学校、考场、座号）。
           - 右侧：准考证号区域（8位数字，上方手写，下方填涂）。
           - **任务**：请OCR识别手写的姓名、班级、考场、座号，以及手写和填涂的考号。
        
        **2. 客观题/选择题区域 (左栏中部)**
           - 位置：在“注意事项”栏目的**右侧空白区域**。
           - 形式：**纯手写**，无填涂框。
           - 格式：可能是 "1.A 2.B" 或 "1-5 ABCDA" 等。
           - **任务**：识别手写字母，按题号评分。
        
        **3. 主观题区域**
           - **第17题**：位于**左栏下方**。
           - **第18题**：位于**右栏上方**。
           - **第19题**：位于**右栏下方**。
           - **任务**：识别手写文字，严格按照评分细则打分，给出每个**小题**（如17(1), 17(2)）的得分。
        """
        
        # Use custom layout if provided
        layout_section = layout_description if layout_description else default_layout

        system_prompt = f"""
        你是一个专业的阅卷助手。请根据【评分细则】批改【答题卡图片】。
        
        {layout_section}

        ### 输出要求
        请输出严格的 JSON 格式，不要包含 Markdown 标记。
        必须包含字段：
        - `ocr_name`: 识别到的手写姓名
        - `ocr_class`: 识别到的手写班级
        - `ocr_room`: 识别到的手写考场号
        - `ocr_seat`: 识别到的手写座号
        - `ocr_id_written`: 识别到的手写考号
        - `ocr_id_filled`: 识别到的填涂考号
        - `details`: 题目详情列表
        - `total_score`: 总分
        
        对于**主观题**，`details` 中必须包含：
        - `scoring_points`: 字符串，列出得分点 (例如: "提到洋流交汇(+2)")
        - `error_analysis`: 字符串，分析失分原因 (例如: "未提到地形影响")
        
        JSON 结构示例：
        {{
            "ocr_name": "刘鑫", 
            "ocr_class": "701",
            "ocr_room": "01",
            "ocr_seat": "05",
            "ocr_id_written": "23090828",
            "ocr_id_filled": "23090828",
            "details": [ 
                {{"question_id": "1", "type": "客观题", "student_answer": "A", "standard_answer": "B", "score": 0, "max_score": 2}},
                {{
                    "question_id": "17(1)", 
                    "type": "主观题", 
                    "student_text": "...", 
                    "score": 2, 
                    "max_score": 3,
                    "scoring_points": "提到寒暖流交汇得2分",
                    "error_analysis": "未提到饵料丰富，扣1分"
                }}
            ], 
            "total_score": 85
        }}
        """
        user_prompt = f"评分细则如下：\n{rubric_text}\n\n请批改这张答题卡。注意左右分栏布局。"

        try:
            if self.provider == "OpenAI":
                base64_image = self.encode_image(image_path)
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": [
                            {"type": "text", "text": user_prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]}
                    ]
                )
                raw_content = response.choices[0].message.content
                return json.loads(clean_json_string(raw_content))

            elif self.provider == "Gemini":
                img_obj = Image.open(image_path)
                full_prompt = system_prompt + "\n" + user_prompt
                response = self.gemini_model.generate_content([full_prompt, img_obj])
                return json.loads(clean_json_string(response.text))
                
        except Exception as e:
            return {"error": str(e)}

    def detect_regions(self, image_path):
        """
        Detects the layout of the answer sheet.
        Returns a description string.
        """
        prompt = """
    请仔细分析这张答题卡图片的布局，并生成一段详细的【布局说明】。
    请重点关注以下区域的位置（左栏/右栏/顶部/中部/底部）和特征：
    1. **基本信息区**：学生填写姓名、班级、考号的位置。考号是手写还是填涂？
    2. **客观题/选择题区域**（请务必完整描述）：
       - **情况一**：如果答题卡设置了标准的机读填涂区（提供A/B/C/D选项的填涂点），请指出其具体位置。
       - **情况二**：如果答题卡未设置标准的机读填涂区，学生需手写答案，请在输出中明确说明：
         * 手写区域的具体位置（如：位于注意事项区域下方的空白位置）
         * **必须说明两种手写方式**：
           1. **带题号格式**：学生按题号手写，如"1.A 2.B"或"1-5 DCADB"
           2. **不带题号格式**：学生连续手写字母，如"CBD ACBDC"，此时需严格按照从左到右、从上到下的顺序识别
         * **必须提醒**：需要正确识别学生的涂改痕迹，以最终修改后的答案为准
    3. **主观题区**：各题号（如17, 18, 19题）分别位于答题卡的什么位置？
    4. **注意事项区**：是否有注意事项区域？

    请直接输出一段清晰的描述文本，用于指导后续的阅卷模型。
    【重要】：对于客观题区域，如果是手写形式，务必在输出中明确说明上述两种手写方式和涂改识别要求。
    
    格式参考：
    ### 答题卡布局说明
    该答题卡分为...
    **1. 基本信息区**...
    **2. 客观题区域**...（如为手写，必须说明带题号和不带题号两种格式，以及涂改识别）
    **3. 主观题区域**...
    """
        
        try:
            if self.provider == "OpenAI":
                base64_image = self.encode_image(image_path)
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "user", "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                        ]}
                    ]
                )
                return response.choices[0].message.content
            elif self.provider == "Gemini":
                img_obj = Image.open(image_path)
                response = self.gemini_model.generate_content([prompt, img_obj])
                return response.text
        except Exception as e:
            return f"Detection failed: {str(e)}"

    def consolidate_layout(self, descriptions):
        """
        Consolidates multiple layout descriptions into one robust description.
        """
        if not descriptions: return ""
        
        prompt = f"""
        以下是对同一种答题卡布局的 {len(descriptions)} 次观察描述。
        请综合这些描述，生成一份最准确、通用的【答题卡布局说明】。
        请去除偶然的错误，保留共性特征。
        输出格式要求：直接输出描述文本，不要包含“根据描述...”等废话。
        
        --- 描述列表 ---
        {json.dumps(descriptions, ensure_ascii=False)}
        """
        
        try:
            if self.provider == "OpenAI":
                response = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": prompt}]
                )
                return response.choices[0].message.content
            elif self.provider == "Gemini":
                response = self.gemini_model.generate_content(prompt)
                return response.text
        except Exception as e:
            return descriptions[0] # Fallback

