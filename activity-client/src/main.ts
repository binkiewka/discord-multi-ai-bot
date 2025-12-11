import { DiscordSDK } from '@discord/embedded-app-sdk';

// Types
interface GameState {
  target: number;
  numbers: number[];
  end_time: number;
  current_round: number;
  total_rounds: number;
  status?: string;
}

interface SubmitResponse {
  success: boolean;
  result?: number;
  distance?: number;
  error?: string;
}

interface AuthenticatedUser {
  id: string;
  username: string;
  discriminator: string;
  avatar: string | null;
  global_name: string | null;
}

// Configuration
const CLIENT_ID = import.meta.env.VITE_DISCORD_CLIENT_ID;

// Discord SDK instance
let discordSdk: DiscordSDK;
let authenticatedUser: AuthenticatedUser | null = null;
let gameId: string = '';

// Game state
let gameState: GameState = {
  target: 0,
  numbers: [],
  end_time: 0,
  current_round: 1,
  total_rounds: 1,
};
let currentExpression = '';
let usedIndices = new Set<number>();

// Polling intervals
let pollInterval: number | null = null;
let timerInterval: number | null = null;

// DOM Elements
const loadingEl = document.getElementById('loading')!;
const lobbyEl = document.getElementById('lobby-container')!;
const gameContainerEl = document.getElementById('game-container')!;
const targetNumberEl = document.getElementById('target-number')!;
const numbersContainerEl = document.getElementById('numbers-container')!;
const calcScreenEl = document.getElementById('calc-screen')!;
const timerValEl = document.getElementById('timer-val')!;
const roundDisplayEl = document.getElementById('round-display')!;
const userDisplayEl = document.getElementById('user-display')!;
const toastEl = document.getElementById('toast')!;
const submitBtn = document.getElementById('btn-submit') as HTMLButtonElement;
const startGameBtn = document.getElementById('btn-start-game') as HTMLButtonElement;

// Lobby State
let lobbySettings = {
  rounds: 3,
  time: 60
};

// Initialize Discord SDK
async function initializeDiscordSDK(): Promise<void> {
  if (!CLIENT_ID) {
    showError('Missing VITE_DISCORD_CLIENT_ID environment variable');
    return;
  }

  try {
    discordSdk = new DiscordSDK(CLIENT_ID);

    // Wait for Discord client to be ready
    await discordSdk.ready();
    console.log('Discord SDK ready');

    // Authorize with Discord
    const { code } = await discordSdk.commands.authorize({
      client_id: CLIENT_ID,
      response_type: 'code',
      state: '',
      prompt: 'none',
      scope: ['identify'],
    });
    console.log('Authorization code received');

    // Exchange code for access token via backend
    const tokenResponse = await fetch('/.proxy/api/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    });

    if (!tokenResponse.ok) {
      const errorData = await tokenResponse.json().catch(() => ({}));
      throw new Error(errorData.error || `Token exchange failed: ${tokenResponse.status} `);
    }

    const { access_token } = await tokenResponse.json();

    // Authenticate with Discord client
    const auth = await discordSdk.commands.authenticate({ access_token });

    if (!auth.user) {
      throw new Error('No user data returned from authentication');
    }

    authenticatedUser = auth.user as AuthenticatedUser;
    console.log('Authenticated as:', authenticatedUser.username);

    // Build game ID from guild and channel
    const guildId = discordSdk.guildId;
    const channelId = discordSdk.channelId;

    if (guildId && channelId) {
      gameId = `${guildId}_${channelId} `;
    } else {
      // Fallback for DMs or other contexts
      gameId = channelId || 'unknown';
    }

    // Initialize the game
    initializeGame();
  } catch (error) {
    console.error('Discord SDK initialization failed:', error);
    // Show actual error message to help debugging
    const errorMessage = error instanceof Error ? error.message : String(error);
    showError(`Failed to connect: ${errorMessage} `);
  }
}

// Initialize game UI and polling
function initializeGame(): void {
  // Hide loading, show game
  loadingEl.classList.add('hidden');
  gameContainerEl.classList.remove('hidden');

  // Update user display
  if (authenticatedUser) {
    const displayName = authenticatedUser.global_name || authenticatedUser.username;
    userDisplayEl.textContent = `Playing as: ${displayName} `;
  }

  // Set up button event listeners
  setupEventListeners();
  setupLobbyListeners(); // New lobby listeners

  // Start polling for game state
  fetchGameState();
  pollInterval = window.setInterval(fetchGameState, 2000);
  timerInterval = window.setInterval(updateTimer, 100);
}

function showLobby(): void {
  loadingEl.classList.add('hidden');
  gameContainerEl.classList.add('hidden');
  lobbyEl.classList.remove('hidden');
}

function showGame(): void {
  loadingEl.classList.add('hidden');
  lobbyEl.classList.add('hidden');
  gameContainerEl.classList.remove('hidden');
}

function setupLobbyListeners(): void {
  // Rounds selection
  document.getElementById('rounds-select')?.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;
    if (target.tagName === 'BUTTON') {
      document.querySelectorAll('#rounds-select .seg-btn').forEach(b => b.classList.remove('active'));
      target.classList.add('active');
      lobbySettings.rounds = parseInt(target.getAttribute('data-value') || '3');
    }
  });

  // Time selection
  document.getElementById('time-select')?.addEventListener('click', (e) => {
    const target = e.target as HTMLElement;
    if (target.tagName === 'BUTTON') {
      document.querySelectorAll('#time-select .seg-btn').forEach(b => b.classList.remove('active'));
      target.classList.add('active');
      lobbySettings.time = parseInt(target.getAttribute('data-value') || '60');
    }
  });

  // Start Game
  startGameBtn?.addEventListener('click', createGame);
}

async function createGame(): Promise<void> {
  if (!authenticatedUser) return;

  startGameBtn.disabled = true;
  startGameBtn.textContent = "STARTING...";

  try {
    const response = await fetch('/.proxy/api/game/create', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        server_id: gameId.split('_')[0], // Extract from gameId logic
        channel_id: gameId.split('_')[1] || gameId.split('_')[0], // Fallback if no underscore
        rounds: lobbySettings.rounds,
        duration: lobbySettings.time,
        started_by: authenticatedUser.id
      })
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.error || "Failed to create game");
    }

    // Success - fetch state immediately
    await fetchGameState();

  } catch (e) {
    showToast(String(e), 'error');
    startGameBtn.disabled = false;
    startGameBtn.textContent = "START GAME";
  }
}

// Set up button event listeners
function setupEventListeners(): void {
  document.getElementById('btn-add')?.addEventListener('click', () => appendOp('+'));
  document.getElementById('btn-sub')?.addEventListener('click', () => appendOp('-'));
  document.getElementById('btn-mul')?.addEventListener('click', () => appendOp('*'));
  document.getElementById('btn-div')?.addEventListener('click', () => appendOp('/'));
  document.getElementById('btn-lparen')?.addEventListener('click', () => appendOp('('));
  document.getElementById('btn-rparen')?.addEventListener('click', () => appendOp(')'));
  document.getElementById('btn-clear')?.addEventListener('click', clearCalc);
  submitBtn?.addEventListener('click', submitAnswer);
}

// Fetch game state from backend
async function fetchGameState(): Promise<void> {
  if (!gameId) return;

  try {
    const response = await fetch(`/.proxy / api / game / ${gameId} `);

    if (!response.ok) {
      if (response.status === 404) {
        showToast('Game not found or ended', 'error');
      }
      return;
    }

    // Debug: read text first
    const textData = await response.text();
    console.log("Raw Game State Response:", textData);

    try {
      const data = JSON.parse(textData);
      // Check for inactive status
      if (data.status === 'inactive') {
        showLobby();
        return;
      }

      // If active game, show game UI
      if (lobbyEl.classList.contains('hidden') === false) {
        showGame();
      }

      const gameStateData = data as GameState;

      if (gameStateData.target !== gameState.target || gameStateData.current_round !== gameState.current_round) {
        initRound(gameStateData);
      }

      gameState = gameStateData;
    } catch (e) {
      console.error("JSON Parse Error:", e, "Data:", textData);
      showToast(`JSON Error: ${textData.substring(0, 20)}...`, 'error');
    }
  } catch (error) {
    console.error('Poll error:', error);
  }
}

// Initialize a new round
function initRound(data: GameState): void {
  gameState = data;
  currentExpression = '';
  usedIndices.clear();

  // Clear and rebuild number cards
  numbersContainerEl.innerHTML = '';

  data.numbers.forEach((num, idx) => {
    const btn = document.createElement('div');
    btn.className = 'num-card';
    btn.textContent = String(num);
    btn.addEventListener('click', () => useNumber(num, idx, btn));
    numbersContainerEl.appendChild(btn);
  });

  // Update UI
  targetNumberEl.textContent = String(data.target);
  roundDisplayEl.textContent = `Round ${data.current_round} of ${data.total_rounds}`;
  updateScreen();
}

// Use a number in the expression
function useNumber(num: number, idx: number, element: HTMLElement): void {
  if (usedIndices.has(idx)) return;

  currentExpression += String(num);
  usedIndices.add(idx);
  element.classList.add('used');

  updateScreen();
}

// Append operator to expression
function appendOp(op: string): void {
  if (op === '(' || op === ')') {
    currentExpression += op;
  } else {
    currentExpression += ` ${op} `;
  }
  updateScreen();
}

// Clear calculator
function clearCalc(): void {
  currentExpression = '';
  usedIndices.clear();

  // Reset visual cards
  document.querySelectorAll('.num-card').forEach((el) => {
    el.classList.remove('used');
  });

  updateScreen();
}

// Update the calculation screen display
function updateScreen(): void {
  if (!currentExpression) {
    calcScreenEl.innerHTML = '<span class="placeholder">Select numbers...</span>';
  } else {
    calcScreenEl.textContent = currentExpression;
  }
}

// Submit answer to backend
async function submitAnswer(): Promise<void> {
  if (!currentExpression || !authenticatedUser) return;

  submitBtn.disabled = true;

  try {
    const response = await fetch('/.proxy/api/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        game_id: gameId,
        user_id: authenticatedUser.id,
        expression: currentExpression,
      }),
    });

    const data: SubmitResponse = await response.json();

    if (data.success) {
      if (data.distance === 0) {
        showToast(`PERFECT! ${data.result} `, 'success');
      } else {
        showToast(`Submitted: ${data.result} (${data.distance} off)`, 'success');
      }
    } else {
      showToast(data.error || 'Invalid Expression', 'error');
    }
  } catch (error) {
    console.error('Submit error:', error);
    showToast('Network Error', 'error');
  } finally {
    submitBtn.disabled = false;
  }
}

// Update timer display
function updateTimer(): void {
  if (!gameState.end_time) return;

  const now = Date.now() / 1000;
  const left = Math.max(0, gameState.end_time - now);

  timerValEl.textContent = `${Math.ceil(left)} s`;

  // Add warning color when time is low
  if (left <= 10) {
    timerValEl.style.color = 'var(--danger)';
  } else {
    timerValEl.style.color = 'var(--success)';
  }
}

// Show toast notification
function showToast(msg: string, type: 'success' | 'error'): void {
  toastEl.textContent = msg;
  toastEl.className = `toast ${type} `;

  setTimeout(() => {
    toastEl.className = 'toast hidden';
  }, 3000);
}

// Show error state
function showError(message: string): void {
  loadingEl.innerHTML = `
  < div class="error-container" >
    <h2>Connection Error </h2>
      < p > ${message} </p>
        < div style = "margin-top: 1rem; font-size: 0.8em; opacity: 0.7; text-align: left; background: rgba(0,0,0,0.2); padding: 0.5rem; border-radius: 4px;" >
          <p><strong>Debug Info: </strong></p >
            <p>Client ID detected: ${CLIENT_ID ? CLIENT_ID.substring(0, 4) + '...' : 'UNDEFINED'} </p>
              < p > Game ID: ${gameId} </p>
                </div>
                </div>
                  `;
}

// Cleanup on unload
window.addEventListener('beforeunload', () => {
  if (pollInterval) clearInterval(pollInterval);
  if (timerInterval) clearInterval(timerInterval);
});

// Start the application
initializeDiscordSDK();
