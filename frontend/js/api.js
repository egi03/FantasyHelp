// API Configuration
const API_CONFIG = {
    baseURL: 'http://localhost:8000/api/v2',
    timeout: 30000,
    retryAttempts: 3,
    retryDelay: 1000
};

// API Client Class
class APIClient {
    constructor(config = API_CONFIG) {
        this.baseURL = config.baseURL;
        this.timeout = config.timeout;
        this.retryAttempts = config.retryAttempts;
        this.retryDelay = config.retryDelay;

         const isLocal = window.location.hostname === 'localhost' || 
                       window.location.hostname === '127.0.0.1';
        
        if (isLocal) {
            this.baseURL = 'http://localhost:8000/api/v2';
        } else {
            this.baseURL = '/api/v2';
        }
        
        // Request interceptors
        this.requestInterceptors = [];
        this.responseInterceptors = [];

        this.defaultHeaders = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
        };
        
        // Add default request interceptor for headers
        this.addRequestInterceptor((config) => {
            config.headers = {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                ...config.headers
            };
            return config;
        });
    }

    addRequestInterceptor(interceptor) {
        this.requestInterceptors.push(interceptor);
    }

    addResponseInterceptor(interceptor) {
        this.responseInterceptors.push(interceptor);
    }

    async request(url, options = {}) {
        let config = {
            method: 'GET',
            headers: {},
            ...options,
            url: `${this.baseURL}${url}`
        };

        // Apply request interceptors
        for (const interceptor of this.requestInterceptors) {
            config = await interceptor(config);
        }

        // Add timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), this.timeout);

        try {
            const response = await this.fetchWithRetry(config.url, {
                ...config,
                signal: controller.signal
            });

            clearTimeout(timeoutId);

            let result = {
                status: response.status,
                statusText: response.statusText,
                headers: response.headers,
                data: null
            };

            // Parse response data
            const contentType = response.headers.get('content-type');
            if (contentType && contentType.includes('application/json')) {
                result.data = await response.json();
            } else {
                result.data = await response.text();
            }

            // Apply response interceptors
            for (const interceptor of this.responseInterceptors) {
                result = await interceptor(result);
            }

            if (!response.ok) {
                throw new APIError(result.data?.message || response.statusText, response.status, result.data);
            }

            return result.data;

        } catch (error) {
            clearTimeout(timeoutId);
            
            if (error.name === 'AbortError') {
                throw new APIError('Request timeout', 408);
            }
            
            throw error;
        }
    }

    async fetchWithRetry(url, options, attempt = 1) {
        try {
            const response = await fetch(url, options);
            
            // Retry on 5xx errors or network issues
            if (response.status >= 500 && attempt < this.retryAttempts) {
                await this.delay(this.retryDelay * attempt);
                return this.fetchWithRetry(url, options, attempt + 1);
            }
            
            return response;
        } catch (error) {
            if (attempt < this.retryAttempts) {
                await this.delay(this.retryDelay * attempt);
                return this.fetchWithRetry(url, options, attempt + 1);
            }
            throw error;
        }
    }

    delay(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    // HTTP Methods
    get(url, params = {}) {
        const queryString = new URLSearchParams(params).toString();
        const fullUrl = queryString ? `${url}?${queryString}` : url;
        return this.request(fullUrl);
    }

    post(url, data) {
        return this.request(url, {
            method: 'POST',
            body: JSON.stringify(data)
        });
    }

    put(url, data) {
        return this.request(url, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
    }

    patch(url, data) {
        return this.request(url, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
    }

    delete(url) {
        return this.request(url, {
            method: 'DELETE'
        });
    }
}

// Custom Error Class
class APIError extends Error {
    constructor(message, status, data = null) {
        super(message);
        this.name = 'APIError';
        this.status = status;
        this.data = data;
    }
}

// Initialize API client
const api = new APIClient();

// API Services
const ApiService = {
    // Teams
    async getTeams() {
        return await api.get('/teams/');
    },

    async getTeam(teamId) {
        return await api.get(`/teams/${teamId}/`);
    },

    async getTeamPlayers(teamId, position = null) {
        const params = position ? { position } : {};
        return await api.get(`/teams/${teamId}/players/`, params);
    },

    async getTeamStats(teamId) {
        return await api.get(`/teams/${teamId}/stats/`);
    },

    // Players
    async getPlayers(params = {}) {
        return await api.get('/players/', params);
    },

    async getPlayer(playerId) {
        return await api.get(`/players/${playerId}/`);
    },

    async searchPlayers(searchData) {
        return await api.post('/players/search/', searchData);
    },

    async comparePlayers(playerIds, metrics) {
        return await api.post('/players/compare/', {
            player_ids: playerIds,
            metrics: metrics
        });
    },

    async getPlayerPerformanceHistory(playerId, gameweeks = null) {
        const params = gameweeks ? { gameweeks } : {};
        return await api.get(`/players/${playerId}/performance_history/`, params);
    },

    async getTopPerformers(metric = 'total_points', position = null, limit = 20) {
        const params = { metric, limit };
        if (position) params.position = position;
        return await api.get('/players/top_performers/', params);
    },

    // User Teams
    async getUserTeams(params = {}) {
        return await api.get('/user-teams/', params);
    },

    async getUserTeam(teamId) {
        return await api.get(`/user-teams/${teamId}/`);
    },

    async loadUserTeam(teamId, async = false) {
        const params = async ? { async: 'true' } : {};
        return await api.post('/user-teams/load_team/', { team_id: teamId }, params);
    },

    async getUserTeamAnalysis(teamId) {
        return await api.get(`/user-teams/${teamId}/analysis/`);
    },

    // Transfer Suggestions
    async getTransferSuggestions(params = {}) {
        return await api.get('/suggestions/', params);
    },

    async generateSuggestions(teamId, maxSuggestions = 10, positionFilter = null, async = false) {
        const data = {
            team_id: teamId,
            max_suggestions: maxSuggestions
        };
        
        if (positionFilter) {
            data.position_filter = positionFilter;
        }

        const params = async ? { async: 'true' } : {};
        return await api.post('/suggestions/generate/', data, params);
    },

    async markSuggestionImplemented(suggestionId) {
        return await api.post(`/suggestions/${suggestionId}/mark_implemented/`);
    },

    // Analytics
    async getAnalyticsOverview() {
        return await api.get('/analytics/');
    },

    async getPlayerAnalytics(params = {}) {
        return await api.get('/analytics/players/', params);
    },

    async getPositionAnalytics(position) {
        return await api.get('/analytics/positions/', { position });
    },

    async getTransferTrends(days = 7, position = null) {
        const params = { days };
        if (position) params.position = position;
        return await api.get('/analytics/trends/', params);
    },

    // Data Synchronization
    async syncPlayerData(async = true) {
        return await api.post('/sync/players/', { async });
    },

    async getSyncStatus(taskId) {
        return await api.get('/sync/status/', { task_id: taskId });
    },

    // Health Check
    async healthCheck() {
        return await api.get('/health/');
    }
};

// Cache Management
class CacheManager {
    constructor(defaultTTL = 300000) { // 5 minutes default
        this.cache = new Map();
        this.defaultTTL = defaultTTL;
    }

    get(key) {
        const item = this.cache.get(key);
        if (!item) return null;

        if (Date.now() > item.expiry) {
            this.cache.delete(key);
            return null;
        }

        return item.data;
    }

    set(key, data, ttl = this.defaultTTL) {
        this.cache.set(key, {
            data,
            expiry: Date.now() + ttl
        });
    }

    delete(key) {
        this.cache.delete(key);
    }

    clear() {
        this.cache.clear();
    }

    // Get cache stats
    getStats() {
        const now = Date.now();
        let expired = 0;
        let active = 0;

        this.cache.forEach(item => {
            if (now > item.expiry) {
                expired++;
            } else {
                active++;
            }
        });

        return { active, expired, total: this.cache.size };
    }
}

// Initialize cache manager
const cacheManager = new CacheManager();

// Cached API Service
const CachedApiService = {
    // Wrapper for caching GET requests
    async cachedGet(key, fetcher, ttl) {
        let data = cacheManager.get(key);
        
        if (data === null) {
            try {
                data = await fetcher();
                cacheManager.set(key, data, ttl);
            } catch (error) {
                console.error(`Failed to fetch data for key ${key}:`, error);
                throw error;
            }
        }
        
        return data;
    },

    // Cached methods
    async getTeams() {
        return await this.cachedGet('teams', () => ApiService.getTeams(), 3600000); // 1 hour
    },

    async getPlayers(params = {}) {
        const key = `players_${JSON.stringify(params)}`;
        return await this.cachedGet(key, () => ApiService.getPlayers(params), 900000); // 15 minutes
    },

    async getTopPerformers(metric = 'total_points', position = null, limit = 20) {
        const key = `top_performers_${metric}_${position}_${limit}`;
        return await this.cachedGet(key, () => ApiService.getTopPerformers(metric, position, limit), 1800000); // 30 minutes
    },

    async getAnalyticsOverview() {
        return await this.cachedGet('analytics_overview', () => ApiService.getAnalyticsOverview(), 1800000); // 30 minutes
    },

    // Clear cache for specific patterns
    clearPlayerCache() {
        const keys = Array.from(cacheManager.cache.keys());
        keys.forEach(key => {
            if (key.startsWith('players_') || key.startsWith('top_performers_')) {
                cacheManager.delete(key);
            }
        });
    },

    clearTeamCache(teamId = null) {
        const keys = Array.from(cacheManager.cache.keys());
        keys.forEach(key => {
            if (teamId) {
                if (key.includes(`team_${teamId}`)) {
                    cacheManager.delete(key);
                }
            } else if (key.startsWith('team_') || key === 'teams') {
                cacheManager.delete(key);
            }
        });
    }
};

// Error Handler
const ErrorHandler = {
    handle(error, context = '') {
        console.error(`Error in ${context}:`, error);

        let message = 'An unexpected error occurred';
        let type = 'error';

        if (error instanceof APIError) {
            switch (error.status) {
                case 400:
                    message = error.data?.message || 'Invalid request data';
                    type = 'warning';
                    break;
                case 404:
                    message = 'Resource not found';
                    type = 'warning';
                    break;
                case 429:
                    message = 'Too many requests. Please wait a moment.';
                    type = 'warning';
                    break;
                case 500:
                    message = 'Server error. Please try again later.';
                    break;
                case 503:
                    message = 'Service temporarily unavailable';
                    break;
                default:
                    message = error.message || message;
            }
        } else if (error.name === 'NetworkError' || error.message.includes('fetch')) {
            message = 'Network error. Please check your connection.';
            type = 'warning';
        }

        // Show notification
        this.showNotification(message, type);

        return { message, type, originalError: error };
    },

    showNotification(message, type = 'error') {
        // Create notification element
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.innerHTML = `
            <div class="notification-content">
                <span class="notification-message">${message}</span>
                <button class="notification-close" onclick="this.parentElement.parentElement.remove()">×</button>
            </div>
        `;

        // Add to page
        document.body.appendChild(notification);

        // Auto remove after 5 seconds
        setTimeout(() => {
            if (notification.parentElement) {
                notification.remove();
            }
        }, 5000);
    }
};

// Request Queue Manager for handling concurrent requests
class RequestQueue {
    constructor(maxConcurrent = 5) {
        this.maxConcurrent = maxConcurrent;
        this.running = 0;
        this.queue = [];
    }

    async add(requestFunction) {
        return new Promise((resolve, reject) => {
            this.queue.push({
                request: requestFunction,
                resolve,
                reject
            });
            this.processNext();
        });
    }

    async processNext() {
        if (this.running >= this.maxConcurrent || this.queue.length === 0) {
            return;
        }

        this.running++;
        const { request, resolve, reject } = this.queue.shift();

        try {
            const result = await request();
            resolve(result);
        } catch (error) {
            reject(error);
        } finally {
            this.running--;
            this.processNext();
        }
    }
}

// Initialize request queue
const requestQueue = new RequestQueue();

// Export for use in other modules
window.ApiService = ApiService;
window.CachedApiService = CachedApiService;
window.ErrorHandler = ErrorHandler;
window.cacheManager = cacheManager;
window.requestQueue = requestQueue;
window.APIError = APIError;