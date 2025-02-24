import os
from dotenv import load_dotenv
from app import app as application

# Load environment variables
load_dotenv()

# This is the WSGI entry point
if __name__ == '__main__':
    application.run()
