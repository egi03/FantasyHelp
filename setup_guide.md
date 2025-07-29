# FPL Transfer Suggestions - Complete Setup Guide

This guide will help you set up the complete FPL Transfer Suggestions application with a Django backend and modern frontend.

## 📁 Project Structure

Your project should be organized as follows:

```
fantasyhelp/
├── backend/
│   ├── fantasyhelp/
│   │   ├── __init__.py
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── wsgi.py
│   │   └── asgi.py
│   ├── apps/
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── admin.py
│   │   │   ├── apps.py
│   │   │   ├── models.py
│   │   │   ├── views.py
│   │   │   ├── serializers.py
│   │   │   ├── permissions.py
│   │   │   ├── pagination.py
│   │   │   ├── middleware.py
│   │   │   ├── utils.py
│   │   │   ├── exceptions.py
│   │   │   ├── tests.py
│   │   │   └── migrations/
│   │   └── fpl/
│   │       ├── __init__.py
│   │       ├── admin.py
│   │       ├── apps.py
│   │       ├── models.py
│   │       ├── views.py
│   │       ├── serializers.py
│   │       ├── services.py
│   │       ├── tasks.py
│   │       ├── filters.py
│   │       ├── tests.py
│   │       ├── urls/
│   │       │   ├── __init__.py
│   │       │   └── v2.py
│   │       ├── management/
│   │       │   ├── __init__.py
│   │       │   └── commands/
│   │       │       ├── __init__.py
│   │       │       └── update_fpl_data.py
│   │       └── migrations/
│   │           └── __init__.py
│   ├── requirements.txt
│   ├── manage.py
│   └── db.sqlite3
├── frontend/
│   ├── index.html
│   ├── manifest.json
│   ├── sw.js
│   ├── css/
│   │   └── styles.css
│   ├── js/
│   │   ├── api.js
│   │   ├── components.js
│   │   └── app.js
│   └── assets/
│       ├── icons/
│       │   ├── favicon-16x16.png
│       │   ├── favicon-32x32.png
│       │   ├── apple-touch-icon.png
│       │   ├── icon-192x192.png
│       │   └── icon-512x512.png
│       └── screenshots/
│           ├── desktop.png
│           └── mobile.png
├── data/
│   └── init.py
├── Checklist.md
└── README.md
```

## 🚀 Backend Setup

### 1. Install Python Dependencies

First, create a virtual environment and install the requirements:

```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Database Setup

Run migrations to set up the database:

```bash
python manage.py makemigrations
python manage.py migrate
```

Create a superuser for admin access:

```bash
python manage.py createsuperuser
```

### 3. Configure Settings

Create a `.env` file in the backend directory with your configuration:

```env
SECRET_KEY=your-secret-key-here
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000

# FPL API Settings
FPL_API_RATE_LIMIT=100
FPL_API_TIMEOUT=30
FPL_API_RETRY_ATTEMPTS=3
FPL_API_CACHE_TTL=300

# Data Update Settings
PLAYER_UPDATE_INTERVAL=3600
DATA_BATCH_SIZE=100
MAX_CONCURRENT_UPDATES=5
```

### 4. Load Initial Data

Run the management command to populate initial FPL data:

```bash
python manage.py update_fpl_data
```

### 5. Start the Development Server

```bash
python manage.py runserver
```

The API will be available at `http://localhost:8000/api/v2/`

## 🎨 Frontend Setup

### 1. Serve the Frontend

You can serve the frontend using any static file server. Here are several options:

#### Option A: Python's Built-in Server

```bash
cd frontend
python -m http.server 3000
```

#### Option B: Node.js http-server

```bash
cd frontend
npx http-server -p 3000 -c-1
```

#### Option C: Live Server (VS Code Extension)

If you're using VS Code, install the "Live Server" extension and right-click on `index.html` → "Open with Live Server"

### 2. Configure API Endpoint

The frontend is configured to use `/api/v2` as the base URL. If your backend is running on a different port, update the `API_CONFIG.baseURL` in `js/api.js`:

```javascript
const API_CONFIG = {
    baseURL: 'http://localhost:8000/api/v2',  // Update this if needed
    // ... other config
};
```

### 3. PWA Setup (Optional)

For full PWA functionality, you'll need to:

1. Create the required icon files in `assets/icons/`
2. Add actual screenshot images in `assets/screenshots/`
3. Serve the app over HTTPS in production

## 🔧 Configuration

### Backend Configuration

Key settings in `settings.py`:

```python
# CORS settings for frontend communication
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# API throttling rates
REST_FRAMEWORK = {
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour'
    }
}

# FPL API settings
FPL_API_SETTINGS = {
    'BASE_URL': 'https://fantasy.premierleague.com/api',
    'RATE_LIMIT': 100,
    'TIMEOUT': 30,
    'RETRY_ATTEMPTS': 3,
    'CACHE_TTL': 300,
}
```

### Frontend Configuration

Key configurations in `js/api.js`:

```javascript
const API_CONFIG = {
    baseURL: '/api/v2',
    timeout: 30000,
    retryAttempts: 3,
    retryDelay: 1000
};
```

## 🚦 Usage

### 1. Load Your FPL Team

1. Go to the Dashboard
2. Enter your FPL team ID (found in the URL when viewing your team on the official FPL site)
3. Click "Load Team"

### 2. Generate Transfer Suggestions

1. After loading your team, click "Generate Suggestions"
2. View AI-powered transfer recommendations
3. Compare players and see detailed analysis

### 3. Explore Players

1. Use the Players page to search and filter players
2. Compare different players side by side
3. View detailed player statistics and performance history

### 4. View Analytics

1. Check the Analytics page for insights
2. See top performers, best value players, and position analysis
3. Track trends and form guides

## 🔌 API Endpoints

The backend provides a comprehensive REST API:

### Core endpoints:
- `GET /api/v2/` - API root with documentation
- `GET /api/v2/teams/` - List all Premier League teams
- `GET /api/v2/players/` - List and search players
- `POST /api/v2/players/search/` - Advanced player search
- `POST /api/v2/players/compare/` - Compare multiple players

### Team Management:
- `POST /api/v2/user-teams/load_team/` - Load FPL team data
- `GET /api/v2/user-teams/{id}/analysis/` - Get team analysis

### Suggestions:
- `POST /api/v2/suggestions/generate/` - Generate transfer suggestions
- `GET /api/v2/suggestions/` - List suggestions

### Analytics:
- `GET /api/v2/analytics/` - Analytics overview
- `GET /api/v2/analytics/players/` - Player analytics
- `GET /api/v2/analytics/positions/` - Position analytics

### Data Management:
- `POST /api/v2/sync/players/` - Sync player data
- `GET /api/v2/health/` - Health check

## 🧪 Testing

### Backend Tests

```bash
cd backend
python manage.py test
```

### Frontend Testing

The frontend includes error handling and can be tested by:

1. Checking browser console for errors
2. Testing offline functionality (service worker)
3. Verifying API integration
4. Testing responsive design on different devices

## 🔒 Security Considerations

### For Development:
- The current setup uses CORS settings suitable for development
- SQLite is used for simplicity
- Debug mode is enabled

### For Production:
- Change `DEBUG = False`
- Use PostgreSQL database
- Configure proper CORS origins
- Add HTTPS
- Set up proper caching (Redis)
- Configure Celery for async tasks
- Add proper logging and monitoring

## 📱 Progressive Web App (PWA)

The frontend is configured as a PWA with:

- Service Worker for offline functionality
- Web App Manifest for installation
- Responsive design
- Cached resources for fast loading

To test PWA features:
1. Serve over HTTPS (required for full PWA features)
2. Open Chrome DevTools → Application → Service Workers
3. Test offline functionality by going offline in DevTools

## 🚀 Deployment

### Backend Deployment (Example with Heroku):

1. Create `Procfile`:
```
web: gunicorn fantasyhelp.wsgi:application
```

2. Add `django-heroku` to requirements.txt

3. Update settings for production

### Frontend Deployment:

The frontend can be deployed to any static hosting service:
- Netlify
- Vercel
- GitHub Pages
- AWS S3 + CloudFront

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is for educational purposes. Please respect the Fantasy Premier League Terms of Service when using their API.

## 🆘 Troubleshooting

### Common Issues:

1. **CORS Errors**: Check CORS_ALLOWED_ORIGINS in settings.py
2. **FPL API Rate Limits**: Implement proper rate limiting and caching
3. **Database Issues**: Ensure migrations are run
4. **Frontend API Calls Failing**: Check the API base URL configuration

### Getting Help:

- Check the browser console for frontend errors
- Check Django logs for backend errors
- Ensure all dependencies are installed
- Verify environment variables are set correctly

---

**Happy FPL managing! 🏆⚽**