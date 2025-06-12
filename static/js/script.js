document.addEventListener('DOMContentLoaded', () => {
    // --- Elementos HTML da Câmera e Controles de Processamento ---
    const cameraFeed = document.getElementById('camera-feed');
    const cameraStatus = document.getElementById('camera-status');
    const startProcessingButton = document.getElementById('start-processing');
    const stopProcessingButton = document.getElementById('stop-processing');

    // --- Elementos SVG para a mão robótica ---
    const robotArmSvg = document.getElementById('robot-arm-svg');
    const armSegmentShoulder = document.getElementById('arm-segment-shoulder');
    const armSegmentElbow = document.getElementById('arm-segment-elbow');
    const robotHand = document.getElementById('robot-hand'); // Este grupo pode não ser usado diretamente para rotação de dedos, mas é bom ter a referência
    const fingerThumb = document.getElementById('finger-thumb');
    const fingerIndex = document.getElementById('finger-index');
    const fingerMiddle = document.getElementById('finger-middle');
    const fingerRing = document.getElementById('finger-ring');
    const fingerPinky = document.getElementById('finger-pinky');

    // --- Elementos de status no frontend ---
    const handDetectedStatus = document.getElementById('hand-detected-status');
    const robotArmStatusText = document.getElementById('robot-arm-status-text');
    const robotArmJsonDisplay = document.getElementById('robot-arm-json-display');

    // --- Define os pontos de origem para rotação dos dedos no SVG ---
    // Estes pontos foram ajustados visualmente no SVG para que as rotações pareçam naturais.
    const fingerOrigins = {
        "finger-thumb": "104 20", // X Y do ponto de pivô para o polegar (relativo ao seu grupo 'robot-hand' ou ao próprio SVG)
        "finger-index": "119 20", // X Y do ponto de pivô para o indicador
        "finger-middle": "131 20",
        "finger-ring": "144 20",
        "finger-pinky": "156 20"
    };

    // Mapeia o nome do dedo do estado do backend para o elemento SVG correspondente
    const fingerElements = {
        "finger_thumb": fingerThumb,
        "finger_index": fingerIndex,
        "finger_middle": fingerMiddle,
        "finger_ring": fingerRing,
        "finger_pinky": fingerPinky
    };

    // --- Função para atualizar a visualização da mão robótica com base no estado do backend ---
    async function updateRobotArmDisplay() {
        try {
            // Faz uma requisição GET ao endpoint do Flask para obter o estado da mão
            const response = await fetch('/robot_arm_status');
            if (!response.ok) {
                throw new Error(`Erro HTTP: ${response.status}`);
            }
            const data = await response.json();
            
            // Exibe o JSON cru para depuração
            robotArmJsonDisplay.textContent = JSON.stringify(data, null, 2);

            // Atualiza o status da câmera
            if (data.camera_is_active) {
                cameraStatus.textContent = 'Câmera do Backend Ativa';
                cameraStatus.style.backgroundColor = 'rgba(46, 204, 113, 0.8)'; // Verde
            } else {
                cameraStatus.textContent = 'Câmera do Backend Inativa/Erro';
                cameraStatus.style.backgroundColor = 'rgba(231, 76, 60, 0.8)'; // Vermelho
            }

            // Atualiza o status de detecção de mão
            if (data.hand_detected) {
                handDetectedStatus.textContent = 'Sim';
                handDetectedStatus.style.color = '#2ecc71'; // Verde se mão detectada
            } else {
                handDetectedStatus.textContent = 'Não';
                handDetectedStatus.style.color = '#e74c3c'; // Vermelho se não detectada
            }

            // Atualiza a rotação dos dedos com base nos dados do backend
            // A lógica de 0 (fechado) e 45 (aberto) é definida no mock de 'mao' no Python.
            for (const fingerKey in fingerElements) {
                const element = fingerElements[fingerKey];
                const angle = data[fingerKey]; // Pega o ângulo do estado do backend
                const origin = fingerOrigins[element.id]; // Pega o ponto de pivô do dedo

                if (element && origin) {
                    // Adaptação: Inverte a rotação para o polegar para simular fechamento
                    // Os outros dedos giram em um sentido para "abrir"
                    if (fingerKey === "finger_thumb") {
                        element.style.transform = `rotate(${-angle}deg)`;
                    } else {
                        element.style.transform = `rotate(${angle}deg)`;
                    }
                    element.setAttribute('transform-origin', origin);
                }
            }

            // Atualiza o texto do status de processamento MediaPipe
            if (data.mediapipe_processing_active) {
                robotArmStatusText.textContent = "Processando...";
                robotArmStatusText.style.color = '#2980b9'; // Azul
            } else {
                robotArmStatusText.textContent = "Inativo";
                robotArmStatusText.style.color = '#6c757d'; // Cinza
            }

        } catch (error) {
            console.error('Erro ao obter status da mão robótica:', error);
            robotArmStatusText.textContent = "Erro de Conexão com Backend.";
            robotArmStatusText.style.color = '#e67e22'; // Laranja para erro
            cameraStatus.textContent = 'Erro de Conexão com Backend';
            cameraStatus.style.backgroundColor = 'rgba(231, 76, 60, 0.8)'; // Vermelho
        }
    }

    // Define um intervalo para buscar e atualizar o estado da mão robótica a cada 100ms
    setInterval(updateRobotArmDisplay, 100);

    // --- Controles de Processamento ---
    startProcessingButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/control_processing/start');
            const data = await response.json();
            console.log('Controle de processamento:', data.message);
            updateRobotArmDisplay(); // Força atualização imediata
        } catch (error) {
            console.error('Erro ao iniciar processamento:', error);
        }
    });

    stopProcessingButton.addEventListener('click', async () => {
        try {
            const response = await fetch('/control_processing/stop');
            const data = await response.json();
            console.log('Controle de processamento:', data.message);
            updateRobotArmDisplay(); // Força atualização imediata
        } catch (error) {
            console.error('Erro ao parar processamento:', error);
        }
    });

    // Chama a função de atualização da mão robótica na inicialização da página
    updateRobotArmDisplay();
});