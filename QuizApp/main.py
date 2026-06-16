import fitz
import re
import json
import os

def is_vietnamese(text):
    """
    Checks if a block of text contains Vietnamese accented characters.
    """
    viet_chars = set("àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệđìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ")
    return any(c in viet_chars for c in text.lower())

def normalize_text(text):
    """
    Normalizes text to lowercase, removes punctuation and standardizes spacing
    for accurate string matching.
    """
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return " ".join(text.split())

def get_chapter_number(page_num):
    """
    Determines the chapter number based on the starting page ranges in the PDF.
    """
    chapter_starts = [
        (1, 1),
        (2, 10),
        (3, 22),
        (6, 36),
        (7, 48),
        (10, 62),
        (12, 77),
        (13, 89),
        (14, 102),
        (15, 117),
        (17, 129),
        (19, 140),
        (21, 155),
        (22, 168),
        (23, 175),
        (24, 191),
        (25, 199)
    ]
    matched_ch = 1
    for ch, start_page in chapter_starts:
        if page_num >= start_page:
            matched_ch = ch
        else:
            break
    return matched_ch

def main():
    base_dir = os.path.dirname(__file__)
    pdf_path = os.path.join(base_dir, "Test Bank - 2.pdf")
    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found at {pdf_path}")
        return
        
    print(f"Opening PDF: {pdf_path}")
    doc = fitz.open(pdf_path)
    
    questions = []
    vietnamese_by_page = {}
    
    print("Step 1: Scanning metadata (Vietnamese translation blocks) page by page...")
    for page_idx in range(len(doc)):
        page_num = page_idx + 1
        page = doc[page_idx]
        
        # Collect Vietnamese translation blocks
        viet_blocks = []
        blocks = page.get_text("blocks")
        for b in blocks:
            x0, y0, x1, y1, text, block_no, block_type = b
            text = text.strip()
            if not text:
                continue
            if "Cengage Learning" in text or "Role of Financial" in text:
                continue
            if is_vietnamese(text):
                y_mid = (y0 + y1) / 2
                viet_blocks.append((y_mid, text))
        vietnamese_by_page[page_num] = viet_blocks

    print("Step 2: Parsing English questions and options page by page using font dict...")
    current_q = None
    current_opt = None
    
    for page_idx in range(len(doc)):
        page_num = page_idx + 1
        page = doc[page_idx]
        blocks_dict = page.get_text("dict")["blocks"]
        
        for block in blocks_dict:
            if "lines" not in block:
                continue
                
            for line in block["lines"]:
                line_text = "".join(span["text"] for span in line["spans"]).strip()
                if not line_text:
                    continue
                if is_vietnamese(line_text):
                    continue
                if "Cengage Learning" in line_text or "All Rights Reserved" in line_text:
                    continue
                if "intended for use outside" in line_text or "publicly accessible website" in line_text:
                    continue
                if "U.S. Edition" in line_text or "scanned, copied" in line_text:
                    continue
                if re.search(r"^Chapter\s+\d+", line_text, re.IGNORECASE):
                    continue
                if "Financial Markets and Institutions" in line_text or "Determination of Interest Rates" in line_text:
                    continue
                if "Structure of Interest Rates" in line_text or "Money Markets" in line_text:
                    continue
                if "\uf076" in line_text:
                    continue
                
                # Check if spans of this line contain bold fonts
                is_bold = any(any(b in span["font"].lower() for b in ["bold", "black", "heavy"]) for span in line["spans"] if span["text"].strip())
                
                q_match = re.match(r"^(\d+)\.(?:\s+(.*))?$", line_text)
                if q_match:
                    if current_q:
                        questions.append(current_q)
                    current_q = {
                        "id": len(questions) + 1,
                        "question": q_match.group(2) or "",
                        "options": [],
                        "raw_options": {},
                        "answer": None,
                        "explanation": "",
                        "page": page_num,
                        "y": line["bbox"][1]  # Top coordinate of the line
                    }
                    current_opt = None
                    continue
                
                opt_match = re.match(r"^([A-E])\)\s*(.*)$", line_text)
                if opt_match and current_q:
                    current_opt = opt_match.group(1)
                    current_q["raw_options"][current_opt] = opt_match.group(2) or ""
                    if is_bold:
                        current_q["answer"] = current_opt
                    continue
                    
                tf_match = re.search(r"([])\s*(True|False)", line_text, re.IGNORECASE)
                if tf_match and current_q:
                    val = tf_match.group(2).strip()
                    current_q["options"] = ["A) True", "B) False"]
                    current_q["answer"] = "A" if val.lower() == "true" else "B"
                    current_opt = None
                    continue
                    
                ans_match = re.match(r"^ANSWER:\s*([A-E])", line_text, re.IGNORECASE)
                if ans_match and current_q:
                    current_q["answer"] = ans_match.group(1).upper()
                    current_opt = None
                    continue
                    
                if current_opt and current_q:
                    current_q["raw_options"][current_opt] += " " + line_text
                    if is_bold:
                        current_q["answer"] = current_opt
                elif current_q and not current_q["raw_options"] and current_q["answer"] is None:
                    current_q["question"] += " " + line_text

    if current_q:
        questions.append(current_q)
        
    print(f"Total raw questions parsed: {len(questions)}")
    
    print("Step 3: Aligning answers, options, and explanations...")
    for q in questions:
        raw = q["raw_options"]
        if not q["options"] and raw:
            sorted_keys = sorted(raw.keys())
            q["options"] = [f"{k}) {raw[k].strip()}" for k in sorted_keys]
            
            # True/False question fallback when it lists only a single line in PDF
            if len(q["options"]) == 1:
                opt_str = q["options"][0].lower()
                if "true" in opt_str:
                    q["options"] = ["A) True", "B) False"]
                    q["answer"] = "A"
                elif "false" in opt_str:
                    q["options"] = ["A) True", "B) False"]
                    q["answer"] = "B"

        viet_blocks = vietnamese_by_page.get(q["page"], [])
        if viet_blocks:
            page_qs = [page_q for page_q in questions if page_q["page"] == q["page"]]
            mapped_blocks = []
            for y_mid, text in viet_blocks:
                best_q = min(page_qs, key=lambda pq: abs(pq["y"] - y_mid))
                if best_q == q:
                    mapped_blocks.append(text)
            if mapped_blocks:
                q["explanation"] = "\n".join(mapped_blocks)

    # Prepare output database list
    output_data = []
    for q in questions:
        output_data.append({
            "id": q["id"],
            "chapter": get_chapter_number(q["page"]),
            "question": q["question"].strip(),
            "options": q["options"],
            "answer": q["answer"],
            "explanation": q["explanation"].strip() if q["explanation"] else ""
        })
        
    # Manual overrides for parsed errors
    overrides = {
        # Chapter 1, PDF Question 45 (which is parsed with ID 46)
        46: {
            "answer": "D",
            "explanation": "Thị trường tài chính mà điều chỉnh dòng vốn ngắn hạn \nvới thời gian đáo hạn ít hơn 1 năm gọi là\nThị trường tiền tệ"
        }
    }
    for q in output_data:
        if q["id"] in overrides:
            for key, val in overrides[q["id"]].items():
                q[key] = val

        
    # Step 4: Write to questions.json
    output_json_path = os.path.join(base_dir, "questions.json")
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"Successfully wrote database to {output_json_path}")

    # Step 5: Embed questions directly inside index.html JavaScript code via string slice markers
    index_html_path = os.path.join(base_dir, "index.html")
    if os.path.exists(index_html_path):
        print(f"Embedding database directly into: {index_html_path}")
        with open(index_html_path, "r", encoding="utf-8") as f:
            html_content = f.read()
            
        # Format the questions list as pretty JS JSON literal
        questions_js_literal = json.dumps(output_data, ensure_ascii=False, indent=4)
        
        start_marker = "// QUESTIONS_START"
        end_marker = "// QUESTIONS_END"
        
        start_idx = html_content.find(start_marker)
        end_idx = html_content.find(end_marker)
        
        if start_idx != -1 and end_idx != -1:
            # Reconstruct HTML file by replacing content between markers
            # This avoids using re.sub and preserves escaped string sequences (like \n) properly
            new_html_content = (
                html_content[:start_idx + len(start_marker)] +
                "\n    let allQuestions = " + questions_js_literal + ";\n    " +
                html_content[end_idx:]
            )
            with open(index_html_path, "w", encoding="utf-8") as f:
                f.write(new_html_content)
            print("Successfully injected questions array into index.html via markers.")
        else:
            print("Warning: Could not find markers in index.html to inject data.")
    else:
        print(f"Warning: index.html not found at {index_html_path}, skipped embedding.")
        
    print("--- Execution Summary ---")
    print(f"Total questions: {len(output_data)}")
    missing_answers = [q for q in output_data if q["answer"] is None]
    print(f"Questions missing answers: {len(missing_answers)}")

if __name__ == "__main__":
    main()
