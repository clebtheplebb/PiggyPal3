from flask import Flask, jsonify, request, render_template, session, redirect, url_for, flash, g
from plaid_link import PlaidLinkSetup
from plaid_transactions import PlaidClient
import os
from datetime import timedelta, date, datetime
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
import google.generativeai as genai
import json
import certifi
from gamification import GamificationSystem, CharacterClass, CharacterLevel

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Required for session management

# Add abs filter to Jinja2 environment
app.jinja_env.filters['abs'] = abs

# Initialize services
plaid_link = PlaidLinkSetup()
plaid_client = PlaidClient()
gamification = GamificationSystem()
gamification.load_state("gamification_state.json")

# MongoDB Atlas connection
client = MongoClient(os.getenv('MONGODB_URI'), 
                    tls=True,
                    tlsAllowInvalidCertificates=False,
                    tlsCAFile=certifi.where())
db = client['finance_app']
users = db['users']  # Store user authentication data
user_data = db['userData']  # Store user financial data

# Shop items
shop_items = {
    'Backgrounds': [
        {'id': 'forest_bg', 'name': 'Forest Background', 'description': 'A peaceful forest scene', 'cost': 5, 'image': 'forest_bg.jpeg'},
        {'id': 'desert_bg', 'name': 'Money Background', 'description': 'A vast desert landscape', 'cost': 5, 'image': 'desert_bg.jpeg'},
        {'id': 'money_bg', 'name': 'Desert Background', 'description': 'A background filled with coins', 'cost': 5, 'image': 'money_bg.jpeg'},
    ],
    'Outfits': [
        {'id': 'outfit1', 'name': 'Business Suit', 'description': 'A professional business suit', 'cost': 100},
        {'id': 'outfit2', 'name': 'Casual Wear', 'description': 'Comfortable casual clothing', 'cost': 50},
        {'id': 'outfit3', 'name': 'Athletic Gear', 'description': 'Sporty athletic clothing', 'cost': 75},
    ],
    'Accessories': [
        {'id': 'acc1', 'name': 'Smart Watch', 'description': 'Track your fitness and finances', 'cost': 150},
        {'id': 'acc2', 'name': 'Briefcase', 'description': 'Carry your important documents', 'cost': 80},
        {'id': 'acc3', 'name': 'Sunglasses', 'description': 'Look cool while managing money', 'cost': 60},
    ],
    'Pets': [
        {'id': 'pet1', 'name': 'Money Cat', 'description': 'A lucky cat that brings wealth', 'cost': 200},
        {'id': 'pet2', 'name': 'Piggy Bank', 'description': 'A cute piggy that helps you save', 'cost': 150},
        {'id': 'pet3', 'name': 'Golden Retriever', 'description': 'A loyal companion for your financial journey', 'cost': 250},
    ]
}

def analyze_transactions(transactions, savings_goal):
    """Analyze transactions and generate personalized daily quests using Gemini"""
    try:
        # Convert transactions to a format suitable for Gemini
        transaction_summary = {
            'total_spent': 0,
            'total_income': 0,
            'category_spending': {},
            'transactions': []
        }
        
        # Only consider last 30 days of transactions for monthly average
        for transaction in transactions:
            amount = float(transaction['amount'])
            if amount < 0:  # Expenses
                transaction_summary['total_spent'] += abs(amount)
                category = transaction.get('category', ['Uncategorized'])[0]
                transaction_summary['category_spending'][category] = transaction_summary['category_spending'].get(category, 0) + abs(amount)
            else:  # Income
                transaction_summary['total_income'] += amount
            
            transaction_summary['transactions'].append({
                'date': transaction['date'],
                'amount': amount,
                'category': transaction.get('category', ['Uncategorized'])[0],
                'name': transaction.get('name', '')
            })
        
        # If we have no transactions or spending data, return early with default values
        if not transactions or (transaction_summary['total_spent'] == 0 and transaction_summary['total_income'] == 0):
            return {
                "time_estimate": "Unable to calculate time estimate. Please add some transactions first.",
                "quests": [
                    {
                        "title": "Add Your Transactions",
                        "progress": 0,
                        "description": "Start by adding your daily transactions to get personalized savings goals"
                    },
                    {
                        "title": "Set a Savings Goal",
                        "progress": 0,
                        "description": f"You've set a goal to save ${savings_goal}. Let's work towards it!"
                    },
                    {
                        "title": "Track Your Spending",
                        "progress": 0,
                        "description": "Record your expenses for better financial insights"
                    }
                ]
            }
        
        # Prepare prompt for Gemini
        prompt = f"""
        Analyze the following financial data and provide personalized savings recommendations:
        
        Monthly Income: ${transaction_summary['total_income']:.2f}
        Monthly Expenses: ${transaction_summary['total_spent']:.2f}
        Savings Goal: ${savings_goal:.2f}
        
        Top Spending Categories:
        {json.dumps(transaction_summary['category_spending'], indent=2)}
        
        Recent Transactions:
        {json.dumps(transaction_summary['transactions'][-5:], indent=2)}
        
        Please provide:
        1. A time estimate to reach the savings goal
        2. Three personalized daily quests to help achieve the goal
        3. Specific recommendations for reducing expenses in the top spending categories
        
        Format the response as a JSON object with 'time_estimate' and 'quests' fields.
        Each quest should have 'title', 'progress', and 'description' fields.
        """
        
        # Get AI-generated insights
        response = model.generate_content(prompt)
        try:
            insights = json.loads(response.text)
            return insights
        except json.JSONDecodeError:
            # Fallback to traditional analysis if AI response is invalid
            return generate_fallback_insights(transaction_summary, savings_goal)
        
    except Exception as e:
        print(f"Error in analyze_transactions: {str(e)}")
        return generate_fallback_insights(transaction_summary, savings_goal)

def generate_fallback_insights(transaction_summary, savings_goal):
    """Generate insights using traditional analysis when AI is unavailable"""
    monthly_expenses = transaction_summary['total_spent']
    monthly_income = transaction_summary['total_income']
    
    # Calculate potential savings (20% from income and 20% from expense reduction)
    income_savings = monthly_income * 0.20
    expense_savings = monthly_expenses * 0.20
    total_potential_savings = income_savings + expense_savings
    
    # Split savings between goal and emergency fund
    goal_savings = total_potential_savings * 0.5
    emergency_savings = total_potential_savings * 0.5
    
    # Calculate time to reach goal
    if goal_savings > 0:
        months_to_goal = savings_goal / goal_savings
        years = int(months_to_goal / 12)
        remaining_months = int(months_to_goal % 12)
        
        time_parts = []
        if years > 0:
            time_parts.append(f"{years} year{'s' if years > 1 else ''}")
        if remaining_months > 0:
            time_parts.append(f"{remaining_months} month{'s' if remaining_months > 1 else ''}")
        
        time_str = " and ".join(time_parts)
        time_estimate = (
            f"Based on your current income of ${monthly_income:.2f}/month and expenses of ${monthly_expenses:.2f}/month, "
            f"saving 20% of income (${income_savings:.2f}/month) and reducing expenses by 20% (${expense_savings:.2f}/month) "
            f"would take {time_str} to reach your goal of ${savings_goal:.2f}. "
            f"You'll also build an emergency fund of ${emergency_savings:.2f}/month."
        )
    else:
        time_estimate = "Unable to calculate time estimate. Please add your regular income and expenses."
    
    # Sort categories by spending
    sorted_categories = sorted(transaction_summary['category_spending'].items(), key=lambda x: x[1], reverse=True)
    
    # Create quests based on top spending categories
    quests = []
    
    # Add income-based quest
    daily_income_savings = income_savings / 30
    quests.append({
        "title": "Income Savings",
        "progress": 0,
        "description": f"Save ${daily_income_savings:.2f} from today's income (20% of income)"
    })
    
    # Add expense reduction quests
    for category, amount in sorted_categories[:2]:
        daily_category_savings = (amount * 0.2) / 30
        quests.append({
            "title": f"Save on {category}",
            "progress": 0,
            "description": f"Target saving ${daily_category_savings:.2f} today on {category}"
        })
    
    # Add generic quest if needed
    while len(quests) < 3:
        quests.append({
            "title": "Track Your Spending",
            "progress": 0,
            "description": "Record all your expenses today for better insights"
        })
    
    return {
        "time_estimate": time_estimate,
        "quests": quests[:3]
    }

def store_user_financial_data(user_id, access_token):
    # Check if user already has financial data
    existing_data = user_data.find_one({'user_id': user_id})
    
    if existing_data and 'transactions' in existing_data and existing_data['transactions']:
        # If user has existing transactions, only update the access token if needed
        if existing_data.get('access_token') != access_token:
            user_data.update_one(
                {'user_id': user_id},
                {'$set': {'access_token': access_token}}
            )
        return
    
    # Get transactions and balances for new accounts
    end_date = date.today()
    start_date = end_date - timedelta(days=30)
    transactions = plaid_client.get_transactions(access_token, start_date, end_date)
    balances = plaid_client.get_balances(access_token)
    
    # Convert date objects to strings in transactions
    processed_transactions = []
    for transaction in transactions:
        processed_transaction = transaction.copy()
        if 'date' in processed_transaction:
            processed_transaction['date'] = str(processed_transaction['date'])
        processed_transactions.append(processed_transaction)
    
    # Store the data
    user_data.update_one(
        {'user_id': user_id},
        {
            '$set': {
                'access_token': access_token,
                'last_updated': str(date.today()),
                'transactions': processed_transactions,
                'balances': balances,
                'completed_quests': [],
                'current_quests': [],
                'savings_goal': 1000,  # Default savings goal
                'current_savings': 0,
                'emergency_fund': 0
            }
        },
        upsert=True
    )

def check_and_refresh_quests(user_id):
    """Check if quests need to be refreshed and update them if necessary"""
    user = users.find_one({'_id': ObjectId(user_id)})
    if not user:
        return None
    
    # Get current date at midnight
    today = date.today()
    
    # Check if we have a last refresh date
    last_refresh = user.get('last_quest_refresh')
    if last_refresh:
        last_refresh_date = date.fromisoformat(last_refresh)
        if last_refresh_date == today:
            return None  # Quests already refreshed today
    
    # Get user's financial data
    user_financial_data = user_data.find_one({'user_id': user_id})
    if not user_financial_data or 'transactions' not in user_financial_data:
        return None
    
    # Get transactions and generate new quests
    transactions = user_financial_data['transactions']
    savings_goal = user.get('savings_goal', 1000)
    goals = analyze_transactions(transactions, savings_goal)
    
    # Update user with new quests and refresh date
    users.update_one(
        {'_id': ObjectId(user_id)},
        {
            '$set': {
                'last_quest_refresh': str(today),
                'completed_quests': [],  # Reset completed quests
                'current_quests': goals['quests']  # Store current quests
            }
        }
    )
    
    return goals['quests']

@app.before_request
def before_request():
    if 'user_id' in session:
        g.character = gamification.get_character(session['user_id'])
        if not g.character:
            # Create a character if one doesn't exist
            g.character = gamification.create_character(
                user_id=session['user_id'],
                name=session['user_id'],
                character_class=CharacterClass.SAVER
            )
            gamification.save_state("gamification_state.json")
    else:
        g.character = None

@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Check if user already has a bank connected
    user_financial_data = user_data.find_one({'user_id': session['user_id']})
    has_bank = user_financial_data and 'access_token' in user_financial_data
    
    # Get character data
    character = gamification.get_character(session['user_id'])
    
    # Update login streak
    if character:
        now = datetime.now()
        if (now - character.last_login).days >= 1:
            character.streak += 1
        else:
            character.streak = 1
        character.last_login = now
        gamification.save_state("gamification_state.json")
    
    # Create a new link token for Plaid
    link_token = plaid_link.create_link_token(session['user_id'])
    
    return render_template('index.html', 
                         link_token=link_token,
                         has_bank=has_bank,
                         bank_name=user_financial_data.get('bank_name', '') if user_financial_data else '',
                         character=character)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        # Check MongoDB for user
        user = users.find_one({'email': email})
        
        if user and check_password_hash(user['password'], password):
            user_id = str(user['_id'])
            session['user_id'] = user_id
            
            # Check if user has existing financial data
            user_financial_data = user_data.find_one({'user_id': user_id})
            
            if user_financial_data and 'access_token' in user_financial_data:
                # Update the user's financial data
                store_user_financial_data(user_id, user_financial_data['access_token'])
                return redirect(url_for('show_transactions'))
            
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid email or password')
    
    return render_template('login.html')

@app.route('/create_account', methods=['GET', 'POST'])
def create_account():
    if request.method == 'GET':
        return render_template('create_account.html')
    
    # Handle POST request
    email = request.form['email']
    password = request.form['password']
    confirm_password = request.form['confirmPassword']
    
    if password != confirm_password:
        return render_template('create_account.html', error='Passwords do not match')
    
    # Check if email already exists
    if users.find_one({'email': email}):
        return render_template('create_account.html', error='Email already exists')
    
    try:
        # Create user in authentication database
        result = users.insert_one({
            'email': email,
            'password': generate_password_hash(password)
        })
        
        # Create initial financial data record
        user_id = str(result.inserted_id)
        user_data.insert_one({
            'user_id': user_id,
            'savings_goal': 1000,
            'current_savings': 0,
            'emergency_fund': 0,
            'transactions': [],
            'balances': {},
            'completed_quests': [],
            'current_quests': []
        })
        
        # Create character for the new user
        try:
            character = gamification.create_character(
                user_id=user_id,
                name="Piggy",  # Set default name to Piggy
                character_class=CharacterClass.SAVER
            )
            gamification.assign_missions(user_id)
            gamification.assign_challenge(user_id)
            gamification.save_state("gamification_state.json")
        except Exception as e:
            print(f"Error creating character: {e}")
        
        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('login'))
    except Exception as e:
        print(f"Error creating account: {e}")
        return render_template('create_account.html', error='An error occurred while creating your account')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/missions')
def missions():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    character = gamification.get_character(user_id)
    
    if not character:
        return redirect(url_for('index'))
    
    # Get user's financial data
    user_financial_data = user_data.find_one({'user_id': user_id})
    if not user_financial_data:
        return redirect(url_for('index'))
    
    # Only generate new quests if there are no active missions
    if not character.active_missions:
        # Get transactions and generate quests
        transactions = user_financial_data.get('transactions', [])
        savings_goal = user_financial_data.get('savings_goal', 1000)
        goals = analyze_transactions(transactions, savings_goal)
        
        # Convert quests to missions format
        missions_list = []
        for quest in goals['quests']:
            mission = {
                'id': str(ObjectId()),
                'title': quest['title'],
                'description': quest['description'],
                'progress': quest['progress'],
                'is_completed': quest.get('completed', False),
                'mission_type': {'name': 'Daily Quest'},
                'reward_exp': 5,
                'reward_coins': 5
            }
            missions_list.append(mission)
        
        # Update character's active missions
        character.active_missions = missions_list
    
    # Ensure character has coins attribute
    if not hasattr(character, 'coins'):
        character.coins = 0
    
    # Save character state
    gamification.save_state("gamification_state.json")
    
    return render_template('missions.html', 
                         character=character,
                         financial_data=user_financial_data)

@app.route('/shop')
def shop():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    character = gamification.get_character(user_id)
    
    if not character:
        return redirect(url_for('index'))
    
    # Get user's financial data
    user_financial_data = user_data.find_one({'user_id': user_id})
    
    # Ensure character has coins attribute
    if not hasattr(character, 'coins'):
        character.coins = 0
        gamification.save_state("gamification_state.json")
    
    # Ensure character has inventory attribute
    if not hasattr(character, 'inventory'):
        character.inventory = []
        gamification.save_state("gamification_state.json")
    
    return render_template('shop.html', 
                         character=character, 
                         shop_items=shop_items,
                         financial_data=user_financial_data)

@app.route('/purchase/<item_id>', methods=['POST'])
def purchase(item_id):
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    
    user_id = session['user_id']
    character = gamification.get_character(user_id)
    
    if not character:
        return jsonify({'status': 'error', 'message': 'Character not found'}), 404
    
    # Find the item in shop_items
    item = None
    for category in shop_items.values():
        for shop_item in category:
            if shop_item['id'] == item_id:
                item = shop_item
                break
        if item:
            break
    
    if not item:
        return jsonify({'status': 'error', 'message': 'Item not found'}), 404
    
    # Check if already owned
    if item_id in character.inventory:
        return jsonify({'status': 'error', 'message': 'Item already owned'}), 400
    
    if character.coins < item['cost']:
        return jsonify({'status': 'error', 'message': 'Not enough coins'}), 400
    
    # Purchase the item
    character.coins -= item['cost']
    character.inventory.append(item_id)
    
    # Save the updated character state
    gamification.save_state("gamification_state.json")
    
    return jsonify({
        'status': 'success',
        'message': f'Successfully purchased {item["name"]}!',
        'coins': character.coins,
        'item_id': item_id
    })

@app.route('/update_progress', methods=['POST'])
def update_progress():
    if 'user_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    user_id = session['user_id']
    character = gamification.get_character(user_id)
    
    if not character:
        return jsonify({"error": "Character not found"}), 404
    
    # Get user data from request
    user_data_request = request.json
    
    # Get current financial data
    user_financial_data = user_data.find_one({'user_id': user_id})
    if user_financial_data:
        # Combine financial data with request data
        financial_data = {
            'savings': user_financial_data.get('current_savings', 0),
            'emergency_fund': user_financial_data.get('emergency_fund', 0),
            'transactions': len(user_financial_data.get('transactions', [])),
            'completed_quests': len(user_financial_data.get('completed_quests', [])),
            **user_data_request  # Add any additional data from the request
        }
    else:
        financial_data = user_data_request
    
    # Update progress
    results = gamification.update_user_progress(user_id, financial_data)
    
    # Save state
    gamification.save_state("gamification_state.json")
    
    return jsonify(results)

@app.route('/exchange_public_token', methods=['POST'])
def exchange_public_token():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    public_token = request.json['public_token']
    access_token = plaid_link.exchange_public_token(public_token)
    
    if access_token:
        # Check if this bank account is already linked to another user
        existing_user = user_data.find_one({'access_token': access_token})
        if existing_user and existing_user['user_id'] != session['user_id']:
            return jsonify({
                'status': 'error',
                'message': 'This bank account is already linked to another user'
            }), 400
        
        # Store the access token in session
        session['access_token'] = access_token
        
        # Store the financial data
        store_user_financial_data(session['user_id'], access_token)
        
        return jsonify({'status': 'success'})
    
    return jsonify({'status': 'error', 'message': 'Failed to exchange token'}), 400

@app.route('/transactions', methods=['GET', 'POST'])
def show_transactions():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    # Get stored transactions from database
    user_financial_data = user_data.find_one({'user_id': session['user_id']})
    
    if not user_financial_data:
        return render_template('error.html', message='No financial data available')
    
    # Process and sort transactions
    processed_transactions = []
    for t in user_financial_data.get('transactions', []):
        processed_t = t.copy()
        processed_t['amount'] = float(t['amount'])
        processed_t['abs_amount'] = abs(float(t['amount']))
        processed_transactions.append(processed_t)
    
    # Sort transactions by date in descending order
    transactions = sorted(
        processed_transactions,
        key=lambda x: x['date'],
        reverse=True
    )
    
    # Get financial data
    savings_goal = user_financial_data.get('savings_goal', 1000)
    current_savings = user_financial_data.get('current_savings', 0)
    emergency_fund = user_financial_data.get('emergency_fund', 0)
    balances = user_financial_data.get('balances', {})
    
    # Update savings goal if POST request
    if request.method == 'POST':
        savings_goal = float(request.form.get('savings_goal', savings_goal))
        user_data.update_one(
            {'user_id': session['user_id']},
            {'$set': {'savings_goal': savings_goal}}
        )
    
    # Calculate progress percentages
    savings_percentage = min(100, (current_savings / savings_goal * 100) if savings_goal > 0 else 0)
    emergency_percentage = min(100, (emergency_fund / (savings_goal * 0.5) * 100) if savings_goal > 0 else 0)
    
    # Calculate financial analysis
    total_income = 0
    total_expenses = 0
    category_spending = {}
    
    for transaction in transactions:
        amount = float(transaction['amount'])
        if amount > 0:
            total_income += amount
        else:
            total_expenses += abs(amount)
            category = transaction.get('category', ['Uncategorized'])[0]
            category_spending[category] = category_spending.get(category, 0) + abs(amount)
    
    # Calculate monthly averages
    monthly_income = total_income / 30 if total_income > 0 else 0
    monthly_expenses = total_expenses / 30 if total_expenses > 0 else 0
    
    # Calculate time to reach goal
    monthly_savings = monthly_income - monthly_expenses
    months_to_goal = savings_goal / monthly_savings if monthly_savings > 0 else float('inf')
    
    # Format financial summary
    financial_summary = f"""
    Monthly Income: ${monthly_income:.2f}
    Monthly Expenses: ${monthly_expenses:.2f}
    Monthly Savings: ${monthly_savings:.2f}
    
    Top Spending Categories:
    """
    for category, amount in sorted(category_spending.items(), key=lambda x: x[1], reverse=True)[:3]:
        financial_summary += f"\n{category}: ${amount:.2f}"
    
    time_estimate = f"Based on your current savings rate, it will take approximately {int(months_to_goal)} months to reach your goal." if months_to_goal != float('inf') else "Unable to calculate time estimate with current savings rate."
    
    return render_template('transactions.html',
                         transactions=transactions, 
                         savings_goal=savings_goal,
                         current_savings=current_savings,
                         emergency_fund=emergency_fund,
                         savings_percentage=savings_percentage,
                         emergency_percentage=emergency_percentage,
                         balances=balances,
                         goals={
                             'time_estimate': time_estimate,
                             'financial_summary': financial_summary
                         })

@app.route('/complete_quest', methods=['POST'])
def complete_quest():
    if 'user_id' not in session:
        return jsonify({"error": "Not logged in"}), 401
    
    try:
        data = request.get_json()
        if not data:
            print("Error: No JSON data received")
            return jsonify({"error": "Invalid request format"}), 400
            
        quest_id = data.get('quest_id')
        print(f"Received quest_id: {quest_id}")
        
        if not quest_id:
            print("Error: No quest_id provided")
            return jsonify({"error": "Quest ID is required"}), 400
        
        user_id = session['user_id']
        character = gamification.get_character(user_id)
        
        if not character:
            print(f"Error: Character not found for user_id: {user_id}")
            return jsonify({"error": "Character not found"}), 404
        
        # Find the quest in active missions
        quest = None
        for mission in character.active_missions:
            # Handle both dictionary and Mission object cases
            mission_id = mission.get('id') if isinstance(mission, dict) else str(mission.id)
            print(f"Checking mission_id: {mission_id} against quest_id: {quest_id}")
            if mission_id == quest_id:
                quest = mission
                break
        
        if not quest:
            print(f"Error: Quest not found with id: {quest_id}")
            return jsonify({"error": "Quest not found"}), 404
        
        # Handle both dictionary and Mission object cases
        is_completed = quest.get('is_completed', False) if isinstance(quest, dict) else quest.is_completed
        if is_completed:
            print(f"Error: Quest already completed: {quest_id}")
            return jsonify({"error": "Quest already completed"}), 400
        
        # Get the quest description
        description = quest.get('description') if isinstance(quest, dict) else quest.description
        
        # Extract the savings amount from the description
        import re
        savings_match = re.search(r'\$(\d+(?:\.\d{2})?)', description)
        if savings_match:
            savings_amount = float(savings_match.group(1))
        else:
            # If no dollar amount found, use a default value
            savings_amount = 5.0
        
        # Mark quest as completed
        if isinstance(quest, dict):
            quest['is_completed'] = True
            quest['progress'] = 100
            reward_coins = quest.get('reward_coins', 5)
        else:
            quest.is_completed = True
            quest.progress = 100
            reward_coins = quest.reward_coins
        
        # Award coins
        character.coins += reward_coins
        
        # Update user's financial data with the savings
        user_financial_data = user_data.find_one({'user_id': user_id})
        if user_financial_data:
            # Split the savings between savings and emergency fund (70% savings, 30% emergency)
            savings_portion = savings_amount * 0.5
            emergency_portion = savings_amount * 0.5
            
            # Update the financial data
            user_data.update_one(
                {'user_id': user_id},
                {
                    '$inc': {
                        'current_savings': savings_portion,
                        'emergency_fund': emergency_portion
                    }
                }
            )
        
        # Save character state
        gamification.save_state("gamification_state.json")
        
        return jsonify({
            "status": "success",
            "coins": character.coins,
            "savings_added": savings_portion,
            "emergency_added": emergency_portion,
            "message": "Quest completed successfully!"
        })
        
    except Exception as e:
        print(f"Error completing quest: {str(e)}")
        return jsonify({"error": f"An error occurred: {str(e)}"}), 500

@app.route('/add_transaction', methods=['POST'])
def add_transaction():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    
    try:
        data = request.json
        user_id = session['user_id']
        
        # Get the user's financial data
        user_financial_data = user_data.find_one({'user_id': user_id})
        if not user_financial_data:
            return jsonify({'status': 'error', 'message': 'No financial data found'}), 404
        
        # Create new transaction with proper formatting
        new_transaction = {
            'date': data['date'],
            'name': data['name'],
            'amount': float(data['amount']),
            'category': data['category'],
            'transaction_id': str(ObjectId()),  # Generate a unique ID
            'pending': False,
            'manual': True  # Flag to indicate this is a manually added transaction
        }
        
        # Add the new transaction to the transactions list
        transactions = user_financial_data.get('transactions', [])
        transactions.append(new_transaction)
        
        # Update the user's data in the database
        user_data.update_one(
            {'user_id': user_id},
            {'$set': {'transactions': transactions}}
        )
        
        return jsonify({'status': 'success'})
    except Exception as e:
        print(f"Error adding transaction: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/character')
def character():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    character = gamification.get_character(session['user_id'])
    if not character:
        return redirect(url_for('login'))
    
    return render_template('character.html', character=character, shop_items=shop_items)

@app.route('/change_character_name', methods=['POST'])
def change_character_name():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    
    data = request.get_json()
    new_name = data.get('new_name')
    
    if not new_name:
        return jsonify({'status': 'error', 'message': 'No name provided'}), 400
    
    try:
        character = gamification.get_character(session['user_id'])
        if character:
            character.name = new_name
            gamification.save_state("gamification_state.json")
            return jsonify({'status': 'success'})
        else:
            return jsonify({'status': 'error', 'message': 'Character not found'}), 404
    except Exception as e:
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/change_background', methods=['POST'])
def change_background():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    
    user_id = session['user_id']
    character = gamification.get_character(user_id)
    
    if not character:
        return jsonify({'status': 'error', 'message': 'Character not found'}), 404
    
    data = request.get_json()
    background_id = data.get('background_id')
    
    if not background_id:
        return jsonify({'status': 'error', 'message': 'No background ID provided'}), 400
    
    # Check if the background is owned
    if background_id not in character.inventory:
        return jsonify({'status': 'error', 'message': 'Background not owned'}), 400
    
    # Update the character's current background
    character.current_background = background_id
    
    # Save the updated character state
    gamification.save_state("gamification_state.json")
    
    return jsonify({
        'status': 'success',
        'message': 'Background changed successfully'
    })

@app.errorhandler(404)
def not_found_error(error):
    return render_template('error.html', 
                         error_title='Page Not Found',
                         error_message='The page you are looking for does not exist.'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('error.html',
                         error_title='Internal Server Error',
                         error_message='An unexpected error has occurred.'), 500

if __name__ == '__main__':
    app.run(debug=True, port=8000) 