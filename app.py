import os
import sys
import logging
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from flask_migrate import Migrate
from datetime import datetime
from slugify import slugify
import markdown2
from werkzeug.utils import secure_filename
from flask_wtf.csrf import CSRFProtect
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

# Initialize extensions
csrf = CSRFProtect()
db = SQLAlchemy()
migrate = Migrate()
mail = Mail()

def create_app():
    app = Flask(__name__)
    
    # Load environment variables
    load_dotenv()
    
    # Configure app
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'your-secret-key-here')
    db_path = os.getenv('DATABASE_PATH', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'blog.db'))
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 587))
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')
    app.config['RECAPTCHA_SITE_KEY'] = os.getenv('RECAPTCHA_SITE_KEY')
    app.config['RECAPTCHA_SECRET_KEY'] = os.getenv('RECAPTCHA_SECRET_KEY')
    app.config['UPLOAD_FOLDER'] = 'static/uploads'
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    
    # Initialize extensions with app
    csrf.init_app(app)
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)
    
    return app

app = create_app()

# Ensure upload directory exists
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.logger.info(f"Upload directory created at {UPLOAD_FOLDER}")

# Ensure database directory exists
DB_DIR = os.path.dirname(os.path.abspath(__file__))
os.makedirs(DB_DIR, exist_ok=True)
app.logger.info(f"Database directory ensured at {DB_DIR}")

# Create database tables
with app.app_context():
    try:
        db.create_all()
        app.logger.info("Database tables created successfully")
    except Exception as e:
        app.logger.error(f"Error initializing database: {str(e)}")
        app.logger.error("Failed to initialize database")

# Add whitenoise for static files
app.wsgi_app = WhiteNoise(app.wsgi_app, root='static/')

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

class AnonymousMessage(db.Model):
    __tablename__ = 'anonymous_message'
    id = db.Column(db.Integer, primary_key=True)
    chat_id = db.Column(db.String(64), nullable=False, index=True)  # Unique ID for each chat thread
    sender_name = db.Column(db.String(100), nullable=False)
    content = db.Column(db.Text, nullable=False)
    response = db.Column(db.Text, nullable=True)
    response_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_read = db.Column(db.Boolean, default=False)

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

@app.route('/chat')
def chat():
    if is_admin():
        # Admin sees list of all chats
        chats = db.session.query(
            AnonymousMessage.chat_id,
            AnonymousMessage.sender_name,
            db.func.count(AnonymousMessage.id).label('message_count'),
            db.func.max(AnonymousMessage.created_at).label('last_message')
        ).group_by(AnonymousMessage.chat_id, AnonymousMessage.sender_name).all()
        return render_template('admin_chats.html', chats=chats)
    return render_template('chat.html')

@app.route('/chat/<chat_id>')
def view_chat(chat_id):
    if not is_admin():
        return redirect(url_for('chat'))
    messages = AnonymousMessage.query.filter_by(chat_id=chat_id).order_by(AnonymousMessage.created_at).all()
    return render_template('chat.html', messages=messages, chat_id=chat_id)

@app.route('/api/messages/<chat_id>')
@csrf.exempt
def get_messages(chat_id):
    messages = AnonymousMessage.query.filter_by(chat_id=chat_id).order_by(AnonymousMessage.created_at).all()
    return jsonify([{
        'id': msg.id,
        'sender_name': msg.sender_name,
        'content': msg.content,
        'response': msg.response,
        'response_at': msg.response_at.strftime('%Y-%m-%d %H:%M:%S') if msg.response_at else None,
        'created_at': msg.created_at.strftime('%Y-%m-%d %H:%M:%S')
    } for msg in messages])

@app.route('/send_message', methods=['POST'])
@csrf.exempt
def send_message():
    try:
        data = request.form
        chat_id = data.get('chat_id')
        sender_name = data.get('sender_name', 'Anonymous')
        content = data.get('content')
        
        if not content:
            return jsonify({'error': 'Message content is required'}), 400
            
        message = AnonymousMessage(
            chat_id=chat_id,
            sender_name=sender_name,
            content=content
        )
        db.session.add(message)
        db.session.commit()
        
        return jsonify({
            'id': message.id,
            'chat_id': message.chat_id,
            'sender_name': message.sender_name,
            'content': message.content,
            'created_at': message.created_at.strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/respond/<int:message_id>', methods=['POST'])
@csrf.exempt
def respond_to_message(message_id):
    if not is_admin():
        return jsonify({'error': 'Unauthorized'}), 401
        
    message = AnonymousMessage.query.get_or_404(message_id)
    response_text = request.form.get('response')
    
    if not response_text:
        return jsonify({'error': 'Response is required'}), 400
        
    message.response = response_text
    message.response_at = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        'id': message.id,
        'response': message.response,
        'response_at': message.response_at.strftime('%Y-%m-%d %H:%M:%S')
    })

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        expected_password = os.getenv('ADMIN_PASSWORD')
        app.logger.info(f"Login attempt. Expected: {expected_password}, Received: {password}")
        
        if password == expected_password:
            response = make_response(redirect(url_for('chat')))
            response.set_cookie('admin_token', os.getenv('ADMIN_TOKEN'))
            return response
        flash('Invalid password', 'error')
    return render_template('admin_login.html')

@app.route('/admin_logout')
def admin_logout():
    response = make_response(redirect(url_for('chat')))
    response.delete_cookie('admin_token')
    return response

def is_admin():
    expected_token = os.getenv('ADMIN_TOKEN')
    received_token = request.cookies.get('admin_token')
    app.logger.info(f"Admin check. Expected: {expected_token}, Received: {received_token}")
    return received_token == expected_token

@app.context_processor
def inject_recaptcha_site_key():
    return dict(recaptcha_site_key=app.config['RECAPTCHA_SITE_KEY'])

def verify_recaptcha(response):
    """Verify reCAPTCHA response"""
    verify_url = 'https://www.google.com/recaptcha/api/siteverify'
    payload = {
        'secret': app.config['RECAPTCHA_SECRET_KEY'],
        'response': response
    }
    response = requests.post(verify_url, data=payload)
    return response.json().get('success', False)

if __name__ == '__main__':
    app.run(debug=True)
