# Fashion Supply Chain Simulation

An educational simulation where students learn supply chain contract negotiation by playing the role of a buyer negotiating with an AI-powered supplier.

## Project Overview

### What the Simulation Is

This is an interactive supply chain management game that simulates a fashion retail supply chain. Students act as buyers who must negotiate contracts with suppliers and make ordering decisions under demand uncertainty.

### Student's Role

Students play as the **buyer** in a supply chain:
- **Negotiate contracts** with an AI supplier, proposing terms like wholesale prices, buyback prices, contract length, and return caps
- **Place orders** each round, deciding how many units to order based on demand uncertainty
- **Analyze results** to understand how contract terms and ordering decisions affect profits

### Learning Objectives

The simulation teaches:
- **Contract mechanics**: How different contract types (buyback, revenue sharing, hybrid) affect profits
- **Negotiation skills**: Iterative discussion and compromise with a supplier
- **Decision-making under uncertainty**: Balancing risk and reward when demand is unpredictable
- **Supply chain dynamics**: Understanding the relationship between buyer and supplier profits
- **Performance analysis**: Using data to evaluate decisions and improve strategy

### How It Works (High Level)

1. **Negotiate a contract**: Student proposes contract terms (wholesale price, buyback price, caps, length, contract type). An AI supplier evaluates the proposal and either accepts it or rejects it. If rejected, the student can discuss terms in a chat interface to reach an agreement.

2. **Place orders**: With an active contract, the student places orders across multiple rounds. Each round:
   - Student decides order quantity (Q)
   - System generates realized demand (D) using historical data
   - Simulation calculates sales, returns, leftovers, and profits for both buyer and supplier

3. **View results**: After each round, students see detailed breakdowns of revenues, costs, and profits, how demand uncertainty affected outcomes, and cumulative performance across all rounds.

4. **Renegotiate**: When contracts expire, students must negotiate new contracts to continue playing.

For detailed information about the negotiation flow and contract mechanics, see [ARCHITECTURE.md](ARCHITECTURE.md).

## UI Overview

The interface is organized into three main tabs:

### Student Tab

The main gameplay interface:
- **Phase Banner**: Shows current game status (no game, needs contract, active contract, game over)
- **Contract Summary**: Displays active contract terms (prices, caps, length, remaining rounds)
- **Negotiation Section**: Form to propose contracts and chat with the AI supplier
- **Order Decision Section**: Form to place orders for each round
- **Round Results**: Detailed breakdown of the most recent round's outcomes
- **Demand History**: Chart and table showing historical demand patterns and game rounds
- **Cumulative Profits**: Running totals for buyer and supplier

### Instructor Tab

Configuration and monitoring tools:
- **Game Setup**: Start new games, set number of rounds, choose demand generation method
- **Economic Parameters**: Configure prices, costs, and salvage values
- **Demand History**: View and edit historical demand data
- **Negotiation Configuration**: Set constraints on contract types, lengths, and parameter ranges
- **Game Summary**: View complete game results and negotiation history

### Debug Tab

Technical information for troubleshooting:
- **Backend Health**: Check if the backend server is running
- **AI Status**: Verify AI provider configuration (OpenAI or DeepSeek)
- **Game State JSON**: Raw game state data
- **Summary Output**: Complete game summary data

## Period vs Round in Demand History
- **Period**: A time unit in the complete demand timeline, including both historical periods (pre-game demand data) and game rounds (demand values generated during gameplay)
- **Round**: An in-game decision step where the student places an order, the system generates realized demand, and the simulation calculates results

The demand history chart shows both historical periods and game rounds together. The UI labels historical data as "Period X" and game data as "Round X" to make this distinction clear. For detailed technical information, see [ARCHITECTURE.md](ARCHITECTURE.md).

## AI Usage

Supplier personality stays fixed for each game and guides both AI proposal evaluation and negotiation chat, including concessions and offered terms. The `POST /game/start` request accepts `personality`: `selfish` (supplier profit first), `fair` (balanced profit and risk), or `altruistic` (buyer benefit with a viable supplier margin). Omitted values default to `fair`; missing or unrecognized values in legacy game state also use fair behavior. The offline proposal evaluator uses the same personality selection with its existing acceptance thresholds.

This project uses AI in two ways:

1. **As part of the negotiation system**: The supplier is powered by AI (OpenAI or DeepSeek) to provide realistic, educational negotiation experiences. The AI evaluates contract proposals and engages in conversational negotiation.
   - **Note**: The OpenAI integration has not been fully tested in production. The system includes fallback logic that works without AI configured, and DeepSeek (via OpenRouter) has been used as an alternative provider.

2. **During development**: AI assistance was extensively used throughout the project lifecycle:
   - **Code organization**: AI helped reformat and reorganize the codebase for better structure and maintainability
   - **Documentation**: AI was used to generate comprehensive documentation, including this README and the ARCHITECTURE.md file
   - **Code generation**: AI assisted with generating boilerplate code, suggesting patterns, and filling knowledge gaps
   - **Final decisions**: All design choices, integration decisions, and architectural patterns remained developer-driven and were reviewed before implementation

## Running the Project

### Prerequisites

- Python 3.8 or higher
- A modern web browser
- OpenAI API key or OpenRouter API key for AI negotiation features

### Starting the Backend

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Set up AI provider:
   - For OpenAI: Set `OPENAI_API_KEY` environment variable
   - For DeepSeek (via OpenRouter): Set `OPENROUTER_API_KEY` environment variable
   - See [OPENAI_SETUP.md](OPENAI_SETUP.md) for detailed setup instructions
   - Note: The simulation works without AI, but negotiation will use simple fallback logic

   **Example `.env` file** (create in the `backend` directory):
   ```
   OPENAI_API_KEY=sk-your-key-here
   OPENROUTER_API_KEY=sk-your-key-here
   ```
   Note: You only need to set one of these keys. The system will use OpenAI if `OPENAI_API_KEY` is set, otherwise it will try `OPENROUTER_API_KEY`.

4. Start the FastAPI server:
   ```bash
   uvicorn app.main:app --reload
   ```

   The backend will run on `http://localhost:8000` by default.

### Opening the Frontend

1. Open `frontend/index.html` in a web browser
   - You can double-click the file, or
   - Use a local server (e.g., `python -m http.server` in the frontend directory)

2. The frontend expects the backend to be running on `http://localhost:8000`
   - If using a different port, update `BASE_URL` in `frontend/main.js`

### Required Configuration Files

The following configuration files are required and should exist in the `backend` directory:

- **`config/economic_params.json`**: Economic parameters (prices, costs, salvage values)
- **`config/negotiation_config.json`**: Negotiation constraints and AI prompt template
- **`data/D_hist.csv`**: Historical demand data (one value per row)

If these files are missing, the system will use default values. See the Instructor tab in the UI to view and edit configuration.

## Current Project Status

### Implemented Features and Notes

- Complete game lifecycle (start, play, end)
- Contract negotiation with AI supplier
- Three contract types: buyback, revenue sharing, hybrid
- Conversational negotiation chat
- Round-by-round simulation with detailed profit breakdowns
- Demand generation (bootstrap and normal distribution methods)
- Configuration management (economic parameters, demand history, negotiation constraints)
- Phase-aware UI with clear guidance
- Game summaries with comprehensive statistics
- Negotiation history tracking
- AI provider fallback (works without AI configured; check ARCHITECTURE.md)
- **FOR DATA COLLECTION**: Data is stored in local memory (browser memory), avaliable after the game/debug menu.

### Future Work

- Prompt Engineering
- Database persistence for game sessions
- Multi-player or team-based gameplay
- Advanced analytics and visualization
- Export game results for analysis
- Additional contract types or mechanics
- Instructor dashboard with student progress tracking


## Contributing

This project is designed for educational use. For technical details about the codebase structure, API design, and data models, see [ARCHITECTURE.md](ARCHITECTURE.md).

**THIS FILE WAS GENERATED WITH AI, BUT REVIEWED**
