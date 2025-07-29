class FPLApp {
    constructor() {
        this.currentTeam = null;
        this.currentPage = 'dashboard';
        this.playersData = null;
        this.teamsData = null;
        this.currentFilters = {};
        this.currentPageNumber = 1;
        this.currentView = 'grid';
        this.quickFilters = new Set();
        this.initializeFromHash()
        
        this.init();
    }

    async init() {
        // Initialize the application
        console.log('🚀 Initializing FPL Transfer Suggestions App...');
        
        // Initialize theme first
        ThemeManager.init();
        
        // Initialize components
        PlayerComparison.init();
        SearchManager.init();
        
        // Setup event listeners
        this.setupEventListeners();
        this.setupNavigation();
        this.setupKeyboardShortcuts();
        
        // Load initial data
        await this.loadInitialData();
        
        // Load team from localStorage if available
        const savedTeamId = localStorage.getItem('fpl_team_id');
        if (savedTeamId) {
            console.log('🔄 Loading saved team:', savedTeamId);
            this.loadTeamData(savedTeamId);
        }

        // Initialize current page
        this.initializePage(this.currentPage);
        
        console.log('✅ App initialization complete');
    }

    async loadInitialData() {
        try {
            console.log('📊 Loading initial data...');
            
            // Load teams data for filters with loading indicator
            const loaderId = LoadingManager.show('Loading teams data...');
            
            this.teamsData = await CachedApiService.getTeams();
            this.populateTeamFilters();
            
            LoadingManager.hide(loaderId);
            
            console.log('✅ Initial data loaded:', this.teamsData.length, 'teams');
        } catch (error) {
            console.error('❌ Failed to load initial data:', error);
            ErrorHandler.handle(error, 'loading initial data');
        }
    }

    setupEventListeners() {
        console.log('🎯 Setting up event listeners...');

        // Team load form
        const teamLoadForm = document.getElementById('teamLoadForm');
        if (teamLoadForm) {
            teamLoadForm.addEventListener('submit', this.handleTeamLoad.bind(this));
        }

        // Find Team ID helper
        const findTeamIdBtn = document.getElementById('findTeamIdBtn');
        if (findTeamIdBtn) {
            findTeamIdBtn.addEventListener('click', this.showFindTeamIdModal.bind(this));
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

        const comparePlayersBtn = document.getElementById('comparePlayersBtn');
        if (comparePlayersBtn) {
            comparePlayersBtn.addEventListener('click', () => PlayerComparison.compare());
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

        // Filter events
        this.setupFilterEvents();
        
        // View toggle
        this.setupViewToggle();
        
        // Pagination
        this.setupPagination();
        
        // Quick filters
        this.setupQuickFilters();

        // Comparison events
        const compareSelectedBtn = document.getElementById('compareSelectedBtn');
        if (compareSelectedBtn) {
            compareSelectedBtn.addEventListener('click', () => PlayerComparison.compare());
        }

        const clearComparisonBtn = document.getElementById('clearComparisonBtn');
        if (clearComparisonBtn) {
            clearComparisonBtn.addEventListener('click', () => PlayerComparison.clear());
        }

        // Analytics events
        this.setupAnalyticsEvents();

        console.log('✅ Event listeners set up');
    }

    setupFilterEvents() {
        // Filter change handlers
        const filterElements = [
            'positionFilter', 'teamFilter', 'priceMinFilter', 'priceMaxFilter', 
            'statusFilter', 'sortFilter'
        ];

        filterElements.forEach(filterId => {
            const element = document.getElementById(filterId);
            if (element) {
                element.addEventListener('change', Utils.debounce(() => {
                    this.handlePlayerSearch();
                }, 300));
            }
        });

        // Clear filters
        const clearFiltersBtn = document.getElementById('clearFiltersBtn');
        if (clearFiltersBtn) {
            clearFiltersBtn.addEventListener('click', this.clearFilters.bind(this));
        }

        // Save search
        const saveSearchBtn = document.getElementById('saveSearchBtn');
        if (saveSearchBtn) {
            saveSearchBtn.addEventListener('click', this.saveCurrentSearch.bind(this));
        }
    }

    setupViewToggle() {
        const gridViewBtn = document.getElementById('gridViewBtn');
        const listViewBtn = document.getElementById('listViewBtn');
        
        if (gridViewBtn) {
            gridViewBtn.addEventListener('click', () => this.switchView('grid'));
        }
        
        if (listViewBtn) {
            listViewBtn.addEventListener('click', () => this.switchView('list'));
        }
    }

    setupPagination() {
        const prevPageBtn = document.getElementById('prevPage');
        const nextPageBtn = document.getElementById('nextPage');
        
        if (prevPageBtn) {
            prevPageBtn.addEventListener('click', () => this.changePage(this.currentPageNumber - 1));
        }
        
        if (nextPageBtn) {
            nextPageBtn.addEventListener('click', () => this.changePage(this.currentPageNumber + 1));
        }
    }

    setupQuickFilters() {
        const quickFilterButtons = document.querySelectorAll('[data-filter]');
        quickFilterButtons.forEach(button => {
            button.addEventListener('click', () => {
                const filterType = button.dataset.filter;
                this.toggleQuickFilter(filterType, button);
            });
        });
    }

    setupAnalyticsEvents() {
        // Top performers metric change
        const topPerformersMetric = document.getElementById('topPerformersMetric');
        if (topPerformersMetric) {
            topPerformersMetric.addEventListener('change', (e) => {
                this.updateTopPerformers(e.target.value);
            });
        }

        // Position analysis change
        const positionSelect = document.getElementById('positionSelect');
        if (positionSelect) {
            positionSelect.addEventListener('change', (e) => {
                this.updatePositionAnalysis(e.target.value);
            });
        }

        // Value metric change
        const valueMetric = document.getElementById('valueMetric');
        if (valueMetric) {
            valueMetric.addEventListener('change', (e) => {
                this.updateBestValue(e.target.value);
            });
        }

        // Form period buttons
        const formPeriod5 = document.getElementById('formPeriod5');
        const formPeriod10 = document.getElementById('formPeriod10');
        
        if (formPeriod5) {
            formPeriod5.addEventListener('click', () => this.updateFormGuide(5));
        }
        
        if (formPeriod10) {
            formPeriod10.addEventListener('click', () => this.updateFormGuide(10));
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

    setupKeyboardShortcuts() {
        document.addEventListener('keydown', (e) => {
            // Ctrl/Cmd + K for search
            if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
                e.preventDefault();
                this.navigateToPage('players');
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

            // Navigation shortcuts
            if (e.altKey) {
                switch(e.key) {
                    case '1':
                        e.preventDefault();
                        this.navigateToPage('dashboard');
                        break;
                    case '2':
                        e.preventDefault();
                        this.navigateToPage('players');
                        break;
                    case '3':
                        e.preventDefault();
                        this.navigateToPage('suggestions');
                        break;
                    case '4':
                        e.preventDefault();
                        this.navigateToPage('analytics');
                        break;
                }
            }
        });
    }

    navigateToPage(pageId) {
        console.log('🧭 Navigating to page:', pageId);

        // Update active nav link
        document.querySelectorAll('.nav-link').forEach(link => {
            link.classList.toggle('active', link.dataset.page === pageId);
        });

        // Show/hide pages with animation
        document.querySelectorAll('.page').forEach(page => {
            const isActive = page.id === pageId;
            page.classList.toggle('active', isActive);
            
            if (isActive) {
                Utils.animate(page, 'fade-in');
            }
        });

        this.currentPage = pageId;

        // Initialize page-specific data
        this.initializePage(pageId);

        // Update URL without page reload
        if (history.pushState) {
            const newUrl = `${window.location.origin}${window.location.pathname}#${pageId}`;
            history.pushState({ page: pageId }, '', newUrl);
        }
    }

    async initializePage(pageId) {
        console.log('🔄 Initializing page:', pageId);

        switch (pageId) {
            case 'dashboard':
                await this.loadDashboardPage();
                break;
            case 'players':
                await this.loadPlayersPage();
                break;
            case 'suggestions':
                await this.loadSuggestionsPage();
                break;
            case 'analytics':
                await this.loadAnalyticsPage();
                break;
        }
    }

    async loadDashboardPage() {
        // Dashboard is mostly static, but we can add some dynamic content
        if (this.currentTeam) {
            this.updateTeamCharts();
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

        // Validate team ID format
        if (!/^\d{6,8}$/.test(teamId)) {
            ErrorHandler.showNotification('Team ID should be 6-8 digits', 'warning');
            return;
        }

        await this.loadTeamData(teamId);
    }

    async loadTeamData(teamId) {
        const loaderId = LoadingManager.show('Loading your FPL team...');
        
        try {
            console.log('🏆 Loading team data for ID:', teamId);

            // Update loading indicator on form
            const indicator = document.getElementById('teamLoadIndicator');
            if (indicator) indicator.style.display = 'block';

            // Load team data
            const response = await ApiService.loadUserTeam(teamId);
            
            if (response.team) {
                this.currentTeam = response.team;
                localStorage.setItem('fpl_team_id', teamId);
                
                this.displayTeamOverview(this.currentTeam);
                this.hideTeamLoadSection();
                this.updateTeamCharts();
                
                console.log('✅ Team loaded successfully:', this.currentTeam.team_name);
                ErrorHandler.showNotification(`Team "${this.currentTeam.team_name}" loaded successfully!`, 'success');
                
                // Auto-navigate to suggestions if coming from another page
                if (this.currentPage === 'suggestions') {
                    await this.loadSuggestionsPage();
                }
            } else if (response.task_id) {
                // Handle async loading
                console.log('⏳ Team loading started asynchronously, task ID:', response.task_id);
                this.handleAsyncTeamLoad(response.task_id, teamId);
            }
            
        } catch (error) {
            console.error('❌ Failed to load team:', error);
            ErrorHandler.handle(error, 'loading team');
        } finally {
            LoadingManager.hide(loaderId);
            
            const indicator = document.getElementById('teamLoadIndicator');
            if (indicator) indicator.style.display = 'none';
        }
    }

    async handleAsyncTeamLoad(taskId, teamId) {
        let attempts = 0;
        const maxAttempts = 30; // 1 minute timeout
        
        const checkStatus = async () => {
            attempts++;
            
            try {
                const status = await ApiService.getSyncStatus(taskId);
                
                LoadingManager.update(null, `Loading team... (${attempts * 2}s)`);
                
                if (status.status === 'SUCCESS') {
                    // Reload team data
                    const team = await ApiService.getUserTeam(teamId);
                    this.currentTeam = team;
                    this.displayTeamOverview(this.currentTeam);
                    this.hideTeamLoadSection();
                    this.updateTeamCharts();
                    
                    console.log('✅ Async team load completed');
                    ErrorHandler.showNotification('Team loaded successfully!', 'success');
                    
                } else if (status.status === 'FAILURE') {
                    console.error('❌ Async team load failed');
                    ErrorHandler.showNotification('Failed to load team. Please try again.', 'error');
                    
                } else if (attempts < maxAttempts) {
                    // Still processing, check again
                    setTimeout(checkStatus, 2000);
                } else {
                    console.error('⏰ Team load timed out');
                    ErrorHandler.showNotification('Team loading timed out. Please try again.', 'error');
                }
            } catch (error) {
                console.error('❌ Error checking team load status:', error);
                ErrorHandler.handle(error, 'checking team load status');
            }
        };

        checkStatus();
    }

    displayTeamOverview(team) {
        console.log('📋 Displaying team overview for:', team.team_name);

        // Update team info
        document.getElementById('teamName').textContent = team.team_name;
        document.getElementById('managerName').textContent = team.manager_name;
        document.getElementById('totalPoints').textContent = Utils.formatPoints(team.total_points);
        document.getElementById('gameweekPoints').textContent = Utils.formatPoints(team.event_points || 0);
        document.getElementById('teamValue').textContent = Utils.formatPrice(team.team_value);
        document.getElementById('bankBalance').textContent = Utils.formatPrice(team.bank_balance);
        document.getElementById('freeTransfers').textContent = team.free_transfers;

        // Update rankings if available
        const overallRank = document.getElementById('overallRank');
        const gameweekRank = document.getElementById('gameweekRank');
        
        if (overallRank) {
            overallRank.textContent = team.overall_rank ? 
                `Rank: ${Utils.formatLargeNumber(team.overall_rank)}` : 'Rank: -';
        }
        
        if (gameweekRank) {
            gameweekRank.textContent = team.event_rank ? 
                `GW Rank: ${Utils.formatLargeNumber(team.event_rank)}` : 'GW Rank: -';
        }

        // Render formation and bench
        if (team.players) {
            const formationContainer = document.getElementById('formation');
            const benchContainer = document.getElementById('bench');
            
            Formation.render(team.players, formationContainer);
            Formation.renderBench(team.players, benchContainer);
            
            // Update bench stats
            this.updateBenchStats(team.players);
        }

        // Animate team overview appearance
        const teamOverview = document.getElementById('teamOverview');
        teamOverview.style.display = 'block';
        Utils.animate(teamOverview, 'fade-in');

        console.log('✅ Team overview displayed');
    }

    updateBenchStats(players) {
        const benchPlayers = players.filter(p => p.position > 11);
        const benchValue = benchPlayers.reduce((sum, p) => sum + parseFloat(p.player.current_price), 0);
        const benchPoints = benchPlayers.reduce((sum, p) => sum + p.player.total_points, 0);
        
        const benchValueEl = document.getElementById('benchValue');
        const benchPointsEl = document.getElementById('benchPoints');
        
        if (benchValueEl) benchValueEl.textContent = Utils.formatPrice(benchValue);
        if (benchPointsEl) benchPointsEl.textContent = `${Utils.formatPoints(benchPoints)} pts`;
    }

    updateTeamCharts() {
        if (!this.currentTeam) return;

        console.log('📊 Updating team charts...');

        // Performance chart - last 10 gameweeks
        this.createPerformanceChart();
        
        // Squad balance chart
        this.createSquadChart();
    }

    createPerformanceChart() {
        // Mock data for now - in real app, this would come from API
        const data = {
            labels: Array.from({length: 10}, (_, i) => `GW${i + 1}`),
            points: Array.from({length: 10}, () => Math.floor(Math.random() * 100) + 20)
        };

        ChartManager.createPerformanceChart('performanceChart', data);
    }

    createSquadChart() {
        if (!this.currentTeam?.players) return;

        const positionCounts = { 1: 0, 2: 0, 3: 0, 4: 0 };
        this.currentTeam.players.forEach(tp => {
            positionCounts[tp.player.position]++;
        });

        const data = {
            labels: ['Goalkeepers', 'Defenders', 'Midfielders', 'Forwards'],
            values: [positionCounts[1], positionCounts[2], positionCounts[3], positionCounts[4]]
        };

        ChartManager.createSquadChart('squadChart', data);
    }

    hideTeamLoadSection() {
        const teamLoadSection = document.getElementById('teamLoadSection');
        if (teamLoadSection) {
            Utils.animate(teamLoadSection, 'fade-out', () => {
                teamLoadSection.style.display = 'none';
            });
        }
    }

    showFindTeamIdModal() {
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <h3>
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px;">
                            <circle cx="11" cy="11" r="8"></circle>
                            <path d="M21 21l-4.35-4.35"></path>
                        </svg>
                        How to Find Your Team ID
                    </h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-content">
                    <div class="find-team-steps">
                        <div class="step">
                            <div class="step-number">1</div>
                            <div class="step-content">
                                <h4>Go to Fantasy Premier League</h4>
                                <p>Visit <a href="https://fantasy.premierleague.com" target="_blank" rel="noopener">fantasy.premierleague.com</a> and log in to your account.</p>
                            </div>
                        </div>
                        <div class="step">
                            <div class="step-number">2</div>
                            <div class="step-content">
                                <h4>Navigate to Your Team</h4>
                                <p>Click on "Pick Team" or "My Team" to view your current squad.</p>
                            </div>
                        </div>
                        <div class="step">
                            <div class="step-number">3</div>
                            <div class="step-content">
                                <h4>Find the ID in URL</h4>
                                <p>Look at the browser address bar. Your team ID is the number after "entry/" in the URL.</p>
                                <div class="url-example">
                                    <code>https://fantasy.premierleague.com/entry/<strong>1234567</strong>/event/15</code>
                                    <p style="margin-top: 8px; font-size: 0.875rem; color: var(--text-secondary);">In this example, your team ID is <strong>1234567</strong></p>
                                </div>
                            </div>
                        </div>
                        <div class="step">
                            <div class="step-number">4</div>
                            <div class="step-content">
                                <h4>Enter Your ID</h4>
                                <p>Copy the 6-8 digit number and paste it into the Team ID field above.</p>
                            </div>
                        </div>
                    </div>
                    <div class="modal-actions" style="margin-top: 24px; text-align: center;">
                        <button class="btn btn-primary" onclick="this.closest('.modal-overlay').remove()">
                            Got it!
                        </button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Add styles for the steps
        const style = document.createElement('style');
        style.textContent = `
            .find-team-steps {
                display: flex;
                flex-direction: column;
                gap: 24px;
            }
            .step {
                display: flex;
                gap: 16px;
                align-items: flex-start;
            }
            .step-number {
                width: 32px;
                height: 32px;
                background: var(--gradient-primary);
                color: white;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: 700;
                flex-shrink: 0;
            }
            .step-content h4 {
                margin: 0 0 8px 0;
                color: var(--text-primary);
            }
            .step-content p {
                margin: 0;
                color: var(--text-secondary);
                line-height: 1.5;
            }
            .url-example {
                background: var(--bg-secondary);
                padding: 12px;
                border-radius: 8px;
                margin-top: 12px;
                border-left: 3px solid var(--primary-purple);
            }
            .url-example code {
                background: none;
                padding: 0;
                font-family: 'Monaco', 'Menlo', monospace;
                color: var(--text-primary);
            }
        `;
        document.head.appendChild(style);

        // Close functionality
        const closeModal = () => {
            modal.remove();
            style.remove();
        };
        modal.querySelector('.modal-close').addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });
    }

    async handleGenerateSuggestions() {
        if (!this.currentTeam) {
            ErrorHandler.showNotification('Please load your team first', 'warning');
            return;
        }

        const loaderId = LoadingManager.show('Generating AI-powered transfer suggestions...');
        
        try {
            console.log('🤖 Generating suggestions for team:', this.currentTeam.fpl_team_id);

            const suggestions = await ApiService.generateSuggestions(
                this.currentTeam.fpl_team_id,
                15 // max suggestions
            );

            if (suggestions.suggestions || suggestions.count > 0) {
                const suggestionsList = suggestions.suggestions || suggestions.results || [];
                this.displaySuggestions(suggestionsList);
                this.navigateToPage('suggestions');
                
                console.log('✅ Generated', suggestionsList.length, 'suggestions');
                ErrorHandler.showNotification(
                    `Generated ${suggestionsList.length} transfer suggestions!`, 
                    'success'
                );
            } else {
                ErrorHandler.showNotification('No suggestions available at the moment', 'info');
            }
            
        } catch (error) {
            console.error('❌ Failed to generate suggestions:', error);
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

        const loaderId = LoadingManager.show('Analyzing your team performance...');
        
        try {
            console.log('📊 Analyzing team:', this.currentTeam.fpl_team_id);

            const analysis = await ApiService.getUserTeamAnalysis(this.currentTeam.fpl_team_id);
            this.displayTeamAnalysis(analysis);
            
        } catch (error) {
            console.error('❌ Failed to analyze team:', error);
            ErrorHandler.handle(error, 'analyzing team');
        } finally {
            LoadingManager.hide(loaderId);
        }
    }

    displayTeamAnalysis(analysis) {
        console.log('📈 Displaying team analysis');

        // Create analysis modal with enhanced design
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal modal-large">
                <div class="modal-header">
                    <h3>
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px;">
                            <polyline points="22,12 18,12 15,21 9,3 6,12 2,12"></polyline>
                        </svg>
                        Team Analysis Report
                    </h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-content">
                    <div class="analysis-content">
                        <!-- Team Summary -->
                        <div class="analysis-section">
                            <h4>Team Summary</h4>
                            <div class="analysis-grid">
                                <div class="analysis-stat">
                                    <span class="label">Squad Value</span>
                                    <span class="value">${Utils.formatPrice(analysis.squad_analysis?.total_squad_value || 0)}</span>
                                </div>
                                <div class="analysis-stat">
                                    <span class="label">Bench Value</span>
                                    <span class="value">${Utils.formatPrice(analysis.squad_analysis?.bench_value || 0)}</span>
                                </div>
                                <div class="analysis-stat">
                                    <span class="label">Team Strength</span>
                                    <span class="value">${analysis.performance_metrics?.squad_average_form?.toFixed(1) || 'N/A'}</span>
                                </div>
                                <div class="analysis-stat">
                                    <span class="label">Avg Player Value</span>
                                    <span class="value">${Utils.formatPrice(analysis.squad_analysis?.average_player_value || 0)}</span>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Performance Analysis -->
                        <div class="analysis-section">
                            <h4>Performance Analysis</h4>
                            <div class="performance-breakdown" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px;">
                                <div class="performance-card" style="background: var(--bg-secondary); padding: 16px; border-radius: 12px;">
                                    <h5 style="margin: 0 0 8px 0; color: var(--text-primary);">Squad Points</h5>
                                    <div style="font-size: 1.5rem; font-weight: 700; color: var(--primary-purple);">
                                        ${Utils.formatPoints(analysis.performance_metrics?.squad_total_points || 0)}
                                    </div>
                                    <div style="font-size: 0.875rem; color: var(--text-secondary); margin-top: 4px;">
                                        Avg: ${analysis.performance_metrics?.average_player_points?.toFixed(1) || '0.0'} per player
                                    </div>
                                </div>
                                
                                ${analysis.performance_metrics?.captain_performance?.name ? `
                                    <div class="performance-card" style="background: var(--bg-secondary); padding: 16px; border-radius: 12px;">
                                        <h5 style="margin: 0 0 8px 0; color: var(--text-primary);">Captain</h5>
                                        <div style="font-weight: 600; color: var(--accent-green); margin-bottom: 4px;">
                                            ${analysis.performance_metrics.captain_performance.name}
                                        </div>
                                        <div style="font-size: 0.875rem; color: var(--text-secondary);">
                                            ${Utils.formatPoints(analysis.performance_metrics.captain_performance.total_points)} pts
                                            • Form: ${analysis.performance_metrics.captain_performance.form}
                                        </div>
                                    </div>
                                ` : ''}
                                
                                <div class="performance-card" style="background: var(--bg-secondary); padding: 16px; border-radius: 12px;">
                                    <h5 style="margin: 0 0 8px 0; color: var(--text-primary);">Bench Strength</h5>
                                    <div style="font-size: 1.25rem; font-weight: 600; color: var(--secondary-pink);">
                                        ${analysis.performance_metrics?.bench_strength?.toFixed(1) || '0.0'}
                                    </div>
                                    <div style="font-size: 0.875rem; color: var(--text-secondary); margin-top: 4px;">
                                        Avg points per bench player
                                    </div>
                                </div>
                            </div>
                        </div>

                        <!-- Position Breakdown -->
                        ${analysis.position_breakdown ? `
                            <div class="analysis-section">
                                <h4>Position Breakdown</h4>
                                <div class="position-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px;">
                                    ${Object.entries(analysis.position_breakdown).map(([position, data]) => `
                                        <div class="position-card" style="background: var(--bg-secondary); padding: 16px; border-radius: 12px; border-left: 4px solid ${Utils.getPositionInfo(position === 'Goalkeeper' ? 1 : position === 'Defender' ? 2 : position === 'Midfielder' ? 3 : 4).color};">
                                            <h5 style="margin: 0 0 12px 0; color: var(--text-primary);">${position}s</h5>
                                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                                                <span style="color: var(--text-secondary);">Players:</span>
                                                <span style="font-weight: 600;">${data.count}</span>
                                            </div>
                                            <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                                                <span style="color: var(--text-secondary);">Value:</span>
                                                <span style="font-weight: 600;">${Utils.formatPrice(data.total_value)}</span>
                                            </div>
                                            <div style="display: flex; justify-content: space-between;">
                                                <span style="color: var(--text-secondary);">Points:</span>
                                                <span style="font-weight: 600; color: var(--primary-purple);">${Utils.formatPoints(data.total_points)}</span>
                                            </div>
                                        </div>
                                    `).join('')}
                                </div>
                            </div>
                        ` : ''}
                        
                        <!-- Recommendations -->
                        ${analysis.recommendations?.length > 0 ? `
                            <div class="analysis-section">
                                <h4>
                                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="margin-right: 8px;">
                                        <path d="M9 12l2 2 4-4"></path>
                                        <path d="M21 12c-1 0-3-1-3-3s2-3 3-3 3 1 3 3-2 3-3 3"></path>
                                        <path d="M3 12c1 0 3-1 3-3s-2-3-3-3-3 1-3 3 2 3 3 3"></path>
                                    </svg>
                                    Recommendations
                                </h4>
                                <div class="recommendations-list">
                                    ${analysis.recommendations.map(rec => `
                                        <div class="recommendation-item ${rec.type}">
                                            <div class="rec-header">
                                                <strong>${rec.type.replace('_', ' ').toUpperCase()}</strong>
                                                <div class="rec-icon">
                                                    ${rec.type === 'injury_concern' ? '🏥' : 
                                                      rec.type === 'poor_form' ? '📉' : 
                                                      rec.type === 'expensive_bench' ? '💰' : '💡'}
                                                </div>
                                            </div>
                                            <p>${rec.message}</p>
                                            ${rec.players ? `
                                                <div class="rec-players" style="margin-top: 8px;">
                                                    <strong>Players:</strong> ${Array.isArray(rec.players) ? rec.players.join(', ') : rec.players}
                                                </div>
                                            ` : ''}
                                        </div>
                                    `).join('')}
                                </div>
                            </div>
                        ` : ''}

                        <div class="analysis-actions" style="display: flex; justify-content: center; gap: 12px; margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--border-primary);">
                            <button class="btn btn-primary" onclick="app.handleGenerateSuggestions(); this.closest('.modal-overlay').remove();">
                                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M9 12l2 2 4-4"></path>
                                    <path d="M21 12c-1 0-3-1-3-3s2-3 3-3 3 1 3 3-2 3-3 3"></path>
                                    <path d="M3 12c1 0 3-1 3-3s-2-3-3-3-3 1-3 3 2 3 3 3"></path>
                                </svg>
                                Generate Suggestions
                            </button>
                            <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">
                                Close
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Add styles for analysis components
        const style = document.createElement('style');
        style.textContent = `
            .rec-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 8px;
            }
            .rec-icon {
                font-size: 1.25rem;
            }
            .rec-players {
                font-size: 0.875rem;
                color: var(--text-secondary);
            }
            .recommendation-item.injury_concern {
                border-left-color: var(--accent-red);
            }
            .recommendation-item.poor_form {
                border-left-color: var(--accent-orange);
            }
            .recommendation-item.expensive_bench {
                border-left-color: var(--primary-purple);
            }
        `;
        document.head.appendChild(style);

        // Close functionality
        const closeModal = () => {
            modal.remove();
            style.remove();
        };
        modal.querySelector('.modal-close').addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        console.log('✅ Team analysis displayed');
    }

    async handleRefreshData() {
        const loaderId = LoadingManager.show('Syncing latest FPL data...');
        
        try {
            console.log('🔄 Refreshing FPL data...');

            await ApiService.syncPlayerData(true);
            
            // Clear caches
            CachedApiService.clearPlayerCache();
            CachedApiService.clearTeamCache();
            
            // Reload current page data
            await this.initializePage(this.currentPage);
            
            console.log('✅ Data refreshed successfully');
            ErrorHandler.showNotification('Data synced successfully! All information is now up to date.', 'success');
            
        } catch (error) {
            console.error('❌ Failed to refresh data:', error);
            ErrorHandler.handle(error, 'syncing data');
        } finally {
            LoadingManager.hide(loaderId);
        }
    }

    async loadPlayersPage() {
        console.log('👥 Loading players page...');
        
        // Load initial players if not already loaded
        if (!this.playersData) {
            await this.handlePlayerSearch();
        }
        
        // Update view toggle states
        this.updateViewToggleState();
    }

    async handlePlayerSearch() {
        const loaderId = LoadingManager.show('Searching players...');
        
        try {
            console.log('🔍 Searching players with filters...');

            // Get filter values
            const filters = this.collectFilters();
            
            // Add quick filters
            this.applyQuickFilters(filters);

            console.log('Applied filters:', filters);

            // Perform search
            const result = await ApiService.getPlayers({
                ...filters,
                page: this.currentPageNumber,
                page_size: 20
            });
            
            this.playersData = result;
            
            this.displayPlayers(result.results || result);
            this.updatePlayerCount(result.count || result.length);
            this.updatePagination(result);
            
            console.log('✅ Found', result.results?.length || result.length, 'players');
            
        } catch (error) {
            console.error('❌ Player search failed:', error);
            ErrorHandler.handle(error, 'searching players');
        } finally {
            LoadingManager.hide(loaderId);
        }
    }

    collectFilters() {
        const filters = {};
        
        // Basic filters
        const filterMappings = {
            'positionFilter': 'position',
            'teamFilter': 'team',
            'priceMinFilter': 'price_min',
            'priceMaxFilter': 'price_max',
            'statusFilter': 'status',
            'sortFilter': 'ordering'
        };
        
        Object.entries(filterMappings).forEach(([elementId, filterKey]) => {
            const element = document.getElementById(elementId);
            if (element && element.value) {
                filters[filterKey] = element.value;
            }
        });
        
        // Search query
        const searchQuery = document.getElementById('searchQuery');
        if (searchQuery && searchQuery.value.trim()) {
            filters.search = searchQuery.value.trim();
        }
        
        this.currentFilters = filters;
        return filters;
    }

    applyQuickFilters(filters) {
        this.quickFilters.forEach(filterType => {
            switch(filterType) {
                case 'premium':
                    filters.price_min = '9.0';
                    break;
                case 'budget':
                    filters.price_max = '5.0';
                    break;
                case 'form':
                    filters.form_min = '4.0';
                    break;
                case 'value':
                    filters.ordering = '-total_points';
                    filters.price_max = '8.0';
                    break;
                case 'template':
                    filters.selected_by_percent_min = '20.0';
                    break;
            }
        });
    }

    toggleQuickFilter(filterType, button) {
        if (this.quickFilters.has(filterType)) {
            this.quickFilters.delete(filterType);
            button.classList.remove('active');
        } else {
            this.quickFilters.add(filterType);
            button.classList.add('active');
        }
        
        // Trigger search
        this.handlePlayerSearch();
    }

    clearFilters() {
        console.log('🧹 Clearing all filters...');
        
        // Clear form inputs
        const filterElements = [
            'positionFilter', 'teamFilter', 'priceMinFilter', 'priceMaxFilter', 
            'statusFilter', 'sortFilter', 'searchQuery'
        ];
        
        filterElements.forEach(elementId => {
            const element = document.getElementById(elementId);
            if (element) {
                element.value = '';
            }
        });
        
        // Clear quick filters
        this.quickFilters.clear();
        document.querySelectorAll('[data-filter]').forEach(btn => {
            btn.classList.remove('active');
        });
        
        // Reset pagination
        this.currentPageNumber = 1;
        
        // Trigger search
        this.handlePlayerSearch();
    }

    saveCurrentSearch() {
        const searchData = {
            filters: this.currentFilters,
            quickFilters: Array.from(this.quickFilters),
            timestamp: new Date().toISOString()
        };
        
        const searches = JSON.parse(localStorage.getItem('saved_searches') || '[]');
        
        // Add name prompt
        const name = prompt('Enter a name for this search:');
        if (name) {
            searchData.name = name;
            searches.unshift(searchData);
            
            // Keep only last 10 searches
            searches.splice(10);
            
            localStorage.setItem('saved_searches', JSON.stringify(searches));
            ErrorHandler.showNotification('Search saved successfully!', 'success');
        }
    }

    displayPlayers(players) {
        const grid = document.getElementById('playersGrid');
        if (!grid) return;

        if (!players || players.length === 0) {
            grid.innerHTML = `
                <div class="no-results">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="margin-bottom: 24px; opacity: 0.5;">
                        <circle cx="11" cy="11" r="8"></circle>
                        <path d="M21 21l-4.35-4.35"></path>
                    </svg>
                    <h3>No Players Found</h3>
                    <p>Try adjusting your search filters or clearing them to see more players.</p>
                    <button class="btn btn-secondary" onclick="app.clearFilters()">Clear Filters</button>
                </div>
            `;
            return;
        }

        console.log('📊 Displaying', players.length, 'players in', this.currentView, 'view');

        grid.innerHTML = '';
        grid.dataset.view = this.currentView;
        
        players.forEach(player => {
            const playerItem = PlayerCard.createPlayerItem(player, this.currentView);
            grid.appendChild(playerItem);
        });

        Utils.animate(grid, 'fade-in');
    }

    updatePlayerCount(count) {
        const countElement = document.getElementById('playerCount');
        if (countElement) {
            countElement.textContent = `${Utils.formatLargeNumber(count)} players`;
        }
    }

    updatePagination(result) {
        const pagination = document.getElementById('playersPagination');
        if (!pagination) return;

        const hasNext = result.next;
        const hasPrevious = result.previous;
        const totalPages = Math.ceil((result.count || 0) / 20);

        if (totalPages <= 1) {
            pagination.style.display = 'none';
            return;
        }

        pagination.style.display = 'flex';

        // Update buttons
        const prevBtn = document.getElementById('prevPage');
        const nextBtn = document.getElementById('nextPage');
        const pageInfo = document.getElementById('pageInfo');

        if (prevBtn) prevBtn.disabled = !hasPrevious;
        if (nextBtn) nextBtn.disabled = !hasNext;
        if (pageInfo) pageInfo.textContent = `Page ${this.currentPageNumber} of ${totalPages}`;

        // Update page numbers
        this.updatePageNumbers(totalPages);
    }

    updatePageNumbers(totalPages) {
        const pageNumbers = document.getElementById('pageNumbers');
        if (!pageNumbers) return;

        pageNumbers.innerHTML = '';

        const maxButtons = 5;
        let startPage = Math.max(1, this.currentPageNumber - Math.floor(maxButtons / 2));
        let endPage = Math.min(totalPages, startPage + maxButtons - 1);

        if (endPage - startPage < maxButtons - 1) {
            startPage = Math.max(1, endPage - maxButtons + 1);
        }

        for (let i = startPage; i <= endPage; i++) {
            const button = document.createElement('button');
            button.textContent = i;
            button.className = i === this.currentPageNumber ? 'active' : '';
            button.addEventListener('click', () => this.changePage(i));
            pageNumbers.appendChild(button);
        }
    }

    changePage(pageNumber) {
        if (pageNumber === this.currentPageNumber) return;
        
        this.currentPageNumber = pageNumber;
        this.handlePlayerSearch();
        
        // Scroll to top of results
        document.getElementById('playersGrid')?.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'start' 
        });
    }

    switchView(viewMode) {
        this.currentView = viewMode;
        
        // Update button states
        const gridBtn = document.getElementById('gridViewBtn');
        const listBtn = document.getElementById('listViewBtn');
        
        if (gridBtn && listBtn) {
            gridBtn.classList.toggle('active', viewMode === 'grid');
            listBtn.classList.toggle('active', viewMode === 'list');
        }
        
        // Re-render current players
        if (this.playersData?.results || this.playersData) {
            this.displayPlayers(this.playersData.results || this.playersData);
        }
        
        // Save preference
        localStorage.setItem('preferred_view', viewMode);
    }

    updateViewToggleState() {
        const savedView = localStorage.getItem('preferred_view') || 'grid';
        this.switchView(savedView);
    }

    populateTeamFilters() {
        const teamFilter = document.getElementById('teamFilter');
        if (teamFilter && this.teamsData) {
            const currentValue = teamFilter.value;
            
            teamFilter.innerHTML = '<option value="">All Teams</option>';
            
            this.teamsData.forEach(team => {
                const option = document.createElement('option');
                option.value = team.fpl_id;
                option.textContent = team.name;
                if (team.fpl_id == currentValue) option.selected = true;
                teamFilter.appendChild(option);
            });
        }
    }

    async loadSuggestionsPage() {
        console.log('💡 Loading suggestions page...');

        if (!this.currentTeam) {
            document.getElementById('suggestionsContainer').innerHTML = `
                <div class="no-team-message">
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="margin-bottom: 24px; opacity: 0.5;">
                        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                        <circle cx="12" cy="7" r="4"></circle>
                    </svg>
                    <h3>No Team Loaded</h3>
                    <p>Please load your FPL team from the Dashboard to see AI-powered transfer suggestions.</p>
                    <button class="btn btn-primary btn-large" data-page="dashboard">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <rect x="3" y="3" width="7" height="7"></rect>
                            <rect x="14" y="3" width="7" height="7"></rect>
                            <rect x="14" y="14" width="7" height="7"></rect>
                            <rect x="3" y="14" width="7" height="7"></rect>
                        </svg>
                        Go to Dashboard
                    </button>
                </div>
            `;
            return;
        }

        // Show suggestion filters
        const suggestionFilters = document.getElementById('suggestionFilters');
        if (suggestionFilters) {
            suggestionFilters.style.display = 'block';
        }

        const loaderId = LoadingManager.show('Loading transfer suggestions...');
        
        try {
            const suggestions = await ApiService.getTransferSuggestions({
                user_team: this.currentTeam.fpl_team_id
            });

            this.displaySuggestions(suggestions.results || suggestions);
            
        } catch (error) {
            console.error('❌ Failed to load suggestions:', error);
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
                    <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1" style="margin-bottom: 24px; opacity: 0.5;">
                        <path d="M9 12l2 2 4-4"></path>
                        <path d="M21 12c-1 0-3-1-3-3s2-3 3-3 3 1 3 3-2 3-3 3"></path>
                        <path d="M3 12c1 0 3-1 3-3s-2-3-3-3-3 1-3 3 2 3 3 3"></path>
                    </svg>
                    <h3>No Suggestions Available</h3>
                    <p>Generate transfer suggestions for your team to see AI-powered recommendations here.</p>
                    <button class="btn btn-primary btn-large" onclick="app.handleGenerateSuggestions()">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M9 12l2 2 4-4"></path>
                            <path d="M21 12c-1 0-3-1-3-3s2-3 3-3 3 1 3 3-2 3-3 3"></path>
                            <path d="M3 12c1 0 3-1-3-3s-2-3-3-3-3 1-3 3 2 3 3 3"></path>
                        </svg>
                        Generate Suggestions
                    </button>
                </div>
            `;
            return;
        }

        console.log('💡 Displaying', suggestions.length, 'transfer suggestions');

        container.innerHTML = `
            <div class="suggestions-header">
                <h3>Transfer Suggestions</h3>
                <p>AI-powered recommendations based on your team analysis</p>
                <div class="suggestions-stats" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 16px; margin-top: 16px;">
                    <div class="stat-card" style="text-align: center;">
                        <div class="stat-value" style="font-size: 1.5rem; font-weight: 700; color: var(--primary-purple);">${suggestions.length}</div>
                        <div class="stat-label" style="font-size: 0.875rem; color: var(--text-secondary);">Total Suggestions</div>
                    </div>
                    <div class="stat-card" style="text-align: center;">
                        <div class="stat-value" style="font-size: 1.5rem; font-weight: 700; color: var(--accent-green);">${suggestions.filter(s => s.confidence_score >= 80).length}</div>
                        <div class="stat-label" style="font-size: 0.875rem; color: var(--text-secondary);">High Confidence</div>
                    </div>
                    <div class="stat-card" style="text-align: center;">
                        <div class="stat-value" style="font-size: 1.5rem; font-weight: 700; color: var(--secondary-pink);">${suggestions.filter(s => s.predicted_points_gain > 0).length}</div>
                        <div class="stat-label" style="font-size: 0.875rem; color: var(--text-secondary);">Positive Impact</div>
                    </div>
                </div>
            </div>
            <div class="suggestions-list" id="suggestionsList"></div>
        `;

        const suggestionsList = document.getElementById('suggestionsList');
        suggestions.forEach((suggestion, index) => {
            const suggestionCard = SuggestionCard.create(suggestion, index);
            suggestionsList.appendChild(suggestionCard);
        });

        Utils.animate(container, 'fade-in');
    }

    async loadAnalyticsPage() {
        console.log('📊 Loading analytics page...');

        const loaderId = LoadingManager.show('Loading analytics data...');
        
        try {
            // Load analytics overview stats
            await this.loadAnalyticsOverview();
            
            // Load different analytics sections
            await Promise.all([
                this.updateTopPerformers('total_points'),
                this.updateBestValue('points_per_price'),
                this.updatePositionAnalysis('3'), // Midfielders
                this.updateFormGuide(5)
            ]);
            
            // Load price trends chart
            await this.loadPriceTrends();
            
        } catch (error) {
            console.error('❌ Analytics loading failed:', error);
            ErrorHandler.handle(error, 'loading analytics');
        } finally {
            LoadingManager.hide(loaderId);
        }
    }

    async loadAnalyticsOverview() {
        try {
            const overview = await ApiService.getAnalyticsOverview();
            
            // Update overview stats
            document.getElementById('totalPlayersCount').textContent = 
                Utils.formatLargeNumber(overview.total_players || 600);
            document.getElementById('avgPoints').textContent = 
                (overview.average_points || 45).toFixed(1);
            document.getElementById('avgPrice').textContent = 
                Utils.formatPrice(overview.average_price || 6.2);
            document.getElementById('topFormPlayer').textContent = 
                overview.top_form_player?.web_name || 'Loading...';
                
        } catch (error) {
            console.error('Failed to load analytics overview:', error);
        }
    }

    async updateTopPerformers(metric) {
        try {
            const result = await ApiService.getTopPerformers(metric, null, 10);
            const container = document.getElementById('topPerformers');
            
            if (container && result.players) {
                container.innerHTML = result.players.map((player, index) => `
                    <div class="analytics-player-item" onclick="PlayerCard.showPlayerModal(${JSON.stringify(player).replace(/"/g, '&quot;')})">
                        <span class="rank">${index + 1}</span>
                        <div style="flex: 1;">
                            <div class="name">${player.web_name}</div>
                            <div class="team">${player.team?.short_name || 'Unknown'}</div>
                        </div>
                        <div class="points">${this.formatMetricValue(player[metric] || player.total_points, metric)}</div>
                    </div>
                `).join('');
            }
        } catch (error) {
            console.error('Failed to update top performers:', error);
        }
    }

    async updateBestValue(metric) {
        try {
            const result = await ApiService.getTopPerformers('value', null, 10);
            const container = document.getElementById('bestValue');
            
            if (container && result.players) {
                container.innerHTML = result.players.map((player, index) => `
                    <div class="analytics-player-item" onclick="PlayerCard.showPlayerModal(${JSON.stringify(player).replace(/"/g, '&quot;')})">
                        <span class="rank">${index + 1}</span>
                        <div style="flex: 1;">
                            <div class="name">${player.web_name}</div>
                            <div class="team">${player.team?.short_name || 'Unknown'}</div>
                        </div>
                        <div class="value">${Utils.calculateValueScore(player.total_points, player.current_price)}</div>
                    </div>
                `).join('');
            }
        } catch (error) {
            console.error('Failed to update best value:', error);
        }
    }

    async updatePositionAnalysis(position) {
        try {
            const analysis = await ApiService.getPositionAnalytics(position);
            const container = document.getElementById('positionAnalysis');
            
            if (container && analysis) {
                const positionInfo = Utils.getPositionInfo(parseInt(position));
                
                container.innerHTML = `
                    <div class="position-stats">
                        <div class="stat">
                            <span class="label">Total Players</span>
                            <span class="value">${analysis.total_players || 0}</span>
                        </div>
                        <div class="stat">
                            <span class="label">Avg Points</span>
                            <span class="value">${analysis.statistics?.avg_points?.toFixed(1) || '0.0'}</span>
                        </div>
                        <div class="stat">
                            <span class="label">Avg Price</span>
                            <span class="value">${Utils.formatPrice(analysis.statistics?.avg_price || 0)}</span>
                        </div>
                        <div class="stat">
                            <span class="label">Top Scorer</span>
                            <span class="value" style="font-size: 0.875rem;">${analysis.top_performer?.web_name || 'N/A'}</span>
                        </div>
                    </div>
                    ${analysis.insights ? `
                        <div style="margin-top: 16px; padding: 12px; background: var(--bg-secondary); border-radius: 8px; font-size: 0.875rem; color: var(--text-secondary);">
                            <strong>Insights:</strong> ${analysis.insights}
                        </div>
                    ` : ''}
                `;
            }
        } catch (error) {
            console.error('Failed to update position analysis:', error);
        }
    }

    async updateFormGuide(period) {
        try {
            // This would typically come from a form guide API endpoint
            const container = document.getElementById('formGuide');
            
            if (container) {
                // Mock data for demonstration
                const formData = [
                    { name: 'Salah', team: 'LIV', form: 8.2, trend: 'up' },
                    { name: 'Haaland', team: 'MCI', form: 7.8, trend: 'stable' },
                    { name: 'Kane', team: 'TOT', form: 7.1, trend: 'down' },
                    { name: 'De Bruyne', team: 'MCI', form: 6.9, trend: 'up' },
                    { name: 'Rashford', team: 'MUN', form: 6.5, trend: 'up' }
                ];
                
                container.innerHTML = formData.map((player, index) => {
                    const trendIcon = player.trend === 'up' ? '↗️' : player.trend === 'down' ? '↘️' : '➡️';
                    const trendColor = player.trend === 'up' ? 'var(--accent-green)' : 
                                    player.trend === 'down' ? 'var(--accent-red)' : 'var(--text-secondary)';
                    
                    return `
                        <div class="analytics-player-item">
                            <span class="rank">${index + 1}</span>
                            <div style="flex: 1;">
                                <div class="name">${player.name}</div>
                                <div class="team">${player.team}</div>
                            </div>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <div class="points">${player.form}</div>
                                <div style="color: ${trendColor};">${trendIcon}</div>
                            </div>
                        </div>
                    `;
                }).join('');
            }
        } catch (error) {
            console.error('Failed to update form guide:', error);
        }
    }

    async loadPriceTrends() {
        try {
            const canvas = document.getElementById('priceChart');
            if (!canvas) return;

            // Mock data for price trends
            const data = {
                labels: ['GW1', 'GW2', 'GW3', 'GW4', 'GW5', 'GW6', 'GW7', 'GW8', 'GW9', 'GW10'],
                datasets: [
                    {
                        label: 'Premium Players (£9m+)',
                        data: [9.2, 9.3, 9.1, 9.4, 9.5, 9.3, 9.6, 9.4, 9.7, 9.5],
                        borderColor: 'rgb(99, 102, 241)',
                        backgroundColor: 'rgba(99, 102, 241, 0.1)',
                        tension: 0.4
                    },
                    {
                        label: 'Mid-price Players (£5-9m)',
                        data: [6.8, 6.9, 6.7, 7.0, 7.1, 6.9, 7.2, 7.0, 7.3, 7.1],
                        borderColor: 'rgb(16, 185, 129)',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        tension: 0.4
                    },
                    {
                        label: 'Budget Players (£5m-)',
                        data: [4.2, 4.3, 4.1, 4.4, 4.5, 4.3, 4.6, 4.4, 4.7, 4.5],
                        borderColor: 'rgb(245, 158, 11)',
                        backgroundColor: 'rgba(245, 158, 11, 0.1)',
                        tension: 0.4
                    }
                ]
            };

            ChartManager.createChart('priceChart', {
                type: 'line',
                data: data,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: true,
                            text: 'Player Price Trends by Category'
                        },
                        legend: {
                            position: 'top'
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: false,
                            title: {
                                display: true,
                                text: 'Average Price (£m)'
                            }
                        },
                        x: {
                            title: {
                                display: true,
                                text: 'Gameweek'
                            }
                        }
                    }
                }
            });
            
        } catch (error) {
            console.error('Failed to load price trends:', error);
        }
    }

    formatMetricValue(value, metric) {
        switch(metric) {
            case 'total_points':
                return Utils.formatPoints(value);
            case 'current_price':
                return Utils.formatPrice(value);
            case 'selected_by_percent':
                return Utils.formatPercentage(value);
            case 'form':
            case 'points_per_game':
            case 'ict_index':
                return parseFloat(value).toFixed(1);
            default:
                return value;
        }
    }

    // Utility method to handle page initialization from URL hash
    initializeFromHash() {
        const hash = window.location.hash.replace('#', '');
        const validPages = ['dashboard', 'players', 'suggestions', 'analytics'];
        
        if (validPages.includes(hash)) {
            this.navigateToPage(hash);
        }
    }
}

// Initialize the application when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.app = new FPLApp();
    
    // Initialize global components
    console.log('🌟 FPL Transfer Suggestions App Ready!');
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
                console.log('✅ SW registered: ', registration);
            })
            .catch(registrationError => {
                console.log('❌ SW registration failed: ', registrationError);
            });
    });
}

// Global error handlers
window.addEventListener('error', (e) => {
    console.error('🚨 Global error:', e.error);
    ErrorHandler.handle(e.error, 'global error handler');
});

window.addEventListener('unhandledrejection', (e) => {
    console.error('🚨 Unhandled promise rejection:', e.reason);
    ErrorHandler.handle(e.reason, 'unhandled promise rejection');
});

// Performance monitoring
if (typeof PerformanceObserver !== 'undefined') {
    const perfObserver = new PerformanceObserver((list) => {
        list.getEntries().forEach((entry) => {
            if (entry.entryType === 'navigation') {
                console.log('📊 Page load time:', entry.loadEventEnd - entry.loadEventStart, 'ms');
            }
        });
    });
    
    perfObserver.observe({ entryTypes: ['navigation'] });
}

console.log('🚀 Application scripts loaded successfully!');
window.app = null;


document.addEventListener('DOMContentLoaded', async () => {

    async function testBackendConnection() {
    try {
        const response = await fetch(`${API_CONFIG.baseURL}/health/`);
        const data = await response.json();
        
        if (response.ok) {
            console.log('✅ Backend connection successful:', data);
            return true;
        } else {
            console.error('❌ Backend health check failed:', data);
            return false;
        }
    } catch (error) {
        console.error('❌ Failed to connect to backend:', error);
        return false;
    }
}


    console.log('🚀 Initializing FPL App...');
    
    // Test backend connection
    const isConnected = await testBackendConnection();
    
    if (isConnected) {
        // Initialize the main app
        window.app = new FPLApp();
        console.log('✅ App initialized successfully');
    } else {
        // Show connection error
        document.body.innerHTML = `
            <div style="text-align: center; padding: 50px; font-family: Arial;">
                <h2>❌ Backend Connection Failed</h2>
                <p>Unable to connect to the FPL API backend.</p>
                <p>Please ensure the Django server is running on <code>localhost:8000</code></p>
                <button onclick="location.reload()">Retry Connection</button>
            </div>
        `;
    }
});