import { DiscordSDK, patchUrlMappings } from '@discord/embedded-app-sdk';

// Types
interface GameState {
  target: number;
  numbers: number[];
  endTime: number;
  round: number;
  totalRounds: number;
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
  endTime: 0,
  round: 1,
  totalRounds: 1,
};
let currentExpression = '';
let usedIndices = new Set<number>();

// Polling intervals
let pollInterval: number | null = null;
let timerInterval: number | null = null;

// DOM Elements
const loadingEl = document.getElementById('loading')!;
const gameContainerEl = document.getElementById('game-container')!;
const targetNumberEl = document.getElementById('target-number')!;
const numbersContainerEl = document.getElementById('numbers-container')!;
const calcScreenEl = document.getElementById('calc-screen')!;
const timerValEl = document.getElementById('timer-val')!;
const roundDisplayEl = document.getElementById('round-display')!;
const userDisplayEl = document.getElementById('user-display')!;
const toastEl = document.getElementById('toast')!;
const submitBtn = document.getElementById('btn-submit') as HTMLButtonElement;

// Initialize Discord SDK
async function initializeDiscordSDK(): Promise<void> {
  if (!CLIENT_ID) {
    showError('Missing VITE_DISCORD_CLIENT_ID environment variable');
    return;
  }

  try {
    discordSdk = new DiscordSDK(CLIENT_ID);

    // Patch URL mappings for API calls through Discord's proxy
    patchUrlMappings([
      { prefix: '/api', target: 'API_TARGET_PLACEHOLDER' }, // Will be replaced in production
    ]);

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
      throw new Error('Failed to exchange token');
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
      gameId = `${guildId}_${channelId}`;
    } else {
      // Fallback for DMs or other contexts
      gameId = channelId || 'unknown';
    }

    // Initialize the game
    initializeGame();
  } catch (error) {
    console.error('Discord SDK initialization failed:', error);
    showError('Failed to connect to Discord. Please try again.');
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
    userDisplayEl.textContent = `Playing as: ${displayName}`;
  }

  // Set up button event listeners
  setupEventListeners();

  // Start polling for game state
  fetchGameState();
  pollInterval = window.setInterval(fetchGameState, 2000);
  timerInterval = window.setInterval(updateTimer, 100);
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
    const response = await fetch(`/.proxy/api/game/${gameId}`);

    if (!response.ok) {
      if (response.status === 404) {
        showToast('Game not found or ended', 'error');
      }
      return;
    }

    const data: GameState = await response.json();

    // If state changed (new round), reset
    if (data.target !== gameState.target || data.round !== gameState.round) {
      initRound(data);
    }

    gameState = data;
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
  roundDisplayEl.textContent = `Round ${data.round} of ${data.totalRounds}`;
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
        showToast(`PERFECT! ${data.result}`, 'success');
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
  if (!gameState.endTime) return;

  const now = Date.now() / 1000;
  const left = Math.max(0, gameState.endTime - now);

  timerValEl.textContent = `${Math.ceil(left)}s`;

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
  toastEl.className = `toast ${type}`;

  setTimeout(() => {
    toastEl.className = 'toast hidden';
  }, 3000);
}

// Show error state
function showError(message: string): void {
  loadingEl.innerHTML = `
    <div class="error-container">
      <h2>Connection Error</h2>
      <p>${message}</p>
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
