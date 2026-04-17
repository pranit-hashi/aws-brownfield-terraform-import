"""
Simple User Data Application
A Flask application that takes user input and stores it in DynamoDB.
"""
import os
import json
import time
import logging
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta
from threading import Lock
from flask import Flask, request, jsonify, render_template, abort, g, make_response
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError, BotoCoreError

app = Flask(__name__)
app.logger.setLevel(logging.INFO)

# Configuration from environment variables
DYNAMODB_TABLE_NAME = os.environ.get('DYNAMODB_TABLE_NAME', 'demo-user-data')
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
ENABLE_UI_PREVIEW = os.environ.get('ENABLE_UI_PREVIEW', 'false').lower() == 'true'
MAX_SCAN_ITEMS = int(os.environ.get('MAX_SCAN_ITEMS', '1000'))

MAX_NAME_LENGTH = 120
MAX_EMAIL_LENGTH = 254
MAX_MESSAGE_LENGTH = 4000
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024  # 32KB request body cap for public demo safety

FORM_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get('FORM_RATE_LIMIT_WINDOW_SECONDS', '60'))
FORM_RATE_LIMIT_MAX_REQUESTS = int(os.environ.get('FORM_RATE_LIMIT_MAX_REQUESTS', '10'))

_form_rate_limit_store = defaultdict(deque)
_form_rate_limit_lock = Lock()

# Initialize DynamoDB client
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
table = dynamodb.Table(DYNAMODB_TABLE_NAME)


def get_client_ip():
    """Get the best-effort source IP for rate limiting and request logs."""
    x_forwarded_for = request.headers.get('X-Forwarded-For', '')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.remote_addr or 'unknown'


def check_form_rate_limit(client_key):
    """Apply a simple in-memory fixed-window limiter for public form posts."""
    now = time.time()
    window_start = now - FORM_RATE_LIMIT_WINDOW_SECONDS

    with _form_rate_limit_lock:
        timestamps = _form_rate_limit_store[client_key]

        while timestamps and timestamps[0] <= window_start:
            timestamps.popleft()

        if len(timestamps) >= FORM_RATE_LIMIT_MAX_REQUESTS:
            retry_after = max(1, int(timestamps[0] + FORM_RATE_LIMIT_WINDOW_SECONDS - now))
            return True, retry_after

        timestamps.append(now)
        return False, 0


@app.before_request
def set_request_context():
    """Track request ID and timing context for response headers and logs."""
    incoming_request_id = request.headers.get('X-Request-ID', '').strip()
    g.request_id = incoming_request_id[:128] if incoming_request_id else str(uuid.uuid4())
    g.request_start_time = time.perf_counter()


@app.after_request
def apply_security_headers(response):
    """Set security headers and emit structured request logs."""
    request_id = getattr(g, 'request_id', str(uuid.uuid4()))
    response.headers['X-Request-ID'] = request_id
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "img-src 'self' data:; "
        "style-src 'self'; "
        "font-src 'self'; "
        "script-src 'none'; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )

    started = getattr(g, 'request_start_time', None)
    duration_ms = round((time.perf_counter() - started) * 1000, 2) if started else None
    log_record = {
        'timestamp': datetime.utcnow().isoformat(timespec='seconds') + 'Z',
        'request_id': request_id,
        'method': request.method,
        'path': request.path,
        'status_code': response.status_code,
        'duration_ms': duration_ms,
        'client_ip': get_client_ip(),
    }
    app.logger.info(json.dumps(log_record, separators=(',', ':')))
    return response


def validate_submission_fields(name, email, message):
    """Validate required fields and enforce max lengths."""
    if not all([name, email, message]):
        return 'All fields are required.'
    if len(name) > MAX_NAME_LENGTH:
        return f'Name must be {MAX_NAME_LENGTH} characters or fewer.'
    if len(email) > MAX_EMAIL_LENGTH:
        return f'Email must be {MAX_EMAIL_LENGTH} characters or fewer.'
    if len(message) > MAX_MESSAGE_LENGTH:
        return f'Message must be {MAX_MESSAGE_LENGTH} characters or fewer.'
    return None

def render_page(items, message=None, message_type=None, values=None, data_source_label='DynamoDB-backed records'):
    """Render the primary page with optional status messaging and preserved form values."""
    if values is None:
        values = {'name': '', 'email': '', 'message': ''}
    return render_template(
        'index.html',
        items=items,
        message=message,
        message_type=message_type,
        values=values,
        data_source_label=data_source_label,
    )


def get_preview_items():
    """Return mock items for UI preview without requiring DynamoDB access."""
    now = datetime.utcnow()
    return [
        {
            'userId': 'preview-1',
            'createdAt': now.isoformat(timespec='seconds') + 'Z',
            'name': 'Avery Patel',
            'email': 'avery.patel@example.com',
            'message': 'Need a quick review of the new onboarding flow before the next release window.'
        },
        {
            'userId': 'preview-2',
            'createdAt': (now - timedelta(minutes=18)).isoformat(timespec='seconds') + 'Z',
            'name': 'Jordan Lee',
            'email': 'jordan.lee@example.com',
            'message': 'Please validate the updated access request copy and confirm the status treatment feels clear.'
        },
        {
            'userId': 'preview-3',
            'createdAt': (now - timedelta(hours=2, minutes=7)).isoformat(timespec='seconds') + 'Z',
            'name': 'Morgan Chen',
            'email': 'morgan.chen@example.com',
            'message': 'This sample entry exists only to preview the UI without AWS dependencies.'
        },
    ]


@app.route('/')
def index():
    """Display the form and recent submissions."""
    items = get_recent_items()
    return render_page(items)


@app.route('/preview')
def preview():
    """Render the UI with sample data and no AWS dependency."""
    if not ENABLE_UI_PREVIEW:
        abort(404)

    return render_page(
        get_preview_items(),
        message='Preview mode is using mock data only. Submission and persistence are intentionally not being verified here.',
        message_type='success',
        data_source_label='Preview sample data',
    )


@app.route('/submit', methods=['POST'])
def submit():
    """Handle form submission and store data in DynamoDB."""
    try:
        client_key = get_client_ip()
        is_limited, retry_after = check_form_rate_limit(client_key)
        if is_limited:
            response = make_response(
                render_page(
                    [],
                    message='Too many submissions from your IP. Please wait and try again.',
                    message_type='error',
                ),
                429,
            )
            response.headers['Retry-After'] = str(retry_after)
            return response

        name = request.form.get('name', '').strip()
        email = request.form.get('email', '').strip()
        message = request.form.get('message', '').strip()
        values = {'name': name, 'email': email, 'message': message}

        validation_error = validate_submission_fields(name, email, message)
        if validation_error:
            items = get_recent_items()
            return render_page(
                items,
                message=validation_error,
                message_type='error',
                values=values,
            )
        
        # Store in DynamoDB
        user_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        
        table.put_item(
            Item={
                'userId': user_id,
                'createdAt': created_at,
                'name': name,
                'email': email,
                'message': message
            }
        )
        
        items = get_recent_items()
        return render_page(
            items,
            message='Data submitted successfully!',
            message_type='success',
        )

    except (ClientError, BotoCoreError):
        app.logger.exception('DynamoDB error while saving submission')
        items = get_recent_items()
        return render_page(
            items,
            message='Unable to save data right now. Please try again in a moment.',
            message_type='error',
            values=values,
        )


@app.route('/api/submit', methods=['POST'])
def api_submit():
    """API endpoint for submitting data."""
    try:
        data = request.get_json(silent=True)
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        name = data.get('name', '').strip()
        email = data.get('email', '').strip()
        message = data.get('message', '').strip()

        validation_error = validate_submission_fields(name, email, message)
        if validation_error:
            return jsonify({'error': validation_error}), 400
        
        user_id = str(uuid.uuid4())
        created_at = datetime.utcnow().isoformat()
        
        table.put_item(
            Item={
                'userId': user_id,
                'createdAt': created_at,
                'name': name,
                'email': email,
                'message': message
            }
        )
        
        return jsonify({
            'success': True,
            'userId': user_id,
            'createdAt': created_at
        }), 201

    except (ClientError, BotoCoreError):
        app.logger.exception('DynamoDB error in api_submit')
        return jsonify({'error': 'Unable to save data right now'}), 500


@app.route('/api/data', methods=['GET'])
def api_get_data():
    """API endpoint to retrieve all data."""
    try:
        items = get_recent_items(limit=100)
        return jsonify({'items': items}), 200
    except (ClientError, BotoCoreError):
        app.logger.exception('DynamoDB error in api_get_data')
        return jsonify({'error': 'Unable to fetch data right now'}), 500


@app.route('/api/data/<user_id>', methods=['GET'])
def api_get_item(user_id):
    """API endpoint to retrieve a specific item."""
    try:
        response = table.query(
            KeyConditionExpression=Key('userId').eq(user_id)
        )
        items = response.get('Items', [])
        
        if not items:
            return jsonify({'error': 'Item not found'}), 404
        
        return jsonify({'item': items[0]}), 200

    except (ClientError, BotoCoreError):
        app.logger.exception('DynamoDB error in api_get_item')
        return jsonify({'error': 'Unable to fetch item right now'}), 500


@app.route('/health')
def health():
    """Health check endpoint for ALB."""
    return jsonify({'status': 'healthy', 'service': 'user-data-app'}), 200


@app.route('/ready')
def ready():
    """Readiness check endpoint."""
    try:
        # Check DynamoDB connectivity
        table.table_status
        return jsonify({'status': 'ready'}), 200
    except Exception:
        return jsonify({'status': 'not ready'}), 503


def get_recent_items(limit=10):
    """Get recent items from DynamoDB."""
    try:
        items = []
        scan_kwargs = {
            'ProjectionExpression': 'userId, createdAt, #n, email, #m',
            'ExpressionAttributeNames': {
                '#n': 'name',
                '#m': 'message',
            },
        }

        while True:
            response = table.scan(**scan_kwargs)
            items.extend(response.get('Items', []))

            if len(items) >= MAX_SCAN_ITEMS:
                items = items[:MAX_SCAN_ITEMS]
                break

            last_key = response.get('LastEvaluatedKey')
            if not last_key:
                break

            scan_kwargs['ExclusiveStartKey'] = last_key

        # Sort by createdAt descending and return requested limit.
        items.sort(key=lambda x: x.get('createdAt', ''), reverse=True)
        return items[:limit]
    except (ClientError, BotoCoreError):
        app.logger.exception('Error fetching recent items')
        return []


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
