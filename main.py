import json
import re
from typing import Dict, List, Any

def parse_syllabus_data(file_path: str) -> Dict[str, Any]:
    """
    Parse syllabus data from a text file and structure it into a dictionary.
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return {}
    except Exception as e:
        print(f"Error reading file: {e}")
        return {}
    
    # Initialize the structured data dictionary
    structured_data = {
        "courses": [],
        "raw_content": content
    }
    
    # Split content by course sections (looking for course codes or major headers)
    courses = []
    current_course = {}
    current_semester = None
    
    lines = content.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip empty lines
        if not line:
            i += 1
            continue
        
        # Check for semester pattern (e.g., SEMESTER S3)
        semester_match = re.search(r'SEMESTER\s+(S?\d+)', line)
        if semester_match:
            current_semester = semester_match.group(1)
            i += 1
            continue
        
        # Check for course code pattern (e.g., PCCST301, PCCST302)
        course_code_match = re.search(r'Course Code\s+([A-Z]+\d+)', line)
        if course_code_match:
            # Save previous course if exists
            if current_course:
                courses.append(current_course)
            
            # Start new course
            current_course = {
                "course_code": course_code_match.group(1),
                "semester": current_semester,
                "modules": [],
                "assessment": {},
                "course_outcomes": [],
                "textbooks": [],
                "reference_books": [],
                "video_links": []
            }
        
        # Extract course title (usually appears before course code)
        elif re.match(r'^[A-Z\s]+$', line) and len(line) > 10 and 'SEMESTER' not in line:
            if current_course and 'title' not in current_course:
                current_course['title'] = line
        
        # Extract CIE and ESE marks
        elif 'CIE Marks' in line:
            cie_match = re.search(r'CIE Marks\s+(\d+)', line)
            if cie_match:
                current_course['cie_marks'] = int(cie_match.group(1))
        
        elif 'ESE Marks' in line:
            ese_match = re.search(r'ESE Marks\s+(\d+)', line)
            if ese_match:
                current_course['ese_marks'] = int(ese_match.group(1))
        
        # Extract credits
        elif 'Credits' in line:
            credits_match = re.search(r'Credits\s+(\d+)', line)
            if credits_match:
                current_course['credits'] = int(credits_match.group(1))
        
        # Extract module information
        elif re.match(r'^\d+$', line) and i + 1 < len(lines):
            module_num = int(line)
            module_content = []
            i += 1
            
            # Collect module content until next module or section
            while i < len(lines) and not re.match(r'^\d+$|^Course Assessment|^Course Outcomes|^Text Books', lines[i].strip()):
                if lines[i].strip():
                    module_content.append(lines[i].strip())
                i += 1
            
            if current_course and module_content:
                current_course['modules'].append({
                    "module_number": module_num,
                    "content": module_content
                })
            i -= 1  # Step back one line to reprocess
        
        # Extract course outcomes
        elif line.startswith('CO') and re.match(r'^CO\d+', line):
            co_match = re.match(r'^(CO\d+)\s+(.+?)\s+([KL]\d+)$', line)
            if co_match and current_course:
                current_course['course_outcomes'].append({
                    "code": co_match.group(1),
                    "description": co_match.group(2),
                    "knowledge_level": co_match.group(3)
                })
        
        i += 1
    
    # Add the last course
    if current_course:
        courses.append(current_course)
    
    structured_data["courses"] = courses
    return structured_data

def save_to_json(data: Dict[str, Any], output_file: str) -> None:
    """
    Save structured data to a JSON file.
    """
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        print(f"Data successfully saved to '{output_file}'")
    except Exception as e:
        print(f"Error saving to JSON file: {e}")

def main():
    """
    Main function to read data.txt and save to JSON.
    """
    input_file = "data.txt"
    output_file = "syllabus_data.json"
    
    print("Reading syllabus data from data.txt...")
    structured_data = parse_syllabus_data(input_file)
    
    if structured_data:
        print("Saving structured data to JSON...")
        save_to_json(structured_data, output_file)
        
        # Print summary
        print(f"\nSummary:")
        print(f"- Courses parsed: {len(structured_data.get('courses', []))}")
        for i, course in enumerate(structured_data.get('courses', []), 1):
            semester = course.get('semester', 'Unknown')
            print(f"  {i}. {course.get('title', 'Unknown')} ({course.get('course_code', 'N/A')}) - Semester: {semester}")
            print(f"     Modules: {len(course.get('modules', []))}")
            print(f"     Course Outcomes: {len(course.get('course_outcomes', []))}")
    else:
        print("No data could be parsed from the file.")

if __name__ == "__main__":
    main()