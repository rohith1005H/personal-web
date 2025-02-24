import os
import sys
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from slugify import slugify
import markdown2
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail, Message
import requests
from dotenv import load_dotenv
from whitenoise import WhiteNoise

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)

load_dotenv()

app = Flask(__name__)

# Database configuration
db_path = os.getenv('DATABASE_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'blog.db'))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Other configurations
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Email configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')

# reCAPTCHA configuration
app.config['RECAPTCHA_SITE_KEY'] = os.getenv('RECAPTCHA_SITE_KEY')
app.config['RECAPTCHA_SECRET_KEY'] = os.getenv('RECAPTCHA_SECRET_KEY')

# Initialize extensions
db = SQLAlchemy(app)
csrf = CSRFProtect(app)
mail = Mail(app)

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
app.logger.info(f"Upload directory created at {app.config['UPLOAD_FOLDER']}")

class Post(db.Model):
    __tablename__ = 'post'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True, nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Photo(db.Model):
    __tablename__ = 'photo'
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    description = db.Column(db.String(500))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

class Message(db.Model):
    __tablename__ = 'message'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)

def init_db():
    """Initialize the database and create all tables"""
    try:
        # Ensure the database directory exists
        db_dir = os.path.dirname(db_path)
        os.makedirs(db_dir, exist_ok=True)
        app.logger.info(f"Database directory ensured at {db_dir}")
        
        # Create all tables
        with app.app_context():
            db.create_all()
            app.logger.info("Database tables created successfully")
            
            # Verify tables were created
            tables = db.engine.table_names()
            app.logger.info(f"Created tables: {', '.join(tables)}")
            
        return True
    except Exception as e:
        app.logger.error(f"Error initializing database: {str(e)}")
        return False

# Initialize database
if init_db():
    app.logger.info("Database initialization completed successfully")
else:
    app.logger.error("Failed to initialize database")

def verify_recaptcha(response):
    """Verify reCAPTCHA response"""
    verify_url = 'https://www.google.com/recaptcha/api/siteverify'
    payload = {
        'secret': app.config['RECAPTCHA_SECRET_KEY'],
        'response': response
    }
    response = requests.post(verify_url, data=payload)
    return response.json().get('success', False)

@app.route('/')
def index():
    try:
        posts = Post.query.order_by(Post.created_at.desc()).limit(5).all()
        photos = Photo.query.order_by(Photo.uploaded_at.desc()).limit(6).all()
        return render_template('index.html', posts=posts, photos=photos)
    except Exception as e:
        app.logger.error(f"Error in index route: {str(e)}")
        return render_template('index.html', posts=[], photos=[])

@app.route('/blog')
def blog():
    try:
        posts = Post.query.order_by(Post.created_at.desc()).all()
        return render_template('blog.html', posts=posts)
    except Exception as e:
        app.logger.error(f"Error in blog route: {str(e)}")
        return render_template('blog.html', posts=[])

@app.route('/blog/<slug>')
def post(slug):
    try:
        post = Post.query.filter_by(slug=slug).first_or_404()
        content = markdown2.markdown(post.content)
        return render_template('post.html', post=post, content=content)
    except Exception as e:
        app.logger.error(f"Error in post route: {str(e)}")
        return render_template('post.html', post=None, content='')

@app.route('/write', methods=['GET', 'POST'])
def write():
    if request.method == 'POST':
        try:
            title = request.form['title']
            content = request.form['content']
            slug = slugify(title)
            
            post = Post(title=title, content=content, slug=slug)
            db.session.add(post)
            db.session.commit()
            
            return redirect(url_for('blog'))
        except Exception as e:
            app.logger.error(f"Error in write route: {str(e)}")
            return render_template('write.html')
    return render_template('write.html')

@app.route('/gallery')
def gallery():
    try:
        photos = Photo.query.order_by(Photo.uploaded_at.desc()).all()
        return render_template('gallery.html', photos=photos)
    except Exception as e:
        app.logger.error(f"Error in gallery route: {str(e)}")
        return render_template('gallery.html', photos=[])

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        try:
            if 'photo' not in request.files:
                flash('No file selected')
                return redirect(request.url)
                
            photo = request.files['photo']
            if photo.filename == '':
                flash('No file selected')
                return redirect(request.url)
                
            if photo:
                filename = secure_filename(photo.filename)
                photo.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                
                new_photo = Photo(
                    filename=filename,
                    description=request.form.get('description', '')
                )
                db.session.add(new_photo)
                db.session.commit()
                
                return redirect(url_for('gallery'))
        except Exception as e:
            app.logger.error(f"Error in upload route: {str(e)}")
            return render_template('upload.html')
    return render_template('upload.html')

@app.route('/contact', methods=['POST'])
def contact():
    try:
        if not verify_recaptcha(request.form.get('g-recaptcha-response')):
            return jsonify({'success': False, 'error': 'Please complete the reCAPTCHA verification'}), 400

        # Save message to database
        message = Message(
            name=request.form['name'],
            email=request.form['email'],
            message=request.form['message']
        )
        db.session.add(message)
        db.session.commit()

        # Send email notification
        msg = Message(
            'New Contact Form Submission',
            recipients=[app.config['MAIL_DEFAULT_SENDER']],
            body=f"""
            New message from your website:
            
            From: {message.name} <{message.email}>
            Message:
            {message.message}
            """
        )
        mail.send(msg)

        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"Error processing contact form: {str(e)}")
        return jsonify({'success': False, 'error': 'An error occurred. Please try again later.'}), 500

@app.context_processor
def inject_recaptcha_site_key():
    return dict(recaptcha_site_key=app.config['RECAPTCHA_SITE_KEY'])

if __name__ == '__main__':
    app.run(debug=True)
