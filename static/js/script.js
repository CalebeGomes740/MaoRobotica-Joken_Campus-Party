document.addEventListener('DOMContentLoaded', () => {
    // --- Elementos HTML da Câmera e Controles de Processamento ---
    const cameraFeed = document.getElementById('camera-feed');
    const cameraStatus = document.getElementById('camera-status');
    const startProcessingButton = document.getElementById('start-processing');
    const stopProcessingButton = document.getElementById('stop-processing');

    // --- Elementos HTML do Jokenpo ---
    const playerScoreSpan = document.getElementById('player-score');
    const aiScoreSpan = document.getElementById('ai-score');
    const roundsPlayedSpan = document.getElementById('rounds-played');
    const playerCurrentGestureSpan = document.getElementById('player-current-gesture');
    const aiCurrentChoiceSpan = document.getElementById('ai-current-choice');
    const playerChoiceIcon = document.getElementById('player-choice-icon');
    const aiChoiceIcon = document.getElementById('ai-choice-icon');
    const roundResultParagraph = document.getElementById('round-result');
    const playRoundButton = document.getElementById('play-round-button');
    const resetScoreboardButton = document.getElementById('reset-scoreboard');
    const detectedGestureFeedback = document.getElementById('detected-gesture-feedback');
    const jokenpoJsonDisplay = document.getElementById('jokenpo-json-display');

    // --- Mapeamento de Jogadas para Ícones Font Awesome ---
    const jokenpoIcons = {
        "Pedra": "fas fa-hand-rock",
        "Papel": "fas fa-hand-paper",
        "Tesoura": "fas fa-hand-scissors",
        "Nenhum": "fas fa-question"
    };

    // --- Função para atualizar o estado do Jokenpo e a UI ---
    async function updateJokenpoGameDisplay() {
        try {
            const response = await fetch('/jokenpo_game_status');
            if (!response.ok) {
                throw new Error(`Erro HTTP: ${response.status}`);
            }
            const data = await response.json();
            
            jokenpoJsonDisplay.textContent = JSON.stringify(data, null, 2);

            // Atualiza o status da câmera
            if (data.camera_is_active) {
                cameraStatus.textContent = 'Câmera do Backend Ativa';
                cameraStatus.style.backgroundColor = 'rgba(46, 204, 113, 0.8)';
            } else {
                cameraStatus.textContent = 'Câmera do Backend Inativa/Erro';
                cameraStatus.style.backgroundColor = 'rgba(231, 76, 60, 0.8)';
            }

            // Atualiza os elementos do placar
            playerScoreSpan.textContent = data.player_score;
            aiScoreSpan.textContent = data.ai_score;
            roundsPlayedSpan.textContent = data.rounds_played;

            // Atualiza as jogadas e os ícones
            playerCurrentGestureSpan.textContent = data.player_choice;
            aiCurrentChoiceSpan.textContent = data.ai_choice;

            playerChoiceIcon.innerHTML = `<i class="${jokenpoIcons[data.player_choice]}"></i>`;
            aiChoiceIcon.innerHTML = `<i class="${jokenpoIcons[data.ai_choice]}"></i>`;

            // Atualiza o resultado da rodada e a cor
            roundResultParagraph.textContent = data.result;
            roundResultParagraph.className = 'result-message';
            if (data.result === 'Ganhou') {
                roundResultParagraph.classList.add('won');
            } else if (data.result === 'Perdeu') {
                roundResultParagraph.classList.add('lost');
            } else if (data.result === 'Empate') {
                roundResultParagraph.classList.add('draw');
            }

            // Atualiza o feedback do gesto detectado pelo backend
            detectedGestureFeedback.textContent = data.current_gesture;
            if (data.hand_detected) {
                detectedGestureFeedback.style.color = '#2ecc71';
            } else {
                detectedGestureFeedback.style.color = '#e74c3c';
            }

            // Atualiza o status de processamento MediaPipe
            if (data.mediapipe_processing_active) {
                robotArmStatusText.textContent = "Processando...";
                robotArmStatusText.style.color = '#2980b9';
            } else {
                robotArmStatusText.textContent = "Inativo";
                robotArmStatusText.style.color = '#6c757d';
            }

        } catch (error) {
            console.error('Erro ao obter status do Jokenpo:', error);
            roundResultParagraph.textContent = "Erro de Conexão com Backend.";
            roundResultParagraph.classList.add('lost');
            cameraStatus.textContent = 'Erro de Conexão com Backend';
            cameraStatus.style.backgroundColor = 'rgba(231, 76, 60, 0.8)';
        }
    }

    setInterval(updateJokenpoGameDisplay, 100);

    // --- Controles de Processamento e Jogo ---
    startProcessingButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/control_processing/start');
            const data = await response.json();
            console.log('Controle de processamento:', data.message);
            updateJokenpoGameDisplay();
        } catch (error) {
            console.error('Erro ao iniciar processamento:', error);
        }
    });

    stopProcessingButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/control_processing/stop');
            const data = await response.json();
            console.log('Controle de processamento:', data.message);
            updateJokenpoGameDisplay();
        } catch (error) {
            console.error('Erro ao parar processamento:', error);
        }
    });

    playRoundButton.addEventListener('click', async () => {
        try {
            const currentGesture = detectedGestureFeedback.textContent;
            
            const validJokenpoGestures = ["Pedra", "Papel", "Tesoura"];
            if (!validJokenpoGestures.includes(currentGesture)) {
                alert('Por favor, faça um gesto válido (Pedra, Papel ou Tesoura) para jogar!');
                return;
            }

            const response = await fetch(`/play_jokenpo/${currentGesture}`);
            const data = await response.json();
            console.log('Resultado da jogada:', data);
            updateJokenpoGameDisplay();
        } catch (error) {
            console.error('Erro ao jogar rodada:', error);
            alert('Não foi possível jogar a rodada. Verifique a conexão com o servidor.');
        }
    });

    resetScoreboardButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/reset_jokenpo');
            const data = await response.json();
            console.log('Reset do placar:', data.message);
            updateJokenpoGameDisplay();
        } catch (error) {
            console.error('Erro ao reiniciar placar:', error);
        }
    });

    updateJokenpoGameDisplay();
});