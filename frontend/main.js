/**
 * Main JavaScript file for Fashion Supply Chain game frontend.
 * 
 * This file handles:
 * - UI initialization (tabs, dropdowns, notifications)
 * - Game state management and rendering
 * - API communication with backend
 * - Negotiation flow (proposals, chat, offers)
 * - Order placement and round results
 * - Configuration management
 * 
 * Structure:
 * 1. Global state variables
 * 2. DOM element references
 * 3. UI initialization functions
 * 4. Rendering functions
 * 5. API helper functions
 * 6. Game control functions
 * 7. Negotiation functions
 * 8. Order functions
 * 9. Configuration functions
 * 10. Initialization on page load
 */

// ================================
// Global State Variables
// ================================
let sessionId = null;     // Current game session_id
let currentState = null;  // Latest GameStateResponse from backend
let latestDisplayedProposal = null;
let currentOfferVersion = null;
let negotiationPending = false;

document.addEventListener("DOMContentLoaded", () => {
    const isLocalFrontend =
        window.location.protocol === "file:" ||
        window.location.hostname === "127.0.0.1" ||
        window.location.hostname === "localhost";
    const BASE_URL = isLocalFrontend ? "http://127.0.0.1:8000/api" : "/api";
    let participantId = sessionStorage.getItem("fsp_participant_id") || null;
    let participantName = sessionStorage.getItem("fsp_participant_name") || "";

    // ================================
    // DOM Element References
    // ================================
    const loginScreenEl = document.getElementById("login-screen");
    const loginFormEl = document.getElementById("login-form");
    const loginNameInput = document.getElementById("login-name");
    const loginEmailInput = document.getElementById("login-email");
    const loginErrorEl = document.getElementById("login-error");
    const loginSubmitBtn = document.getElementById("login-submit-btn");

    // Navigation and UI elements
    const notificationListEl = document.getElementById("notification-list");
    const phaseBannerEl = document.getElementById("phase-banner");
    const contractSummaryEl = document.getElementById("contract-summary");
    
    // Demand history elements
    const demandChartCanvas = document.getElementById("demand-chart");
    const demandHistorySummaryEl = document.getElementById("demand-history-summary");
    const demandHistoryTableEl = document.getElementById("demand-history-table");
    
    // Round result element
    const roundResultCardEl = document.getElementById("round-result-card");
    const roundResultsTableEl = document.getElementById("round-results-table");
    
    // Debug output elements
    const gameStateOutput = document.getElementById("game-state-output");
    const summaryOutput = document.getElementById("summary-output");
    const summaryOutputInstructor = document.getElementById("summary-output-instructor");
    const summaryOutputDebug = document.getElementById("summary-output-debug");
    
    // Chart instance
    let demandChart = null;  // Chart.js instance for demand visualization
    
    // Notification system
    let notifications = [];

    // ================================
    // UI Initialization Functions
    // ================================

    function unlockApp() {
        document.body.classList.remove("app-locked");
        if (loginScreenEl) {
            loginScreenEl.classList.add("hidden-section");
        }
    }

    function initLoginSection() {
        if (participantId) {
            unlockApp();
            return;
        }

        document.body.classList.add("app-locked");
        if (!loginFormEl) return;

        loginFormEl.addEventListener("submit", async (e) => {
            e.preventDefault();

            const name = (loginNameInput?.value || "").trim();
            if (!name) {
                if (loginErrorEl) loginErrorEl.textContent = "Please enter your name.";
                return;
            }

            if (loginSubmitBtn) {
                loginSubmitBtn.disabled = true;
                loginSubmitBtn.textContent = "Entering...";
            }
            if (loginErrorEl) loginErrorEl.textContent = "";

            try {
                const data = await fetchJsonWithDetail(`${BASE_URL}/participants`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        name,
                        email: (loginEmailInput?.value || "").trim() || null,
                    }),
                });

                participantId = data.participant_id;
                participantName = name;
                sessionStorage.setItem("fsp_participant_id", participantId);
                sessionStorage.setItem("fsp_participant_name", participantName);
                unlockApp();
                addNotification(`Welcome, ${participantName}.`, "success");
            } catch (err) {
                console.error(err);
                if (loginErrorEl) {
                    loginErrorEl.textContent = "Login failed: " + err.message;
                }
            } finally {
                if (loginSubmitBtn) {
                    loginSubmitBtn.disabled = false;
                    loginSubmitBtn.textContent = "Enter Game";
                }
            }
        });
    }
    
    /**
     * Initializes tab switching functionality.
     * 
     * What happens:
     * - Sets up click handlers for tab buttons
     * - Switches active tab and corresponding content
     * - Removes active class from all tabs/contents before activating selected one
     */
    function initTabSwitching() {
        const tabButtons = document.querySelectorAll(".tab-btn");
        const tabContents = document.querySelectorAll(".tab-content");

        tabButtons.forEach(btn => {
            btn.addEventListener("click", () => {
                const targetTab = btn.dataset.tab;

                // Remove active class from all tabs and contents
                tabButtons.forEach(b => b.classList.remove("active"));
                tabContents.forEach(c => c.classList.remove("active"));

                // Add active class to clicked tab and corresponding content
                btn.classList.add("active");
                const targetContent = document.getElementById(`${targetTab}-tab`);
                if (targetContent) {
                    targetContent.classList.add("active");
                }
            });
        });
    }

    /**
     * Initializes status dropdown in navigation bar.
     * 
     * What happens:
     * - Sets up click handler to toggle dropdown visibility
     * - Closes dropdown when clicking outside
     */
    function initStatusDropdown() {
        const statusBtn = document.getElementById("status-dropdown-btn");
        const statusDropdown = document.querySelector(".status-dropdown");

        if (statusBtn && statusDropdown) {
            statusBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                statusDropdown.classList.toggle("active");
            });

            // Close when clicking outside
            document.addEventListener("click", (e) => {
                if (!statusDropdown.contains(e.target)) {
                    statusDropdown.classList.remove("active");
                }
            });
        }
    }

    /**
     * Initializes notification dropdown and badge system.
     * 
     * What happens:
     * - Sets up click handler to toggle dropdown visibility
     * - Closes dropdown when clicking outside
     * - Returns function to update notification badge
     * 
     * Output:
     * Returns updateNotificationBadge function for external use
     */
    function initNotificationDropdown() {
        const notificationBtn = document.getElementById("notification-dropdown-btn");
        const notificationDropdown = document.querySelector(".notification-dropdown");
        const notificationBadge = document.getElementById("notification-badge");

        if (notificationBtn && notificationDropdown) {
            notificationBtn.addEventListener("click", (e) => {
                e.stopPropagation();
                notificationDropdown.classList.toggle("active");
            });

            // Close when clicking outside
            document.addEventListener("click", (e) => {
                if (!notificationDropdown.contains(e.target)) {
                    notificationDropdown.classList.remove("active");
                }
            });
        }

        /**
         * Updates the notification badge with current unread count.
         * 
         * What happens:
         * - Counts notifications in the array
         * - Updates badge text (shows "99+" if count > 99)
         * - Shows/hides badge based on count
         */
        function updateNotificationBadge() {
            if (notificationBadge) {
                const unreadCount = notifications.length;
                if (unreadCount > 0) {
                    notificationBadge.textContent = unreadCount > 99 ? "99+" : unreadCount;
                    notificationBadge.classList.remove("hidden");
                } else {
                    notificationBadge.classList.add("hidden");
                }
            }
        }

        return updateNotificationBadge;
    }

    // Initialize notification system
    const updateNotificationBadge = initNotificationDropdown();

    // ================================
    // Notification Functions
    // ================================
    
    /**
     * Renders notifications list in the dropdown.
     * 
     * What happens:
     * - Clears existing notification list
     * - Displays notifications in reverse order (newest first)
     * - Updates notification badge
     */
    function renderNotifications() {
        if (!notificationListEl) return;
        notificationListEl.innerHTML = "";

        // Display newest first
        const items = [...notifications].reverse();
        for (const n of items) {
            const li = document.createElement("li");
            li.textContent = `[${n.timestamp}] ${n.message}`;
            li.dataset.type = n.type;
            notificationListEl.appendChild(li);
        }

        // Update badge
        if (updateNotificationBadge) {
            updateNotificationBadge();
        }
    }

    /**
     * Adds a new notification to the system.
     * 
     * Inputs:
     * - message: The notification message text
     * - type: Notification type ("info", "success", "error")
     * 
     * What happens:
     * - Creates timestamp for the notification
     * - Adds notification to array
     * - Keeps only last 20 notifications
     * - Renders updated notification list
     */
    function addNotification(message, type = "info") {
        const timestamp = new Date().toLocaleTimeString();
        notifications.push({ timestamp, message, type });

        // Keep only last 20 notifications
        if (notifications.length > 20) {
            notifications.shift();
        }

        renderNotifications();
    }

    // ================================
    // Rendering Functions
    // ================================
    
    /**
     * Renders the demand history chart using Chart.js.
     * 
     * What happens:
     * - Checks if demand data exists
     * - Calculates initial history length (pre-game periods vs game rounds)
     * - Creates labels distinguishing historical periods from game rounds
     * - Calculates statistics (min, max, average)
     * - Destroys previous chart if exists
     * - Creates new Chart.js line chart with demand data
     * - Updates summary text with statistics
     */
    function renderDemandChart() {
        if (!demandChartCanvas) return;

        if (!currentState ||
            !Array.isArray(currentState.historical_demands) ||
            currentState.historical_demands.length === 0
        ) {
            if (demandHistorySummaryEl) {
                demandHistorySummaryEl.textContent = "No demand history yet.";
            }
            if (demandChart) {
                demandChart.destroy();
                demandChart = null;
            }
            return;
        }

        const data = currentState.historical_demands.map(Number).filter(Number.isFinite);

        // Calculate initial history length: historical_demands starts with pre-game history,
        // then adds one demand per game round. round_number starts at 1 and increments after each round.
        const initialHistoryLength = data.length - (currentState.round_number - 1);

        // Create labels: historical periods vs game rounds
        const labels = data.map((_, idx) => {
            if (idx < initialHistoryLength) {
                return `Period ${idx + 1}`;
            } else {
                const gameRoundNum = idx - initialHistoryLength + 1;
                return `Round ${gameRoundNum}`;
            }
        });

        const minVal = Math.min(...data);
        const maxVal = Math.max(...data);
        const sum = data.reduce((a, b) => a + b, 0);
        const avg = sum / data.length;

        // Write summary
        if (demandHistorySummaryEl) {
            demandHistorySummaryEl.textContent =
                `n = ${data.length}, min = ${minVal}, max = ${maxVal}, avg ≈ ${avg.toFixed(1)}`;
        }

        // Destroy previous chart if it exists
        if (demandChart) {
            demandChart.destroy();
            demandChart = null;
        }

        // Create new Chart
        demandChart = new Chart(demandChartCanvas, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Demand',
                    data: data,
                    borderColor: 'black',
                    borderWidth: 2,
                    backgroundColor: 'rgba(0,0,0,0.1)',
                    pointRadius: 3,
                    tension: 0.2  // Slight smoothing
                }]
            },
            options: {
                responsive: true,
                scales: {
                    x: {
                        title: { display: true, text: "Period / Round" }
                    },
                    y: {
                        title: { display: true, text: "Demand" },
                        beginAtZero: false
                    }
                }
            }
        });
    }

    /**
     * Renders the demand history table.
     * 
     * What happens:
     * - Checks if demand data exists
     * - Calculates initial history length (pre-game periods vs game rounds)
     * - Creates table rows for each demand value
     * - Labels rows as "Period X" for historical data, "Round X" for game rounds
     * - Shows/hides table based on data availability
     */
    function renderDemandTable() {
        if (!demandHistoryTableEl) return;

        if (!currentState ||
            !Array.isArray(currentState.historical_demands) ||
            currentState.historical_demands.length === 0
        ) {
            demandHistoryTableEl.style.display = "none";
            return;
        }

        const data = currentState.historical_demands.map(Number).filter(Number.isFinite);

        if (data.length === 0) {
            demandHistoryTableEl.style.display = "none";
            return;
        }

        // Calculate initial history length: historical_demands starts with pre-game history,
        // then adds one demand per game round. round_number starts at 1 and increments after each round.
        const initialHistoryLength = data.length - (currentState.round_number - 1);

        const tbody = demandHistoryTableEl.querySelector("tbody");
        if (!tbody) return;

        tbody.innerHTML = "";

        for (let idx = 0; idx < data.length; idx++) {
            const row = document.createElement("tr");
            const periodCell = document.createElement("td");
            const demandCell = document.createElement("td");

            // Label historical periods vs game rounds
            if (idx < initialHistoryLength) {
                periodCell.textContent = `Period ${idx + 1}`;
            } else {
                const gameRoundNum = idx - initialHistoryLength + 1;
                periodCell.textContent = `Round ${gameRoundNum}`;
            }
            demandCell.textContent = data[idx];

            row.appendChild(periodCell);
            row.appendChild(demandCell);
            tbody.appendChild(row);
        }

        demandHistoryTableEl.style.display = "table";
    }

    /**
     * Renders the round result card with detailed round information.
     * 
     * Inputs:
     * - roundOutput: RoundOutput object from backend with round results
     * - orderQuantity: The quantity ordered (optional, falls back to roundOutput.order_quantity)
     * 
     * What happens:
     * - Extracts all round data (demand, sales, returns, profits, etc.)
     * - Calculates round index (round_number - 1, since round_number increments after each round)
     * - Formats numbers with 2 decimal places
     * - Creates HTML card displaying buyer and supplier results
     * 
     * Output:
     * Updates roundResultCardEl innerHTML with formatted round results
     */
    function renderRoundResultCard(roundOutput, orderQuantity) {
        if (!roundResultCardEl) return;

        if (!roundOutput) {
            roundResultCardEl.textContent = "No order placed yet.";
            return;
        }

        // round_number starts at 1 and increments after each round
        // So after the first round, round_number = 2, meaning we just completed Round 1
        const roundIndex = currentState ? (currentState.round_number - 1) : null;

        const Q = orderQuantity ?? roundOutput.order_quantity ?? null;
        const D = roundOutput.realized_demand ?? null;
        const sales = roundOutput.sales ?? null;
        const unsold = roundOutput.unsold ?? null;
        const returnsVal = roundOutput.returns ?? null;
        const leftovers = roundOutput.leftovers ?? null;

        const buyerRevenue = roundOutput.buyer_revenue;
        const buyerCost = roundOutput.buyer_cost;
        const buyerProfit = roundOutput.buyer_profit;

        const supplierRevenue = roundOutput.supplier_revenue;
        const supplierCost = roundOutput.supplier_cost;
        const supplierProfit = roundOutput.supplier_profit;

        /**
         * Formats a number to 2 decimal places, or returns "?" if not a number.
         */
        function fmt(x) {
            return (typeof x === "number") ? x.toFixed(2) : (x ?? "?");
        }

        function profitClass(val) {
            if (typeof val !== "number") return "";
            return val >= 0 ? "profit-positive" : "profit-negative";
        }

        roundResultCardEl.innerHTML = `
            <div class="round-result-header">
                <div class="round-result-field"><strong>Round:</strong> ${roundIndex !== null ? `Round ${roundIndex}` : "?"}</div>
                <div class="round-result-field"><strong>Order Q:</strong> ${Q ?? "?"}</div>
                <div class="round-result-field"><strong>Realized demand D:</strong> ${D ?? "?"}</div>
            </div>
            <div class="round-result-stats">
                <span class="round-result-stat"><strong>Sales:</strong> ${sales ?? "?"}</span>
                <span class="round-result-stat"><strong>Returns:</strong> ${returnsVal ?? "?"}</span>
                <span class="round-result-stat"><strong>Leftover inventory:</strong> ${leftovers ?? "?"}</span>
            </div>
            <div class="round-result-row">
                <h5>Buyer</h5>
                <div class="round-result-field">Revenue: ${fmt(buyerRevenue)}</div>
                <div class="round-result-field">Cost: ${fmt(buyerCost)}</div>
                <div class="round-result-field profit ${profitClass(buyerProfit)}"><strong>Profit: ${fmt(buyerProfit)}</strong></div>
            </div>
            <div class="round-result-row">
                <h5>Supplier</h5>
                <div class="round-result-field">Revenue: ${fmt(supplierRevenue)}</div>
                <div class="round-result-field">Cost: ${fmt(supplierCost)}</div>
                <div class="round-result-field profit ${profitClass(supplierProfit)}"><strong>Profit: ${fmt(supplierProfit)}</strong></div>
            </div>
        `;
    }

    function resetRoundResultsTable() {
        if (!roundResultsTableEl) return;

        const tbody = roundResultsTableEl.querySelector("tbody");
        if (!tbody) return;

        tbody.innerHTML = `
            <tr class="empty-row">
                <td colspan="12">No rounds completed yet.</td>
            </tr>
        `;
    }

    function appendRoundResultsTableRow(roundOutput, orderQuantity) {
        if (!roundResultsTableEl || !roundOutput) return;

        const tbody = roundResultsTableEl.querySelector("tbody");
        if (!tbody) return;

        const emptyRow = tbody.querySelector(".empty-row");
        if (emptyRow) {
            emptyRow.remove();
        }

        const roundIndex = currentState ? (currentState.round_number - 1) : tbody.children.length + 1;
        const buyerProfit = roundOutput.buyer_profit;
        const supplierProfit = roundOutput.supplier_profit;
        const supplyChainProfit =
            (typeof buyerProfit === "number" ? buyerProfit : 0) +
            (typeof supplierProfit === "number" ? supplierProfit : 0);

        function fmt(x) {
            return (typeof x === "number") ? x.toFixed(2) : (x ?? "?");
        }

        const row = document.createElement("tr");
        const cells = [
            roundIndex,
            orderQuantity ?? roundOutput.order_quantity ?? "?",
            roundOutput.realized_demand ?? "?",
            roundOutput.sales ?? "?",
            roundOutput.returns ?? "?",
            fmt(roundOutput.buyer_revenue),
            fmt(roundOutput.buyer_cost),
            fmt(buyerProfit),
            fmt(roundOutput.supplier_revenue),
            fmt(roundOutput.supplier_cost),
            fmt(supplierProfit),
            fmt(supplyChainProfit),
        ];

        for (const value of cells) {
            const cell = document.createElement("td");
            cell.textContent = value;
            row.appendChild(cell);
        }

        tbody.appendChild(row);
    }

    // ================================
    // API Helper Functions
    // ================================
    
    /**
     * Fetches JSON from API with detailed error handling.
     * 
     * Inputs:
     * - url: API endpoint URL
     * - options: Fetch options (method, headers, body, etc.)
     * 
     * What happens:
     * - Makes fetch request to API
     * - Reads response as text first (can only read body once)
     * - If response not OK, tries to extract error detail from JSON
     * - Throws error with HTTP status and detail message
     * - If successful, parses and returns JSON
     * 
     * Output:
     * Returns parsed JSON object, or null if response is empty
     * 
     * Throws:
     * Error with HTTP status and detail message if request fails
     */
    async function fetchJsonWithDetail(url, options = {}) {
        const response = await fetch(url, options);
        const text = await response.text(); // Read body once

        if (!response.ok) {
            let detail = text;
            try {
                const parsed = JSON.parse(text);
                if (typeof parsed.detail === "string") {
                    detail = parsed.detail;
                } else if (parsed.detail !== undefined) {
                    detail = JSON.stringify(parsed.detail);
                }
            } catch {
                // Not JSON, keep raw text
            }

            throw new Error(`HTTP ${response.status}: ${detail}`);
        }

        if (!text) return null;
        return JSON.parse(text);
    }

    // ================================
    // Phase-Aware UI Functions
    // ================================
    
    /**
     * Computes the current game phase based on game state.
     * 
     * Inputs:
     * - state: Current GameStateResponse object
     * 
     * What happens:
     * - Checks if game exists
     * - Checks if game is over
     * - Checks if contract exists and has remaining rounds
     * 
     * Output:
     * Returns phase string: "no_game", "game_over", "needs_contract", or "active_contract"
     */
    function computePhase(state) {
        if (!state) return "no_game";
        if (state.game_over) return "game_over";

        const contract = state.contract || null;
        const remaining = contract ? (contract.remaining_rounds ?? 0) : 0;

        if (!contract || remaining <= 0) {
            return "needs_contract";
        }
        return "active_contract";
    }

    /**
     * Updates UI elements based on current game phase.
     * 
     * What happens:
     * - Computes current phase
     * - Updates phase banner text
     * - Enables/disables negotiate and order buttons based on phase
     * - Sets button tooltips explaining why buttons are disabled
     */
    function updatePhaseUI() {
        if (!phaseBannerEl) return;

        const phase = computePhase(currentState);

        const negotiateForm = document.getElementById("negotiate-form");
        const orderForm = document.getElementById("order-form");
        const startGameBtn = document.getElementById("start-game-btn");

        const negotiateButton = negotiateForm?.querySelector('button[type="submit"]');
        const orderButton = orderForm?.querySelector('button[type="submit"]');

        switch (phase) {
            case "no_game":
                phaseBannerEl.textContent = "No game started. Use Game Setup to start a new game.";
                if (negotiateButton) { negotiateButton.disabled = true;  negotiateButton.title = "Start a game before negotiating."; }
                if (orderButton)     { orderButton.disabled = true;      orderButton.title = "Start a game and negotiate a contract before ordering."; }
                if (startGameBtn)    { startGameBtn.disabled = false;    startGameBtn.title = ""; }
                break;
            case "needs_contract":
                phaseBannerEl.textContent = "No active contract. Negotiate terms before ordering.";
                if (negotiateButton) { negotiateButton.disabled = false; negotiateButton.title = "Propose contract terms to the supplier."; }
                if (orderButton)     { orderButton.disabled = true;      orderButton.title = "You must have an active contract before placing orders."; }
                if (startGameBtn)    { startGameBtn.disabled = true;     startGameBtn.title = "A game is already in progress."; }
                break;
            case "active_contract":
                phaseBannerEl.textContent = "Active contract. You may place your order for this round.";
                if (negotiateButton) { negotiateButton.disabled = true;  negotiateButton.title = "Contract already active. Wait until it expires to renegotiate."; }
                if (orderButton)     { orderButton.disabled = false;     orderButton.title = "Enter Q for this round and place your order."; }
                if (startGameBtn)    { startGameBtn.disabled = true;     startGameBtn.title = "A game is already in progress."; }
                break;
            case "game_over":
                phaseBannerEl.textContent = "Game is over. Start a new game to play again.";
                if (negotiateButton) { negotiateButton.disabled = true;  negotiateButton.title = "Game is over. Start a new game to negotiate again."; }
                if (orderButton)     { orderButton.disabled = true;      orderButton.title = "Game is over. Start a new game to place orders."; }
                if (startGameBtn)    { startGameBtn.disabled = false;    startGameBtn.title = ""; }
                break;
            default:
                phaseBannerEl.textContent = "";
        }
    }

    /**
     * Updates the contract summary display.
     * 
     * What happens:
     * - Checks if game state exists
     * - Checks if contract exists and is active
     * - Builds HTML displaying all contract terms (type, prices, caps, length, etc.)
     * - Updates contract summary element with formatted HTML
     */
    function updateContractSummary() {
        if (!contractSummaryEl) return;

        if (!currentState) {
            contractSummaryEl.textContent = "No game started yet.";
            return;
        }

        const contract = currentState.contract;
        if (!contract) {
            contractSummaryEl.textContent = "No active contract. Negotiate terms before ordering.";
            return;
        }

        const remaining = contract.remaining_rounds ?? 0;
        if (remaining <= 0) {
            contractSummaryEl.textContent =
                "No active contract. Negotiate terms before ordering.";
            return;
        }

        const typeLabelMap = { buyback: "Buyback" };
        const typeLabel = typeLabelMap[contract.contract_type] || contract.contract_type;
        const totalRounds = contract.length || 1;
        const usedRounds = totalRounds - remaining;
        const progressPct = Math.round((usedRounds / totalRounds) * 100);

        let html = `<span class="contract-badge active-contract-badge">Active ${typeLabel} Contract</span>`;
        html += '<div class="contract-summary-grid">';
        html += `<div class="contract-field"><strong>Wholesale (w):</strong> ${contract.wholesale_price}</div>`;
        html += `<div class="contract-field"><strong>Buyback (b):</strong> ${contract.buyback_price}</div>`;
        html += `<div class="contract-field"><strong>Length:</strong> ${contract.length} rounds</div>`;
        html += `<div class="contract-field"><strong>Remaining:</strong> ${remaining} round${remaining !== 1 ? "s" : ""}</div>`;
        html += '</div>';
        html += `
            <div class="contract-progress">
                <div class="contract-progress-label">${usedRounds} of ${totalRounds} rounds used</div>
                <div class="contract-progress-bar">
                    <div class="contract-progress-fill" style="width: ${progressPct}%"></div>
                </div>
            </div>
        `;
        
        contractSummaryEl.innerHTML = html;
    }

    /**
     * Main function to render all game state UI elements.
     * 
     * What happens:
     * - Updates debug output with JSON state
     * - Updates phase UI (banner, buttons)
     * - Updates contract summary
     * - Renders demand chart and table
     * - Updates section visibility (negotiation/order sections)
     */
    function renderGameState() {
        if (!currentState) {
            if (gameStateOutput) {
                gameStateOutput.textContent = "No game state available.";
            }
            updatePhaseUI();
            updateContractSummary();
            renderDemandChart();
            renderDemandTable();
            updateSectionVisibility();
            return;
        }
        if (gameStateOutput) {
            gameStateOutput.textContent = JSON.stringify(currentState, null, 2);
        }
        updatePhaseUI();
        updateContractSummary();
        renderDemandChart();
        renderDemandTable();
        updateSectionVisibility();
    }

    /**
     * Updates visibility of sections based on game state.
     * 
     * What happens:
     * - Checks if there's an active contract
     * - Checks if there's an ongoing negotiation (chat or offer visible)
     * - Hides Order Decision section if no active contract
     * - Hides Negotiation section if there's an active contract
     * - Hides proposal form if there's an ongoing negotiation (but keeps chat/offer visible)
     */
    function updateSectionVisibility() {
        // Check if there's an active contract
        const contract = currentState?.contract || null;
        const hasActiveContract = contract && (contract.remaining_rounds ?? 0) > 0;
        
        // Check if there's an ongoing negotiation (chat section visible or offer visible)
        const chatSection = document.getElementById("negotiation-chat-section");
        const counterofferSection = document.getElementById("counteroffer-section");
        const hasOngoingNegotiation = 
            (chatSection && chatSection.style.display !== "none") ||
            (counterofferSection && counterofferSection.style.display !== "none");
        
        // Get section elements
        const negotiationSection = document.getElementById("negotiation-section");
        const orderDecisionSection = document.getElementById("order-decision-section");
        const negotiateForm = document.getElementById("negotiate-form");
        
        // Hide Order Decision if no active contract
        if (orderDecisionSection) {
            orderDecisionSection.style.display = hasActiveContract ? "block" : "none";
        }
        
        // Hide Negotiation section if there's an active contract
        if (negotiationSection) {
            negotiationSection.style.display = "block";
        }
        
        // Hide proposal form if there's an ongoing negotiation (but keep chat/offer visible)
        if (negotiateForm) {
            negotiateForm.style.display = hasOngoingNegotiation ? "none" : "block";
        }
    }

    function escapeHtml(value) {
        return String(value ?? "")
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    function formatMoney(value) {
        const num = Number(value);
        if (!Number.isFinite(num)) return "$0.00";
        return `$${num.toFixed(2)}`;
    }

    function formatNumber(value, digits = 1) {
        const num = Number(value);
        if (!Number.isFinite(num)) return "0";
        return num.toFixed(digits);
    }

    function formatPercent(value) {
        const num = Number(value);
        if (!Number.isFinite(num)) return "0.0%";
        return `${(num * 100).toFixed(1)}%`;
    }

    function latestAcceptedContract(summary) {
        const rounds = summary.rounds || [];
        if (rounds.length > 0) {
            const last = rounds[rounds.length - 1];
            return {
                contract_type: last.contract_type,
                wholesale_price: last.wholesale_price,
                buyback_price: last.buyback_price,
                contract_length: last.contract_length,
            };
        }

        const negotiations = summary.negotiation_history || [];
        for (let i = negotiations.length - 1; i >= 0; i--) {
            if (negotiations[i].final_contract) {
                return negotiations[i].final_contract;
            }
        }
        return null;
    }

    function buildSummaryInterpretation(summary) {
        const rounds = summary.rounds || [];
        if (!rounds.length) {
            return ["No rounds were completed, so there is no ordering strategy to summarize yet."];
        }

        const aboveDemand = rounds.filter(r => Number(r.order_quantity) > Number(r.realized_demand)).length;
        const belowDemand = rounds.filter(r => Number(r.order_quantity) < Number(r.realized_demand)).length;
        const totalReturns = Number(summary.total_returns || 0);
        const buyerProfit = Number(summary.cumulative_buyer_profit || 0);
        const supplierProfit = Number(summary.cumulative_supplier_profit || 0);
        const supplyChainProfit = buyerProfit + supplierProfit;
        const notes = [];

        if (aboveDemand > belowDemand) {
            notes.push(`Orders were above realized demand in ${aboveDemand} of ${rounds.length} rounds, which increased exposure to unsold inventory and returns.`);
        } else if (belowDemand > aboveDemand) {
            notes.push(`Orders were below realized demand in ${belowDemand} of ${rounds.length} rounds, which reduced leftover risk but may have left sales unmet.`);
        } else {
            notes.push("Ordering was balanced around realized demand across the completed rounds.");
        }

        if (totalReturns > 0) {
            notes.push(`The contract generated ${totalReturns} returned unit(s), so buyback terms affected how risk and cost were shared.`);
        } else {
            notes.push("No returns occurred, so supplier profit mainly depended on the wholesale margin over production cost.");
        }

        if (buyerProfit > supplierProfit) {
            notes.push("Buyer profit was higher than supplier profit; discuss whether the contract terms created balanced incentives.");
        } else if (supplierProfit > buyerProfit) {
            notes.push("Supplier profit was higher than buyer profit; discuss whether the buyer carried too much demand risk.");
        } else {
            notes.push("Buyer and supplier profits were similar, suggesting relatively balanced realized outcomes.");
        }
        notes.push(`Total supply chain profit was ${formatMoney(supplyChainProfit)}, combining buyer and supplier profit.`);

        return notes;
    }

    function renderSummaryHtml(summary) {
        const rounds = summary.rounds || [];
        const contract = latestAcceptedContract(summary);
        const notes = buildSummaryInterpretation(summary);

        let html = '<div class="summary-dashboard">';
        html += '<div class="summary-metric-grid">';
        html += `<div class="summary-metric"><span>Rounds Played</span><strong>${summary.total_rounds_played ?? rounds.length}</strong></div>`;
        html += `<div class="summary-metric"><span>Buyer Profit</span><strong>${formatMoney(summary.cumulative_buyer_profit)}</strong></div>`;
        html += `<div class="summary-metric"><span>Supplier Profit</span><strong>${formatMoney(summary.cumulative_supplier_profit)}</strong></div>`;
        html += `<div class="summary-metric"><span>Supply Chain Profit</span><strong>${formatMoney(Number(summary.cumulative_buyer_profit || 0) + Number(summary.cumulative_supplier_profit || 0))}</strong></div>`;
        html += `<div class="summary-metric"><span>Average Demand</span><strong>${formatNumber(summary.average_demand)}</strong></div>`;
        html += `<div class="summary-metric"><span>Fill Rate</span><strong>${formatPercent(summary.fill_rate)}</strong></div>`;
        html += `<div class="summary-metric"><span>Return Rate</span><strong>${formatPercent(summary.return_rate)}</strong></div>`;
        html += '</div>';

        html += '<div class="summary-section-grid">';
        html += '<div class="summary-panel"><h4>Contract Terms</h4>';
        if (contract) {
            html += `<dl class="summary-dl">
                <div><dt>Type</dt><dd>${escapeHtml(contract.contract_type || "buyback")}</dd></div>
                <div><dt>Wholesale price</dt><dd>${formatMoney(contract.wholesale_price)}</dd></div>
                <div><dt>Buyback price</dt><dd>${formatMoney(contract.buyback_price)}</dd></div>
                <div><dt>Length</dt><dd>${contract.contract_length || contract.length || 0} rounds</dd></div>
            </dl>`;
        } else {
            html += '<p>No accepted contract was recorded.</p>';
        }
        html += '</div>';

        html += '<div class="summary-panel"><h4>What Happened</h4><ul class="summary-notes">';
        notes.forEach(note => {
            html += `<li>${escapeHtml(note)}</li>`;
        });
        html += '</ul></div>';
        html += '</div>';

        if (rounds.length) {
            html += '<div class="summary-panel"><h4>Round-by-Round Results</h4>';
            html += '<div class="records-table-wrap"><table class="records-table summary-round-table"><thead><tr>';
            ["Round", "Order", "Demand", "Buyer Profit", "Supplier Profit", "Wholesale", "Buyback"].forEach(label => {
                html += `<th>${label}</th>`;
            });
            html += '</tr></thead><tbody>';
            rounds.forEach(round => {
                html += `<tr>
                    <td>${round.round_index}</td>
                    <td>${round.order_quantity}</td>
                    <td>${round.realized_demand}</td>
                    <td>${formatMoney(round.buyer_profit)}</td>
                    <td>${formatMoney(round.supplier_profit)}</td>
                    <td>${formatMoney(round.wholesale_price)}</td>
                    <td>${formatMoney(round.buyback_price)}</td>
                </tr>`;
            });
            html += '</tbody></table></div></div>';
        }

        html += '</div>';
        return html;
    }

    function setSummaryPlaceholder(text) {
        if (summaryOutput) {
            summaryOutput.textContent = text;
            summaryOutput.classList.add("empty-summary");
        }
        if (summaryOutputInstructor) {
            summaryOutputInstructor.textContent = text;
            summaryOutputInstructor.classList.add("empty-summary");
        }
        if (summaryOutputDebug) {
            summaryOutputDebug.textContent = text;
        }
    }

    function updateSummaryOutputs(summary) {
        const summaryText = JSON.stringify(summary, null, 2);
        const summaryHtml = renderSummaryHtml(summary);

        if (summaryOutput) {
            summaryOutput.innerHTML = summaryHtml;
            summaryOutput.classList.remove("empty-summary");
        }
        if (summaryOutputInstructor) {
            summaryOutputInstructor.innerHTML = summaryHtml;
            summaryOutputInstructor.classList.remove("empty-summary");
        }
        if (summaryOutputDebug) {
            summaryOutputDebug.textContent = summaryText;
        }
    }

    /**
     * Fetches and renders game summary if game is over.
     * 
     * What happens:
     * - Checks if game is over and session exists
     * - Fetches game summary from API
     * - Updates all summary outputs with JSON summary
     * - Shows notification
     * - Handles errors gracefully
     */
    async function fetchAndRenderSummaryIfGameOver() {
        if (!currentState || !currentState.game_over || !sessionId) {
            return;
        }
        try {
            const summary = await fetchJsonWithDetail(
                `${BASE_URL}/game/summary?session_id=${encodeURIComponent(sessionId)}`
            );
            updateSummaryOutputs(summary);
            addNotification("Game summary loaded.", "info");
        } catch (err) {
            console.error(err);
            const errorText = "Error loading summary: " + err.message;
            setSummaryPlaceholder(errorText);
            addNotification("Failed to load game summary: " + err.message, "error");
        }
    }

    // ================================
    // Debug Section Functions
    // ================================
    
    /**
     * Initializes backend health check section.
     * 
     * What happens:
     * - Sets up click handler for health check button
     * - Fetches health status from backend
     * - Displays health status in debug output
     * - Shows notification with result
     */
    function initHealthSection() {
        const healthButton = document.getElementById("health_button");
        const healthOutput = document.getElementById("health_output");
        if (!healthButton || !healthOutput) return;

        healthButton.addEventListener("click", async () => {
            healthOutput.textContent = "Contacting Backend...";
            try {
                const data = await fetchJsonWithDetail(`${BASE_URL}/health`);
                healthOutput.textContent = JSON.stringify(data, null, 2);
                addNotification("Backend health OK.", "success");
            } catch (err) {
                console.error(err);
                healthOutput.textContent = "Error: " + err.message;
                addNotification("Backend health check failed: " + err.message, "error");
            }
        });
    }

    /**
     * Initializes AI provider status check section.
     * 
     * What happens:
     * - Sets up click handler for AI status button
     * - Fetches AI status from backend (OpenAI and DeepSeek)
     * - Displays formatted status with colors (green/red/orange)
     * - Shows notifications based on status
     */
    function initAIStatusSection() {
        const aiStatusButton = document.getElementById("ai-status-button");
        const aiStatusOutput = document.getElementById("ai-status-output");
        if (!aiStatusButton || !aiStatusOutput) return;

        aiStatusButton.addEventListener("click", async () => {
            aiStatusOutput.innerHTML = "<p>Checking AI provider status...</p>";
            try {
                const data = await fetchJsonWithDetail(`${BASE_URL}/ai/status`);
                
                let statusHtml = '<div style="padding: 1rem; border: 1px solid #ccc; border-radius: 4px; background: #f9f9f9;">';
                statusHtml += `<p><strong>Active Provider:</strong> ${data.active_provider || 'None'}</p>`;
                statusHtml += '<hr style="margin: 1rem 0;">';
                
                // OpenAI Status
                statusHtml += '<h4>OpenAI Status</h4>';
                statusHtml += `<p><strong>Configured:</strong> ${data.openai_configured ? 'Yes' : 'No'}</p>`;
                if (data.openai_configured) {
                    const openaiColor = data.openai_status === 'working' ? 'green' : data.openai_status === 'error' ? 'red' : 'orange';
                    statusHtml += `<p><strong>Status:</strong> <span style="color: ${openaiColor}">${data.openai_status.toUpperCase()}</span></p>`;
                    statusHtml += `<p><strong>Test Result:</strong> ${data.openai_test_successful ? 'Passed' : 'Failed'}</p>`;
                    statusHtml += `<p><strong>Message:</strong> ${data.openai_message}</p>`;
                } else {
                    statusHtml += `<p><strong>Message:</strong> ${data.openai_message}</p>`;
                }
                
                statusHtml += '<hr style="margin: 1rem 0;">';
                
                // DeepSeek Status
                statusHtml += '<h4>DeepSeek Status (via OpenRouter)</h4>';
                statusHtml += `<p><strong>Configured:</strong> ${data.deepseek_configured ? 'Yes' : 'No'}</p>`;
                if (data.deepseek_configured) {
                    const deepseekColor = data.deepseek_status === 'working' ? 'green' : data.deepseek_status === 'error' ? 'red' : 'orange';
                    statusHtml += `<p><strong>Status:</strong> <span style="color: ${deepseekColor}">${data.deepseek_status.toUpperCase()}</span></p>`;
                    statusHtml += `<p><strong>Test Result:</strong> ${data.deepseek_test_successful ? 'Passed' : 'Failed'}</p>`;
                    statusHtml += `<p><strong>Message:</strong> ${data.deepseek_message}</p>`;
                } else {
                    statusHtml += `<p><strong>Message:</strong> ${data.deepseek_message}</p>`;
                }
                
                statusHtml += '</div>';
                
                aiStatusOutput.innerHTML = statusHtml;
                
                // Notifications
                if (data.openai_test_successful) {
                    addNotification("OpenAI is working correctly.", "success");
                } else if (data.deepseek_test_successful) {
                    addNotification("DeepSeek is working correctly.", "success");
                } else if (data.openai_status === "error") {
                    addNotification(`OpenAI error: ${data.openai_message}`, "error");
                } else if (data.deepseek_status === "error") {
                    addNotification(`DeepSeek error: ${data.deepseek_message}`, "error");
                } else if (!data.openai_configured && !data.deepseek_configured) {
                    addNotification("No AI provider configured. Set OPENAI_API_KEY or OPENROUTER_API_KEY.", "info");
                }
            } catch (err) {
                console.error(err);
                aiStatusOutput.innerHTML = `<div style="padding: 1rem; border: 1px solid #f00; border-radius: 4px; background: #ffe6e6;"><p><strong>Error:</strong> ${err.message}</p></div>`;
                addNotification("AI status check failed: " + err.message, "error");
            }
        });
    }

    // ================================
    // Game Control Functions
    // ================================
    
    /**
     * Initializes game control section (start game, end game early).
     * 
     * What happens:
     * - Sets up click handler for "Start New Game" button
     * - Collects game parameters (rounds, demand method)
     * - Calls API to start new game
     * - Updates session ID and game state
     * - Clears UI elements (chat, round results, etc.)
     * - Sets up "End Game Early" button handler
     */
    function initGameControlSection() {
        const startGameButton = document.getElementById("start-game-btn");
        const demandMethodInput = document.getElementById("demand-method-input");
        const demandHistoryInput = document.getElementById("demand-history-input");
        const roundsInput = document.getElementById("rounds-input");
        const endGameEarlyBtn = document.getElementById("end-game-early-btn");
        const endGameEarlyOutput = document.getElementById("end-game-early-output");
        
        if (!startGameButton) return;

        startGameButton.addEventListener("click", async () => {
            if (gameStateOutput) {
                gameStateOutput.textContent = "Starting new game...";
            }

            const demandMethod = demandMethodInput ? demandMethodInput.value : "bootstrap";
            const roundsValueRaw = roundsInput ? roundsInput.value : "";
            let rounds = parseInt(roundsValueRaw, 10);
            if (Number.isNaN(rounds) || rounds <= 0) {
                rounds = 50;
            }

            const body = {
                rounds: rounds,
                demand_method: demandMethod,
                demand_history_id: demandHistoryInput ? demandHistoryInput.value : "default",
                participant_id: participantId,
            };

            try {
                const data = await fetchJsonWithDetail(`${BASE_URL}/game/start`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(body),
                });

                // Update session and state
                sessionId = data.state.session_id;
                currentState = data.state;

                // Reset summary for the new game
                setSummaryPlaceholder("No summary yet.");

                // Clear chat history UI when starting a new game
                const chatMessages = document.getElementById("chat-messages");
                if (chatMessages) {
                    chatMessages.innerHTML = "";
                }
                hideChatSection();
                hideCounterofferSection();

                // Clear round result card when starting a new game
                if (roundResultCardEl) {
                    roundResultCardEl.textContent = "No order placed yet.";
                }
                resetRoundResultsTable();

                // Clear "end game early" status message when starting a new game
                const endGameEarlyOutput = document.getElementById("end-game-early-output");
                if (endGameEarlyOutput) {
                    endGameEarlyOutput.textContent = "";
                }

                addNotification(
                    `Game started (session ${sessionId.slice(0, 8)}..., rounds=${rounds}, method=${demandMethod}).`,
                    "success"
                );
                renderGameState();
            } catch (err) {
                console.error(err);
                if (gameStateOutput) {
                    gameStateOutput.textContent = "Error: " + err.message;
                }
                addNotification("Failed to start game: " + err.message, "error");
            }
        });

        // End game early button
        if (endGameEarlyBtn) {
            endGameEarlyBtn.addEventListener("click", async () => {
                if (!sessionId) {
                    if (endGameEarlyOutput) {
                        endGameEarlyOutput.textContent = "No game session found. Please start a game first.";
                    }
                    addNotification("No game session found. Please start a game first.", "error");
                    return;
                }

                if (endGameEarlyOutput) {
                    endGameEarlyOutput.textContent = "Ending game early...";
                }

                try {
                    const data = await fetchJsonWithDetail(`${BASE_URL}/game/end-early`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ session_id: sessionId }),
                    });

                    if (endGameEarlyOutput) {
                        endGameEarlyOutput.textContent = "Game ended early. Summary is now available.";
                    }
                    addNotification("Game ended early. Summary is now available.", "success");
                    
                    // Refresh game state to show updated status
                    const stateData = await fetchJsonWithDetail(`${BASE_URL}/game/state`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ session_id: sessionId }),
                    });
                    currentState = stateData;
                    renderGameState();
                    
                    // Try to fetch and display summary
                    await fetchAndRenderSummaryIfGameOver();
                } catch (err) {
                    console.error(err);
                    if (endGameEarlyOutput) {
                        endGameEarlyOutput.textContent = "Error: " + err.message;
                    }
                    addNotification("Failed to end game early: " + err.message, "error");
                }
            });
        }
    }

    async function loadDemandHistoryOptionsOnStartup() {
        const demandHistoryInput = document.getElementById("demand-history-input");
        if (!demandHistoryInput) return;

        try {
            const data = await fetchJsonWithDetail(`${BASE_URL}/config/demand-histories`);
            const histories = Array.isArray(data.histories) ? data.histories : [];
            if (histories.length === 0) return;

            demandHistoryInput.innerHTML = "";
            for (const history of histories) {
                const option = document.createElement("option");
                option.value = history.id;
                const rangeLabel =
                    typeof history.min === "number" && typeof history.max === "number"
                        ? `, ${history.min}-${history.max}`
                        : "";
                option.textContent = `${history.label} (${history.count} values${rangeLabel})`;
                demandHistoryInput.appendChild(option);
            }
        } catch (err) {
            console.error("Failed to load demand history options:", err);
            addNotification("Could not load demand history options. Using default history.", "error");
        }
    }

    // ================================
    // Negotiation Functions
    // ================================
    
    /**
     * Shows the counteroffer section with contract details.
     * 
     * Inputs:
     * - counterContract: Contract object from supplier's offer
     * - message: Message to display with the offer
     * 
     * What happens:
     * - Builds HTML displaying all contract terms
     * - Shows the counteroffer section
     * - Updates section visibility
     */
    function showCounterofferSection(counterContract, message, offerVersion) {
        const section = document.getElementById("counteroffer-section");
        const details = document.getElementById("counteroffer-details");
        if (!section || !details) return;
        if (!counterContract || !Number.isInteger(offerVersion) || offerVersion <= 0) {
            hideCounterofferSection();
            return;
        }
        currentOfferVersion = offerVersion;

        let html = `<p><strong>${message}</strong></p>`;
        html += `<p>Offer version ${offerVersion}</p>`;
        html += `<div class="contract-summary-grid">`;
        html += `<div class="contract-field"><strong>Type:</strong> ${counterContract.contract_type || "buyback"}</div>`;
        html += `<div class="contract-field"><strong>Wholesale (w):</strong> ${counterContract.wholesale_price}</div>`;
        html += `<div class="contract-field"><strong>Buyback (b):</strong> ${counterContract.buyback_price}</div>`;
        html += `<div class="contract-field"><strong>Length (L):</strong> ${counterContract.length} rounds</div>`;
        html += `</div>`;

        details.innerHTML = html;
        section.classList.remove("hidden-section");
        section.style.display = "block";
        updateSectionVisibility();
        section.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }

    function renderSubmittedProposal(contract, statusText = "Submitted Proposal") {
        const submittedDetailsEl = document.getElementById("submitted-details");
        const submittedSection = document.getElementById("submitted-proposal");
        if (!submittedDetailsEl || !submittedSection || !contract) return;

        latestDisplayedProposal = { ...contract };
        const isAccepted = statusText.toLowerCase().includes("accepted");
        const statusClass = isAccepted ? "proposal-status accepted" : "proposal-status pending";

        submittedDetailsEl.innerHTML = `
            <div><span class="${statusClass}">${statusText}</span></div>
            <div><strong>Wholesale Price (w):</strong> ${contract.wholesale_price}</div>
            <div><strong>Buyback Price (b):</strong> ${contract.buyback_price}</div>
            <div><strong>Contract Length (L):</strong> ${contract.length}</div>
            <div><strong>Contract Type:</strong> ${contract.contract_type || "buyback"}</div>
            <div class="proposal-note">${isAccepted ? "These terms are now active for ordering." : "These terms are proposed only. They are not active until accepted."}</div>
        `;
        submittedSection.style.display = "block";
        submittedSection.classList.remove("hidden-section");
    }

    function updateSubmittedProposalFromChat(message) {
        if (!latestDisplayedProposal || !message) return;

        const text = message.toLowerCase();
        const nextProposal = { ...latestDisplayedProposal };
        let changed = false;

        function numberFrom(pattern) {
            const match = text.match(pattern);
            return match ? parseFloat(match[1]) : null;
        }

        function applyField(fieldName, aliases, directPatterns) {
            const mentionsField = aliases.some((alias) => text.includes(alias));
            if (!mentionsField) return;

            const increaseBy = numberFrom(/increase(?:\s+\w+){0,3}\s+by\s+\$?(\d+(?:\.\d+)?)/);
            const decreaseBy = numberFrom(/decrease(?:\s+\w+){0,3}\s+by\s+\$?(\d+(?:\.\d+)?)/);
            const directValue = directPatterns
                .map((pattern) => numberFrom(pattern))
                .find((value) => value !== null);

            if (increaseBy !== null && typeof nextProposal[fieldName] === "number") {
                nextProposal[fieldName] += increaseBy;
                changed = true;
            } else if (decreaseBy !== null && typeof nextProposal[fieldName] === "number") {
                nextProposal[fieldName] -= decreaseBy;
                changed = true;
            } else if (directValue !== null) {
                nextProposal[fieldName] = directValue;
                changed = true;
            }
        }

        applyField("buyback_price", ["buyback", " b ", " b=", "b as"], [
            /(?:buyback|b)\s*(?:price)?\s*(?:is|as|=|to|works)?\s*\$?(\d+(?:\.\d+)?)/,
            /\$?(\d+(?:\.\d+)?)\s*(?:buyback|b)\b/,
        ]);
        applyField("wholesale_price", ["wholesale", " w ", " w=", "w as"], [
            /(?:wholesale|w)\s*(?:price)?\s*(?:is|as|=|to|works)?\s*\$?(\d+(?:\.\d+)?)/,
            /\$?(\d+(?:\.\d+)?)\s*(?:wholesale|w)\b/,
        ]);
        applyField("length", ["length", "round", "rounds"], [
            /(?:length|rounds?)\s*(?:is|as|=|to|works)?\s*(\d+(?:\.\d+)?)/,
            /(\d+(?:\.\d+)?)\s*(?:rounds?|length)\b/,
        ]);

        if (changed) {
            renderSubmittedProposal(nextProposal, "Updated Proposal");
        }
    }
    
    /**
     * Hides the counteroffer section.
     */
    function hideCounterofferSection() {
        currentOfferVersion = null;
        const section = document.getElementById("counteroffer-section");
        if (section) {
            section.style.display = "none";
            section.classList.add("hidden-section");
        }
    }
    
    /**
     * Shows the negotiation chat section.
     */
    function showChatSection() {
        const section = document.getElementById("negotiation-chat-section");
        if (section) {
            section.classList.remove("hidden-section");
            section.style.display = "block";
        }
        updateSectionVisibility();
    }
    
    /**
     * Hides the negotiation chat section.
     */
    function hideChatSection() {
        const section = document.getElementById("negotiation-chat-section");
        if (section) {
            section.style.display = "none";
            section.classList.add("hidden-section");
        }
        updateSectionVisibility();
    }
    
    /**
     * Adds a chat message to the negotiation chat.
     * 
     * Inputs:
     * - role: "student" or "supplier"
     * - content: Message text
     * 
     * What happens:
     * - Creates styled message div
     * - Appends message to chat container
     * - Scrolls chat to bottom to show latest message
     */
    function addChatMessage(role, content) {
        const chatMessages = document.getElementById("chat-messages");
        if (!chatMessages) return;

        const isUser = role === "student";

        // Outer wrap controls left/right alignment
        const wrap = document.createElement("div");
        wrap.className = `chat-bubble-wrap ${isUser ? "user" : "supplier"}`;

        // Sender label
        const label = document.createElement("div");
        label.className = "bubble-label";
        label.textContent = isUser ? "You" : "Supplier AI";
        wrap.appendChild(label);

        // Bubble
        const bubble = document.createElement("div");
        bubble.className = "chat-bubble";
        bubble.textContent = content;
        wrap.appendChild(bubble);

        // Timestamp
        const now = new Date();
        const timeStr = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        const time = document.createElement("div");
        time.className = "bubble-time";
        time.textContent = timeStr;
        wrap.appendChild(time);

        chatMessages.appendChild(wrap);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }
    
    /**
     * Handles student's response to a counteroffer (accept or reject).
     * 
     * Inputs:
     * - accept: Boolean - true to accept, false to reject
     * 
     * What happens:
     * - Sends accept/reject decision to backend
     * - Updates game state
     * - If accepted: hides chat and offer sections, shows order section
     * - If rejected: hides offer section, keeps chat visible
     * - Shows appropriate notifications
     */
    async function handleCounterofferResponse(accept) {
        if (negotiationPending) return;
        if (!sessionId) {
            addNotification("No active session.", "error");
            return;
        }
        
        if (currentOfferVersion === null) {
            addNotification("Review a current supplier offer before responding.", "info");
            return;
        }

        negotiationPending = true;
        try {
            const data = await fetchJsonWithDetail(`${BASE_URL}/game/negotiate/accept-counter`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    session_id: sessionId,
                    accept: accept,
                    offer_version: currentOfferVersion
                }),
            });
            
            currentState = data.state;
            renderGameState();
            
            if (accept) {
                if (currentState && currentState.contract) {
                    renderSubmittedProposal(currentState.contract, "Accepted Supplier Offer");
                }
                addNotification("Offer accepted. Contract is now active.", "success");
                hideCounterofferSection();
                hideChatSection();
                // Clear chat messages UI when contract is accepted
                const chatMessages = document.getElementById("chat-messages");
                if (chatMessages) {
                    chatMessages.innerHTML = "";
                }
                updateSectionVisibility();
            } else {
                addNotification("Offer rejected.", "info");
                hideCounterofferSection();
                updateSectionVisibility();
            }
        } catch (err) {
            console.error(err);
            hideCounterofferSection();
            updateSectionVisibility();
            addNotification("Error handling offer: " + err.message, "error");
        } finally {
            negotiationPending = false;
        }
    }

    /**
     * Initializes negotiation section (proposal form, chat, offer handling).
     * 
     * What happens:
     * - Sets up proposal form submission handler
     * - Validates game state before allowing negotiation
     * - Collects contract terms from form
     * - Sends proposal to backend
     * - Handles response (accept/reject/counter)
     * - Sets up offer accept/reject button handlers
     * - Sets up chat form submission handler
     */
    function initNegotiationSection() {
        const negotiateForm = document.getElementById("negotiate-form");
        const negotiateOutput = document.getElementById("negotiate-output");
        if (!negotiateForm) return;

        negotiateForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            if (negotiationPending) return;

            if (negotiateOutput) {
                negotiateOutput.textContent = "Submitting proposal...";
            }

            if (!sessionId) {
                if (negotiateOutput) {
                    negotiateOutput.textContent = "Start a game first!";
                }
                addNotification("Negotiation attempted without a game.", "error");
                return;
            }

            if (!currentState) {
                if (negotiateOutput) {
                    negotiateOutput.textContent = "No game state available.";
                }
                addNotification("Negotiation failed: no game state.", "error");
                return;
            }

            if (currentState.game_over) {
                if (negotiateOutput) {
                    negotiateOutput.textContent = "Game is over. Start a new game.";
                }
                addNotification("Negotiation attempted after game over.", "error");
                return;
            }

            // Collect form values
            const wInput = document.getElementById("wholesale-input");
            const bInput = document.getElementById("buyback-input");
            const lengthInput = document.getElementById("length-input");
            const contractTypeInput = document.getElementById("contract-type-input");

            const w = parseFloat(wInput?.value ?? "0");
            const b = parseFloat(bInput?.value ?? "0");
            const length = parseInt(lengthInput?.value ?? "1", 10);
            const contractType = contractTypeInput?.value ?? "buyback";

            const body = {
                session_id: sessionId,
                wholesale_price: w,
                buyback_price: b,
                length: length,
                contract_type: contractType,
            };

            renderSubmittedProposal(body, "Submitted Proposal");

            hideCounterofferSection();
            showChatSection();
            negotiationPending = true;
            try {
                const data = await fetchJsonWithDetail(`${BASE_URL}/game/negotiate`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(body),
                });

                currentState = data.state;
                if (negotiateOutput) {
                    negotiateOutput.textContent = JSON.stringify(data, null, 2);
                }
                renderGameState();

                const decision = (data.decision || "unknown").toLowerCase();
                
                // Handle different decision outcomes
                if (decision === "accept") {
                    if (currentState && currentState.contract) {
                        renderSubmittedProposal(currentState.contract, "Accepted Proposal");
                    }
                    addNotification("Negotiation: contract accepted and activated.", "success");
                    hideCounterofferSection();
                    hideChatSection();
                    // Clear chat messages UI when contract is accepted
                    const chatMessages = document.getElementById("chat-messages");
                    if (chatMessages) {
                        chatMessages.innerHTML = "";
                    }
                    updateSectionVisibility();
                } else if (decision === "counter") {
                    addNotification("Negotiation: supplier issued an offer.", "info");
                    showCounterofferSection(data.counter_contract, data.ai_message, data.offer_version);
                    hideChatSection();
                    updateSectionVisibility();
                } else if (decision === "reject") {
                    addNotification("Negotiation: supplier rejected the proposal. You can enter negotiation chat.", "error");
                    hideCounterofferSection();
                    showChatSection();
                    addChatMessage("supplier", data.ai_message);
                    updateSectionVisibility();
                } else {
                    addNotification(`Negotiation result: ${decision}`, "info");
                    updateSectionVisibility();
                }
            } catch (err) {
                console.error(err);
                if (negotiateOutput) {
                    negotiateOutput.textContent = "Error: " + err.message;
                }
                addNotification("Negotiation error: " + err.message, "error");
            } finally {
                negotiationPending = false;
            }
        });
        
        // Offer acceptance/rejection buttons
        const acceptCounterBtn = document.getElementById("accept-counter-btn");
        const rejectCounterBtn = document.getElementById("reject-counter-btn");
        
        if (acceptCounterBtn) {
            acceptCounterBtn.addEventListener("click", async () => {
                await handleCounterofferResponse(true);
            });
        }
        
        if (rejectCounterBtn) {
            rejectCounterBtn.addEventListener("click", async () => {
                await handleCounterofferResponse(false);
            });
        }
        
        // Chat form submission
        const chatForm = document.getElementById("chat-form");
        if (chatForm) {
            chatForm.addEventListener("submit", async (e) => {
                e.preventDefault();
                if (negotiationPending) return;
                const chatInput = document.getElementById("chat-input");
                if (!chatInput || !chatInput.value.trim()) return;
                
                const message = chatInput.value.trim();
                chatInput.value = "";
                
                addChatMessage("student", message);
                updateSubmittedProposalFromChat(message);
                // The previous offer is withdrawn as soon as negotiations resume.
                hideCounterofferSection();
                updateSectionVisibility();
                
                negotiationPending = true;
                try {
                    const data = await fetchJsonWithDetail(`${BASE_URL}/game/negotiate/chat`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            session_id: sessionId,
                            message: message
                        }),
                    });
                    
                    addChatMessage("supplier", data.supplier_message);
                    
                    // If draft contract is provided, show it as an offer
                    if (data.negotiation_draft_contract) {
                        showCounterofferSection(data.negotiation_draft_contract, "Based on our discussion, here's the proposed contract. You can accept or reject it:", data.offer_version);
                        updateSectionVisibility();
                        addNotification("Supplier offer ready. Review the accept/reject buttons.", "info");
                    } else {
                        hideCounterofferSection();
                        updateSectionVisibility();
                    }
                    
                } catch (err) {
                    console.error(err);
                    addChatMessage("supplier", `Chat request failed: ${err.message}`);
                    addNotification("Chat error: " + err.message, "error");
                } finally {
                    negotiationPending = false;
                }
            });
        }
    }

    // ================================
    // Order Functions
    // ================================
    
    /**
     * Initializes order section (order form submission).
     * 
     * What happens:
     * - Sets up order form submission handler
     * - Validates game state and order quantity
     * - Sends order to backend
     * - Renders round result card
     * - Updates game state
     * - Checks if game is over and fetches summary if so
     */
    function initOrderSection() {
        const orderForm = document.getElementById("order-form");
        const orderOutput = document.getElementById("order-output");
        const orderQuantityInput = document.getElementById("order-quantity-input");

        if (!orderForm || !orderQuantityInput) return;

        orderForm.addEventListener("submit", async (e) => {
            e.preventDefault();

            if (orderOutput) {
                orderOutput.textContent = "Placing order...";
            }

            if (!sessionId) {
                if (orderOutput) {
                    orderOutput.textContent = "Start a game first!";
                }
                addNotification("Order attempted without a game.", "error");
                return;
            }

            if (!currentState) {
                if (orderOutput) {
                    orderOutput.textContent = "No game state available.";
                }
                addNotification("Order attempted with no game state.", "error");
                return;
            }

            if (currentState.game_over) {
                if (orderOutput) {
                    orderOutput.textContent = "Game is over. Start a new game.";
                }
                addNotification("Order attempted after game over.", "error");
                return;
            }

            const quantity = parseInt(orderQuantityInput.value, 10);
            if (Number.isNaN(quantity) || quantity < 0) {
                if (orderOutput) {
                    orderOutput.textContent = "Please enter a valid (non-negative) order quantity.";
                }
                addNotification("Invalid order quantity entered.", "error");
                return;
            }

            const body = {
                session_id: sessionId,
                order_quantity: quantity,
            };

            try {
                const data = await fetchJsonWithDetail(`${BASE_URL}/game/order`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(body),
                });

                currentState = data.state;

                // Render round result card for the student
                renderRoundResultCard(data.round_output, quantity);
                appendRoundResultsTableRow(data.round_output, quantity);

                // Keep raw JSON for debug
                if (orderOutput) {
                    orderOutput.textContent = JSON.stringify(data.round_output, null, 2);
                }

                renderGameState();

                const submittedSection = document.getElementById("submitted-proposal");
                if (submittedSection) {
                    submittedSection.style.display = "block";
                }

                const ro = data.round_output || {};
                const D = ro.realized_demand;
                const bp = ro.buyer_profit;
                const sp = ro.supplier_profit;

                addNotification(
                    `Order success: Q=${quantity}, D=${D}, buyer_profit=${bp}, supplier_profit=${sp}.`,
                    "success"
                );

                if (currentState.game_over) {
                    addNotification(
                        `Game ended after round ${currentState.round_number - 1}.`,
                        "info"
                    );
                    await fetchAndRenderSummaryIfGameOver();
                }
            } catch (err) {
                console.error(err);
                if (orderOutput) {
                    orderOutput.textContent = "Error: " + err.message;
                }
                renderRoundResultCard(null);
                addNotification("Order error: " + err.message, "error");
            }

        });
    }

    // ================================
    // Configuration Functions
    // ================================
    
    /**
     * Initializes configuration section (economic parameters and demand history).
     * 
     * What happens:
     * - Sets up "Load Current Config" button handler
     * - Sets up economic parameters update form handler
     * - Sets up demand history save button handler
     * - Loads config from backend and populates form fields
     * - Saves updated config to backend
     */
    function initConfigSection() {
        const loadConfigBtn = document.getElementById("load-config-btn");
        const configOutput = document.getElementById("config-output");

        const econRetail = document.getElementById("econ-retail");
        const econBuyerSalv = document.getElementById("econ-buyer-salvage");
        const econSupplierSalv = document.getElementById("econ-supplier-salvage");
        const econSupplierCost = document.getElementById("econ-supplier-cost");
        const econReturnShip = document.getElementById("econ-return-ship");
        const econReturnHandle = document.getElementById("econ-return-handle");

        const updateEconForm = document.getElementById("update-econ-form");

        const historyInput = document.getElementById("history-input");
        const saveHistoryBtn = document.getElementById("save-history-btn");

        if (!loadConfigBtn || !configOutput) return;

        // Load current config
        loadConfigBtn.addEventListener("click", async () => {
            configOutput.textContent = "Loading config...";

            try {
                const data = await fetchJsonWithDetail(`${BASE_URL}/config/current`);

                configOutput.textContent = JSON.stringify(data, null, 2);

                const econ = data.economic_params;
                if (econRetail) econRetail.value = econ.retail_price;
                if (econBuyerSalv) econBuyerSalv.value = econ.buyer_salvage_value;
                if (econSupplierSalv) econSupplierSalv.value = econ.supplier_salvage_value;
                if (econSupplierCost) econSupplierCost.value = econ.supplier_cost;
                if (econReturnShip) econReturnShip.value = econ.return_shipping_buyer;
                if (econReturnHandle) econReturnHandle.value = econ.return_handling_supplier;

                if (historyInput && data.history_summary?.sample) {
                    historyInput.value = data.history_summary.sample.join("\n");
                }

                addNotification("Config loaded.", "info");
            } catch (err) {
                console.error(err);
                configOutput.textContent = "Error: " + err.message;
                addNotification("Failed to load config: " + err.message, "error");
            }
        });

        // Update economic parameters
        if (updateEconForm) {
            updateEconForm.addEventListener("submit", async (e) => {
                e.preventDefault();

                configOutput.textContent = "Saving economic parameters...";

                const body = {
                    economic_params: {
                        retail_price: parseFloat(econRetail?.value ?? "0"),
                        buyer_salvage_value: parseFloat(econBuyerSalv?.value ?? "0"),
                        supplier_salvage_value: parseFloat(econSupplierSalv?.value ?? "0"),
                        supplier_cost: parseFloat(econSupplierCost?.value ?? "0"),
                        return_shipping_buyer: parseFloat(econReturnShip?.value ?? "0"),
                        return_handling_supplier: parseFloat(econReturnHandle?.value ?? "0"),
                    },
                };

                try {
                    const data = await fetchJsonWithDetail(`${BASE_URL}/config/update`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(body),
                    });

                    configOutput.textContent = JSON.stringify(data, null, 2);
                    addNotification("Economic parameters saved.", "success");
                } catch (err) {
                    console.error(err);
                    configOutput.textContent = "Error: " + err.message;
                    addNotification("Failed to save economic parameters: " + err.message, "error");
                }
            });
        }

        // Save demand history
        if (saveHistoryBtn && historyInput) {
            saveHistoryBtn.addEventListener("click", async () => {
                configOutput.textContent = "Saving history...";

                const lines = historyInput.value
                    .split("\n")
                    .map(line => line.trim())
                    .filter(line => line.length > 0)
                    .map(val => parseInt(val, 10));

                const body = { history: lines };

                try {
                    const data = await fetchJsonWithDetail(`${BASE_URL}/config/update`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(body),
                    });

                    configOutput.textContent = JSON.stringify(data, null, 2);
                    addNotification("Demand history saved.", "success");
                } catch (err) {
                    console.error(err);
                    configOutput.textContent = "Error: " + err.message;
                    addNotification("Failed to save demand history: " + err.message, "error");
                }
            });
        }
    }

    function downloadFile(url) {
        const link = document.createElement("a");
        link.href = url;
        document.body.appendChild(link);
        link.click();
        link.remove();
    }

    function renderRecordsTable(containerId, rows, columns) {
        const container = document.getElementById(containerId);
        if (!container) return;

        if (!rows.length) {
            container.textContent = "No records yet.";
            return;
        }

        let html = "<table class=\"records-table\"><thead><tr>";
        columns.forEach(col => {
            html += `<th>${col.label}</th>`;
        });
        html += "</tr></thead><tbody>";

        rows.forEach(row => {
            html += "<tr>";
            columns.forEach(col => {
                const value = col.get(row);
                html += `<td>${value ?? ""}</td>`;
            });
            html += "</tr>";
        });

        html += "</tbody></table>";
        container.innerHTML = html;
    }

    function initRecordsSection() {
        const loadRecordsBtn = document.getElementById("load-records-btn");
        const downloadParticipantsBtn = document.getElementById("download-participants-btn");
        const downloadRoundsBtn = document.getElementById("download-rounds-btn");
        const downloadChatLogsBtn = document.getElementById("download-chat-logs-btn");
        const recordsAccessCodeInput = document.getElementById("records-access-code");
        const recordsSummary = document.getElementById("records-summary");

        function getRecordsAccessCode() {
            return (recordsAccessCodeInput?.value || "").trim();
        }

        function requireRecordsAccessCode() {
            const code = getRecordsAccessCode();
            if (!code) {
                if (recordsSummary) recordsSummary.textContent = "Enter the instructor access code first.";
                addNotification("Instructor access code required.", "error");
                return null;
            }
            return code;
        }

        if (loadRecordsBtn) {
            loadRecordsBtn.addEventListener("click", async () => {
                const code = requireRecordsAccessCode();
                if (!code) return;

                if (recordsSummary) recordsSummary.textContent = "Loading records...";
                try {
                    const data = await fetchJsonWithDetail(`${BASE_URL}/records/summary`, {
                        headers: { "X-Instructor-Code": code },
                    });
                    if (recordsSummary) {
                        recordsSummary.textContent =
                            `${data.participant_count} login record(s), ${data.round_count} round record(s).`;
                    }

                    renderRecordsTable("participants-records-table", data.participants || [], [
                        { label: "Name", get: row => row.name },
                        { label: "Email", get: row => row.email },
                        { label: "Student ID", get: row => row.student_id },
                        { label: "Section", get: row => row.section },
                        { label: "Created", get: row => row.created_at },
                    ]);

                    renderRecordsTable("rounds-records-table", data.rounds || [], [
                        { label: "Name", get: row => row.participant?.name },
                        { label: "Student ID", get: row => row.participant?.student_id },
                        { label: "Round", get: row => row.round?.round_index },
                        { label: "Order", get: row => row.round?.order_quantity },
                        { label: "Demand", get: row => row.round?.realized_demand },
                        { label: "Buyer Profit", get: row => row.round?.buyer_profit },
                        { label: "Supplier Profit", get: row => row.round?.supplier_profit },
                    ]);
                } catch (err) {
                    console.error(err);
                    if (recordsSummary) recordsSummary.textContent = "Error: " + err.message;
                    addNotification("Failed to load records: " + err.message, "error");
                }
            });
        }

        if (downloadParticipantsBtn) {
            downloadParticipantsBtn.addEventListener("click", () => {
                const code = requireRecordsAccessCode();
                if (!code) return;
                downloadFile(`${BASE_URL}/records/participants.csv?code=${encodeURIComponent(code)}`);
            });
        }

        if (downloadRoundsBtn) {
            downloadRoundsBtn.addEventListener("click", () => {
                const code = requireRecordsAccessCode();
                if (!code) return;
                downloadFile(`${BASE_URL}/records/rounds.csv?code=${encodeURIComponent(code)}`);
            });
        }

        if (downloadChatLogsBtn) {
            downloadChatLogsBtn.addEventListener("click", () => {
                const code = requireRecordsAccessCode();
                if (!code) return;
                downloadFile(`${BASE_URL}/records/chat-logs.csv?code=${encodeURIComponent(code)}`);
            });
        }
    }

    /**
     * Updates the contract type dropdown based on available types.
     * 
     * Inputs:
    * - availableTypes: Array of contract type strings ("buyback")
     * 
     * What happens:
     * - Clears existing dropdown options
     * - Adds options for each available contract type
     * - Sets "buyback" as default if available
     */
    function updateContractTypeDropdown(availableTypes) {
        const contractTypeSelect = document.getElementById("contract-type-input");
        if (!contractTypeSelect) return;
        
        // Clear existing options
        contractTypeSelect.innerHTML = "";
        
        // Add available types
        const typeLabels = {
            "buyback": "Buyback"
        };
        
        availableTypes.forEach(type => {
            const option = document.createElement("option");
            option.value = type;
            option.textContent = typeLabels[type] || type;
            if (type === "buyback") option.selected = true;
            contractTypeSelect.appendChild(option);
        });

        contractTypeSelect.dispatchEvent(new Event("change"));
    }

    /**
     * Initializes negotiation configuration section.
     * 
     * What happens:
     * - Sets up "Load Current Negotiation Config" button handler
     * - Sets up negotiation config update form handler
     * - Loads config from backend and populates form fields
     * - Validates that at least one contract type is selected
     * - Saves updated config to backend
     * - Updates contract type dropdown in negotiation form
     */
    function initNegotiationConfigSection() {
        const loadNegConfigBtn = document.getElementById("load-negotiation-config-btn");
        const negConfigOutput = document.getElementById("negotiation-config-output");
        const updateNegConfigForm = document.getElementById("update-negotiation-config-form");

        // Load negotiation config
        if (loadNegConfigBtn && negConfigOutput) {
            loadNegConfigBtn.addEventListener("click", async () => {
                negConfigOutput.textContent = "Loading negotiation config...";
                try {
                    const data = await fetchJsonWithDetail(`${BASE_URL}/config/negotiation`);
                    negConfigOutput.textContent = JSON.stringify(data, null, 2);
                    
                    // Populate form fields
                    const config = data.negotiation_config;
                    const buybackCheckbox = document.getElementById("neg-config-ct-buyback");
                    const lengthMinInput = document.getElementById("neg-config-length-min");
                    const lengthMaxInput = document.getElementById("neg-config-length-max");
                    const promptTemplateInput = document.getElementById("neg-config-prompt-template");
                    
                    if (buybackCheckbox) buybackCheckbox.checked = config.contract_types_available.includes("buyback");
                    if (lengthMinInput) lengthMinInput.value = config.length_min;
                    if (lengthMaxInput) lengthMaxInput.value = config.length_max;
                    if (promptTemplateInput) promptTemplateInput.value = config.system_prompt_template;
                    
                    addNotification("Negotiation config loaded.", "success");
                } catch (err) {
                    console.error(err);
                    negConfigOutput.textContent = "Error: " + err.message;
                    addNotification("Failed to load negotiation config: " + err.message, "error");
                }
            });
        }

        // Update negotiation config
        if (updateNegConfigForm) {
            updateNegConfigForm.addEventListener("submit", async (e) => {
                e.preventDefault();

                negConfigOutput.textContent = "Saving negotiation configuration...";

                // Get selected contract types from checkboxes
                const contractTypeCheckboxes = document.querySelectorAll('input[name="contract-type"]:checked');
                const contractTypes = Array.from(contractTypeCheckboxes).map(cb => cb.value);
                
                // Validate at least one is selected
                if (contractTypes.length === 0) {
                    negConfigOutput.textContent = "Error: At least one contract type must be selected.";
                    addNotification("Please select at least one contract type.", "error");
                    return;
                }

                const body = {
                    negotiation_config: {
                        contract_types_available: contractTypes,
                        length_min: parseInt(document.getElementById("neg-config-length-min")?.value || "1"),
                        length_max: parseInt(document.getElementById("neg-config-length-max")?.value || "10"),
                        system_prompt_template: document.getElementById("neg-config-prompt-template")?.value || "",
                        example_dialog: [],  // Can be extended later if needed
                    },
                };

                try {
                    const data = await fetchJsonWithDetail(`${BASE_URL}/config/negotiation/update`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(body),
                    });

                    negConfigOutput.textContent = JSON.stringify(data, null, 2);
                    addNotification("Negotiation configuration saved.", "success");
                    
                    // Update contract type dropdown in negotiation form
                    updateContractTypeDropdown(contractTypes);
                } catch (err) {
                    console.error(err);
                    negConfigOutput.textContent = "Error: " + err.message;
                    addNotification("Failed to save negotiation configuration: " + err.message, "error");
                }
            });
        }
    }

    /**
     * Loads negotiation config on startup to update form limits and dropdowns.
     * 
     * What happens:
     * - Fetches negotiation config from backend
     * - Updates contract type dropdown with available types
     * - Updates length input min/max limits
    * - Cap/revenue inputs removed from frontend; only updates types and length limits
     * - Silently fails if config can't be loaded (allows app to work without config)
     */
    async function loadNegotiationConfigOnStartup() {
        try {
            const data = await fetchJsonWithDetail(`${BASE_URL}/config/negotiation`);
            const config = data.negotiation_config;

            // Update contract type dropdown
            updateContractTypeDropdown(config.contract_types_available);

            // Update length input limits
            const lengthInput = document.getElementById("length-input");
            if (lengthInput) {
                lengthInput.min = config.length_min;
                lengthInput.max = config.length_max;
                lengthInput.value = Math.max(config.length_min, Math.min(parseInt(lengthInput.value) || config.length_min, config.length_max));
            }
        } catch (err) {
            console.error("Failed to load negotiation config on startup:", err);
        }
    }

    // ================================
    // Loading Button Helpers
    // ================================

    /**
     * Sets a button into a loading state (spinner, disabled).
     * Returns a restore function to call when done.
     */
    function setButtonLoading(btn, loadingText) {
        if (!btn) return () => {};
        const originalText = btn.textContent;
        const originalDisabled = btn.disabled;
        btn.textContent = loadingText || "Loading…";
        btn.classList.add("loading");
        btn.disabled = true;
        return () => {
            btn.textContent = originalText;
            btn.classList.remove("loading");
            btn.disabled = originalDisabled;
        };
    }

    // ================================
    // Conditional Negotiation Fields
    // ================================

    /**
     * Shows/hides negotiation form fields based on selected contract type.
     */
    function initConditionalNegotiationFields() {
        const contractTypeSelect = document.getElementById("contract-type-input");
        if (!contractTypeSelect) return;

        function updateFields() {
            const val = contractTypeSelect.value;
            // Fields tagged with neg-field-buyback
            document.querySelectorAll(".form-field[class*='neg-field-']").forEach(el => {
                const classes = Array.from(el.classList);
                const relevant = classes.some(c => c === `neg-field-${val}`);
                el.style.display = relevant ? "" : "none";
            });
        }

        contractTypeSelect.addEventListener("change", updateFields);
        updateFields(); // Run on load
    }

    // ================================
    // Loading Indicator Wrappers
    // ================================

    /**
     * Wraps async button handlers with loading state.
     * Call after all sections are initialized.
     */
    function initLoadingIndicators() {
        // Start game button
        const startGameBtn = document.getElementById("start-game-btn");
        if (startGameBtn) {
            const original = startGameBtn.onclick;
            // We patch via event listener override — handled via click event already in initGameControlSection
            // Instead wrap by monkey-patching the click handler
        }

        // Helper: wrap a button's existing click listeners with loading state
        function wrapButtonWithLoading(btnId, loadingLabel) {
            const btn = document.getElementById(btnId);
            if (!btn) return;
            btn.addEventListener("click", function() {
                // The actual async work starts after this event; mark loading
                // We rely on the existing handlers to do the work
                // Just add the class — it'll be removed when state re-renders
                btn.classList.add("loading");
                setTimeout(() => btn.classList.remove("loading"), 8000); // safety fallback
            }, true); // capture phase so it fires first
        }

        wrapButtonWithLoading("start-game-btn", "Starting…");
        wrapButtonWithLoading("end-game-early-btn", "Ending…");
        wrapButtonWithLoading("health_button", "Checking…");
        wrapButtonWithLoading("ai-status-button", "Checking…");
        wrapButtonWithLoading("load-config-btn", "Loading…");
        wrapButtonWithLoading("load-negotiation-config-btn", "Loading…");
        wrapButtonWithLoading("save-history-btn", "Saving…");
        wrapButtonWithLoading("accept-counter-btn", "Accepting…");
        wrapButtonWithLoading("reject-counter-btn", "Rejecting…");

        // Form submit buttons
        ["negotiate-form", "chat-form", "order-form", "update-econ-form", "update-negotiation-config-form"].forEach(formId => {
            const form = document.getElementById(formId);
            if (!form) return;
            form.addEventListener("submit", () => {
                const btn = form.querySelector("button[type='submit']");
                if (btn) {
                    btn.classList.add("loading");
                    setTimeout(() => btn.classList.remove("loading"), 8000);
                }
            }, true);
        });
    }

    // ================================
    // Initialization on Page Load
    // ================================
    
    // Initialize UI components
    initLoginSection();
    initTabSwitching();
    initStatusDropdown();
    addNotification("UI ready. No game started yet.", "info");
    updatePhaseUI();

    // Initialize all sections
    initHealthSection();
    initAIStatusSection();
    initGameControlSection();
    initNegotiationSection();
    initOrderSection();
    initConfigSection();
    initRecordsSection();
    initNegotiationConfigSection();
    loadDemandHistoryOptionsOnStartup();
    loadNegotiationConfigOnStartup();

    // Additional UX enhancements
    initConditionalNegotiationFields();
    initLoadingIndicators();
});
