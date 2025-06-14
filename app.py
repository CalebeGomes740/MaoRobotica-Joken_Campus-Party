import cv2
import mediapipe as mp
import random
import time
import threading
from flask import Flask, render_template, Response, jsonify

app = Flask(__name__)

# --- Variáveis Globais para o Estado da Aplicação e Stream de Vídeo ---
latest_frame = None  # Armazena o último frame da câmera processado, em formato JPEG.
frame_lock = threading.Lock()  # Um bloqueio de thread para garantir que 'latest_frame' é acedido de forma segura.

jokenpo_game_state = {
    "player_score": 0,
    "ai_score": 0,
    "ties": 0, # Contagem de empates
    "rounds_played": 0,
    "player_choice": "Nenhum",             # Jogada final do jogador nesta rodada
    "ai_choice": "Nenhum",                 # Jogada final da IA nesta rodada
    "result_message": "Aguardando...",     # Mensagem do resultado da rodada (Você venceu!, Empate!, etc.)
    "current_gesture_detected": "Nenhum",  # Gesto detectado em tempo real pelo MediaPipe (feedback ao usuário)
    "hand_detected": False,                # Indica se uma mão está a ser detetada
    "camera_is_active": False,             # Indica se a câmera do backend está a funcionar
    "countdown_message": "",               # Mensagem da contagem regressiva ("Jogue em... X")
    "game_phase": "waiting_start",         # Fases: "waiting_start", "counting_down", "round_finished"
    "mediapipe_processing_active": False   # Controla se o MediaPipe está ativo (ativado/desativado pelos botões do frontend)
}

# --- Funções de Jogo (DO SEU CÓDIGO ORIGINAL - MANTIDAS EXATAMENTE COMO FORNECIDAS) ---
def detectar_gesto(pontos):
    """
    Tenta determinar a jogada de Jokenpo a partir dos pontos da mão.
    Utiliza os limiares e a lógica fornecida pelo utilizador.
    Retorna "Pedra", "Papel", "Tesoura" ou "Indefinido".
    """
    if len(pontos) < 21: # Certifica-se de que há pontos suficientes
        return "Indefinido"

    distPolegar = abs(pontos[17][0] - pontos[4][0])
    distIndicador = pontos[5][1] - pontos[8][1]
    distMedio = pontos[9][1] - pontos[12][1]
    distAnelar = pontos[13][1] - pontos[16][1]
    distMinimo = pontos[17][1] - pontos[20][1]

    polegar_aberto = distPolegar >= 80
    indicador_aberto = distIndicador >= 1
    medio_aberto = distMedio >= 1
    anelar_aberto = distAnelar >= 1
    minimo_aberto = distMinimo >= 1

    dedos_abertos = [polegar_aberto, indicador_aberto, medio_aberto, anelar_aberto, minimo_aberto]

    if not any(dedos_abertos):
        return "Pedra"
    elif all(dedos_abertos):
        return "Papel"
    elif indicador_aberto and medio_aberto and not (polegar_aberto or anelar_aberto or minimo_aberto):
        return "Tesoura"
    else:
        return "Indefinido"

def escolher_jogada_robo():
    return random.choice(["Pedra", "Papel", "Tesoura"])

def resultado_jogo(jogador, robo):
    if jogador == "Indefinido":
        return "Mostre Pedra, Papel ou Tesoura claramente!"
    if jogador == robo:
        return "Empate!"
    elif (jogador == "Pedra" and robo == "Tesoura") or \
         (jogador == "Tesoura" and robo == "Papel") or \
         (jogador == "Papel" and robo == "Pedra"):
        return "Voce venceu!"
    else:
        return "Robo venceu!"
# --- Fim das Funções de Jogo ---


# --- Thread para Captura de Câmara e Processamento MediaPipe ---
def camera_and_hand_processing_thread():
    """
    Função executada numa thread separada para capturar vídeo,
    processar com MediaPipe e atualizar o estado do jogo de Jokenpo.
    """
    global latest_frame, jokenpo_game_state

    cap_obj = None # Objeto da câmara
    
    # Inicializa o MediaPipe Hands e Drawing Utils APENAS UMA VEZ
    mp_hands_sol = mp.solutions.hands
    hands_detector = mp_hands_sol.Hands(max_num_hands=1, min_detection_confidence=0.7)
    mp_draw = mp.solutions.drawing_utils

    print("Iniciando thread de câmara e processamento de mão...")

    # Variáveis de controlo de jogo para a thread (temporizadores e flags)
    tempo_espera_countdown = 3 # Segundos para a contagem regressiva da jogada
    tempo_exibicao_resultado = 5 # Segundos para exibir o resultado final

    timer_control_start = None 
    
    while True: # LOOP PRINCIPAL DA THREAD DA CÂMERA
        # Tenta abrir a câmara se não estiver aberta
        if cap_obj is None or not cap_obj.isOpened():
            print("Tentando abrir a câmara (cv2.VideoCapture(0))...")
            cap_obj = cv2.VideoCapture(0)
            if not cap_obj.isOpened():
                print("Erro: Não foi possível abrir a câmara. Verifique as permissões. Tentando novamente em 2 segundos...")
                jokenpo_game_state["camera_is_active"] = False
                time.sleep(2)
                continue
            else:
                cap_obj.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap_obj.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                print("Câmara aberta com sucesso.")
                jokenpo_game_state["camera_is_active"] = True

        success, img = cap_obj.read()
        if not success or img is None:
            print("Erro: Não foi possível capturar a imagem da câmara ou o frame está vazio! Reabrindo...")
            if cap_obj: cap_obj.release()
            cap_obj = None # Força a reinicialização
            jokenpo_game_state["camera_is_active"] = False
            time.sleep(0.5) # PAUSA IMPORTANTE AQUI para evitar loop rápido em caso de erro
            continue

        img = cv2.flip(img, 1) # Espelha a imagem para visualização

        frameRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Reseta o estado de deteção da mão para o frame atual
        jokenpo_game_state["hand_detected"] = False
        pontos = []
        
        # Gesto detectado em tempo real (para feedback ao usuário)
        current_gesture_live_detection = "Nenhum" 

        # INDENTAÇÃO CHAVE: Este 'if' controla se o MediaPipe está ativo (ativado/desativado pelos botões)
        if jokenpo_game_state["mediapipe_processing_active"]:
            results = hands_detector.process(frameRGB)
            handPoints = results.multi_hand_landmarks

            if handPoints: # Se mãos foram detectadas pelo MediaPipe
                jokenpo_game_state["hand_detected"] = True
                for points in handPoints:
                    mp_draw.draw_landmarks(img, points, mp_hands_sol.HAND_CONNECTIONS)
                    for id, lm in enumerate(points.landmark):
                        pontos.append((int(lm.x * img.shape[1]), int(lm.y * img.shape[0])))
                
                if pontos: # Se pontos de referência foram extraídos (mão válida)
                    current_gesture_live_detection = detectar_gesto(pontos)
                else: # Mão detectada, mas pontos insuficientes ou inválidos para formar um gesto
                    current_gesture_live_detection = "Indefinido" 
            # Se handPoints é None (nenhuma mão detectada), jokenpo_game_state["hand_detected"] permanecerá False,
            # e current_gesture_live_detection permanecerá "Nenhum" (seu valor inicial por frame).

            # Atualiza o estado global com o gesto detectado em tempo real (para o frontend)
            jokenpo_game_state["current_gesture_detected"] = current_gesture_live_detection

            # --- Lógica de Fases do Jogo ---
            # Esta lógica avança independentemente da deteção de mão contínua.
            if jokenpo_game_state["game_phase"] == "counting_down":
                if timer_control_start is None: # Inicia o timer da contagem regressiva
                    timer_control_start = time.time()
                    jokenpo_game_state["result_message"] = "Contando..."
                    jokenpo_game_state["player_choice"] = "Nenhum" # Reseta jogadas para nova rodada
                    jokenpo_game_state["ai_choice"] = "Nenhum"
                    print(f"DEBUG: Contagem regressiva iniciada.")

                time_elapsed = time.time() - timer_control_start
                segundos_restantes = int(tempo_espera_countdown - time_elapsed) + 1

                if segundos_restantes > 0:
                    jokenpo_game_state["countdown_message"] = f"Jogue em... {segundos_restantes}"
                else:
                    # Timer de contagem regressiva zerou: Fim da jogada do jogador
                    jokenpo_game_state["countdown_message"] = "Jogada!"
                    jokenpo_game_state["game_phase"] = "round_finished"
                    print(f"DEBUG: Timer de jogada zerou. Fase: round_finished.")
                    
                    # A jogada do jogador é o último gesto detectado quando o timer zera.
                    # Se não houver mão na câmera, será "Nenhum" ou "Indefinido".
                    jokenpo_game_state["player_choice"] = current_gesture_live_detection 
                    
                    ai_play = escolher_jogada_robo()
                    jokenpo_game_state["ai_choice"] = ai_play
                    
                    result_msg = resultado_jogo(jokenpo_game_state["player_choice"], ai_play)
                    jokenpo_game_state["result_message"] = result_msg
                    jokenpo_game_state["rounds_played"] += 1

                    if "Voce venceu!" in result_msg:
                        jokenpo_game_state["player_score"] += 1
                    elif "Robo venceu!" in result_msg:
                        jokenpo_game_state["ai_score"] += 1
                    elif "Empate!" in result_msg:
                        jokenpo_game_state["ties"] += 1
                    
                    print(f"DEBUG: Jogador: {jokenpo_game_state['player_choice']}, IA: {jokenpo_game_state['ai_choice']}, Resultado: {result_msg}")
                    print(f"DEBUG: Placar - Jogador: {jokenpo_game_state['player_score']}, IA: {jokenpo_game_state['ai_score']}, Empates: {jokenpo_game_state['ties']}")
                    
                    timer_control_start = time.time() # Reinicia timer para contagem do tempo de exibição do resultado
            
            elif jokenpo_game_state["game_phase"] == "round_finished":
                # Mantém o resultado por um tempo (tempo_exibicao_resultado)
                if timer_control_start is not None and (time.time() - timer_control_start) > tempo_exibicao_resultado:
                    # Tempo de exibição esgotado, reseta para nova rodada
                    jokenpo_game_state["game_phase"] = "waiting_start"
                    jokenpo_game_state["countdown_message"] = ""
                    jokenpo_game_state["result_message"] = "Aguardando..."
                    jokenpo_game_state["player_choice"] = "Nenhum" # Limpa jogadas exibidas
                    jokenpo_game_state["ai_choice"] = "Nenhum"
                    timer_control_start = None # Reseta o timer
                    print(f"DEBUG: Rodada finalizada, voltando para waiting_start.")
            
            elif jokenpo_game_state["game_phase"] == "waiting_start":
                # Nenhuma ação de jogo ativa, apenas esperando o botão "Jogar Rodada"
                jokenpo_game_state["result_message"] = "Pressione 'Jogar Rodada' para começar!"
                jokenpo_game_state["countdown_message"] = ""
                jokenpo_game_state["player_choice"] = "Nenhum"
                jokenpo_game_state["ai_choice"] = "Nenhum"
                timer_control_start = None # Garante que o timer esteja limpo
        
        # INDENTAÇÃO CHAVE: Este 'else' corresponde ao 'if jokenpo_game_state["mediapipe_processing_active"]:'
        # Ele só é executado se o processamento MediaPipe NÃO estiver ativo (usuário clicou em 'Parar Processamento')
        else: 
            jokenpo_game_state["hand_detected"] = False
            jokenpo_game_state["current_gesture_detected"] = "Nenhum"
            jokenpo_game_state["countdown_message"] = ""
            jokenpo_game_state["game_phase"] = "waiting_start" # Volta para o estado inicial
            jokenpo_game_state["result_message"] = "Processamento Inativo. Ative para jogar."
            jokenpo_game_state["player_choice"] = "Nenhum"
            jokenpo_game_state["ai_choice"] = "Nenhum"
            timer_control_start = None # Garante que o timer seja resetado se o processamento for parado


        # Converte o frame OpenCV para o formato JPEG para transmissão HTTP.
        ret, buffer = cv2.imencode('.jpg', img)
        if not ret:
            print("Erro: Falha ao codificar o frame para JPEG!")
            continue

        frame_bytes = buffer.tobytes()
        with frame_lock:
            latest_frame = frame_bytes

        time.sleep(0.01) # Pequena pausa para evitar consumo excessivo da CPU

    if cap_obj:
        cap_obj.release()
    print("Thread de câmara e processamento de mão finalizada.")

# Inicia a thread de captura e processamento da câmara quando o Flask inicia.
camera_thread = threading.Thread(target=camera_and_hand_processing_thread)
camera_thread.daemon = True
camera_thread.start()

# --- Rotas do Flask ---

@app.route('/')
def index():
    """Renderiza a página principal."""
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    """
    Gera o stream de vídeo da câmara para o frontend.
    Envia frames JPEG como um stream multipart/x-mixed-replace.
    """
    def generate_frames():
        while True:
            with frame_lock:
                if latest_frame is not None:
                    # Adicionado \r\n\r\n após o Content-Type para garantir a conformidade MIME
                    # e um \r\n extra antes do delimitador --frame
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + latest_frame + b'\r\n')
            time.sleep(0.03)

    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/jokenpo_game_status')
def jokenpo_status():
    """Endpoint para retornar o estado atual do jogo de Jokenpo como JSON."""
    global jokenpo_game_state
    return jsonify(jokenpo_game_state.copy())

@app.route('/play_jokenpo')
def play_jokenpo():
    """
    Endpoint para iniciar uma rodada de Jokenpo.
    Define a fase do jogo para "counting_down" se não houver uma rodada em andamento.
    """
    global jokenpo_game_state
    print(f"DEBUG: /play_jokenpo chamado. Fase atual: {jokenpo_game_state['game_phase']}, Processamento ativo: {jokenpo_game_state['mediapipe_processing_active']}")
    if jokenpo_game_state["mediapipe_processing_active"] and jokenpo_game_state["game_phase"] == "waiting_start":
        jokenpo_game_state["game_phase"] = "counting_down"
        # O timer_control_start é iniciado dentro da thread da câmara na próxima iteração
        jokenpo_game_state["result_message"] = "Contagem iniciada..."
        jokenpo_game_state["player_choice"] = "Nenhum"
        jokenpo_game_state["ai_choice"] = "Nenhum"
        jokenpo_game_state["countdown_message"] = "" # Limpa qualquer mensagem antiga
        print(f"DEBUG: Rodada iniciada. Nova fase: {jokenpo_game_state['game_phase']}")
        return jsonify({"status": "success", "message": "Rodada de Jokenpo iniciada."})
    else:
        status_msg = "Processamento da mão não ativo ou rodada já em andamento."
        if not jokenpo_game_state["mediapipe_processing_active"]:
            status_msg = "Por favor, ative o processamento da mão antes de jogar."
        elif jokenpo_game_state["game_phase"] != "waiting_start":
            status_msg = "Uma rodada já está em andamento. Aguarde ou reinicie."
        print(f"DEBUG: Erro ao iniciar rodada: {status_msg}")
        return jsonify({"status": "error", "message": status_msg})

@app.route('/reset_jokenpo')
def reset_jokenpo():
    """Endpoint para resetar o placar do Jokenpo."""
    global jokenpo_game_state
    jokenpo_game_state["player_score"] = 0
    jokenpo_game_state["ai_score"] = 0
    jokenpo_game_state["ties"] = 0 # Reinicia empates
    jokenpo_game_state["rounds_played"] = 0
    jokenpo_game_state["player_choice"] = "Nenhum"
    jokenpo_game_state["ai_choice"] = "Nenhum"
    jokenpo_game_state["result_message"] = "Aguardando..."
    jokenpo_game_state["current_gesture_detected"] = "Nenhum"
    jokenpo_game_state["countdown_message"] = ""
    jokenpo_game_state["game_phase"] = "waiting_start"
    print(f"DEBUG: Placar resetado.")
    return jsonify({"status": "success", "message": "Placar do Jokenpo resetado."})


@app.route('/control_processing/<action>')
def control_processing(action):
    """
    Endpoint para controlar se o processamento MediaPipe está ativo ou não.
    """
    global jokenpo_game_state
    if action == "start":
        jokenpo_game_state["mediapipe_processing_active"] = True
        jokenpo_game_state["game_phase"] = "waiting_start" # Garante fase inicial
        jokenpo_game_state["countdown_message"] = ""
        jokenpo_game_state["result_message"] = "Aguardando..."
        jokenpo_game_state["player_choice"] = "Nenhum"
        jokenpo_game_state["ai_choice"] = "Nenhum"
        print(f"DEBUG: Processamento iniciado. Fase: {jokenpo_game_state['game_phase']}")
        return jsonify({"status": "started", "message": "Processamento da mão iniciado."})
    elif action == "stop":
        jokenpo_game_state["mediapipe_processing_active"] = False
        jokenpo_game_state["hand_detected"] = False
        jokenpo_game_state["current_gesture_detected"] = "Nenhum"
        jokenpo_game_state["countdown_message"] = ""
        jokenpo_game_state["game_phase"] = "waiting_start" # Volta para o estado inicial
        jokenpo_game_state["result_message"] = "Aguardando..."
        jokenpo_game_state["player_choice"] = "Nenhum"
        jokenpo_game_state["ai_choice"] = "Nenhum"
        print(f"DEBUG: Processamento parado. Fase: {jokenpo_game_state['game_phase']}")
        return jsonify({"status": "stopped", "message": "Processamento da mão parado."})
    return jsonify({"status": "invalid_action", "message": "Ação inválida."})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)