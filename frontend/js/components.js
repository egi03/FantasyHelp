const Utils = {
    // Format price for display
    formatPrice(price) {
        return `£${parseFloat(price).toFixed(1)}m`;
    },

    // Format points
    formatPoints(points) {
        return parseInt(points).toLocaleString();
    },

    // Format percentage
    formatPercentage(percentage) {
        return `${parseFloat(percentage).toFixed(1)}%`;
    },

    // Format large numbers
    formatLargeNumber(number) {
        if (number < 1000) return number.toString();
        if (number < 1000000) return `${(number/1000).toFixed(1)}K`;
        if (number < 1000000000) return `${(number/1000000).toFixed(1)}M`;
        return `${(number/1000000000).toFixed(1)}B`;
    },

    // Get player status color and text
    getPlayerStatus(status) {
        const statusMap = {
            'a': { text: 'Available', class: 'status-available', color: '#10b981' },
            'd': { text: 'Doubtful', class: 'status-doubtful', color: '#f59e0b' },
            'i': { text: 'Injured', class: 'status-injured', color: '#ef4444' },
            's': { text: 'Suspended', class: 'status-suspended', color: '#6b7280' },
            'u': { text: 'Unavailable', class: 'status-injured', color: '#ef4444' },
            'n': { text: 'Not Available', class: 'status-injured', color: '#ef4444' }
        };
        return statusMap[status] || { text: 'Unknown', class: '', color: '#6b7280' };
    },

    // Get position name and color
    getPositionInfo(positionId) {
        const positions = {
            1: { name: 'GK', full: 'Goalkeeper', color: '#f59e0b' },
            2: { name: 'DEF', full: 'Defender', color: '#10b981' },
            3: { name: 'MID', full: 'Midfielder', color: '#6366f1' },
            4: { name: 'FWD', full: 'Forward', color: '#ef4444' }
        };
        return positions[positionId] || { name: 'Unknown', full: 'Unknown', color: '#6b7280' };
    },

    // Debounce function
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    // Throttle function
    throttle(func, limit) {
        let inThrottle;
        return function() {
            const args = arguments;
            const context = this;
            if (!inThrottle) {
                func.apply(context, args);
                inThrottle = true;
                setTimeout(() => inThrottle = false, limit);
            }
        }
    },

    // Generate unique ID
    generateId() {
        return Date.now().toString(36) + Math.random().toString(36).substr(2);
    },

    // Animate element
    animate(element, animation, callback) {
        if (!element) return;
        
        element.classList.add(animation);
        
        const handleAnimationEnd = () => {
            element.classList.remove(animation);
            element.removeEventListener('animationend', handleAnimationEnd);
            if (callback) callback();
        };
        
        element.addEventListener('animationend', handleAnimationEnd);
    },

    // Copy to clipboard
    async copyToClipboard(text) {
        try {
            await navigator.clipboard.writeText(text);
            return true;
        } catch (err) {
            // Fallback for older browsers
            const textArea = document.createElement('textarea');
            textArea.value = text;
            document.body.appendChild(textArea);
            textArea.select();
            const success = document.execCommand('copy');
            document.body.removeChild(textArea);
            return success;
        }
    },

    // Format duration
    formatDuration(seconds) {
        if (seconds < 60) return `${Math.round(seconds)}s`;
        if (seconds < 3600) return `${Math.round(seconds / 60)}m`;
        return `${Math.round(seconds / 3600)}h`;
    },

    // Calculate value score
    calculateValueScore(totalPoints, price) {
        return price > 0 ? (totalPoints / price).toFixed(1) : 0;
    },

    // Get trending direction
    getTrendDirection(current, previous) {
        if (current > previous) return { direction: 'up', class: 'trend-up', color: '#10b981' };
        if (current < previous) return { direction: 'down', class: 'trend-down', color: '#ef4444' };
        return { direction: 'stable', class: 'trend-stable', color: '#6b7280' };
    }
};

// Enhanced Loading Manager
const LoadingManager = {
    activeLoaders: new Map(),

    show(message = 'Loading...', id = null) {
        const loaderId = id || Utils.generateId();
        this.activeLoaders.set(loaderId, { message, timestamp: Date.now() });

        const overlay = document.getElementById('loadingOverlay');
        const loadingText = document.getElementById('loadingText');
        
        if (loadingText) {
            loadingText.textContent = message;
        }
        
        if (overlay) {
            overlay.style.display = 'flex';
            Utils.animate(overlay, 'fade-in');
        }

        return loaderId;
    },

    update(id, message) {
        if (this.activeLoaders.has(id)) {
            this.activeLoaders.set(id, { ...this.activeLoaders.get(id), message });
            const loadingText = document.getElementById('loadingText');
            if (loadingText) loadingText.textContent = message;
        }
    },

    hide(id = null) {
        if (id) {
            this.activeLoaders.delete(id);
        } else {
            this.activeLoaders.clear();
        }

        // Only hide if no active loaders
        if (this.activeLoaders.size === 0) {
            const overlay = document.getElementById('loadingOverlay');
            if (overlay) {
                overlay.style.display = 'none';
            }
        }
    },

    hideAll() {
        this.activeLoaders.clear();
        const overlay = document.getElementById('loadingOverlay');
        if (overlay) {
            overlay.style.display = 'none';
        }
    }
};

// Enhanced Theme Manager
const ThemeManager = {
    init() {
        this.loadTheme();
        this.setupToggle();
    },

    loadTheme() {
        const savedTheme = localStorage.getItem('theme') || 'light';
        this.setTheme(savedTheme);
    },

    setTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem('theme', theme);
        this.updateToggleIcon(theme);
    },

    toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        this.setTheme(newTheme);
    },

    updateToggleIcon(theme) {
        const sunIcon = document.querySelector('.sun-icon');
        const moonIcon = document.querySelector('.moon-icon');
        
        if (theme === 'dark') {
            if (sunIcon) sunIcon.style.display = 'none';
            if (moonIcon) moonIcon.style.display = 'block';
        } else {
            if (sunIcon) sunIcon.style.display = 'block';
            if (moonIcon) moonIcon.style.display = 'none';
        }
    },

    setupToggle() {
        const themeToggle = document.getElementById('themeToggle');
        if (themeToggle) {
            themeToggle.addEventListener('click', () => this.toggleTheme());
        }
    }
};

// Enhanced Player Card Component
const PlayerCard = {
    create(player, options = {}) {
        const { 
            showStats = false, 
            isClickable = true, 
            extraClasses = '',
            showComparison = false,
            isSelected = false 
        } = options;
        
        const card = document.createElement('div');
        card.className = `player-card ${extraClasses}`;
        card.dataset.playerId = player.fpl_id;

        if (player.is_captain) card.classList.add('captain');
        if (player.is_vice_captain) card.classList.add('vice-captain');
        if (isSelected) card.classList.add('selected');

        const statusInfo = Utils.getPlayerStatus(player.status);
        const positionInfo = Utils.getPositionInfo(player.position);
        
        card.innerHTML = `
            <div class="player-card-header">
                <div class="player-position" style="background: ${positionInfo.color}; color: white; padding: 2px 6px; border-radius: 4px; font-size: 0.7rem; font-weight: 600;">
                    ${positionInfo.name}
                </div>
                ${showComparison ? `
                    <button class="comparison-toggle ${isSelected ? 'active' : ''}" data-player-id="${player.fpl_id}">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M9 11H1l2-2 2 2"></path>
                            <path d="M1 13h8l-2 2-2-2"></path>
                            <path d="M15 11h8l-2-2-2 2"></path>
                            <path d="M23 13h-8l2 2 2-2"></path>
                        </svg>
                    </button>
                ` : ''}
            </div>
            <div class="player-name" title="${player.first_name} ${player.second_name}">
                ${player.web_name}
            </div>
            <div class="player-team" style="font-size: 0.7rem; color: var(--text-secondary); margin: 2px 0;">
                ${player.team?.short_name || 'Unknown'}
            </div>
            <div class="player-price">${Utils.formatPrice(player.current_price)}</div>
            <div class="player-points">${Utils.formatPoints(player.total_points)} pts</div>
            ${showStats ? `
                <div class="player-stats-mini" style="margin-top: 8px; font-size: 0.65rem;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 2px;">
                        <span>Form:</span>
                        <span style="font-weight: 600;">${player.form}</span>
                    </div>
                    <div style="display: flex; justify-content: space-between;">
                        <span>Own:</span>
                        <span style="font-weight: 600;">${Utils.formatPercentage(player.selected_by_percent)}</span>
                    </div>
                </div>
            ` : ''}
            <div class="status-indicator ${statusInfo.class}" title="${statusInfo.text}"></div>
        `;

        // Add event listeners
        if (isClickable) {
            card.style.cursor = 'pointer';
            card.addEventListener('click', (e) => {
                if (!e.target.closest('.comparison-toggle')) {
                    this.showPlayerModal(player);
                }
            });
        }

        if (showComparison) {
            const compareToggle = card.querySelector('.comparison-toggle');
            if (compareToggle) {
                compareToggle.addEventListener('click', (e) => {
                    e.stopPropagation();
                    PlayerComparison.toggle(player);
                });
            }
        }

        return card;
    },

    createBenchPlayer(player) {
        const benchPlayer = document.createElement('div');
        benchPlayer.className = 'bench-player';
        benchPlayer.dataset.playerId = player.fpl_id;

        const statusInfo = Utils.getPlayerStatus(player.status);
        const positionInfo = Utils.getPositionInfo(player.position);
        
        benchPlayer.innerHTML = `
            <div class="status-indicator ${statusInfo.class}"></div>
            <div class="bench-player-info">
                <div class="bench-player-name">${player.web_name}</div>
                <div class="bench-player-meta" style="font-size: 0.75rem; color: var(--text-secondary);">
                    ${positionInfo.name} • ${Utils.formatPrice(player.current_price)}
                </div>
            </div>
            <div class="bench-player-points" style="font-weight: 600; color: var(--secondary-pink);">
                ${Utils.formatPoints(player.total_points)}
            </div>
        `;

        benchPlayer.addEventListener('click', () => {
            this.showPlayerModal(player);
        });

        return benchPlayer;
    },

    createPlayerItem(player, viewMode = 'grid') {
        const item = document.createElement('div');
        item.className = 'player-item';
        item.dataset.playerId = player.fpl_id;

        const statusInfo = Utils.getPlayerStatus(player.status);
        const positionInfo = Utils.getPositionInfo(player.position);
        const valueScore = Utils.calculateValueScore(player.total_points, player.current_price);
        
        if (viewMode === 'list') {
            item.innerHTML = `
                <div class="player-avatar" style="width: 48px; height: 48px; background: ${positionInfo.color}; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: 700; font-size: 0.875rem;">
                    ${positionInfo.name}
                </div>
                <div class="player-info">
                    <h4>${player.web_name}</h4>
                    <div class="player-meta" style="display: flex; align-items: center; gap: 8px; margin-top: 4px;">
                        <span class="player-team">${player.team?.short_name || 'Unknown'}</span>
                        <div class="status-indicator ${statusInfo.class}"></div>
                        <span class="status-text" style="font-size: 0.75rem; color: var(--text-secondary);">${statusInfo.text}</span>
                    </div>
                </div>
                <div class="player-price-tag">${Utils.formatPrice(player.current_price)}</div>
                <div class="player-actions">
                    <button class="btn btn-secondary btn-small comparison-toggle" data-player-id="${player.fpl_id}">
                        Compare
                    </button>
                </div>
            `;
        } else {
            item.innerHTML = `
                <div class="player-header">
                    <div class="player-info">
                        <h4>${player.web_name}</h4>
                        <div class="player-team">${player.team?.short_name || 'Unknown'} • ${positionInfo.name}</div>
                    </div>
                    <div class="player-price-tag">${Utils.formatPrice(player.current_price)}</div>
                </div>
                <div class="player-meta">
                    <div class="status-indicator ${statusInfo.class}"></div>
                    <span class="status-text">${statusInfo.text}</span>
                    <button class="comparison-toggle ${PlayerComparison.isSelected(player.fpl_id) ? 'active' : ''}" data-player-id="${player.fpl_id}" title="Add to comparison">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M9 11H1l2-2 2 2"></path>
                            <path d="M1 13h8l-2 2-2-2"></path>
                            <path d="M15 11h8l-2-2-2 2"></path>
                            <path d="M23 13h-8l2 2 2-2"></path>
                        </svg>
                    </button>
                </div>
                <div class="player-stats">
                    <div class="stat-item">
                        <span class="value">${Utils.formatPoints(player.total_points)}</span>
                        <span class="label">Points</span>
                    </div>
                    <div class="stat-item">
                        <span class="value">${player.form}</span>
                        <span class="label">Form</span>
                    </div>
                    <div class="stat-item">  
                        <span class="value">${Utils.formatPercentage(player.selected_by_percent)}</span>
                        <span class="label">Owned</span>
                    </div>
                </div>
                <div class="player-advanced-stats" style="margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border-primary); display: grid; grid-template-columns: repeat(2, 1fr); gap: 8px; font-size: 0.75rem;">
                    <div style="text-align: center;">
                        <div style="font-weight: 600; color: var(--text-primary);">${valueScore}</div>
                        <div style="color: var(--text-secondary);">Value</div>
                    </div>
                    <div style="text-align: center;">
                        <div style="font-weight: 600; color: var(--text-primary);">${player.points_per_game || '0.0'}</div>
                        <div style="color: var(--text-secondary);">PPG</div>
                    </div>
                </div>
            `;
        }

        // Add event listeners
        item.addEventListener('click', (e) => {
            if (!e.target.closest('.comparison-toggle')) {
                this.showPlayerModal(player);
            }
        });

        const compareToggle = item.querySelector('.comparison-toggle');
        if (compareToggle) {
            compareToggle.addEventListener('click', (e) => {
                e.stopPropagation();
                PlayerComparison.toggle(player);
            });
        }

        return item;
    },

    async showPlayerModal(player) {
        // Create modal
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal modal-large">
                <div class="modal-header">
                    <h3>${player.web_name}</h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-content">
                    <div class="player-modal-loading">
                        <div class="spinner" style="width: 32px; height: 32px; margin: 0 auto 16px;"></div>
                        <p>Loading player details...</p>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Close modal functionality
        const closeModal = () => modal.remove();
        modal.querySelector('.modal-close').addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        // Load player details
        try {
            const [playerDetails, performanceHistory] = await Promise.all([
                ApiService.getPlayer(player.fpl_id),
                ApiService.getPlayerPerformanceHistory(player.fpl_id, 10).catch(() => ({ performances: [] }))
            ]);
            
            modal.querySelector('.modal-content').innerHTML = this.createPlayerModalContent(playerDetails, performanceHistory);

        } catch (error) {
            modal.querySelector('.modal-content').innerHTML = `
                <div class="error-message">
                    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="margin-bottom: 16px; opacity: 0.5;">
                        <circle cx="12" cy="12" r="10"></circle>
                        <line x1="15" y1="9" x2="9" y2="15"></line>
                        <line x1="9" y1="9" x2="15" y2="15"></line>
                    </svg>
                    <h3>Failed to Load Player Details</h3>
                    <p>Please try again later or check your connection.</p>
                    <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Close</button>
                </div>
            `;
        }
    },

    createPlayerModalContent(player, performanceHistory) {
        const statusInfo = Utils.getPlayerStatus(player.status);
        const positionInfo = Utils.getPositionInfo(player.position);
        const valueScore = Utils.calculateValueScore(player.total_points, player.current_price);

        return `
            <div class="player-details">
                <div class="player-overview">
                    <div class="player-info-detailed">
                        <div class="player-header-modal" style="display: flex; align-items: center; gap: 16px; margin-bottom: 16px;">
                            <div class="player-avatar-large" style="width: 64px; height: 64px; background: ${positionInfo.color}; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: 800; font-size: 1.25rem;">
                                ${positionInfo.name}
                            </div>
                            <div>
                                <h4>${player.web_name}</h4>
                                <p>${player.team?.name || 'Unknown Team'} • ${positionInfo.full}</p>
                                <div style="display: flex; align-items: center; gap: 8px; margin-top: 8px;">
                                    <div class="status-indicator ${statusInfo.class}"></div>
                                    <span style="font-size: 0.875rem; color: var(--text-secondary);">${statusInfo.text}</span>
                                </div>
                            </div>
                        </div>
                        <div class="price-tag">${Utils.formatPrice(player.current_price)}</div>
                    </div>
                    <div class="player-stats-grid">
                        <div class="stat">
                            <span class="value">${Utils.formatPoints(player.total_points)}</span>
                            <span class="label">Total Points</span>
                        </div>
                        <div class="stat">
                            <span class="value">${player.form}</span>
                            <span class="label">Form</span>
                        </div>
                        <div class="stat">
                            <span class="value">${player.points_per_game || '0.0'}</span>
                            <span class="label">PPG</span>
                        </div>
                        <div class="stat">
                            <span class="value">${Utils.formatPercentage(player.selected_by_percent)}</span>
                            <span class="label">Ownership</span>
                        </div>
                        <div class="stat">
                            <span class="value">${valueScore}</span>
                            <span class="label">Value</span>
                        </div>
                        <div class="stat">
                            <span class="value">${player.ict_index || '0.0'}</span>
                            <span class="label">ICT Index</span>
                        </div>
                    </div>
                </div>
                
                ${performanceHistory.performances?.length > 0 ? `
                    <div class="performance-history">
                        <h5>Recent Performance (Last 10 Gameweeks)</h5>
                        <div class="performance-chart" style="margin: 16px 0;">
                            <canvas id="playerPerformanceChart-${player.fpl_id}" width="400" height="200"></canvas>
                        </div>
                        <div class="performance-summary" style="display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; margin-top: 16px; padding: 16px; background: var(--bg-secondary); border-radius: 12px;">
                            <div style="text-align: center;">
                                <div style="font-size: 1.25rem; font-weight: 700; color: var(--primary-purple);">${performanceHistory.analysis?.average_points?.toFixed(1) || '0.0'}</div>
                                <div style="font-size: 0.875rem; color: var(--text-secondary);">Avg Points</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="font-size: 1.25rem; font-weight: 700; color: var(--accent-green);">${performanceHistory.analysis?.best_performance || 0}</div>
                                <div style="font-size: 0.875rem; color: var(--text-secondary);">Best GW</div>
                            </div>
                            <div style="text-align: center;">
                                <div style="font-size: 1.25rem; font-weight: 700; color: ${performanceHistory.analysis?.trend === 'improving' ? 'var(--accent-green)' : 'var(--accent-red)'};">
                                    ${performanceHistory.analysis?.trend === 'improving' ? '↗' : performanceHistory.analysis?.trend === 'declining' ? '↘' : '→'}
                                </div>
                                <div style="font-size: 0.875rem; color: var(--text-secondary);">Trend</div>
                            </div>
                        </div>
                    </div>
                ` : ''}
                
                <div class="detailed-stats">
                    <h5>Season Statistics</h5>
                    <div class="stats-grid">
                        <div class="stat-row">
                            <span>Minutes Played</span>
                            <span>${player.minutes || 0}</span>
                        </div>
                        <div class="stat-row">
                            <span>Goals</span>
                            <span>${player.goals_scored || 0}</span>
                        </div>
                        <div class="stat-row">
                            <span>Assists</span>
                            <span>${player.assists || 0}</span>
                        </div>
                        <div class="stat-row">
                            <span>Clean Sheets</span>
                            <span>${player.clean_sheets || 0}</span>
                        </div>
                        <div class="stat-row">
                            <span>Bonus Points</span>
                            <span>${player.bonus || 0}</span>
                        </div>
                        <div class="stat-row">
                            <span>Yellow Cards</span>
                            <span>${player.yellow_cards || 0}</span>
                        </div>
                        <div class="stat-row">
                            <span>Red Cards</span>
                            <span>${player.red_cards || 0}</span>
                        </div>
                        ${player.saves ? `
                            <div class="stat-row">
                                <span>Saves</span>
                                <span>${player.saves}</span>
                            </div>
                        ` : ''}
                    </div>
                </div>

                ${player.expected_goals || player.expected_assists ? `
                    <div class="expected-stats">
                        <h5>Expected Stats (xG/xA)</h5>
                        <div class="stats-grid">
                            ${player.expected_goals ? `
                                <div class="stat-row">
                                    <span>Expected Goals (xG)</span>
                                    <span>${parseFloat(player.expected_goals).toFixed(2)}</span>
                                </div>
                            ` : ''}
                            ${player.expected_assists ? `
                                <div class="stat-row">
                                    <span>Expected Assists (xA)</span>
                                    <span>${parseFloat(player.expected_assists).toFixed(2)}</span>
                                </div>
                            ` : ''}
                            ${player.expected_goal_involvements ? `
                                <div class="stat-row">
                                    <span>Expected Goal Involvements</span>
                                    <span>${parseFloat(player.expected_goal_involvements).toFixed(2)}</span>
                                </div>
                            ` : ''}
                        </div>
                    </div>
                ` : ''}

                <div class="player-actions" style="display: flex; gap: 12px; margin-top: 24px; padding-top: 24px; border-top: 1px solid var(--border-primary);">
                    <button class="btn btn-primary" onclick="PlayerComparison.add(${JSON.stringify(player).replace(/"/g, '&quot;')})">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M9 11H1l2-2 2 2"></path>
                            <path d="M1 13h8l-2 2-2-2"></path>
                            <path d="M15 11h8l-2-2-2 2"></path>
                            <path d="M23 13h-8l2 2 2-2"></path>
                        </svg>
                        Add to Comparison
                    </button>
                    <button class="btn btn-secondary" onclick="Utils.copyToClipboard('${player.web_name} - ${Utils.formatPrice(player.current_price)} - ${Utils.formatPoints(player.total_points)} pts').then(() => ErrorHandler.showNotification('Player stats copied to clipboard!', 'success'))">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect>
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
                        </svg>
                        Copy Stats
                    </button>
                    <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">
                        Close
                    </button>
                </div>
            </div>
        `;
    }
};

// Player Comparison Component
const PlayerComparison = {
    selectedPlayers: new Set(),
    maxPlayers: 4,

    init() {
        this.loadSavedComparison();
        this.updateUI();
    },

    toggle(player) {
        if (this.isSelected(player.fpl_id)) {
            this.remove(player.fpl_id);
        } else {
            this.add(player);
        }
    },

    add(player) {
        if (this.selectedPlayers.size >= this.maxPlayers) {
            ErrorHandler.showNotification(`Maximum ${this.maxPlayers} players can be compared`, 'warning');
            return false;
        }

        this.selectedPlayers.add(player);
        this.updateUI();
        this.saveComparison();
        ErrorHandler.showNotification(`${player.web_name} added to comparison`, 'success');
        return true;
    },

    remove(playerId) {
        for (const player of this.selectedPlayers) {
            if (player.fpl_id == playerId) {
                this.selectedPlayers.delete(player);
                break;
            }
        }
        this.updateUI();
        this.saveComparison();
    },

    clear() {
        this.selectedPlayers.clear();
        this.updateUI();
        this.saveComparison();
    },

    isSelected(playerId) {
        for (const player of this.selectedPlayers) {
            if (player.fpl_id == playerId) return true;
        }
        return false;
    },

    updateUI() {
        // Update comparison card visibility
        const comparisonCard = document.getElementById('comparisonCard');
        if (comparisonCard) {
            comparisonCard.style.display = this.selectedPlayers.size > 0 ? 'block' : 'none';
        }

        // Update comparison players display
        const comparisonPlayers = document.getElementById('comparisonPlayers');
        if (comparisonPlayers) {
            if (this.selectedPlayers.size === 0) {
                comparisonPlayers.innerHTML = `
                    <div class="comparison-placeholder">
                        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="margin-bottom: 16px; opacity: 0.5;">
                            <path d="M9 11H1l2-2 2 2"></path>
                            <path d="M1 13h8l-2 2-2-2"></path>
                            <path d="M15 11h8l-2-2-2 2"></path>
                            <path d="M23 13h-8l2 2 2-2"></path>
                        </svg>
                        <p>Click on players to add them to comparison (max ${this.maxPlayers})</p>
                    </div>
                `;
            } else {
                comparisonPlayers.innerHTML = Array.from(this.selectedPlayers).map(player => `
                    <div class="comparison-player-card">
                        <button class="comparison-remove" onclick="PlayerComparison.remove(${player.fpl_id})">×</button>
                        <div class="player-name" style="font-weight: 600; margin-bottom: 4px;">${player.web_name}</div>
                        <div class="player-team" style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 8px;">${player.team?.short_name || 'Unknown'}</div>
                        <div class="player-price" style="font-size: 0.875rem; font-weight: 600;">${Utils.formatPrice(player.current_price)}</div>
                        <div class="player-points" style="font-size: 0.875rem; color: var(--secondary-pink);">${Utils.formatPoints(player.total_points)} pts</div>
                    </div>
                `).join('');
            }
        }

        // Update compare button
        const compareBtn = document.getElementById('compareSelectedBtn');
        if (compareBtn) {
            compareBtn.disabled = this.selectedPlayers.size < 2;
            compareBtn.textContent = `Compare Selected Players (${this.selectedPlayers.size})`;
        }

        // Update comparison toggles in player cards
        document.querySelectorAll('.comparison-toggle').forEach(toggle => {
            const playerId = toggle.dataset.playerId;
            const isSelected = this.isSelected(playerId);
            toggle.classList.toggle('active', isSelected);
            
            if (isSelected) {
                toggle.style.background = 'var(--accent-green)';
                toggle.style.color = 'white';
            } else {
                toggle.style.background = '';
                toggle.style.color = '';
            }
        });
    },

    async compare() {
        if (this.selectedPlayers.size < 2) {
            ErrorHandler.showNotification('Select at least 2 players to compare', 'warning');
            return;
        }

        const playerIds = Array.from(this.selectedPlayers).map(p => p.fpl_id);
        const metrics = [
            'total_points', 'form', 'points_per_game', 'current_price', 
            'selected_by_percent', 'minutes', 'goals_scored', 'assists', 
            'clean_sheets', 'bonus', 'ict_index'
        ];

        try {
            const comparison = await ApiService.comparePlayers(playerIds, metrics);
            this.showComparisonModal(comparison);
        } catch (error) {
            ErrorHandler.handle(error, 'comparing players');
        }
    },

    showComparisonModal(comparison) {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal modal-large">
                <div class="modal-header">
                    <h3>
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px;">
                            <path d="M9 11H1l2-2 2 2"></path>
                            <path d="M1 13h8l-2 2-2-2"></path>
                            <path d="M15 11h8l-2-2-2 2"></path>
                            <path d="M23 13h-8l2 2 2-2"></path>
                        </svg>
                        Player Comparison
                    </h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-content">
                    <div class="comparison-grid">
                        ${comparison.players.map(player => `
                            <div class="comparison-player">
                                <div class="comparison-player-header" style="text-align: center; margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--border-primary);">
                                    <h4>${player.name}</h4>
                                    <p style="color: var(--text-secondary); margin: 4px 0;">${player.team} • ${player.position}</p>
                                    <div class="price-tag" style="display: inline-block; margin-top: 8px;">${Utils.formatPrice(player.stats.current_price)}</div>
                                </div>
                                <div class="comparison-stats">
                                    ${Object.entries(player.stats).map(([key, value]) => {
                                        const isHighest = comparison.summary[key]?.best_player === player.name;
                                        return `
                                            <div class="stat-row ${isHighest ? 'stat-best' : ''}">
                                                <span class="stat-name">${key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                                                <span class="stat-value">${typeof value === 'number' ? value.toFixed(key.includes('percent') ? 1 : key === 'current_price' ? 1 : 0) : value}</span>
                                                ${isHighest ? '<span class="best-indicator">👑</span>' : ''}
                                            </div>
                                        `;
                                    }).join('')}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                    
                    <div class="comparison-summary" style="margin-top: 24px; padding: 20px; background: var(--bg-secondary); border-radius: 12px;">
                        <h5 style="margin-bottom: 16px;">Comparison Summary</h5>
                        <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px;">
                            ${Object.entries(comparison.summary).slice(0, 6).map(([metric, data]) => `
                                <div style="text-align: center;">
                                    <div style="font-size: 0.875rem; color: var(--text-secondary); margin-bottom: 4px;">
                                        ${metric.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                                    </div>
                                    <div style="font-weight: 600; color: var(--text-primary);">
                                        ${data.best_player}
                                    </div>
                                    <div style="font-size: 0.875rem; color: var(--primary-purple);">
                                        ${typeof data.max === 'number' ? data.max.toFixed(1) : data.max}
                                    </div>
                                </div>
                            `).join('')}
                        </div>
                    </div>

                    <div class="comparison-actions" style="display: flex; justify-content: center; gap: 12px; margin-top: 24px;">
                        <button class="btn btn-secondary" onclick="PlayerComparison.exportComparison(${JSON.stringify(comparison).replace(/"/g, '&quot;')})">
                            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                                <polyline points="7 10 12 15 17 10"></polyline>
                                <line x1="12" y1="15" x2="12" y2="3"></line>
                            </svg>
                            Export
                        </button>
                        <button class="btn btn-primary" onclick="this.closest('.modal-overlay').remove()">
                            Close
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Close functionality
        const closeModal = () => modal.remove();
        modal.querySelector('.modal-close').addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        // Add CSS for best stats highlighting
        const style = document.createElement('style');
        style.textContent = `
            .stat-best {
                background: linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.05) 100%);
                border-left: 3px solid var(--accent-green);
            }
            .best-indicator {
                margin-left: 8px;
                font-size: 0.875rem;
            }
        `;
        document.head.appendChild(style);
    },

    exportComparison(comparison) {
        const csv = this.generateComparisonCSV(comparison);
        const blob = new Blob([csv], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `fpl-player-comparison-${new Date().toISOString().split('T')[0]}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
        
        ErrorHandler.showNotification('Comparison exported successfully!', 'success');
    },

    generateComparisonCSV(comparison) {
        const headers = ['Metric', ...comparison.players.map(p => p.name)];
        const rows = [headers.join(',')];

        // Get all metrics
        const metrics = Object.keys(comparison.players[0].stats);
        
        metrics.forEach(metric => {
            const row = [
                metric.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()),
                ...comparison.players.map(p => p.stats[metric])
            ];
            rows.push(row.join(','));
        });

        return rows.join('\n');
    },

    saveComparison() {
        const data = Array.from(this.selectedPlayers);
        localStorage.setItem('player_comparison', JSON.stringify(data));
    },

    loadSavedComparison() {
        try {
            const saved = localStorage.getItem('player_comparison');
            if (saved) {
                const players = JSON.parse(saved);
                players.forEach(player => this.selectedPlayers.add(player));
            }
        } catch (error) {
            console.error('Failed to load saved comparison:', error);
        }
    }
};

// Chart Manager for Analytics
const ChartManager = {
    charts: new Map(),

    createChart(canvasId, config) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return null;

        // Destroy existing chart if it exists
        if (this.charts.has(canvasId)) {
            this.charts.get(canvasId).destroy();
        }

        const chart = new Chart(canvas, config);
        this.charts.set(canvasId, chart);
        return chart;
    },

    destroyChart(canvasId) {
        if (this.charts.has(canvasId)) {
            this.charts.get(canvasId).destroy();
            this.charts.delete(canvasId);
        }
    },

    destroyAll() {
        this.charts.forEach(chart => chart.destroy());
        this.charts.clear();
    },

    // Predefined chart configurations
    createPerformanceChart(canvasId, data) {
        return this.createChart(canvasId, {
            type: 'line',
            data: {
                labels: data.labels,
                datasets: [{
                    label: 'Points',
                    data: data.points,
                    borderColor: 'rgb(99, 102, 241)',
                    backgroundColor: 'rgba(99, 102, 241, 0.1)',
                    tension: 0.4,
                    fill: true
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        display: false
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true
                    }
                }
            }
        });
    },

    createSquadChart(canvasId, data) {
        return this.createChart(canvasId, {
            type: 'doughnut',
            data: {
                labels: data.labels,
                datasets: [{
                    data: data.values,
                    backgroundColor: [
                        '#f59e0b', // GK
                        '#10b981', // DEF
                        '#6366f1', // MID
                        '#ef4444'  // FWD
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'bottom'
                    }
                }
            }
        });
    }
};

// Search Manager
const SearchManager = {
    suggestions: [],
    currentQuery: '',
    isVisible: false,

    init() {
        this.setupSearchInput();
        this.setupSuggestions();
    },

    setupSearchInput() {
        const searchInput = document.getElementById('searchQuery');
        if (!searchInput) return;

        searchInput.addEventListener('input', Utils.debounce((e) => {
            this.handleSearch(e.target.value);
        }, 300));

        searchInput.addEventListener('focus', () => {
            if (this.suggestions.length > 0) {
                this.showSuggestions();
            }
        });

        searchInput.addEventListener('blur', () => {
            // Delay hiding to allow clicking on suggestions
            setTimeout(() => this.hideSuggestions(), 150);
        });
    },

    async handleSearch(query) {
        this.currentQuery = query.trim();
        
        if (this.currentQuery.length < 2) {
            this.hideSuggestions();
            return;
        }

        try {
            // Simple search for suggestions
            const response = await ApiService.getPlayers({
                search: this.currentQuery,
                page_size: 10
            });

            this.suggestions = response.results || response;
            this.updateSuggestions();
            this.showSuggestions();

        } catch (error) {
            console.error('Search suggestion error:', error);
            this.hideSuggestions();
        }
    },

    updateSuggestions() {
        const container = document.getElementById('searchSuggestions');
        if (!container) return;

        if (this.suggestions.length === 0) {
            container.innerHTML = `
                <div class="suggestion-item-search">
                    <div style="color: var(--text-secondary); font-style: italic;">No players found</div>
                </div>
            `;
            return;
        }

        container.innerHTML = this.suggestions.map(player => {
            const positionInfo = Utils.getPositionInfo(player.position);
            return `
                <div class="suggestion-item-search" data-player-id="${player.fpl_id}">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <div style="width: 32px; height: 32px; background: ${positionInfo.color}; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: 600; font-size: 0.75rem;">
                            ${positionInfo.name}
                        </div>
                        <div style="flex: 1;">
                            <div style="font-weight: 600;">${player.web_name}</div>
                            <div style="font-size: 0.875rem; color: var(--text-secondary);">${player.team?.short_name || 'Unknown'} • ${Utils.formatPrice(player.current_price)}</div>
                        </div>
                        <div style="text-align: right;">
                            <div style="font-weight: 600; color: var(--secondary-pink);">${Utils.formatPoints(player.total_points)}</div>
                            <div style="font-size: 0.875rem; color: var(--text-secondary);">pts</div>
                        </div>
                    </div>
                </div>
            `;
        }).join('');

        // Add click handlers
        container.querySelectorAll('.suggestion-item-search').forEach(item => {
            item.addEventListener('click', () => {
                const playerId = item.dataset.playerId;
                const player = this.suggestions.find(p => p.fpl_id == playerId);
                if (player) {
                    PlayerCard.showPlayerModal(player);
                    this.hideSuggestions();
                }
            });
        });
    },

    showSuggestions() {
        const container = document.getElementById('searchSuggestions');
        if (container) {
            container.style.display = 'block';
            this.isVisible = true;
        }
    },

    hideSuggestions() {
        const container = document.getElementById('searchSuggestions');
        if (container) {
            container.style.display = 'none';
            this.isVisible = false;
        }
    },

    setupSuggestions() {
        // Create suggestions container if it doesn't exist
        const searchInput = document.getElementById('searchQuery');
        if (!searchInput) return;

        const inputGroup = searchInput.closest('.input-group');
        if (!inputGroup) return;

        let suggestionsContainer = document.getElementById('searchSuggestions');
        if (!suggestionsContainer) {
            suggestionsContainer = document.createElement('div');
            suggestionsContainer.id = 'searchSuggestions';
            suggestionsContainer.className = 'search-suggestions';
            suggestionsContainer.style.display = 'none';
            inputGroup.appendChild(suggestionsContainer);
        }
    }
};

// Formation Component
const Formation = {
    render(players, container) {
        if (!container || !players) return;

        console.log('⚽ Rendering formation with', players.length, 'players');

        // Clear existing content
        container.innerHTML = `
            <div class="formation-line goalkeeper">
                <div class="position-players" data-position="1"></div>
            </div>
            <div class="formation-line defenders">
                <div class="position-players" data-position="2"></div>
            </div>
            <div class="formation-line midfielders">
                <div class="position-players" data-position="3"></div>
            </div>
            <div class="formation-line forwards">
                <div class="position-players" data-position="4"></div>
            </div>
        `;

        // Group players by position (starters only)
        const starters = players.filter(p => p.position <= 11).sort((a, b) => a.position - b.position);
        const positionGroups = { 1: [], 2: [], 3: [], 4: [] };

        starters.forEach(teamPlayer => {
            const positionId = teamPlayer.player.position;
            if (positionGroups[positionId]) {
                positionGroups[positionId].push(teamPlayer);
            }
        });

        // Render players in each position
        Object.keys(positionGroups).forEach(positionId => {
            const positionContainer = container.querySelector(`[data-position="${positionId}"]`);
            if (positionContainer) {
                positionGroups[positionId].forEach(teamPlayer => {
                    const playerCard = PlayerCard.create(teamPlayer.player, {
                        extraClasses: this.getPlayerClasses(teamPlayer),
                        showStats: true
                    });
                    
                    // Add formation-specific data
                    playerCard.dataset.position = teamPlayer.position;
                    playerCard.dataset.multiplier = teamPlayer.multiplier || 1;
                    
                    positionContainer.appendChild(playerCard);
                });
            }
        });

        console.log('✅ Formation rendered successfully');
    },

    renderBench(players, container) {
        if (!container || !players) return;

        console.log('🪑 Rendering bench with', players.filter(p => p.position > 11).length, 'players');

        const benchContainer = container.querySelector('.bench-players');
        if (!benchContainer) return;

        benchContainer.innerHTML = '';

        const bench = players.filter(p => p.position > 11).sort((a, b) => a.position - b.position);
        
        bench.forEach(teamPlayer => {
            const benchPlayer = PlayerCard.createBenchPlayer(teamPlayer.player);
            benchPlayer.dataset.position = teamPlayer.position;
            benchContainer.appendChild(benchPlayer);
        });

        console.log('✅ Bench rendered successfully');
    },

    getPlayerClasses(teamPlayer) {
        const classes = [];
        
        if (teamPlayer.is_captain) classes.push('captain');
        if (teamPlayer.is_vice_captain) classes.push('vice-captain');
        
        // Add status-based classes
        const status = teamPlayer.player.status;
        if (status !== 'a') classes.push('player-unavailable');
        
        return classes.join(' ');
    },

    // Get formation name based on player distribution
    getFormationName(players) {
        const starters = players.filter(p => p.position <= 11);
        const positionCounts = { 1: 0, 2: 0, 3: 0, 4: 0 };
        
        starters.forEach(p => {
            positionCounts[p.player.position]++;
        });

        const def = positionCounts[2];
        const mid = positionCounts[3];
        const fwd = positionCounts[4];

        return `${def}-${mid}-${fwd}`;
    },

    // Validate formation
    validateFormation(players) {
        const starters = players.filter(p => p.position <= 11);
        const positionCounts = { 1: 0, 2: 0, 3: 0, 4: 0 };
        
        starters.forEach(p => {
            positionCounts[p.player.position]++;
        });

        const issues = [];
        
        // Check position requirements
        if (positionCounts[1] !== 1) issues.push('Must have exactly 1 goalkeeper');
        if (positionCounts[2] < 3) issues.push('Must have at least 3 defenders');
        if (positionCounts[3] < 2) issues.push('Must have at least 2 midfielders');
        if (positionCounts[4] < 1) issues.push('Must have at least 1 forward');
        
        // Check total players
        if (starters.length !== 11) issues.push('Must have exactly 11 starting players');
        
        return {
            valid: issues.length === 0,
            issues: issues
        };
    }
};

// Enhanced Suggestion Card Component
const SuggestionCard = {
    create(suggestion, index = 0) {
        const card = document.createElement('div');
        card.className = 'suggestion-item';
        card.dataset.suggestionId = suggestion.id;
        
        const confidenceColor = this.getConfidenceColor(suggestion.confidence_score);
        const typeInfo = this.getSuggestionTypeInfo(suggestion.suggestion_type);
        
        card.innerHTML = `
            <div class="suggestion-header">
                <div class="suggestion-type" style="background: ${typeInfo.color};">
                    ${typeInfo.icon} ${typeInfo.label}
                </div>
                <div class="suggestion-meta">
                    <div class="priority-score" title="Priority Score">${suggestion.priority_score?.toFixed(1) || '0.0'}</div>
                    <div class="suggestion-time" style="font-size: 0.75rem; color: var(--text-secondary);">
                        ${this.formatTimeAgo(suggestion.created_at)}
                    </div>
                </div>
            </div>
            
            <div class="transfer-details">
                <div class="player-out">
                    <div class="player-avatar" style="width: 48px; height: 48px; background: ${Utils.getPositionInfo(suggestion.player_out.position).color}; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: 700; font-size: 0.875rem; margin-bottom: 8px;">
                        ${Utils.getPositionInfo(suggestion.player_out.position).name}
                    </div>
                    <div class="name">${suggestion.player_out.web_name}</div>
                    <div class="team" style="margin: 4px 0;">${suggestion.player_out.team?.short_name || 'Unknown'}</div>
                    <div class="price">${Utils.formatPrice(suggestion.player_out.current_price)}</div>
                    <div class="stats" style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
                        ${Utils.formatPoints(suggestion.player_out.total_points)} pts • Form: ${suggestion.player_out.form || '0.0'}
                    </div>
                </div>
                
                <div class="transfer-arrow">
                    <div class="arrow-container" style="display: flex; flex-direction: column; align-items: center; gap: 8px;">
                        <div style="font-size: 1.5rem; color: var(--secondary-pink);">→</div>
                        <div class="transfer-type" style="font-size: 0.75rem; color: var(--text-secondary); text-transform: uppercase; font-weight: 600;">
                            ${suggestion.cost_change > 0 ? 'Upgrade' : suggestion.cost_change < 0 ? 'Downgrade' : 'Sideways'}
                        </div>
                    </div>
                </div>
                
                <div class="player-in">
                    <div class="player-avatar" style="width: 48px; height: 48px; background: ${Utils.getPositionInfo(suggestion.player_in.position).color}; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: 700; font-size: 0.875rem; margin-bottom: 8px;">
                        ${Utils.getPositionInfo(suggestion.player_in.position).name}
                    </div>
                    <div class="name">${suggestion.player_in.web_name}</div>
                    <div class="team" style="margin: 4px 0;">${suggestion.player_in.team?.short_name || 'Unknown'}</div>
                    <div class="price">${Utils.formatPrice(suggestion.player_in.current_price)}</div>
                    <div class="stats" style="font-size: 0.75rem; color: var(--text-secondary); margin-top: 4px;">
                        ${Utils.formatPoints(suggestion.player_in.total_points)} pts • Form: ${suggestion.player_in.form || '0.0'}
                    </div>
                </div>
            </div>
            
            <div class="suggestion-stats">
                <div class="stat">
                    <span class="label">Cost Change</span>
                    <span class="value ${suggestion.cost_change >= 0 ? 'negative' : 'positive'}">
                        ${suggestion.cost_change >= 0 ? '+' : ''}${Utils.formatPrice(suggestion.cost_change)}
                    </span>
                </div>
                <div class="stat">
                    <span class="label">Points Gain (5 GWs)</span>
                    <span class="value ${suggestion.predicted_points_gain > 0 ? 'positive' : 'negative'}">
                        ${suggestion.predicted_points_gain > 0 ? '+' : ''}${suggestion.predicted_points_gain?.toFixed(1) || '0.0'}
                    </span>
                </div>
                <div class="stat">
                    <span class="label">Confidence</span>
                    <span class="value" style="color: ${confidenceColor};">
                        ${suggestion.confidence_score?.toFixed(0) || '0'}%
                    </span>
                </div>
            </div>
            
            <div class="suggestion-reason">
                <div class="reason-header" style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"></path>
                        <line x1="12" y1="17" x2="12.01" y2="17"></line>
                    </svg>
                    <strong>Why this transfer?</strong>
                </div>
                <p>${suggestion.reason || 'No specific reason provided.'}</p>
                
                ${suggestion.fixtures_impact ? `
                    <div class="fixtures-info" style="margin-top: 12px; padding: 12px; background: var(--bg-secondary); border-radius: 8px; font-size: 0.875rem;">
                        <strong>Fixture Analysis:</strong> ${suggestion.fixtures_impact}
                    </div>
                ` : ''}
            </div>

            <div class="suggestion-progress" style="margin: 16px 0;">
                <div class="progress-header" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-size: 0.875rem; font-weight: 600;">Recommendation Strength</span>
                    <span style="font-size: 0.875rem; color: ${confidenceColor};">
                        ${this.getConfidenceLabel(suggestion.confidence_score)}
                    </span>
                </div>
                <div class="progress-bar" style="width: 100%; height: 6px; background: var(--border-primary); border-radius: 3px; overflow: hidden;">
                    <div class="progress-fill" style="width: ${suggestion.confidence_score || 0}%; height: 100%; background: ${confidenceColor}; transition: width 0.3s ease;"></div>
                </div>
            </div>
            
            <div class="suggestion-actions">
                <button class="btn btn-secondary" onclick="SuggestionCard.comparePlayers(${suggestion.player_out.fpl_id}, ${suggestion.player_in.fpl_id})">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M9 11H1l2-2 2 2"></path>
                        <path d="M1 13h8l-2 2-2-2"></path>
                        <path d="M15 11h8l-2-2-2 2"></path>
                        <path d="M23 13h-8l2 2 2-2"></path>
                    </svg>
                    Compare Players
                </button>
                <button class="btn btn-success" onclick="SuggestionCard.markImplemented(${suggestion.id})" 
                        ${suggestion.is_implemented ? 'disabled' : ''}>
                    ${suggestion.is_implemented ? 
                        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4"></path><path d="M21 12c-1 0-3-1-3-3s2-3 3-3 3 1 3 3-2 3-3 3"></path><path d="M3 12c1 0 3-1 3-3s-2-3-3-3-3 1-3 3 2 3 3 3"></path></svg> Completed' :
                        '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M9 12l2 2 4-4"></path><path d="M21 12c-1 0-3-1-3-3s2-3 3-3 3 1 3 3-2 3-3 3"></path><path d="M3 12c1 0 3-1 3-3s-2-3-3-3-3 1-3 3 2 3 3 3"></path></svg> Mark as Done'
                    }
                </button>
                <button class="btn btn-secondary" onclick="SuggestionCard.shareSuggestion(${suggestion.id})">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M4 12v8a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8"></path>
                        <polyline points="16,6 12,2 8,6"></polyline>
                        <line x1="12" y1="2" x2="12" y2="15"></line>
                    </svg>
                    Share
                </button>
            </div>

            ${suggestion.is_implemented ? `
                <div class="implemented-badge" style="position: absolute; top: 16px; right: 16px; background: var(--accent-green); color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 600;">
                    ✓ Implemented
                </div>
            ` : ''}
        `;

        // Add entrance animation with delay
        setTimeout(() => {
            Utils.animate(card, 'slide-up');
        }, index * 100);

        return card;
    },

    getSuggestionTypeInfo(type) {
        const types = {
            'upgrade': { label: 'Upgrade', color: 'var(--accent-green)', icon: '⬆️' },
            'sideways': { label: 'Sideways', color: 'var(--primary-purple)', icon: '↔️' },
            'downgrade': { label: 'Downgrade', color: 'var(--accent-orange)', icon: '⬇️' },
            'injury': { label: 'Injury Replace', color: 'var(--accent-red)', icon: '🏥' },
            'rotation': { label: 'Rotation Risk', color: 'var(--accent-orange)', icon: '🔄' },
            'fixture': { label: 'Fixture Play', color: 'var(--accent-cyan)', icon: '📅' },
            'form': { label: 'Form Based', color: 'var(--secondary-pink)', icon: '📈' },
            'value': { label: 'Value Pick', color: 'var(--accent-green)', icon: '💰' }
        };

        return types[type] || { label: type.replace('_', ' '), color: 'var(--text-secondary)', icon: '💡' };
    },

    getConfidenceColor(confidence) {
        if (confidence >= 80) return 'var(--accent-green)';
        if (confidence >= 60) return 'var(--accent-orange)';
        return 'var(--accent-red)';
    },

    getConfidenceLabel(confidence) {
        if (confidence >= 80) return 'High Confidence';
        if (confidence >= 60) return 'Medium Confidence'; 
        return 'Low Confidence';
    },

    formatTimeAgo(dateString) {
        if (!dateString) return 'Recently';
        
        const date = new Date(dateString);
        const now = new Date();
        const diffMs = now - date;
        const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
        const diffDays = Math.floor(diffHours / 24);

        if (diffDays > 0) return `${diffDays}d ago`;
        if (diffHours > 0) return `${diffHours}h ago`;
        return 'Recently';
    },

    async comparePlayers(playerOutId, playerInId) {
        try {
            console.log('🔄 Comparing players:', playerOutId, 'vs', playerInId);

            const comparison = await ApiService.comparePlayers(
                [playerOutId, playerInId],
                ['total_points', 'form', 'points_per_game', 'current_price', 'selected_by_percent', 'minutes', 'goals_scored', 'assists', 'clean_sheets', 'bonus', 'ict_index']
            );
            
            this.showComparisonModal(comparison);
        } catch (error) {
            console.error('❌ Player comparison failed:', error);
            ErrorHandler.handle(error, 'comparing players');
        }
    },

    showComparisonModal(comparison) {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal modal-large">
                <div class="modal-header">
                    <h3>
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px;">
                            <path d="M9 11H1l2-2 2 2"></path>
                            <path d="M1 13h8l-2 2-2-2"></path>
                            <path d="M15 11h8l-2-2-2 2"></path>
                            <path d="M23 13h-8l2 2 2-2"></path>
                        </svg>
                        Transfer Comparison
                    </h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-content">
                    <div class="comparison-grid">
                        ${comparison.players.map((player, index) => `
                            <div class="comparison-player ${index === 0 ? 'player-out-comparison' : 'player-in-comparison'}">
                                <div class="comparison-player-header" style="text-align: center; margin-bottom: 16px; padding-bottom: 16px; border-bottom: 1px solid var(--border-primary);">
                                    <div class="player-avatar" style="width: 64px; height: 64px; background: ${Utils.getPositionInfo(player.stats.position || 3).color}; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: 800; font-size: 1.25rem; margin: 0 auto 12px;">
                                        ${Utils.getPositionInfo(player.stats.position || 3).name}
                                    </div>
                                    <h4>${player.name}</h4>
                                    <p style="color: var(--text-secondary); margin: 4px 0;">${player.team} • ${player.position}</p>
                                    <div class="price-tag" style="display: inline-block; margin-top: 8px;">${Utils.formatPrice(player.stats.current_price)}</div>
                                    ${index === 0 ? 
                                        '<div style="margin-top: 8px; padding: 4px 12px; background: var(--accent-red); color: white; border-radius: 20px; font-size: 0.75rem; font-weight: 600;">Transfer Out</div>' :
                                        '<div style="margin-top: 8px; padding: 4px 12px; background: var(--accent-green); color: white; border-radius: 20px; font-size: 0.75rem; font-weight: 600;">Transfer In</div>'
                                    }
                                </div>
                                <div class="comparison-stats">
                                    ${Object.entries(player.stats).map(([key, value]) => {
                                        if (key === 'position') return '';
                                        
                                        const isHighest = comparison.summary[key]?.best_player === player.name;
                                        const formattedKey = key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                                        const formattedValue = this.formatComparisonValue(value, key);
                                        
                                        return `
                                            <div class="stat-row ${isHighest ? 'stat-best' : ''}">
                                                <span class="stat-name">${formattedKey}</span>
                                                <span class="stat-value">${formattedValue}</span>
                                                ${isHighest ? '<span class="best-indicator">👑</span>' : ''}
                                            </div>
                                        `;
                                    }).join('')}
                                </div>
                            </div>
                        `).join('')}
                    </div>
                    
                    <div class="comparison-verdict" style="margin-top: 24px; padding: 20px; background: var(--bg-secondary); border-radius: 12px; text-align: center;">
                        <h5 style="margin-bottom: 12px; color: var(--primary-purple);">Transfer Verdict</h5>
                        <div class="verdict-content">
                            ${this.generateTransferVerdict(comparison)}
                        </div>
                    </div>

                    <div class="comparison-actions" style="display: flex; justify-content: center; gap: 12px; margin-top: 24px;">
                        <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">
                            Close Comparison
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Close functionality
        const closeModal = () => modal.remove();
        modal.querySelector('.modal-close').addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });
    },

    formatComparisonValue(value, key) {
        switch(key) {
            case 'current_price':
                return Utils.formatPrice(value);
            case 'selected_by_percent':
                return Utils.formatPercentage(value);
            case 'total_points':
                return Utils.formatPoints(value);
            case 'form':
            case 'points_per_game':
            case 'ict_index':
                return typeof value === 'number' ? value.toFixed(1) : value;
            default:
                return typeof value === 'number' ? value.toFixed(0) : value;
        }
    },

    generateTransferVerdict(comparison) {
        const playerOut = comparison.players[0];
        const playerIn = comparison.players[1];
        
        const pointsDiff = playerIn.stats.total_points - playerOut.stats.total_points;
        const formDiff = playerIn.stats.form - playerOut.stats.form;
        const priceDiff = playerIn.stats.current_price - playerOut.stats.current_price;
        
        let verdict = '';
        let verdictClass = '';
        
        if (pointsDiff > 10 && formDiff > 0) {
            verdict = `✅ Strong recommendation! ${playerIn.name} has significantly outperformed ${playerOut.name} this season.`;
            verdictClass = 'verdict-positive';
        } else if (pointsDiff > 0 && formDiff > 1) {
            verdict = `👍 Good transfer. ${playerIn.name} is in better form and has more points.`;
            verdictClass = 'verdict-positive';
        } else if (pointsDiff < -5 || formDiff < -1) {
            verdict = `⚠️ Consider carefully. ${playerOut.name} has been performing better recently.`;
            verdictClass = 'verdict-negative';
        } else {
            verdict = `🤔 Sideways move. Similar performance levels - consider other factors like fixtures.`;
            verdictClass = 'verdict-neutral';
        }
        
        return `<div class="verdict-text ${verdictClass}">${verdict}</div>`;
    },

    async markImplemented(suggestionId) {
        try {
            console.log('✅ Marking suggestion as implemented:', suggestionId);

            await ApiService.markSuggestionImplemented(suggestionId);
            
            // Find and update the suggestion card
            const card = document.querySelector(`[data-suggestion-id="${suggestionId}"]`);
            if (card) {
                // Add implemented styling
                card.style.opacity = '0.8';
                card.style.background = 'linear-gradient(135deg, rgba(16, 185, 129, 0.05) 0%, rgba(5, 150, 105, 0.02) 100%)';
                
                // Update button
                const button = card.querySelector('.btn-success');
                if (button) {
                    button.disabled = true;
                    button.innerHTML = `
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M9 12l2 2 4-4"></path>
                            <path d="M21 12c-1 0-3-1-3-3s2-3 3-3 3 1 3 3-2 3-3 3"></path>
                            <path d="M3 12c1 0 3-1 3-3s-2-3-3-3-3 1-3 3 2 3 3 3"></path>
                        </svg>
                        Completed
                    `;
                }
                
                // Add implemented badge
                const badge = document.createElement('div');
                badge.className = 'implemented-badge';
                badge.style.cssText = 'position: absolute; top: 16px; right: 16px; background: var(--accent-green); color: white; padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 600;';
                badge.textContent = '✓ Implemented';
                card.style.position = 'relative';
                card.appendChild(badge);
            }
            
            ErrorHandler.showNotification('Transfer suggestion marked as completed!', 'success');
        } catch (error) {
            console.error('❌ Failed to mark suggestion as implemented:', error);
            ErrorHandler.handle(error, 'marking suggestion as implemented');
        }
    },

    async shareTransfer(suggestionId) {
        try {
            const card = document.querySelector(`[data-suggestion-id="${suggestionId}"]`);
            if (!card) return;

            const playerOut = card.querySelector('.player-out .name').textContent;
            const playerIn = card.querySelector('.player-in .name').textContent;
            const reason = card.querySelector('.suggestion-reason p').textContent;

            const shareText = `FPL Transfer Suggestion: ${playerOut} → ${playerIn}\nReason: ${reason}\n\nGenerated by FPL Transfer Suggestions`;

            if (navigator.share) {
                await navigator.share({
                    title: 'FPL Transfer Suggestion',
                    text: shareText,
                    url: window.location.href
                });
            } else {
                await Utils.copyToClipboard(shareText);
                ErrorHandler.showNotification('Transfer suggestion copied to clipboard!', 'success');
            }
        } catch (error) {
            console.error('Failed to share suggestion:', error);
        }
    }
};

// Notification System Enhancement
const NotificationSystem = {
    notifications: new Map(),
    maxNotifications: 5,

    show(message, type = 'info', duration = 5000, actions = []) {
        const id = Utils.generateId();
        
        const notification = document.createElement('div');
        notification.className = `notification notification-${type}`;
        notification.dataset.notificationId = id;
        
        const typeIcons = {
            success: '✅',
            error: '❌', 
            warning: '⚠️',
            info: 'ℹ️'
        };

        notification.innerHTML = `
            <div class="notification-content">
                <div class="notification-icon">${typeIcons[type] || 'ℹ️'}</div>
                <div class="notification-body">
                    <span class="notification-message">${message}</span>
                    ${actions.length > 0 ? `
                        <div class="notification-actions" style="margin-top: 8px; display: flex; gap: 8px;">
                            ${actions.map(action => `
                                <button class="btn btn-small btn-secondary" onclick="${action.handler}">
                                    ${action.label}
                                </button>
                            `).join('')}
                        </div>
                    ` : ''}
                </div>
                <button class="notification-close" onclick="NotificationSystem.hide('${id}')">×</button>
            </div>
        `;

        // Position notification
        this.positionNotification(notification);
        
        document.body.appendChild(notification);
        this.notifications.set(id, { element: notification, timeout: null });

        // Auto-hide after duration
        if (duration > 0) {
            const timeout = setTimeout(() => this.hide(id), duration);
            this.notifications.get(id).timeout = timeout;
        }

        Utils.animate(notification, 'slide-in-right');

        // Limit number of notifications
        this.limitNotifications();

        return id;
    },

    hide(id) {
        const notification = this.notifications.get(id);
        if (!notification) return;

        const { element, timeout } = notification;
        
        if (timeout) clearTimeout(timeout);
        
        Utils.animate(element, 'slide-out-right', () => {
            element.remove();
            this.notifications.delete(id);
            this.repositionNotifications();
        });
    },

    positionNotification(notification) {
        const existingCount = this.notifications.size;
        const offset = existingCount * 80; // 80px between notifications
        notification.style.top = `${20 + offset}px`;
    },

    repositionNotifications() {
        Array.from(this.notifications.values()).forEach((notification, index) => {
            notification.element.style.top = `${20 + (index * 80)}px`;
        });
    },

    limitNotifications() {
        if (this.notifications.size > this.maxNotifications) {
            const oldest = Array.from(this.notifications.keys())[0];
            this.hide(oldest);
        }
    },

    clear() {
        Array.from(this.notifications.keys()).forEach(id => this.hide(id));
    }
};

// Enhanced Error Handler using the new notification system
window.ErrorHandler = {
    handle(error, context = '') {
        console.error(`Error in ${context}:`, error);

        let message = 'An unexpected error occurred';
        let type = 'error';

        if (error instanceof APIError || error.name === 'APIError') {
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
        } else if (error.name === 'NetworkError' || error.message?.includes('fetch')) {
            message = 'Network error. Please check your connection.';
            type = 'warning';
        }

        this.showNotification(message, type);
        return { message, type, originalError: error };
    },

    showNotification(message, type = 'error') {
        NotificationSystem.show(message, type);
    }
};

window.Utils = Utils;
window.LoadingManager = LoadingManager;
window.ThemeManager = ThemeManager;
window.PlayerCard = PlayerCard;
window.PlayerComparison = PlayerComparison;
window.ChartManager = ChartManager;
window.Formation = Formation;
window.SuggestionCard = SuggestionCard;
window.NotificationSystem = NotificationSystem;
window.SearchManager = SearchManager;