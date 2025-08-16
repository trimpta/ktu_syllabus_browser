import re
import json
import time
from google import genai
from typing import List, Dict, Any
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SyllabusProcessor:
    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
        # Initialize the client with the API key
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name
        self.rate_limit_delay = 2.1  # 30 RPM = ~2 seconds between requests
        
        self.schema = {
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

    def read_data_file(self, filename: str) -> str:
        """Read the data.txt file"""
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                return file.read()
        except FileNotFoundError:
            logger.error(f"File {filename} not found")
            raise
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            raise

    def extract_course_sections(self, text: str) -> List[str]:
        """Extract course sections using regex pattern"""
        pattern = r"SEMESTER S\d.+?(?=SEMESTER S\d)" 
        matches = re.findall(pattern, text, re.MULTILINE | re.DOTALL)
        
        logger.info(f"Found {len(matches)} course sections")
        return matches

    def call_gemini_api(self, prompt: str) -> str:
        """Call Gemini API with rate limiting"""
        try:
            response = self.client.models.generate_content(
                model=self.model_name, 
                contents=prompt
            )
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"API request failed: {e}")
            raise

    def process_course_text(self, course_text: str) -> Dict[str, Any]:
        """Process a single course text through Gemma API"""
        prompt = f"""
Convert the following course syllabus into a structured JSON object following this schema:
{json.dumps(self.schema, indent=2)}

Rules:
- Clean up formatting, merge broken lines
- Extract each module's references (e.g., 'Text 1') and match them to the textbooks list
- For all book_short_code or short_code fields, store only the integer (e.g., 'Text 2' → 2)
- All numbers must be actual integers, not strings
- Return ONLY valid JSON, no extra commentary

Syllabus text:
{course_text}
"""
        
        logger.info("Sending request to Gemini API...")
        response = self.call_gemini_api(prompt)
        
        try:
            # Try to parse the JSON response
            parsed_json = json.loads(response)
            logger.info("Successfully parsed JSON response")
            return parsed_json
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {e}")
            logger.error(f"Raw response: {response[:500]}...")
            
            # Try to extract JSON from response if it has extra text
            try:
                json_start = response.find('{')
                json_end = response.rfind('}') + 1
                if json_start != -1 and json_end != 0:
                    json_str = response[json_start:json_end]
                    parsed_json = json.loads(json_str)
                    logger.info("Successfully extracted and parsed JSON from response")
                    return parsed_json
            except:
                pass
            
            raise Exception(f"Could not parse API response as JSON: {e}")

    def process_all_courses(self, filename: str) -> List[Dict[str, Any]]:
        """Process all courses from the data file"""
        # Read the data file
        text = self.read_data_file(filename)
        
        # Extract course sections
        course_sections = self.extract_course_sections(text)
        
        if not course_sections:
            logger.warning("No course sections found in the file")
            return []
        
        processed_courses = []
        
        for i, course_text in enumerate(course_sections, 1):
            try:
                logger.info(f"Processing course {i}/{len(course_sections)}")
                
                # Process the course text
                course_json = self.process_course_text(course_text)
                processed_courses.append(course_json)
                
                logger.info(f"Successfully processed course {i}")
                
                # Rate limiting - wait between requests
                if i < len(course_sections):
                    logger.info(f"Waiting {self.rate_limit_delay}s for rate limiting...")
                    time.sleep(self.rate_limit_delay)
                    
            except Exception as e:
                logger.error(f"Failed to process course {i}: {e}")
                # Continue with next course instead of failing completely
                continue
        
        return processed_courses

    def save_results(self, courses: List[Dict[str, Any]], output_filename: str):
        """Save processed courses to JSON file"""
        combined_result = {
            "total_courses": len(courses),
            "courses": courses,
            "processing_timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }
        
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump(combined_result, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Results saved to {output_filename}")

def main():
    """Main execution function"""
    # Configuration
    API_KEY = "KEY"  # Replace with your actual API key
    INPUT_FILE = "data.txt"
    OUTPUT_FILE = "processed_syllabi.json"
    
    try:
        # Initialize processor
        processor = SyllabusProcessor(API_KEY)
        
        # Process all courses
        logger.info("Starting syllabus processing...")
        courses = processor.process_all_courses(INPUT_FILE)
        
        if courses:
            # Save results
            processor.save_results(courses, OUTPUT_FILE)
            logger.info(f"Successfully processed {len(courses)} courses")
        else:
            logger.warning("No courses were successfully processed")
            
    except Exception as e:
        logger.error(f"Processing failed: {e}")
        raise

if __name__ == "__main__":
    main()