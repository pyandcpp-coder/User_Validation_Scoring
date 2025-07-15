from flask import Flask, request, jsonify
from werkzeug.utils import secure_filename
import os
from ai_validator import ContentValidator 
import uuid


UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

print("Initializing Content Validator...")
validator = ContentValidator()
print("Validator ready.")

# --- Helper Function ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- API Endpoint ---
@app.route('/validate_post', methods=['POST'])
def validate_post_endpoint():
    """
    API endpoint to validate a new post.
    Expects a multipart form with 'user_id', 'text_content', and an 'image' file.
    """
    # 1. Check for required parts in the request
    if 'image' not in request.files:
        return jsonify({"status": "rejected", "reason": "No image file provided"}), 400
    if 'user_id' not in request.form or 'text_content' not in request.form:
         return jsonify({"status": "rejected", "reason": "Missing user_id or text_content"}), 400

    # 2. Get data from the request
    user_id = request.form['user_id']
    text_content = request.form['text_content']
    image_file = request.files['image']

    # 3. Validate and save the image file temporarily
    if image_file.filename == '' or not allowed_file(image_file.filename):
        return jsonify({"status": "rejected", "reason": "Invalid or no selected image file"}), 400
    
    filename = secure_filename(str(uuid.uuid4()) + os.path.splitext(image_file.filename)[1])
    image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    image_file.save(image_path)

    # 4. Process the post using our ContentValidator
    # We wrap this in a try/finally block to ensure the temp image is always deleted
    try:
        post_id = validator.process_new_post(
            user_id=user_id,
            text_content=text_content,
            image_path=image_path
        )
    finally:
        # Clean up the uploaded file after processing
        if os.path.exists(image_path):
            os.remove(image_path)

    # 5. Return the result to the caller
    if post_id:
        return jsonify({
            "status": "approved",
            "post_id": post_id,
            "message": "Post was successfully validated and stored."
        }), 200
    else:
        # The validator's console output will show the specific reason (gibberish/duplicate)
        return jsonify({
            "status": "rejected",
            "reason": "Content failed validation (gibberish or duplicate)."
        }), 400

# --- Run the Server ---
if __name__ == '__main__':
    # Use host='0.0.0.0' to make the server accessible from other devices on your network
    app.run(host='0.0.0.0', port=8020, debug=True)