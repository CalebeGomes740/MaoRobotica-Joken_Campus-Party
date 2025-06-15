document.addEventListener('DOMContentLoaded', () => {
    // --- Elementos HTML da Câmera e Controles de Processamento ---
    const cameraFeed = document.getElementById('camera-feed');
    const cameraStatus = document.getElementById('camera-status');
    const startProcessingButton = document.getElementById('start-processing');
    const stopProcessingButton = document.getElementById('stop-processing');

    // --- Ícones de Gesto ---
    const playerLiveGestureIcon = document.getElementById('player-live-gesture-icon'); // Ícone do gesto ao vivo do jogador
    const robotChoiceIcon = document.getElementById('robot-choice-icon'); // Ícone da mão robótica (IA)

    // --- Jokenpo HTML Elements (scoreboard) ---
    const playerScoreSpan = document.getElementById('player-score');
    const aiScoreSpan = document.getElementById('ai-score');
    const tiesSpan = document.getElementById('ties'); 
    const roundsPlayedSpan = document.getElementById('rounds-played');
    
    // --- Game Feedback Area elements (mensagens de jogo) ---
    const roundResultMain = document.getElementById('round-result-main'); 
    const countdownMessageElement = document.getElementById('countdown-message'); 
    const aiCountdownMessage = document.getElementById('ai-countdown-message'); // Contagem regressiva para IA (na seção da IA)
    const aiResultMessage = document.getElementById('ai-result-message'); // Resultado da IA (na seção da IA)

    // --- Control Buttons and Debug Info ---
    const playRoundButton = document.getElementById('play-round-button');
    const finishRoundButton = document.getElementById('finish-round-button'); 
    const resetScoreboardButton = document.getElementById('reset-scoreboard');
    const handDetectedStatus = document.getElementById('hand-detected-status');
    const detectedGestureFeedback = document.getElementById('detected-gesture-feedback');
    const jokenpoJsonDisplay = document.getElementById('jokenpo-json-display');

    // --- Mapping Jokenpo Moves to Font Awesome Icons ---
    const jokenpoIcons = {
        "Pedra": "fas fa-hand-rock",
        "Papel": "fas fa-hand-paper",
        "Tesoura": "fas fa-hand-scissors",
        "Nenhum": "fas fa-question", // Default icon for "Nenhum" (None)
        "Indefinido": "fas fa-question" // For "Indefinido" (Undefined) gesture
    };

    // --- Function to update Jokenpo game state and UI ---
    async function updateJokenpoGameDisplay() {
        try {
            const response = await fetch('/jokenpo_game_status');
            if (!response.ok) {
                throw new Error(`HTTP Error: ${response.status}`);
            }
            const data = await response.json();
            
            jokenpoJsonDisplay.textContent = JSON.stringify(data, null, 2);

            // Update camera status and force refresh if needed
            if (data.camera_is_active) {
                cameraStatus.textContent = 'Câmera do Backend Ativa';
                cameraStatus.style.backgroundColor = 'rgba(46, 204, 113, 0.8)'; 
                // Força o navegador a recarregar o stream da câmera adicionando um timestamp
                // Isso pode ajudar em casos onde o navegador não atualiza o stream automaticamente
                const newSrc = `/video_feed?t=${new Date().getTime()}`;
                // Só atualiza se a URL base for diferente ou se for a primeira vez para evitar recargas constantes desnecessárias
                if (!cameraFeed.src || cameraFeed.src.split('?')[0] !== newSrc.split('?')[0]) {
                    cameraFeed.src = newSrc;
                    console.log('DEBUG: Camera feed URL updated to force refresh.');
                }
            } else {
                cameraStatus.textContent = 'Câmera do Backend Inativa/Erro';
                cameraStatus.style.backgroundColor = 'rgba(231, 76, 60, 0.8)'; 
                // Se a câmera estiver inativa, podemos limpar ou definir uma imagem de placeholder se necessário
                // Para este caso, vamos deixar a imagem atual, mas o status claro.
            }

            // Update main scoreboard elements (agora na seção superior)
            playerScoreSpan.textContent = data.player_score;
            aiScoreSpan.textContent = data.ai_score;
            tiesSpan.textContent = data.ties; 
            roundsPlayedSpan.textContent = data.rounds_played;

            // Update player's live gesture icon (na seção da câmera)
            playerLiveGestureIcon.innerHTML = `<i class="${jokenpoIcons[data.current_gesture_detected]}"></i>`;
            
            // Update AI's choice icon (na seção da mão robótica)
            robotChoiceIcon.innerHTML = `<i class="${jokenpoIcons[data.ai_choice]}"></i>`; 

            // Update round result message (na seção de mensagens principais)
            roundResultMain.textContent = data.result_message;
            roundResultMain.className = ''; 
            if (data.result_message.includes('Você venceu!')) {
                roundResultMain.classList.add('won');
            } else if (data.result_message.includes('Robô venceu!')) {
                roundResultMain.classList.add('lost');
            } else if (data.result_message.includes('Empate!')) {
                roundResultMain.classList.add('draw');
            }

            // Update AI's game feedback (countdown and result, específicos da seção da IA)
            aiCountdownMessage.textContent = data.countdown_message; 

            aiResultMessage.textContent = data.result_message; 
            aiResultMessage.className = 'result-ai'; 
            if (data.result_message.includes('Você venceu!')) {
                aiResultMessage.classList.add('lost'); 
            } else if (data.result_message.includes('Robô venceu!')) {
                aiResultMessage.classList.add('won'); 
            } else if (data.result_message.includes('Empate!')) {
                aiResultMessage.classList.add('draw'); 
            }


            // Update hand detection status (for debug info)
            if (data.hand_detected) {
                handDetectedStatus.textContent = 'Sim';
                handDetectedStatus.style.color = '#2ecc71';
            } else {
                handDetectedStatus.textContent = 'Não';
                handDetectedStatus.style.color = '#e74c3c';
            }

            // Update detected gesture feedback from backend (for debug info)
            detectedGestureFeedback.textContent = data.current_gesture_detected;

            // Update MediaPipe processing status and button states
            if (data.mediapipe_processing_active) {
                startProcessingButton.style.display = 'none';
                stopProcessingButton.style.display = 'inline-flex';
                
                if (data.game_phase === "waiting_start") {
                    playRoundButton.style.display = 'inline-flex';
                    playRoundButton.disabled = false;
                    finishRoundButton.style.display = 'none';
                } else if (data.game_phase === "counting_down") {
                    playRoundButton.style.display = 'inline-flex';
                    playRoundButton.disabled = true; 
                    finishRoundButton.style.display = 'none';
                } else if (data.game_phase === "round_finished") {
                    playRoundButton.style.display = 'none'; 
                    finishRoundButton.style.display = 'inline-flex';
                    finishRoundButton.disabled = false; 
                } else { 
                    playRoundButton.style.display = 'none';
                    finishRoundButton.style.display = 'none';
                }

            } else { // MediaPipe processing is NOT active
                startProcessingButton.style.display = 'inline-flex';
                stopProcessingButton.style.display = 'none';
                playRoundButton.style.display = 'inline-flex'; 
                playRoundButton.disabled = true;
                finishRoundButton.style.display = 'none'; 
            }

            // Update countdown message (main display)
            countdownMessageElement.textContent = data.countdown_message;

        } catch (error) {
            console.error('Error getting Jokenpo status:', error);
            roundResultMain.textContent = "Erro de Conexão com Backend.";
            roundResultMain.classList.add('lost');
            cameraStatus.textContent = 'Erro de Conexão com Backend';
            cameraStatus.style.backgroundColor = 'rgba(231, 76, 60, 0.8)';
            playRoundButton.disabled = true;
            finishRoundButton.disabled = true;
        }
    }

    setInterval(updateJokenpoGameDisplay, 100);

    // --- Processing and Game Controls ---
    startProcessingButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/control_processing/start');
            const data = await response.json();
            console.log('Processing control:', data.message);
            updateJokenpoGameDisplay();
        } catch (error) {
            console.error('Error starting processing:', error);
        }
    });

    stopProcessingButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/control_processing/stop');
            const data = await response.json();
            console.log('Processing control:', data.message);
            updateJokenpoGameDisplay();
        } catch (error) {
            console.error('Error stopping processing:', error);
        }
    });

    playRoundButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/play_jokenpo');
            const data = await response.json();
            console.log('Round Start Message:', data.message);

            if (data.status === "error") {
                alert(data.message);
            }
            updateJokenpoGameDisplay();
        } catch (error) {
            console.error('Error initiating round:', error);
            alert('Não foi possível iniciar a rodada. Verifique a conexão com o servidor.');
        }
    });

    finishRoundButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/finish_round');
            const data = await response.json();
            console.log('Finish Round Message:', data.message);
            updateJokenpoGameDisplay();
        } catch (error) {
            console.error('Error finishing round:', error);
            alert('Não foi possível terminar a rodada. Verifique a conexão com o servidor.');
        }
    });

    resetScoreboardButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/reset_jokenpo');
            const data = await response.json();
            console.log('Scoreboard Reset:', data.message);
            updateJokenpoGameDisplay();
        } catch (error) {
            console.error('Error resetting scoreboard:', error);
        }
    });

    updateJokenpoGameDisplay(); 
});
