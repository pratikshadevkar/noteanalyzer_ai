from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import fitz
from PIL import Image
import os
import base64
import io
import re
import numpy as np
import easyocr
import uuid
from wordfreq import zipf_frequency
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer

app = Flask(__name__)
CORS(app)

SESSION_CACHE = {}

_reader_instance = None

def get_sentence_model():
   

def get_ocr_reader():
    global _reader_instance
    if _reader_instance is None:
        print("🚀 [Lazy Load] Initializing EasyOCR Engine...")
        _reader_instance = easyocr.Reader(['en'], gpu=False)
    return _reader_instance

def clean_text_completely(text):
    text = re.sub(r'—_+', ' ', text)
    text = re.sub(r'__+', ' ', text)
    text = re.sub(r'[^\w\s]', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.lower().strip()

def extract_text_from_pdf(pdf_bytes):
    text = ""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            text += page.get_text("text") + "\n"
        doc.close()
    except Exception as e:
        print(f"PDF extraction error: {e}")
    return text.strip()

def pdf_to_images(pdf_bytes):
    images = []
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_num in range(min(len(doc), 2)): # Reduced to 2 pages max for faster optimization
            page = doc.load_page(page_num)
            mat = fitz.Matrix(1.2, 1.2) # Dropped matrix sizing to 1.2 for major speedup
            pix = page.get_pixmap(matrix=mat)
            images.append(Image.open(io.BytesIO(pix.tobytes("png"))))
        doc.close()
    except Exception as e:
        print(f"PDF to image error: {e}")
    return images

def extract_text_from_image(image):
    try:
        image_np = np.array(image)
        result = get_ocr_reader().readtext(image_np)
        text = " ".join([r[1] for r in result])
        return text
    except Exception as e:
        print(f"OCR reading error: {e}")
        return ""

def extract_keywords(text):
    words = text.lower().split()
    stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to',
                 'for', 'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were',
                 'be', 'been', 'being', 'have', 'has', 'had', 'this', 'that', 'our'}
    keywords = []
    for word in words:
        clean_w = re.sub(r'[^\w]', '', word)
        if clean_w in stopwords or len(clean_w) <= 2:
            continue
        if zipf_frequency(clean_w, 'en') < 2.0:
            continue
        keywords.append(clean_w)
    return keywords

def generate_preview_image(image, max_size=(250, 350)):
    if isinstance(image, list):
        if len(image) == 0:
            return None
        image = image[0]
    img_copy = image.copy()
    img_copy.thumbnail(max_size, Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    img_copy.save(buffer, format='JPEG', quality=60) # Fast quality setting
    return base64.b64encode(buffer.getvalue()).decode('utf-8')

@app.route('/init_session', methods=['POST'])
def init_session():
    try:
        if 'pdf' not in request.files:
            return jsonify({'error': 'PDF file is required'}), 400
        
        pdf_file = request.files['pdf']
        pdf_bytes = pdf_file.read()
        
        pdf_text_raw = extract_text_from_pdf(pdf_bytes)
        pdf_images = pdf_to_images(pdf_bytes)
        
        pdf_preview = None
        if pdf_images:
            pdf_preview = generate_preview_image(pdf_images[0])
            
        if not pdf_text_raw and pdf_images:
            pdf_text_raw = " ".join([extract_text_from_image(img) for img in pdf_images]).strip()

        pdf_clean = clean_text_completely(pdf_text_raw)
        pdf_word_count = len(pdf_clean.split()) # Calculated securely from cleaned data array
        
       
        pdf_kw = extract_keywords(pdf_clean)
        pdf_sentences = [s.strip() for s in re.split(r'[.!?\n]+', pdf_text_raw) if len(s.strip()) > 15]

        session_id = str(uuid.uuid4())
        SESSION_CACHE[session_id] = {
            'pdf_text_raw': pdf_text_raw,
            'pdf_clean': pdf_clean,
            'pdf_word_count': pdf_word_count,
            'pdf_kw': pdf_kw,
            'pdf_sentences': pdf_sentences,
            'pdf_preview': pdf_preview
        }
        
        return jsonify({
            'session_id': session_id,
            'pdf_word_count': pdf_word_count,
            'pdf_preview': pdf_preview,
            'pdf_text_preview': pdf_text_raw[:300] + "..."
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/analyze_notes', methods=['POST'])
def analyze_notes():
    try:
        session_id = request.form.get('session_id')
        if not session_id or session_id not in SESSION_CACHE:
            return jsonify({'error': 'Invalid session token.'}), 400
            
        if 'notes' not in request.files:
            return jsonify({'error': 'Notes file is required'}), 400

        notes_file = request.files['notes']
        extraction_mode = request.form.get('extractionMode', 'standard')
        deep_match = request.form.get('deepMatch', 'true') == 'true'
        
        cache = SESSION_CACHE[session_id]
        pdf_text_raw = cache['pdf_text_raw']
        pdf_clean = cache['pdf_clean']
        pdf_word_count = cache['pdf_word_count'] # Pulled accurately from session state cache
        pdf_kw = cache['pdf_kw']
        pdf_sentences = cache['pdf_sentences']
        
        results = {'pdf_preview': cache['pdf_preview']}
        notes_bytes = notes_file.read()

        notes_filename = notes_file.filename.lower()
        if notes_filename.endswith('.pdf'):
            notes_text_raw = extract_text_from_pdf(notes_bytes)
            notes_images = pdf_to_images(notes_bytes)
            if notes_images:
                results['notes_preview'] = generate_preview_image(notes_images[0])
                if not notes_text_raw:
                    notes_text_raw = " ".join([extract_text_from_image(img) for img in notes_images[:1]])
        else:
            notes_image = Image.open(io.BytesIO(notes_bytes))
            results['notes_preview'] = generate_preview_image(notes_image)
            notes_text_raw = extract_text_from_image(notes_image)

        notes_clean = clean_text_completely(notes_text_raw)
        results['notes_word_count'] = len(notes_clean.split())
        results['pdf_word_count'] = pdf_word_count # Crucial: pass value back down so it is never undefined!

        if not pdf_clean or not notes_clean:
            return jsonify({'error': 'No readable text identified.'}), 400
        
        vectorizer = TfidfVectorizer()

        tfidf_matrix = vectorizer.fit_transform([pdf_clean, notes_clean])

        semantic_similarity = cosine_similarity(
          tfidf_matrix[0:1],
          tfidf_matrix[1:2]
        )[0][0] * 100
       

        notes_kw = extract_keywords(notes_clean)
        matched_set = set(pdf_kw).intersection(set(notes_kw))
        missing_set = set(pdf_kw) - set(notes_kw)
        
        keyword_coverage = (len(matched_set) / max(len(set(pdf_kw)), 1)) * 100
        
        covered_count = 0
        covered_topics = []
        uncovered_topics = []
        
        overlap_threshold = 0.20 if deep_match else 0.30

        for s in pdf_sentences:
            s_clean = clean_text_completely(s)
            s_words = extract_keywords(s_clean)
            if not s_words:
                continue
            
            overlap = set(s_words).intersection(set(notes_kw))
            if len(overlap) / len(s_words) >= overlap_threshold:
                covered_count += 1
                if len(covered_topics) < 4:
                    covered_topics.append(s[:60] + "...")
            else:
                if len(uncovered_topics) < 4:
                    uncovered_topics.append(s[:60] + "...")

        topic_coverage = (covered_count / max(len(pdf_sentences), 1)) * 100
        sequence_similarity = min(results['notes_word_count'] / max(pdf_word_count * 0.4, 1), 1.0) * 100

        composite_score = (semantic_similarity * 0.50 + keyword_coverage * 0.20 + topic_coverage * 0.25 + sequence_similarity * 0.05)
        composite_score = round(composite_score, 1)

        if composite_score >= 85:
            grade, grade_color, feedback = "Excellent", "#22c55e", "Outstanding notes coverage."
        elif composite_score >= 65:
            grade, grade_color, feedback = "Good", "#3b82f6", "Good work! Key concepts identified."
        else:
            grade, grade_color, feedback = "Needs Work", "#ef4444", "Review missing textbook criteria."

        results.update({
            'composite_score': composite_score,
            'grade': grade,
            'grade_color': grade_color,
            'feedback': feedback,
            'metrics': {
                'tfidf_similarity': round(semantic_similarity, 1),
                'keyword_coverage': round(keyword_coverage, 1),
                'topic_coverage': round(topic_coverage, 1),
                'sequence_similarity': round(sequence_similarity, 1)
            },
            'matched_keywords': list(matched_set)[:15],
            'missing_keywords': list(missing_set)[:15],
            'covered_topics': covered_topics if covered_topics else ["No direct matches."],
            'uncovered_topics': uncovered_topics[:4] if uncovered_topics else ["None"],
            'pdf_text_preview': pdf_text_raw[:300] + "...",
            'notes_text_preview': notes_text_raw[:300] + "..."
        })

        return jsonify(results)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route("/")
def home():
    return render_template("index.html")

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=5050)