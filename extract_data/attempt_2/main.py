import pdfplumber
import json
import re
import time
import sys
from typing import Dict, List, Any, Optional

class ProgressBar:
    """Simple progress bar for terminal output"""
    
    def __init__(self, total: int, width: int = 50):
        self.total = total
        self.width = width
        self.current = 0
        self.start_time = time.time()
    
    def update(self, current: int, description: str = ""):
        self.current = current
        percent = (current / self.total) * 100
        filled = int(self.width * current // self.total)
        bar = '█' * filled + '░' * (self.width - filled)
        
        # Calculate time estimates
        elapsed = time.time() - self.start_time
        if current > 0:
            rate = current / (elapsed if elapsed else 0.0001)
            eta = (self.total - current) / rate if rate > 0 else 0
            eta_str = f" ETA: {int(eta//60)}:{int(eta%60):02d}"
        else:
            eta_str = " ETA: --:--"
        
        # Clear line and print progress
        sys.stdout.write(f'\r{bar} {percent:6.1f}% ({current}/{self.total}){eta_str} {description[:30]}')
        sys.stdout.flush()
    
    def finish(self):
        self.update(self.total, "Complete!")
        print()

class SyllabusExtractor:
    def __init__(self):
        self.courses = []
        self.raw_content = ""
        self.current_stage = ""
        self.start_time = time.time()
    
    def log_status(self, message: str, level: str = "INFO"):
        """Log status messages with timestamp"""
        elapsed = time.time() - self.start_time
        timestamp = f"[{int(elapsed//60):02d}:{int(elapsed%60):02d}]"
        print(f"{timestamp} {level}: {message}")
    
    def split_into_courses(self, text: str) -> List[str]:
        """Split text into individual course sections using SEMESTER markers"""
        self.log_status("Looking for course boundaries using SEMESTER markers...")
        
        # Find all SEMESTER occurrences
        semester_pattern = r'SEMESTER\s+S?\d+'
        matches = list(re.finditer(semester_pattern, text, re.IGNORECASE))
        
        if not matches:
            self.log_status("No SEMESTER markers found, trying alternative patterns", "WARN")
            return [text]  # Return entire text as single section
        
        course_sections = []
        for i, match in enumerate(matches):
            start_pos = match.start()
            
            # Find end position (start of next course or end of text)
            if i + 1 < len(matches):
                end_pos = matches[i + 1].start()
            else:
                end_pos = len(text)
            
            section = text[start_pos:end_pos].strip()
            if len(section) > 200:  # Only include substantial sections
                course_sections.append(section)
        
        self.log_status(f"Split text into {len(course_sections)} course sections")
        return course_sections
    
    def extract_course_header(self, text: str) -> Dict[str, Any]:
        """Extract course header information"""
        course_data = {
            "course_code": "",
            "semester": "",
            "title": "",
            "group": "",
            "cie_marks": 0,
            "ese_marks": 0,
            "credits": 0,
            "teaching_hours": {},
            "exam_hours": "",
            "prerequisites": "",
            "course_type": ""
        }
        
        # Extract semester
        semester_match = re.search(r'SEMESTER\s+(S?\d+)', text, re.IGNORECASE)
        if semester_match:
            course_data['semester'] = semester_match.group(1)
        
        # Extract course title - usually the line after SEMESTER
        title_lines = text.split('\n')[:10]  # Look in first 10 lines
        for i, line in enumerate(title_lines):
            if re.search(r'SEMESTER\s+S?\d+', line, re.IGNORECASE) and i + 1 < len(title_lines):
                potential_title = title_lines[i + 1].strip()
                # Clean title - remove group info if present
                title = re.sub(r'\([^)]+\)$', '', potential_title).strip()
                if len(title) > 5:
                    course_data['title'] = title
                
                # Extract group if present
                group_match = re.search(r'\(([^)]+)\)$', potential_title)
                if group_match:
                    course_data['group'] = group_match.group(1)
                break
        
        # Extract course code
        course_code_match = re.search(r'Course Code\s+([A-Z]+\d+)', text, re.IGNORECASE)
        if course_code_match:
            course_data['course_code'] = course_code_match.group(1)
        
        # Extract CIE and ESE marks
        cie_match = re.search(r'CIE Marks\s+(\d+)', text, re.IGNORECASE)
        if cie_match:
            course_data['cie_marks'] = int(cie_match.group(1))
        
        ese_match = re.search(r'ESE Marks\s+(\d+)', text, re.IGNORECASE)
        if ese_match:
            course_data['ese_marks'] = int(ese_match.group(1))
        
        # Extract credits
        credits_match = re.search(r'Credits\s+(\d+)', text, re.IGNORECASE)
        if credits_match:
            course_data['credits'] = int(credits_match.group(1))
        
        # Extract teaching hours
        hours_match = re.search(r'Teaching Hours/Week.*?(\d+):(\d+):(\d+):(\d+)', text, re.IGNORECASE)
        if hours_match:
            course_data['teaching_hours'] = {
                'lecture': int(hours_match.group(1)),
                'tutorial': int(hours_match.group(2)),
                'practical': int(hours_match.group(3)),
                'research': int(hours_match.group(4))
            }
        
        # Extract exam hours
        exam_hours_match = re.search(r'Exam Hours\s+([^\\n]+)', text, re.IGNORECASE)
        if exam_hours_match:
            course_data['exam_hours'] = exam_hours_match.group(1).strip()
        
        # Extract prerequisites
        prereq_match = re.search(r'Prerequisites \(if any\)\s+([^\\n]+?)(?=Course Type|$)', text, re.IGNORECASE)
        if prereq_match:
            course_data['prerequisites'] = prereq_match.group(1).strip()
        
        # Extract course type
        type_match = re.search(r'Course Type\s+([^\\n]+)', text, re.IGNORECASE)
        if type_match:
            course_data['course_type'] = type_match.group(1).strip()
        
        return course_data
    
    def extract_course_objectives(self, text: str) -> List[str]:
        """Extract course objectives"""
        objectives = []
        
        # Find Course Objectives section
        obj_match = re.search(r'Course Objectives:\s*\n(.*?)(?=SYLLABUS|Module)', text, re.DOTALL | re.IGNORECASE)
        if obj_match:
            obj_text = obj_match.group(1).strip()
            
            # Split by numbered items
            obj_lines = obj_text.split('\n')
            current_objective = ""
            
            for line in obj_lines:
                line = line.strip()
                if re.match(r'^\d+\.', line):  # Starts with number
                    if current_objective:
                        objectives.append(current_objective.strip())
                    current_objective = re.sub(r'^\d+\.\s*', '', line)
                elif line and current_objective:
                    current_objective += " " + line
            
            if current_objective:
                objectives.append(current_objective.strip())
        
        return objectives
    
    def extract_modules(self, text: str) -> List[Dict[str, Any]]:
        """Extract syllabus modules with contact hours"""
        modules = []
        
        # Find SYLLABUS section
        syllabus_match = re.search(r'SYLLABUS.*?(?=Course Assessment Method)', text, re.DOTALL | re.IGNORECASE)
        if not syllabus_match:
            return modules
        
        syllabus_text = syllabus_match.group(0)
        
        # Look for the table structure
        # Module No. | Syllabus Description | Contact Hours
        
        # Split by lines and look for module entries
        lines = syllabus_text.split('\n')
        current_module = None
        current_content = []
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Check if this line starts a new module (just a number)
            if re.match(r'^\d+$', line):
                # Save previous module if exists
                if current_module is not None and current_content:
                    modules.append({
                        "module_number": current_module,
                        "content": current_content,
                        "contact_hours": None  # Will be set later
                    })
                
                # Start new module
                current_module = int(line)
                current_content = []
            
            # Check if this line is contact hours (number at end)
            elif current_module is not None and re.match(r'^\d+$', line) and current_content:
                # This is the contact hours for the current module
                if modules and modules[-1]["module_number"] == current_module:
                    modules[-1]["contact_hours"] = int(line)
                else:
                    # Add contact hours to current module and save it
                    modules.append({
                        "module_number": current_module,
                        "content": current_content,
                        "contact_hours": int(line)
                    })
                current_module = None
                current_content = []
            
            # Regular content line
            elif current_module is not None:
                # Skip headers
                if 'Module' in line or 'Syllabus Description' in line or 'Contact Hours' in line:
                    continue
                current_content.append(line)
        
        # Handle last module if no contact hours found
        if current_module is not None and current_content:
            modules.append({
                "module_number": current_module,
                "content": current_content,
                "contact_hours": None
            })
        
        return modules
    
    def extract_assessment_details(self, text: str) -> Dict[str, Any]:
        """Extract detailed assessment information"""
        assessment = {
            "cie_breakdown": {},
            "ese_breakdown": {}
        }
        
        # Extract CIE breakdown
        cie_pattern = r'Continuous Internal Evaluation Marks \(CIE\):(.*?)End Semester Examination'
        cie_match = re.search(cie_pattern, text, re.DOTALL | re.IGNORECASE)
        if cie_match:
            cie_text = cie_match.group(1)
            
            # Look for the table with Attendance, Assignment, etc.
            # Try to extract numbers
            attendance_match = re.search(r'(\d+)(?=\s+\d+\s+\d+\s+\d+\s+\d+)', cie_text)
            if attendance_match:
                numbers = re.findall(r'\d+', cie_text.split('\n')[-2:][0] if '\n' in cie_text else cie_text)
                if len(numbers) >= 5:
                    assessment["cie_breakdown"] = {
                        "attendance": int(numbers[0]) if numbers else 0,
                        "assignment_microproject": int(numbers[1]) if len(numbers) > 1 else 0,
                        "internal_exam_1": int(numbers[2]) if len(numbers) > 2 else 0,
                        "internal_exam_2": int(numbers[3]) if len(numbers) > 3 else 0,
                        "total": int(numbers[4]) if len(numbers) > 4 else 0
                    }
        
        # Extract ESE breakdown
        ese_pattern = r'End Semester Examination Marks \(ESE\)(.*?)(?=Course Outcomes|$)'
        ese_match = re.search(ese_pattern, text, re.DOTALL | re.IGNORECASE)
        if ese_match:
            ese_text = ese_match.group(1)
            assessment["ese_breakdown"] = {
                "description": ese_text.strip(),
                "part_a_marks": 24,  # Default based on pattern
                "part_b_marks": 36,  # Default based on pattern
                "total": 60
            }
            
            # Try to extract specific marks
            part_a_match = re.search(r'(\d+x\d+\s*=\s*\d+)', ese_text)
            if part_a_match:
                marks_calc = part_a_match.group(1)
                total_match = re.search(r'=\s*(\d+)', marks_calc)
                if total_match:
                    assessment["ese_breakdown"]["part_a_marks"] = int(total_match.group(1))
        
        return assessment
    
    def extract_course_outcomes(self, text: str) -> List[Dict[str, Any]]:
        """Extract course outcomes"""
        outcomes = []
        
        # Find Course Outcomes section
        co_pattern = r'Course Outcomes \(COs\)(.*?)(?=CO-PO Mapping|Text Books|Note:|$)'
        co_match = re.search(co_pattern, text, re.DOTALL | re.IGNORECASE)
        
        if not co_match:
            return outcomes
        
        co_text = co_match.group(1)
        
        # Look for CO patterns
        # CO1 description K3
        co_entries = re.finditer(r'(CO\d+)\s+(.*?)\s+(K\d+)', co_text, re.DOTALL)
        
        for match in co_entries:
            code = match.group(1)
            description = match.group(2).strip()
            knowledge_level = match.group(3)
            
            # Clean description
            description = re.sub(r'\s+', ' ', description)
            description = description.strip()
            
            # Remove any table artifacts
            description = re.sub(r'Bloom\'?s.*?Level.*?\(KL\)', '', description, flags=re.IGNORECASE)
            
            if description and len(description) > 10:
                outcomes.append({
                    "code": code,
                    "description": description,
                    "knowledge_level": knowledge_level
                })
        
        return outcomes
    
    def extract_video_links(self, text: str) -> List[Dict[str, Any]]:
        """Extract video links"""
        video_links = []
        
        # Find Video Links section
        video_pattern = r'Video Links.*?Module.*?No\..*?Link ID(.*?)(?=SEMESTER|$)'
        video_match = re.search(video_pattern, text, re.DOTALL | re.IGNORECASE)
        
        if video_match:
            video_text = video_match.group(1)
            lines = video_text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Look for module number and URL
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        module_num = int(parts[0])
                        url = parts[1]
                        if url.startswith('http') or url.startswith('<http'):
                            url = url.strip('<>')
                            video_links.append({
                                "module": module_num,
                                "url": url
                            })
                    except (ValueError, IndexError):
                        continue
        
        return video_links
    
    def process_course_section(self, section_text: str, course_index: int) -> Optional[Dict[str, Any]]:
        """Process a single course section"""
        try:
            # Extract basic course info
            course_data = self.extract_course_header(section_text)
            
            # Skip if no essential information found
            if not course_data['course_code'] and not course_data['title']:
                self.log_status(f"Skipping section {course_index + 1}: No course code or title found", "WARN")
                return None
            
            # Extract additional data
            course_data['objectives'] = self.extract_course_objectives(section_text)
            course_data['modules'] = self.extract_modules(section_text)
            course_data['assessment'] = self.extract_assessment_details(section_text)
            course_data['course_outcomes'] = self.extract_course_outcomes(section_text)
            course_data['video_links'] = self.extract_video_links(section_text)
            
            # Add placeholder fields for consistency
            course_data['textbooks'] = []
            course_data['reference_books'] = []
            
            return course_data
            
        except Exception as e:
            self.log_status(f"Error processing course section {course_index + 1}: {e}", "ERROR")
            return None
    
    def process_pdf(self, pdf_path: str) -> Dict[str, Any]:
        """Main method to process the entire PDF"""
        self.log_status(f"Starting PDF processing: {pdf_path}")
        self.log_status("Processing structure-aware syllabus extraction...")
        
        # Stage 1: Extract text from PDF
        self.log_status("Stage 1/4: Extracting text from PDF pages...")
        full_text = ""
        page_count = 0
        
        try:
            with pdfplumber.open(pdf_path) as pdf:
                total_pages = len(pdf.pages)
                self.log_status(f"Found {total_pages} pages in PDF")
                
                progress = ProgressBar(total_pages, width=40)
                
                for i, page in enumerate(pdf.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            full_text += page_text + "\n\n"
                        
                        page_count += 1
                        progress.update(i + 1, f"Page {i + 1}")
                        
                    except Exception as e:
                        self.log_status(f"Warning: Could not extract text from page {i + 1}: {e}", "WARN")
                        continue
                
                progress.finish()
                
        except Exception as e:
            self.log_status(f"Error opening PDF: {e}", "ERROR")
            raise
        
        self.log_status(f"Successfully extracted text from {page_count} pages")
        self.log_status(f"Total text length: {len(full_text):,} characters")
        self.raw_content = full_text
        
        # Stage 2: Split into course sections
        self.log_status("Stage 2/4: Splitting into course sections...")
        course_sections = self.split_into_courses(full_text)
        
        # Stage 3: Process each course section
        self.log_status("Stage 3/4: Processing individual courses...")
        successful_courses = 0
        
        if course_sections:
            progress = ProgressBar(len(course_sections), width=40)
            
            for i, section in enumerate(course_sections):
                progress.update(i + 1, f"Course {i + 1}")
                
                course_data = self.process_course_section(section, i)
                
                if course_data:
                    self.courses.append(course_data)
                    successful_courses += 1
                    
                    # Log details for first few courses
                    if i < 3:
                        code = course_data.get('course_code', 'Unknown')
                        title = course_data.get('title', 'Unknown')[:40]
                        modules_count = len(course_data.get('modules', []))
                        self.log_status(f"  ✓ {code}: {title}... ({modules_count} modules)")
            
            progress.finish()
        
        # Stage 4: Final validation
        self.log_status("Stage 4/4: Final validation...")
        
        total_modules = sum(len(course.get('modules', [])) for course in self.courses)
        total_outcomes = sum(len(course.get('course_outcomes', [])) for course in self.courses)
        
        self.log_status(f"Extraction completed!")
        self.log_status(f"  ✓ Courses processed: {successful_courses}")
        self.log_status(f"  ✓ Total modules: {total_modules}")
        self.log_status(f"  ✓ Total outcomes: {total_outcomes}")
        
        return {
            "courses": self.courses,
            "raw_content": self.raw_content
        }
    
    def save_to_json(self, output_path: str, data: Dict[str, Any]):
        """Save extracted data to JSON file"""
        self.log_status(f"Saving extracted data to JSON file: {output_path}")
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            file_size_mb = len(json.dumps(data).encode('utf-8')) / (1024 * 1024)
            self.log_status(f"Successfully saved JSON ({file_size_mb:.2f} MB)")
            
            # Final summary
            self.log_status("="*60)
            self.log_status("EXTRACTION SUMMARY")
            self.log_status("="*60)
            self.log_status(f"Total courses: {len(data['courses'])}")
            
            for i, course in enumerate(data['courses'][:5]):  # Show first 5
                code = course.get('course_code', 'N/A')
                title = course.get('title', 'N/A')[:30]
                modules = len(course.get('modules', []))
                self.log_status(f"  {i+1}. {code}: {title}... ({modules} modules)")
            
            if len(data['courses']) > 5:
                self.log_status(f"  ... and {len(data['courses']) - 5} more courses")
                
        except Exception as e:
            self.log_status(f"Error saving to JSON: {e}", "ERROR")
            raise

def main():
    """Main execution function"""
    pdf_file_path = "syllabus.pdf"  # Update this path
    json_output_path = "syllabus_extracted.json"
    
    print("🔄 STRUCTURE-AWARE SYLLABUS EXTRACTOR")
    print("=" * 60)
    
    extractor = SyllabusExtractor()
    
    try:
        import os
        if not os.path.exists(pdf_file_path):
            print(f"❌ Error: PDF file not found at {pdf_file_path}")
            return
        
        result = extractor.process_pdf(pdf_file_path)
        extractor.save_to_json(json_output_path, result)
        
        print("\n🎉 EXTRACTION COMPLETED SUCCESSFULLY!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()