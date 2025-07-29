// Utility Functions
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

    // Get player status color and text
    getPlayerStatus(status) {
        const statusMap = {
            'a': { text: 'Available', class: 'status-available' },
            'd': { text: 'Doubtful', class: 'status-doubtful' },
            'i': { text: 'Injured', class: 'status-injured' },
            's': { text: 'Suspended', class: 'status-suspended' },
            'u': { text: 'Unavailable', class: 'status-injured' },
            'n': { text: 'Not Available', class: 'status-injured' }
        };
        return statusMap[status] || { text: 'Unknown', class: '' };
    },

    // Get position name
    getPositionName(positionId) {
        const positions = {
            1: 'GK',
            2: 'DEF', 
            3: 'MID',
            4: 'FWD'
        };
        return positions[positionId] || 'Unknown';
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

    // Generate unique ID
    generateId() {
        return Date.now().toString(36) + Math.random().toString(36).substr(2);
    },

    // Animate element
    animate(element, animation) {
        element.classList.add(animation);
        element.addEventListener('animationend', () => {
            element.classList.remove(animation);
        }, { once: true });
    }
};

// Loading Manager
const LoadingManager = {
    activeLoaders: new Set(),

    show(message = 'Loading...', id = null) {
        const loaderId = id || Utils.generateId();
        this.activeLoaders.add(loaderId);

        const overlay = document.getElementById('loadingOverlay');
        const loadingText = document.getElementById('loadingText');
        
        if (loadingText) {
            loadingText.textContent = message;
        }
        
        if (overlay) {
            overlay.style.display = 'flex';
        }

        return loaderId;
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

// Player Card Component
const PlayerCard = {
    create(player, options = {}) {
        const { showStats = false, isClickable = true, extraClasses = '' } = options;
        
        const card = document.createElement('div');
        card.className = `player-card ${extraClasses}`;
        card.dataset.playerId = player.fpl_id;

        if (player.is_captain) card.classList.add('captain');
        if (player.is_vice_captain) card.classList.add('vice-captain');

        const statusInfo = Utils.getPlayerStatus(player.status);
        
        card.innerHTML = `
            <div class="player-name">${player.web_name}</div>
            <div class="player-price">${Utils.formatPrice(player.current_price)}</div>
            <div class="player-points">${Utils.formatPoints(player.total_points)}</div>
            ${showStats ? `
                <div class="player-stats-mini">
                    <span class="form">Form: ${player.form}</span>
                    <span class="ownership">${Utils.formatPercentage(player.selected_by_percent)}</span>
                </div>
            ` : ''}
            <div class="status-indicator ${statusInfo.class}" title="${statusInfo.text}"></div>
        `;

        if (isClickable) {
            card.style.cursor = 'pointer';
            card.addEventListener('click', () => {
                this.showPlayerModal(player);
            });
        }

        return card;
    },

    createBenchPlayer(player) {
        const benchPlayer = document.createElement('div');
        benchPlayer.className = 'bench-player';
        benchPlayer.dataset.playerId = player.fpl_id;

        const statusInfo = Utils.getPlayerStatus(player.status);
        
        benchPlayer.innerHTML = `
            <div class="status-indicator ${statusInfo.class}"></div>
            <span class="name">${player.web_name}</span>
            <span class="price">${Utils.formatPrice(player.current_price)}</span>
        `;

        return benchPlayer;
    },

    createPlayerItem(player) {
        const item = document.createElement('div');
        item.className = 'player-item';
        item.dataset.playerId = player.fpl_id;

        const statusInfo = Utils.getPlayerStatus(player.status);
        
        item.innerHTML = `
            <div class="player-header">
                <div class="player-info">
                    <h4>${player.web_name}</h4>
                    <div class="player-team">${player.team?.short_name || 'Unknown'} • ${Utils.getPositionName(player.position)}</div>
                </div>
                <div class="player-price-tag">${Utils.formatPrice(player.current_price)}</div>
            </div>
            <div class="player-meta">
                <div class="status-indicator ${statusInfo.class}"></div>
                <span class="status-text">${statusInfo.text}</span>
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
        `;

        item.addEventListener('click', () => {
            this.showPlayerModal(player);
        });

        return item;
    },

    async showPlayerModal(player) {
        // Create modal
        const modal = document.createElement('div');
        modal.className = 'modal-overlay';
        modal.innerHTML = `
            <div class="modal">
                <div class="modal-header">
                    <h3>${player.web_name}</h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-content">
                    <div class="player-modal-loading">Loading player details...</div>
                </div>
            </div>
        `;

        document.body.appendChild(modal);

        // Close modal functionality
        const closeModal = () => {
            modal.remove();
        };

        modal.querySelector('.modal-close').addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        // Load player details
        try {
            const playerDetails = await ApiService.getPlayer(player.fpl_id);
            const performanceHistory = await ApiService.getPlayerPerformanceHistory(player.fpl_id, 5);
            
            modal.querySelector('.modal-content').innerHTML = `
                <div class="player-details">
                    <div class="player-overview">
                        <div class="player-info-detailed">
                            <h4>${playerDetails.web_name}</h4>
                            <p>${playerDetails.team?.name} • ${Utils.getPositionName(playerDetails.position)}</p>
                            <div class="price-tag">${Utils.formatPrice(playerDetails.current_price)}</div>
                        </div>
                        <div class="player-stats-grid">
                            <div class="stat">
                                <span class="value">${Utils.formatPoints(playerDetails.total_points)}</span>
                                <span class="label">Total Points</span>
                            </div>
                            <div class="stat">
                                <span class="value">${playerDetails.form}</span>
                                <span class="label">Form</span>
                            </div>
                            <div class="stat">
                                <span class="value">${playerDetails.points_per_game}</span>
                                <span class="label">PPG</span>
                            </div>
                            <div class="stat">
                                <span class="value">${Utils.formatPercentage(playerDetails.selected_by_percent)}</span>
                                <span class="label">Ownership</span>
                            </div>
                        </div>
                    </div>
                    
                    ${performanceHistory.performances?.length > 0 ? `
                        <div class="performance-history">
                            <h5>Recent Performance</h5>
                            <div class="performance-bars">
                                ${performanceHistory.performances.slice(0, 5).map(perf => `
                                    <div class="performance-bar">
                                        <div class="bar" style="height: ${Math.max(perf.points * 5, 5)}px"></div>
                                        <span class="gw">GW${perf.gameweek}</span>
                                        <span class="points">${perf.points}</span>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}
                    
                    <div class="detailed-stats">
                        <h5>Season Stats</h5>
                        <div class="stats-grid">
                            <div class="stat-row">
                                <span>Minutes Played</span>
                                <span>${playerDetails.minutes || 0}</span>
                            </div>
                            <div class="stat-row">
                                <span>Goals</span>
                                <span>${playerDetails.goals_scored || 0}</span>
                            </div>
                            <div class="stat-row">
                                <span>Assists</span>
                                <span>${playerDetails.assists || 0}</span>
                            </div>
                            <div class="stat-row">
                                <span>Clean Sheets</span>
                                <span>${playerDetails.clean_sheets || 0}</span>
                            </div>
                            <div class="stat-row">
                                <span>Bonus Points</span>
                                <span>${playerDetails.bonus || 0}</span>
                            </div>
                        </div>
                    </div>
                </div>
            `;

        } catch (error) {
            modal.querySelector('.modal-content').innerHTML = `
                <div class="error-message">
                    <p>Failed to load player details</p>
                    <button class="btn btn-secondary" onclick="this.closest('.modal-overlay').remove()">Close</button>
                </div>
            `;
        }
    }
};

// Formation Component
const Formation = {
    render(players, container) {
        if (!container) return;

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

        // Group players by position
        const starters = players.filter(p => p.position <= 11).sort((a, b) => a.position - b.position);
        const positionGroups = {
            1: [], // GK
            2: [], // DEF
            3: [], // MID
            4: []  // FWD
        };

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
                        extraClasses: teamPlayer.is_captain ? 'captain' : teamPlayer.is_vice_captain ? 'vice-captain' : ''
                    });
                    positionContainer.appendChild(playerCard);
                });
            }
        });
    },

    renderBench(players, container) {
        if (!container) return;

        const benchContainer = container.querySelector('.bench-players');
        if (!benchContainer) return;

        benchContainer.innerHTML = '';

        const bench = players.filter(p => p.position > 11).sort((a, b) => a.position - b.position);
        
        bench.forEach(teamPlayer => {
            const benchPlayer = PlayerCard.createBenchPlayer(teamPlayer.player);
            benchContainer.appendChild(benchPlayer);
        });
    }
};

// Suggestion Component
const SuggestionCard = {
    create(suggestion) {
        const card = document.createElement('div');
        card.className = 'suggestion-item';
        
        const confidenceColor = suggestion.confidence_score >= 80 ? 'var(--secondary-green)' : 
                               suggestion.confidence_score >= 60 ? '#ffa500' : 'var(--primary-pink)';

        card.innerHTML = `
            <div class="suggestion-header">
                <div class="suggestion-type">${suggestion.suggestion_type.replace('_', ' ')}</div>
                <div class="priority-score">${suggestion.priority_score}</div>
            </div>
            
            <div class="transfer-details">
                <div class="player-out">
                    <div class="name">${suggestion.player_out.web_name}</div>
                    <div class="team">${suggestion.player_out.team?.short_name}</div>
                    <div class="price">${Utils.formatPrice(suggestion.player_out.current_price)}</div>
                </div>
                
                <div class="transfer-arrow">→</div>
                
                <div class="player-in">
                    <div class="name">${suggestion.player_in.web_name}</div>
                    <div class="team">${suggestion.player_in.team?.short_name}</div>
                    <div class="price">${Utils.formatPrice(suggestion.player_in.current_price)}</div>
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
                    <span class="label">Predicted Gain</span>
                    <span class="value">${suggestion.predicted_points_gain > 0 ? '+' : ''}${suggestion.predicted_points_gain} pts</span>
                </div>
                <div class="stat">
                    <span class="label">Confidence</span>
                    <span class="value" style="color: ${confidenceColor}">${suggestion.confidence_score}%</span>
                </div>
            </div>
            
            <div class="suggestion-reason">
                ${suggestion.reason}
            </div>
            
            <div class="suggestion-actions">
                <button class="btn btn-secondary" onclick="SuggestionCard.comparePlayers(${suggestion.player_out.id}, ${suggestion.player_in.id})">
                    Compare Players
                </button>
                <button class="btn btn-primary" onclick="SuggestionCard.markImplemented(${suggestion.id})">
                    Mark as Done
                </button>
            </div>
        `;

        return card;
    },

    async comparePlayers(playerOutId, playerInId) {
        try {
            const comparison = await ApiService.comparePlayers(
                [playerOutId, playerInId],
                ['total_points', 'form', 'points_per_game', 'current_price', 'selected_by_percent']
            );
            
            // Show comparison modal
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
                    <h3>Player Comparison</h3>
                    <button class="modal-close">&times;</button>
                </div>
                <div class="modal-content">
                    <div class="comparison-grid">
                        ${comparison.players.map(player => `
                            <div class="comparison-player">
                                <h4>${player.name}</h4>
                                <p>${player.team} • ${player.position}</p>
                                <div class="comparison-stats">
                                    ${Object.entries(player.stats).map(([key, value]) => `
                                        <div class="stat-row">
                                            <span class="stat-name">${key.replace('_', ' ')}</span>
                                            <span class="stat-value">${typeof value === 'number' ? value.toFixed(1) : value}</span>
                                        </div>
                                    `).join('')}
                                </div>
                            </div>
                        `).join('')}
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

    async markImplemented(suggestionId) {
        try {
            await ApiService.markSuggestionImplemented(suggestionId);
            
            // Find and update the suggestion card
            const card = document.querySelector(`[data-suggestion-id="${suggestionId}"]`);
            if (card) {
                card.style.opacity = '0.6';
                card.querySelector('.suggestion-actions').innerHTML = `
                    <span class="implemented-badge">✓ Implemented</span>
                `;
            }
            
            ErrorHandler.showNotification('Suggestion marked as implemented', 'success');
        } catch (error) {
            ErrorHandler.handle(error, 'marking suggestion as implemented');
        }
    }
};

// Filter Component
const FilterComponent = {
    create(filters, onFilterChange) {
        const container = document.createElement('div');
        container.className = 'filters';

        Object.entries(filters).forEach(([key, config]) => {
            const filterGroup = document.createElement('div');
            filterGroup.className = 'filter-group';

            const label = document.createElement('label');
            label.htmlFor = key;
            label.textContent = config.label;

            let input;
            if (config.type === 'select') {
                input = document.createElement('select');
                input.innerHTML = `
                    <option value="">${config.placeholder || 'All'}</option>
                    ${config.options.map(option => 
                        `<option value="${option.value}">${option.label}</option>`
                    ).join('')}
                `;
            } else {
                input = document.createElement('input');
                input.type = config.type || 'text';
                input.placeholder = config.placeholder || '';
                if (config.step) input.step = config.step;
                if (config.min) input.min = config.min;
                if (config.max) input.max = config.max;
            }

            input.id = key;
            input.addEventListener('change', () => {
                onFilterChange(key, input.value);
            });

            filterGroup.appendChild(label);
            filterGroup.appendChild(input);
            container.appendChild(filterGroup);
        });

        return container;
    }
};

// Pagination Component
const Pagination = {
    create(currentPage, totalPages, onPageChange) {
        const container = document.createElement('div');
        container.className = 'pagination';

        // Previous button
        const prevBtn = document.createElement('button');
        prevBtn.className = 'btn btn-secondary';
        prevBtn.textContent = 'Previous';
        prevBtn.disabled = currentPage <= 1;
        prevBtn.addEventListener('click', () => {
            if (currentPage > 1) onPageChange(currentPage - 1);
        });

        // Page info
        const pageInfo = document.createElement('span');
        pageInfo.textContent = `Page ${currentPage} of ${totalPages}`;

        // Next button
        const nextBtn = document.createElement('button');
        nextBtn.className = 'btn btn-secondary';
        nextBtn.textContent = 'Next';
        nextBtn.disabled = currentPage >= totalPages;
        nextBtn.addEventListener('click', () => {
            if (currentPage < totalPages) onPageChange(currentPage + 1);
        });

        container.appendChild(prevBtn);
        container.appendChild(pageInfo);
        container.appendChild(nextBtn);

        return container;
    }
};

// Export components
window.Utils = Utils;
window.LoadingManager = LoadingManager;
window.PlayerCard = PlayerCard;
window.Formation = Formation;
window.SuggestionCard = SuggestionCard;
window.FilterComponent = FilterComponent;
window.Pagination = Pagination;