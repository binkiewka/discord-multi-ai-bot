const API_BASE = '/api';
const urlParams = new URLSearchParams(window.location.search);
const GAME_ID = urlParams.get('id');
const USER_ID = urlParams.get('user');

let gameState = {
    numbers: [],
    target: 0,
    endTime: 0
};

let currentExpression = "";
let usedIndices = new Set();
let uiNumbers = []; // Array of number objects {value, index, used}

// Polling interval
setInterval(fetchGameState, 2000); // 2s polling
setInterval(updateTimer, 100);     // timer UI update

async function fetchGameState() {
    if (!GAME_ID) return;

    try {
        const res = await fetch(`${API_BASE}/game/${GAME_ID}`);
        if (!res.ok) {
            if (res.status === 404) showToast("Game Ended", "error");
            return;
        }
        const data = await res.json();

        // If state changed (new round), reset
        if (data.target !== gameState.target || data.round !== gameState.round) {
            initRound(data);
        }
        gameState = data;
    } catch (e) {
        console.error("Poll error", e);
    }
}

function initRound(data) {
    gameState = data;
    currentExpression = "";
    usedIndices.clear();

    // Setup UI Numbers
    // We map the numbers to buttons. 
    // We need to render them in the top "Available Numbers" row AND the keypad?
    // Modern design usually has them as cards at top, and you tap THEM to use them.
    // Let's hide the generic keypad numbers and map the Top cards as the buttons.

    const container = document.getElementById('numbers-container');
    container.innerHTML = '';

    data.numbers.forEach((num, idx) => {
        const btn = document.createElement('div');
        btn.className = 'num-card';
        btn.textContent = num;
        btn.onclick = () => useNumber(num, idx, btn);
        container.appendChild(btn);
    });

    updateScreen();
    // Update Target
    document.getElementById('target-number').textContent = data.target;
}

function useNumber(num, idx, element) {
    if (usedIndices.has(idx)) return;

    currentExpression += `${num}`;
    usedIndices.add(idx);
    element.classList.add('used');

    updateScreen();
}

function appendOp(op) {
    if (op === '(' || op === ')') {
        currentExpression += op;
    } else {
        currentExpression += ` ${op} `;
    }
    updateScreen();
}

function clearCalc() {
    currentExpression = "";
    usedIndices.clear();
    // Reset visual cards
    document.querySelectorAll('.num-card').forEach(el => el.classList.remove('used'));
    updateScreen();
}

function updateScreen() {
    const screen = document.getElementById('calc-screen');
    if (!currentExpression) {
        screen.innerHTML = '<span class="placeholder">Select numbers...</span>';
    } else {
        screen.textContent = currentExpression;
    }
}

async function submitAnswer() {
    if (!currentExpression) return;

    try {
        const res = await fetch(`${API_BASE}/submit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                game_id: GAME_ID,
                user_id: USER_ID,
                expression: currentExpression
            })
        });

        const data = await res.json();

        if (data.success) {
            if (data.distance === 0) {
                showToast(`PERFECT! ${data.result}`, 'success');
            } else {
                showToast(`Submitted: ${data.result} (${data.distance} off)`, 'success');
            }
        } else {
            showToast(data.error || "Invalid Expression", 'error');
        }
    } catch (e) {
        showToast("Network Error", "error");
    }
}

function showToast(msg, type) {
    const toast = document.getElementById('toast');
    toast.textContent = msg;
    toast.className = `toast ${type}`;

    setTimeout(() => {
        toast.className = 'toast hidden';
    }, 3000);
}

function updateTimer() {
    if (!gameState.endTime) return;

    const now = Date.now() / 1000;
    const left = Math.max(0, gameState.endTime - now);

    document.getElementById('timer-val').textContent = Math.ceil(left) + 's';

    const ring = document.querySelector('.timer-ring-circle');
    // Calculate stroke offset for ring animation if desired
    // Circumference = 2 * pi * 8 ~= 50
    // ring.style.strokeDasharray = `${(left/60)*50} 50`;
}

// Initial load
fetchGameState();
