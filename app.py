from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import openai
import os
from dotenv import load_dotenv
import json
from datetime import datetime
import sqlite3

# Load environment variables
load_dotenv()

app = Flask(__name__)
CORS(app, origins=["https://lambent-croquembouche-a5bdcb.netlify.app"])
# Serve HTML files          ← add from here
from flask import send_from_directory

@app.route('/home')
def index():
    return send_from_directory('.', 'index.html')

@app.route('/auth')
def auth():
    return send_from_directory('.', 'Auth.html')

@app.route('/history')
def history():
    return send_from_directory('.', 'History.html')
                               # ← to here

# Set your OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

# Set your OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')

# Database setup
DATABASE = 'career_guidance.db'

def get_db_connection():
    """Create a database connection"""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with required tables"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            education TEXT NOT NULL,
            percentage REAL NOT NULL,
            skills TEXT NOT NULL,
            interests TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Create recommendations table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS recommendations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            career TEXT NOT NULL,
            explanation TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database initialized successfully!")

# Initialize database when app starts
init_db()

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "AI Career Guide Backend is running!",
        "status": "success",
        "database": "connected"
    })

@app.route('/get-career-guidance', methods=['POST'])
def get_career_guidance():
    try:
        # Get data from request
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['name', 'education', 'percentage', 'skills', 'interests']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    "success": False,
                    "error": f"Missing required field: {field}"
                }), 400
        
        # Extract user data
        name = data['name']
        education = data['education']
        percentage = data['percentage']
        skills = data['skills']
        interests = data['interests']
        
        # Store user data in database
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO users (name, education, percentage, skills, interests)
            VALUES (?, ?, ?, ?, ?)
        ''', (name, education, percentage, json.dumps(skills), json.dumps(interests)))
        
        user_id = cursor.lastrowid
        conn.commit()
        
        # Create a detailed prompt for OpenAI
        prompt = f"""
        As an expert career counselor, analyze the following student profile and provide 3-4 personalized career recommendations with detailed explanations.

        Student Profile:
        - Name: {name}
        - Education Level: {education}
        - Academic Performance: {percentage}%
        - Skills: {', '.join(skills)}
        - Interests: {', '.join(interests)}

        Please provide career recommendations in the following JSON format:
        {{
            "career_recommendations": [
                {{
                    "career": "Career Title",
                    "explanation": "Detailed explanation of why this career is suitable, including how their skills and interests align, potential growth opportunities, and why their academic performance indicates success in this field."
                }}
            ]
        }}

        Consider:
        1. How their skills match the career requirements
        2. How their interests align with the work environment
        3. Their academic performance and its relevance
        4. Growth opportunities and market demand
        5. Specific reasons why they would excel in this field

        Make each explanation at least 3-4 sentences long and personalized to their specific profile.
        """
        
        # Make request to OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert career counselor with deep knowledge of various industries and career paths. Provide thoughtful, personalized career guidance."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.7
        )
        
        # Extract the response content
        ai_response = response.choices[0].message.content.strip()
        
        # Try to parse the JSON response
        try:
            career_data = json.loads(ai_response)
        except json.JSONDecodeError:
            # If JSON parsing fails, create a fallback response
            career_data = {
                "career_recommendations": [
                    {
                        "career": "Personalized Career Path",
                        "explanation": ai_response
                    }
                ]
            }
        
        # Store recommendations in database
        for recommendation in career_data.get('career_recommendations', []):
            cursor.execute('''
                INSERT INTO recommendations (user_id, career, explanation)
                VALUES (?, ?, ?)
            ''', (user_id, recommendation['career'], recommendation['explanation']))
        
        conn.commit()
        conn.close()
        
        # Add success flag and user_id
        career_data["success"] = True
        career_data["user_id"] = user_id
        career_data["message"] = "Data saved successfully!"
        
        return jsonify(career_data)
        
    except openai.error.OpenAIError as e:
        return jsonify({
            "success": False,
            "error": f"OpenAI API error: {str(e)}"
        }), 500
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Internal server error: {str(e)}"
        }), 500

@app.route('/get-user-history/<int:user_id>', methods=['GET'])
def get_user_history(user_id):
    """Retrieve user's previous recommendations"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get user details
        user = cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        
        if not user:
            return jsonify({
                "success": False,
                "error": "User not found"
            }), 404
        
        # Get recommendations
        recommendations = cursor.execute(
            'SELECT * FROM recommendations WHERE user_id = ? ORDER BY created_at DESC',
            (user_id,)
        ).fetchall()
        
        conn.close()
        
        return jsonify({
            "success": True,
            "user": {
                "id": user['id'],
                "name": user['name'],
                "education": user['education'],
                "percentage": user['percentage'],
                "skills": json.loads(user['skills']),
                "interests": json.loads(user['interests']),
                "created_at": user['created_at']
            },
            "recommendations": [
                {
                    "career": rec['career'],
                    "explanation": rec['explanation'],
                    "created_at": rec['created_at']
                }
                for rec in recommendations
            ]
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Error retrieving history: {str(e)}"
        }), 500

@app.route('/get-all-users', methods=['GET'])
def get_all_users():
    """Get all users (for admin purposes)"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        users = cursor.execute(
            'SELECT id, name, education, percentage, created_at FROM users ORDER BY created_at DESC'
        ).fetchall()
        
        conn.close()
        
        return jsonify({
            "success": True,
            "total_users": len(users),
            "users": [
                {
                    "id": user['id'],
                    "name": user['name'],
                    "education": user['education'],
                    "percentage": user['percentage'],
                    "created_at": user['created_at']
                }
                for user in users
            ]
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Error retrieving users: {str(e)}"
        }), 500

@app.route('/search-users', methods=['GET'])
def search_users():
    """Search users by name"""
    try:
        search_term = request.args.get('name', '')
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        users = cursor.execute(
            'SELECT * FROM users WHERE name LIKE ? ORDER BY created_at DESC',
            (f'%{search_term}%',)
        ).fetchall()
        
        conn.close()
        
        return jsonify({
            "success": True,
            "results": len(users),
            "users": [
                {
                    "id": user['id'],
                    "name": user['name'],
                    "education": user['education'],
                    "percentage": user['percentage'],
                    "skills": json.loads(user['skills']),
                    "interests": json.loads(user['interests']),
                    "created_at": user['created_at']
                }
                for user in users
            ]
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Error searching users: {str(e)}"
        }), 500

@app.route('/delete-user/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete a user and their recommendations"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Delete recommendations first (foreign key constraint)
        cursor.execute('DELETE FROM recommendations WHERE user_id = ?', (user_id,))
        
        # Delete user
        cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
        
        conn.commit()
        conn.close()
        
        return jsonify({
            "success": True,
            "message": "User deleted successfully"
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Error deleting user: {str(e)}"
        }), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        "status": "healthy",
        "service": "AI Career Guide Backend",
        "database": "connected"
    })

@app.route('/stats', methods=['GET'])
def get_stats():
    """Get database statistics"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        total_users = cursor.execute('SELECT COUNT(*) as count FROM users').fetchone()['count']
        total_recommendations = cursor.execute('SELECT COUNT(*) as count FROM recommendations').fetchone()['count']
        
        # Get most common careers recommended
        top_careers = cursor.execute('''
            SELECT career, COUNT(*) as count 
            FROM recommendations 
            GROUP BY career 
            ORDER BY count DESC 
            LIMIT 5
        ''').fetchall()
        
        conn.close()
        
        return jsonify({
            "success": True,
            "stats": {
                "total_users": total_users,
                "total_recommendations": total_recommendations,
                "top_careers": [
                    {"career": career['career'], "count": career['count']}
                    for career in top_careers
                ]
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": f"Error getting stats: {str(e)}"
        }), 500

if __name__ == '__main__':
    # Check if API key is set
    if not os.getenv('OPENAI_API_KEY'):
        print("Warning: OPENAI_API_KEY not found in environment variables.")
        print("Please set your OpenAI API key in a .env file or environment variable.")
    
    print("\n=== AI Career Guide Backend ===")
    print("Database: career_guidance.db")
    print("Starting server on http://0.0.0.0:5000")
    print("================================\n")
    
import os
port = int(os.environ.get("PORT", 5000))
app.run(host="0.0.0.0", port=port)