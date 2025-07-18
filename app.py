# app.py
import os
import uuid
from datetime import datetime
from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
from moviepy import VideoFileClip  # Fixed import
from dotenv import load_dotenv

from utils.audio_processor import process_audio_file
from utils.cloudinary_utils import upload_to_cloudinary
from utils.airtable_utils import sync_to_airtable

load_dotenv()

app = Flask(__name__)
BASE_FOLDER = 'media'
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'avi', 'mkv'}
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB max
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH
os.makedirs(BASE_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def convert_video_to_audio(video_path, output_audio_path):
    clip = VideoFileClip(video_path)
    if clip.audio is None:
        raise ValueError("No audio track found in video.")
    clip.audio.write_audiofile(output_audio_path)
    clip.close()

@app.route('/', methods=['GET'])
def index():
    return jsonify({"message": "Video-to-Audio API is running"}), 200

@app.route('/upload-video', methods=['POST'])
def upload_video():
    if 'video' not in request.files:
        return jsonify({"error": "No video file provided"}), 400

    file = request.files['video']
    language = request.form.get('language', 'en-IN')

    if not allowed_file(file.filename):
        return jsonify({"error": "Invalid file type"}), 400

    try:
        uid = datetime.now().strftime('%Y%m%d_%H%M%S') + "_" + str(uuid.uuid4())[:6]
        folder_path = os.path.join(BASE_FOLDER, uid)
        os.makedirs(folder_path, exist_ok=True)

        video_path = os.path.join(folder_path, secure_filename(file.filename))
        file.save(video_path)

        audio_path = os.path.join(folder_path, "audio.wav")
        convert_video_to_audio(video_path, audio_path)

        transcript = process_audio_file(audio_path, language)
        transcript_path = os.path.join(folder_path, "transcript.txt")
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(transcript)

        cloudinary_folder = f"pipeline/{uid}"
        video_url = upload_to_cloudinary(video_path, cloudinary_folder, uid, "video")
        audio_url = upload_to_cloudinary(audio_path, cloudinary_folder, uid + "_audio", "video")
        transcript_url = upload_to_cloudinary(transcript_path, cloudinary_folder, uid + "_transcript", "raw")

        record = sync_to_airtable(video_url, audio_url, transcript_url, transcript)

        return jsonify({
            "message": "Success",
            "video_url": video_url,
            "audio_url": audio_url,
            "transcript_url": transcript_url,
            "transcript_text": transcript,
            "airtable_record_id": record.get("id", "unknown")
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
