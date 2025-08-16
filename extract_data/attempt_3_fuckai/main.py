import re
import json

pattern = r"SEMESTER S\d.+?SEMESTER S\d"

schema = {
            "semester": "",
            "title": "",
            "group": "",
            "course_code": "",
            "cie_marks": 0,
            "ese_marks": 0,
            "credits": 0,
            "teaching_hours_per_week": {
                "lecture": 0,
                "tutorial": 0,
                "practical": 0,
                "research": 0
            },
            "exam_hours": "",
            "prerequisites": [],
            "course_type": "",
            "objectives": [],
            "syllabus_modules": [
                {
                    "module_no": 0,
                    "description": "",
                    "references": [
                        {
                            "book_no": 0,
                            "sections": ""
                        }
                    ],
                    "contact_hours": 0
                }
            ],
            "assessment": {
                "cie": {
                    "total": 0,
                    "components": {}
                },
                "ese": {
                    "total": 0,
                    "pattern": {}
                }
            },
            "course_outcomes": [
                {
                    "co_no": "",
                    "description": "",
                    "bloom_kl": ""
                }
            ],
            "co_po_mapping": [],
            "textbooks": [
                {
                    "short_code": 0,
                    "title": "",
                    "author": "",
                    "publisher": "",
                    "edition": "",
                    "year": 0
                }
            ],
            "reference_books": [
                {
                    "title": "",
                    "author": "",
                    "publisher": "",
                    "edition": "",
                    "year": 0
                }
            ],
            "video_links": [
                {
                    "module_no": 0,
                    "link": ""
                }
            ]
        }


def get_prompt(course_text):
    prompt = f"""
Convert the following course syllabus into a structured JSON object following this schema:
{json.dumps(schema, indent=2)}

Rules:
- Clean up formatting, merge broken lines
- Extract each module's references (e.g., 'Text 1') and match them to the textbooks list
- For all book_short_code or short_code fields, store only the integer (e.g., 'Text 2' → 2)
- All numbers must be actual integers, not strings
- Return ONLY valid JSON, no extra commentary

Syllabus text:
{course_text}
"""
    return prompt


with open("data.txt", 'r', encoding='utf-8') as f:
    text = f.read()

matches = re.findall(pattern, text, re.MULTILINE | re.DOTALL)

print(matches[1])