// Main Application Class
class FPLApp {
    constructor() {
        this.currentTeam = null;
        this.currentPage = 'dashboard';
        this.playersData = null;
        this.teamsData = null;
        this.currentFilters = {};
        this.currentPageNumber = 1;
        
        this.init();
    }

    async init() {
        // Initialize the application
        this.setupEventListeners();
        this.setupNavigation();
        await this.loadInitialData();
        
        // Load team from localStorage if available
        const savedTeamId = localStorage.getItem('fpl_team_id');
        if (savedTeamId) {
            this.loadTeamData(savedTeamId);
        }
    }

    async loadInitialData() {
        try {
            // Load teams data for filters
            this.teamsData = await CachedApiService.getTeams();
            this.populateTeamFilters();
        } catch (error) {
            console.error('Failed to load initial data:', error);
        }
    }

    setupEventListeners() {
        // Team load form
        const teamLoadForm = document.getElementById('teamLoadForm');
        if (teamLoadForm) {
            teamLoadForm.addEventListener('submit', this.handleTeamLoad.bind(this));
        }

        // Action buttons
        const generateSuggestionsBtn = document.getElementById('generateSuggestionsBtn');
        if (generateSuggestionsBtn) {
            generateSuggestionsBtn.addEventListener('click', this.handleGenerateSuggestions.bind(this));
        }

        const analyzeTeamBtn = document.getElementById('analyzeTeamBtn');
        if (analyzeTeamBtn) {
            analyzeTeamBtn.addEventListener('click', this.handleAnalyzeTeam.bind(this));
        }

        const refreshDataBtn = document.getElementById('refreshDataBtn');
        if (refreshDataBtn) {
            refreshDataBtn.addEventListener('click', this.handleRefreshData.bind(this));
        }

        // Player search
        const searchPlayersBtn = document.getElementById('searchPlayersBtn');
        if (searchPlayersBtn) {
            searchPlayersBtn.addEventListener('click', this.handlePlayerSearch.bind(this));
        }

        // Search input with debounce
        const searchQuery = document.getElementById('searchQuery');
        if (searchQuery) {
            searchQuery.addEventListener('input', 
                Utils.debounce(this.handlePlayerSearch.bind(this), 500)
            );
        }
    }

    setupNavigation() {
        const navLinks = document.querySelectorAll('.nav-link');
        navLinks.forEach(link => {
            link.addEventListener('click', (e) => {
                e.preventDefault();
                const page = link.dataset.page;
                this.navigateToPage(page);
            });
        });

        // Handle page-specific navigation buttons
        document.addEventListener('click', (e) => {
            if (e.target.dataset.page) {
                this.navigateToPage(e.target.dataset.page);
            }
        });
    }

    navigateToPage(pageId) {
        // Update active nav link
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.toggle('active', link.dataset.page === pageId);
        });

        // Show/hide pages
        document.querySelectorAll('.page').forEach(page => {
            page.classList.toggle('active', page.id === pageId);
        });

        this.currentPage = pageId;

        // Load page-specific data
        switch (pageId) {
            case 'players':
                this.loadPlayersPage();
                break;
            case 'suggestions':
                this.loadSuggestionsPage();
                break;
            case 'analytics':
                this.loadAnalyticsPage();
                break;
        }
    }

    async handleTeamLoad(e) {
        e.preventDefault();
        
        const formData = new FormData(e.target);
        const teamId = formData.get('teamId');
        
        if (!teamId) {
            ErrorHandler.showNotification('Please enter a team ID', 'warning');
            return;
        }

        await this.loadTeamData(teamId);
    }

    async loadTeamData(teamId) {
        const loaderId = LoadingManager.show('Loading your FPL team...');
        
        try {
            // Load team data
            const team = await ApiService.loadUserTeam(teamId);
            
            if (team.team) {
                this.currentTeam = team.team;
                localStorage.setItem('fpl_team_id', teamId);
                
                this.displayTeamOverview(this.currentTeam);
                this.hideTeamLoadSection();
                
                ErrorHandler.showNotification('Team loaded successfully!', 'success');
            } else if (team.task_id) {
                // Handle async loading
                this.handleAsyncTeamLoad(team.task_id, teamId);
            }
            
        } catch (error) {
            ErrorHandler.handle(error, 'loading team');
        } finally {
            LoadingManager.hide(loaderId);
        }
    }

    async handleAsyncTeamLoad(taskId, teamId) {
        const checkStatus = async () => {
            try {
                const status = await ApiService.getSyncStatus(taskId);
                
                if (status.status === 'SUCCESS') {
                    // Reload team data
                    const team = await ApiService.getUserTeam(teamId);
                    this.currentTeam = team;
                    this.displayTeamOverview(this.currentTeam);
                    this.hideTeamLoadSection();
                    ErrorHandler.showNotification('Team loaded successfully!', 'success');
                } else if (status.status === 'FAILURE') {
                    ErrorHandler.showNotification('Failed to load team', 'error');
                } else {
                    // Still processing, check again
                    setTimeout(checkStatus, 2000);
                }
            } catch (error) {
                ErrorHandler.handle(error, 'checking team load status');
            }
        };

        checkStatus();
    }

    displayTeamOverview(team) {
        // Update team info
        document.getElementById('teamName').textContent = team.team_name;
        document.getElementById('managerName').textContent = team.manager_name;
        document.getElementById('totalPoints').textContent = Utils.formatPoints(team.total_points);
        document.getElementById('teamValue').textContent = Utils.formatPrice(team.team_value);
        document.getElementById('bankBalance').textContent = Utils.formatPrice(team.bank_balance);
        document.getElementById('freeTransfers').textContent = team.free_transfers;

        // Render formation
        if (team.players) {
            const formationContainer = document.getElementById('formation');
            const benchContainer = document.getElementById('bench');
            
            Formation.render(team.players, formationContainer);
            Formation.renderBench(team.players, benchContainer);
        }

        // Show team overview
        document.getElementById('teamOverview').style.display = 'block';
        Utils.animate(document.getElementById('teamOverview'), 'fade-in');
    }

    hideTeamLoadSection() {
        document.getElementById('teamLoadSection').style.display = 'none';
    }

    async handleGenerateSuggestions() {
        if (!this.currentTeam) {
            ErrorHandler.showNotification('Please load your team first', 'warning');
            return;
        }

        const loaderId = LoadingManager.show('Generating transfer suggestions...');
        
        try {
            const suggestions = await ApiService.generateSuggestions(
                this.currentTeam.fpl_team_id,
                10 // max suggestions
            );

            if (suggestions.suggestions) {
                this.displaySuggestions(suggestions.suggestions);
                this.navigateToPage('suggestions');
                ErrorHandler.showNotification(`Generated ${suggestions.count} suggestions`, 'success');
            }
            
        } catch (error) {
            ErrorHandler.handle(error, 'generating suggestions');
        } finally {
            LoadingManager.hide(loaderId);
        }
    }

    async handleAnalyzeTeam() {
        if (!this.currentTeam) {
            ErrorHandler.showNotification('Please load your team first', 'warning');
            return;
        }

        const loaderId = LoadingManager.show('Analyzing your team...');
        
        try {
            const analysis = await ApiService.getUserTeamAnalysis(this.currentTeam.fpl_team_id);
            this.displayTeamAnalysis(analysis);
            
        } catch (error) {
            ErrorHandler.handle(error, 'analyzing team');
        } finally {
            LoadingManager.hide(loaderId);
        }
    }

    displayTeamAnalysis(analysis) {
        // Create analysis modal
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal modal-large">
                <div class="modal-header">
                    <h3>Team Analysis</h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-content">
                    <div class="analysis-content">
                        <div class="analysis-section">
                            <h4>Squad Analysis</h4>
                            <div class="analysis-grid">
                                <div class="analysis-stat">
                                    <span class="label">Total Squad Value</span>
                                    <span class="value">${Utils.formatPrice(analysis.squad_analysis.total_squad_value)}</span>
                                </div>
                                <div class="analysis-stat">
                                    <span class="label">Bench Value</span>
                                    <span class="value">${Utils.formatPrice(analysis.squad_analysis.bench_value)}</span>
                                </div>
                                <div class="analysis-stat">
                                    <span class="label">Most Expensive</span>
                                    <span class="value">${analysis.squad_analysis.most_expensive}</span>
                                </div>
                            </div>
                        </div>
                        
                        ${analysis.recommendations.length > 0 ? `
                            <div class="analysis-section">
                                <h4>Recommendations</h4>
                                <div class="recommendations-list">
                                    ${analysis.recommendations.map(rec => `
                                        <div class="recommendation-item">
                                            <strong>${rec.type.replace('_', ' ').toUpperCase()}</strong>
                                            <p>${rec.message}</p>
                                        </div>
                                    `).join('')}
                                </div>
                            </div>
                        ` : ''}
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
    }

    async handleRefreshData() {
        const loaderId = LoadingManager.show('Syncing latest FPL data...');
        
        try {
            await ApiService.syncPlayerData(true);
            
            // Clear caches
            CachedApiService.clearPlayerCache();
            CachedApiService.clearTeamCache();
            
            // Reload current page data
            if (this.currentPage === 'players') {
                await this.loadPlayersPage();
            }
            
            ErrorHandler.showNotification('Data synced successfully', 'success');
            
        } catch (error) {
            ErrorHandler.handle(error, 'syncing data');
        } finally {
            LoadingManager.hide(loaderId);
        }
    }

    async loadPlayersPage() {
        if (!this.playersData) {
            await this.handlePlayerSearch();
        }
    }

    async handlePlayerSearch() {
        const loaderId = LoadingManager.show('Searching players...');
        
        try {
            // Get filter values
            const filters = {
                position: document.getElementById('positionFilter')?.value || '',
                team: document.getElementById('teamFilter')?.value || '',
                price_min: document.getElementById('priceMinFilter')?.value || '',
                price_max: document.getElementById('priceMaxFilter')?.value || '',
                search: document.getElementById('searchQuery')?.value || ''
            };

            // Remove empty filters
            Object.keys(filters).forEach(key => {
                if (!filters[key]) delete filters[key];
            });

            const result = await ApiService.getPlayers(filters);
            this.playersData = result;
            
            this.displayPlayers(result.results || result);
            this.updatePlayerCount(result.count || result.length);
            
        } catch (error) {
            ErrorHandler.handle(error, 'searching players');
        } finally {
            LoadingManager.hide(loaderId);
        }
    }

    displayPlayers(players) {
        const grid = document.getElementById('playersGrid');
        if (!grid) return;

        if (!players || players.length === 0) {
            grid.innerHTML = '<div class="no-results"><p>No players found matching your criteria</p></div>';
            return;
        }

        grid.innerHTML = '';
        players.forEach(player => {
            const playerItem = PlayerCard.createPlayerItem(player);
            grid.appendChild(playerItem);
        });

        Utils.animate(grid, 'fade-in');
    }

    updatePlayerCount(count) {
        const countElement = document.getElementById('playerCount');
        if (countElement) {
            countElement.textContent = `${count} players`;
        }
    }

    populateTeamFilters() {
        const teamFilter = document.getElementById('teamFilter');
        if (teamFilter && this.teamsData) {
            teamFilter.innerHTML = '<option value="">All Teams</option>';
            this.teamsData.forEach(team => {
                const option = document.createElement('option');
                option.value = team.fpl_id;
                option.textContent = team.name;
                teamFilter.appendChild(option);
            });
        }
    }

    async loadSuggestionsPage() {
        if (!this.currentTeam) {
            document.getElementById('suggestionsContainer').innerHTML = `
                <div class="no-team-message">
                    <h3>No Team Loaded</h3>
                    <p>Please load your FPL team from the Dashboard to see transfer suggestions.</p>
                    <button class="btn btn-primary" data-page="dashboard">Go to Dashboard</button>
                </div>
            `;
            return;
        }

        const loaderId = LoadingManager.show('Loading suggestions...');
        
        try {
            const suggestions = await ApiService.getTransferSuggestions({
                user_team: this.currentTeam.fpl_team_id
            });

            this.displaySuggestions(suggestions.results || suggestions);
            
        } catch (error) {
            ErrorHandler.handle(error, 'loading suggestions');
        } finally {
            LoadingManager.hide(loaderId);
        }
    }

    displaySuggestions(suggestions) {
        const container = document.getElementById('suggestionsContainer');
        if (!container) return;

        if (!suggestions || suggestions.length === 0) {
            container.innerHTML = `
                <div class="no-results">
                    <h3>No Suggestions Available</h3>
                    <p>Generate transfer suggestions for your team to see recommendations here.</p>
                    <button class="btn btn-primary" onclick="app.handleGenerateSuggestions()">Generate Suggestions</button>
                </div>
            `;
            return;
        }

        container.innerHTML = `
            <div class="suggestions-header">
                <h3>Transfer Suggestions</h3>
                <p>AI-powered recommendations for your team</p>
            </div>
            <div class="suggestions-list" id="suggestionsList"></div>
        `;

        const suggestionsList = document.getElementById('suggestionsList');
        suggestions.forEach(suggestion => {
            const suggestionCard = SuggestionCard.create(suggestion);
            suggestionCard.dataset.suggestionId = suggestion.id;
            suggestionsList.appendChild(suggestionCard);
        });

        Utils.animate(container, 'fade-in');
    }

    async loadAnalyticsPage() {
        const loaderId = LoadingManager.show('Loading analytics...');
        
        try {
            // Load different analytics data
            const [topPerformers, bestValue, positionAnalysis] = await Promise.all([
                ApiService.getTopPerformers('total_points', null, 10),
                ApiService.getTopPerformers('value', null, 10),
                ApiService.getPositionAnalytics(3) // Midfielders
            ]);

            this.displayAnalytics({
                topPerformers,
                bestValue,
                positionAnalysis
            });
            
        } catch (error) {
            ErrorHandler.handle(error, 'loading analytics');
        } finally {
            LoadingManager.hide(loaderId);
        }
    }

    displayAnalytics(data) {
        // Top Performers
        const topPerformersContainer = document.getElementById('topPerformers');
        if (topPerformersContainer && data.topPerformers.players) {
            topPerformersContainer.innerHTML = data.topPerformers.players.map((player, index) => `
                <div class="analytics-player-item">
                    <span class="rank">${index + 1}</span>
                    <span class="name">${player.web_name}</span>
                    <span class="team">${player.team?.short_name}</span>
                    <span class="points">${Utils.formatPoints(player.total_points)}</span>
                </div>
            `).join('');
        }

        // Best Value
        const bestValueContainer = document.getElementById('bestValue');
        if (bestValueContainer && data.bestValue.players) {
            bestValueContainer.innerHTML = data.bestValue.players.map((player, index) => `
                <div class="analytics-player-item">
                    <span class="rank">${index + 1}</span>
                    <span class="name">${player.web_name}</span>
                    <span class="team">${player.team?.short_name}</span>
                    <span class="value">${(player.total_points / player.current_price).toFixed(1)}</span>
                </div>
            `).join('');
        }

        // Position Analysis
        const positionAnalysisContainer = document.getElementById('positionAnalysis');
        if (positionAnalysisContainer && data.positionAnalysis) {
            positionAnalysisContainer.innerHTML = `
                <div class="position-stats">
                    <div class="stat">
                        <span class="label">Total Players</span>
                        <span class="value">${data.positionAnalysis.total_players}</span>
                    </div>
                    <div class="stat">
                        <span class="label">Avg Points</span>
                        <span class="value">${data.positionAnalysis.statistics?.avg_points?.toFixed(1) || 'N/A'}</span>
                    </div>
                    <div class="stat">
                        <span class="label">Avg Price</span>
                        <span class="value">${Utils.formatPrice(data.positionAnalysis.statistics?.avg_price || 0)}</span>
                    </div>
                </div>
            `;
        }
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.app = new FPLApp();
});

// Handle browser back/forward buttons
window.addEventListener('popstate', (e) => {
    if (e.state && e.state.page) {
        window.app.navigateToPage(e.state.page);
    }
});

// Service Worker Registration (for PWA functionality)
if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js')
            .then(registration => {
                console.log('SW registered: ', registration);
            })
            .catch(registrationError => {
                console.log('SW registration failed: ', registrationError);
            });
    });
}

// Global error handler
window.addEventListener('error', (e) => {
    console.error('Global error:', e.error);
    ErrorHandler.handle(e.error, 'global error handler');
});

window.addEventListener('unhandledrejection', (e) => {
    console.error('Unhandled promise rejection:', e.reason);
    ErrorHandler.handle(e.reason, 'unhandled promise rejection');
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + K for search
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        window.app.navigateToPage('players');
        setTimeout(() => {
            document.getElementById('searchQuery')?.focus();
        }, 100);
    }
    
    // Escape to close modals
    if (e.key === 'Escape') {
        const modal = document.querySelector('.modal-overlay');
        if (modal) {
            modal.remove();
        }
    }
});