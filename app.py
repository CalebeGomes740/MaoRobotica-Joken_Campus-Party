from flask import Flask, render_template, Response, jsonify
import cv2
import mediapipe as mp
import threading
import time
import random

app = Flask(__name__)

# --- Variáveis Globais para Estado da Aplicação e Stream de Vídeo ---
latest_frame = None  # Stores the last processed camera frame, in JPEG format.
frame_lock = threading.Lock()  # A thread lock to ensure 'latest_frame' is accessed safely.

jokenpo_game_state = {
    "player_score": 0,
    "ai_score": 0,
    "rounds_played": 0,
    "player_choice": "Nenhum",         # Jogada final do jogador nesta rodada
    "ai_choice": "Nenhum",             # Jogada final da IA nesta rodada
    "result_message": "Aguardando...", # Mensagem do resultado da rodada (Você venceu!, Empate!, etc.)
    "current_gesture_detected": "Nenhum", # Gesto detectado em tempo real pelo MediaPipe
    "hand_detected": False,            # Indica se uma mão está a ser detetada
    "camera_is_active": False,         # Indica se a câmara do backend está a funcionar
    "countdown_message": "",           # Mensagem da contagem regressiva ("Jogue em... X")
    "game_phase": "waiting_start",     # Fases: "waiting_start", "counting_down", "round_finished"
    "mediapipe_processing_active": False # Controla se o MediaPipe está ativo
}

# --- Jokenpo Game Logic ---
def determine_winner(player_choice, ai_choice):
    """Determines the winner of a Jokenpo round."""
    if player_choice == ai_choice:
        return "Empate"
    elif (player_choice == "Pedra" and ai_choice == "Tesoura") or \
         (player_choice == "Papel" and ai_choice == "Pedra") or \
         (player_choice == "Tesoura" and ai_choice == "Papel"):
        return "Ganhou"
    else:
        return "Perdeu"

def detectar_gesto(pontos):
    """
    Tenta determinar a jogada de Jokenpo a partir dos pontos da mão.
    Retorna "Pedra", "Papel", "Tesoura" ou "Indefinido".
    """
    # Pontos de interesse para detecção de dedos
    # Pontas dos dedos: 8 (Indicador), 12 (Médio), 16 (Anelar), 20 (Mínimo)
    # Bases dos dedos: 5 (Indicador), 9 (Médio), 13 (Anelar), 17 (Mínimo)
    # Ponta do Polegar: 4
    # Outros pontos para o polegar: 2 (base), 3 (meio)
    
    # Heurística para Polegar Aberto:
    # Verifica a distância X entre a ponta do polegar (4) e o ponto da base do indicador (5)
    # Se for maior que um limiar, sugere que o polegar está esticado para fora.
    is_thumb_open_dist_x = abs(pontos[4][0] - pontos[5][0]) > 40
    # Opcional: verificar se a ponta do polegar está acima do seu próprio nó (3)
    is_thumb_open_y = pontos[4][1] < pontos[3][1]

    # Heurística para Outros Dedos Abertos:
    # A ponta do dedo (ex: 8 para Indicador) deve estar significativamente acima do seu nó de dobra (ex: 6)
    is_index_open = pontos[8][1] < pontos[6][1] 
    is_middle_open = pontos[12][1] < pontos[10][1]
    is_ring_open = pontos[16][1] < pontos[14][1]
    is_pinky_open = pontos[20][1] < pontos[18][1]

    # Contagem de dedos abertos (excluindo polegar, para algumas lógicas)
    open_straight_fingers_count = sum([is_index_open, is_middle_open, is_ring_open, is_pinky_open])

    # Pedra: Todos os dedos (incluindo polegar) estão fechados
    # Se a contagem de dedos abertos é zero E o polegar não parece aberto lateralmente ou para cima
    if open_straight_fingers_count == 0 and not is_thumb_open_dist_x and (not is_thumb_open_y or abs(pontos[4][1] - pontos[2][1]) < 20):
        return "Pedra"
    
    # Papel: Todos os dedos (incluindo polegar) estão abertos/esticados
    if open_straight_fingers_count == 4 and is_thumb_open_dist_x:
        return "Papel"
    
    # Tesoura: Indicador e Médio abertos, outros fechados
    # E o polegar não deve estar esticado para a frente (como em papel)
    if is_index_open and is_middle_open and not is_ring_open and not is_pinky_open and not is_thumb_open_dist_x:
        # Adicionalmente, o polegar deve estar mais próximo da palma ou dobrado
        if abs(pontos[4][0] - pontos[2][0]) < 30 and abs(pontos[4][1] - pontos[2][1]) < 30:
            return "Tesoura"
    
    return "Indefinido" # Gesto não reconhecido

def escolher_jogada_robo():
    """A IA escolhe aleatoriamente uma jogada."""
    return random.choice(["Pedra", "Papel", "Tesoura"])

def resultado_jogo(jogador, robo):
    """Determina o vencedor da rodada."""
    if jogador == "Indefinido":
        return "Mostre Pedra, Papel ou Tesoura claramente!"
    if jogador == robo:
        return "Empate!"
    elif (jogador == "Pedra" and robo == "Tesoura") or \
         (jogador == "Tesoura" and robo == "Papel") or \
         (jogador == "Papel" and robo == "Pedra"):
        return "Você venceu!"
    else:
        return "Robô venceu!"

# --- Thread para Captura de Câmera e Processamento MediaPipe ---
def camera_and_hand_processing_thread():
    """
    Função executada em uma thread separada para capturar vídeo,
    processar com MediaPipe e atualizar o estado do jogo de Jokenpo.
    """
    global latest_frame, jokenpo_game_state

    cap_obj = None # Objeto da câmera
    
    # Inicializa o MediaPipe Hands e Drawing Utils APENAS UMA VEZ
    hands_mp_sol = mp.solutions.hands
    mp_hands = hands_mp_sol.Hands(max_num_hands=1, min_detection_confidence=0.7, min_tracking_confidence=0.5)
    mp_drawing = mp.solutions.drawing_utils

    print("Iniciando thread de câmera e processamento de mão...")

    # Variáveis de controle de jogo dentro da thread (mantendo o estado do jogo na global jokenpo_game_state)
    timer_start_time = None
    TIME_TO_PLAY = 3 # Segundos para a contagem regressiva
    
    while True:
        # Tenta abrir a câmera se não estiver aberta
        if cap_obj is None or not cap_obj.isOpened():
            print("Tentando abrir a câmera (cv2.VideoCapture(0))...")
            # Para Windows, se tiver problemas, tente: cap_obj = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            cap_obj = cv2.VideoCapture(0)
            if not cap_obj.isOpened():
                print("Erro: Não foi possível abrir a câmera. Verifique as permissões. Tentando novamente em 2 segundos...")
                jokenpo_game_state["camera_is_active"] = False
                time.sleep(2)
                continue
            else:
                cap_obj.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap_obj.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                print("Câmera aberta com sucesso.")
                jokenpo_game_state["camera_is_active"] = True

        success, img = cap_obj.read()
        if not success or img is None:
            print("Erro: Não foi possível capturar a imagem da câmera ou o frame está vazio! Reabrindo...")
            if cap_obj: cap_obj.release()
            cap_obj = None # Força a reinicialização
            jokenpo_game_state["camera_is_active"] = False
            time.sleep(0.5) # PAUSA IMPORTANTE AQUI
            continue

        img = cv2.flip(img, 1) # Espelha a imagem para visualização

        frameRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Reseta o estado de detecção da mão e gesto para o frame atual
        jokenpo_game_state["hand_detected"] = False
        jokenpo_game_state["current_gesture_detected"] = "Nenhum"
        pontos = []

        # Somente processa MediaPipe se a flag estiver ativa
        if jokenpo_game_state["mediapipe_processing_active"]:
            results = mp_hands.process(frameRGB)
            handPoints = results.multi_hand_landmarks

            h, w, _ = img.shape

            if handPoints:
                jokenpo_game_state["hand_detected"] = True
                for points in handPoints:
                    mp_drawing.draw_landmarks(img, points, hands_mp_sol.HAND_CONNECTIONS)
                    for id, lm in enumerate(points.landmark):
                        cx, cy = int(lm.x * w), int(lm.y * h)
                        pontos.append((cx, cy))

                if pontos:
                    current_detected_gesture = detectar_gesto(pontos)
                    jokenpo_game_state["current_gesture_detected"] = current_detected_gesture

                    # Lógica do Timer e Jogo
                    if jokenpo_game_state["game_phase"] == "counting_down":
                        if timer_start_time is None: # Inicia o timer na primeira vez que entra na fase
                            timer_start_time = time.time()
                            jokenpo_game_state["result_message"] = "Contando..."
                            jokenpo_game_state["player_choice"] = "Nenhum" # Reseta jogadas para nova rodada
                            jokenpo_game_state["ai_choice"] = "Nenhum"

                        time_elapsed = time.time() - timer_start_time
                        seconds_remaining = int(TIME_TO_PLAY - time_elapsed) + 1

                        if seconds_remaining > 0:
                            jokenpo_game_state["countdown_message"] = f"Jogue em... {seconds_remaining}"
                        else:
                            # Timer esgotado, robô joga
                            jokenpo_game_state["countdown_message"] = "Jogada!"
                            jokenpo_game_state["game_phase"] = "round_finished"
                            
                            # Registra a jogada do jogador no momento da finalização do timer
                            jokenpo_game_state["player_choice"] = current_detected_gesture
                            
                            ai_play = escolher_jogada_robo()
                            jokenpo_game_state["ai_choice"] = ai_play
                            
                            result = resultado_jogo(jokenpo_game_state["player_choice"], ai_play)
                            jokenpo_game_state["result_message"] = result
                            jokenpo_game_state["rounds_played"] += 1

                            # Limpa o timer para que não continue a contar na próxima fase
                            timer_start_time = None
                    elif jokenpo_game_state["game_phase"] == "round_finished":
                        # Mantém o resultado por um tempo antes de voltar para waiting_start
                        if timer_start_time is None: # Inicia um novo timer para exibir o resultado
                             timer_start_time = time.time()
                        if time.time() - timer_start_time > 3: # Exibe resultado por 3 segundos
                            jokenpo_game_state["game_phase"] = "waiting_start"
                            jokenpo_game_state["countdown_message"] = ""
                            jokenpo_game_state["result_message"] = "Aguardando..."
                            jokenpo_game_state["player_choice"] = "Nenhum"
                            jokenpo_game_state["ai_choice"] = "Nenhum"
                            timer_start_time = None # Reseta o timer para a próxima jogada
                else:
                    # Se mão detectada, mas pontos ausentes ou indefinidos
                    jokenpo_game_state["current_gesture_detected"] = "Indefinido"
            else:
                # Nenhuma mão detectada (handPoints é None)
                jokenpo_game_state["current_gesture_detected"] = "Nenhum"
                # Se não há mão, e estamos esperando por uma jogada, ou a rodada acabou,
                # garantir que a fase não seja "counting_down"
                if jokenpo_game_state["game_phase"] == "counting_down":
                    # Se a mão sumiu durante a contagem, cancela a rodada e reseta
                    jokenpo_game_state["game_phase"] = "waiting_start"
                    jokenpo_game_state["countdown_message"] = "Mão não detectada, reinicie a jogada."
                    jokenpo_game_state["result_message"] = "Aguardando..."
                    jokenpo_game_state["player_choice"] = "Nenhum"
                    jokenpo_game_state["ai_choice"] = "Nenhum"
                    timer_start_time = None

        else: # MediaPipe processing is not active
            jokenpo_game_state["hand_detected"] = False
            jokenpo_game_state["current_gesture_detected"] = "Nenhum"
            jokenpo_game_state["countdown_message"] = ""
            jokenpo_game_state["game_phase"] = "waiting_start" # Volta para o estado inicial
            jokenpo_game_state["result_message"] = "Aguardando..."
            jokenpo_game_state["player_choice"] = "Nenhum"
            jokenpo_game_state["ai_choice"] = "Nenhum"
            timer_start_time = None # Garante que o timer seja resetado se o processamento for parado


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
    print("Thread de câmera e processamento de mão finalizada.")

# Inicia a thread de captura e processamento da câmera quando o Flask inicia.
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
    Gera o stream de vídeo da câmera para o frontend.
    Envia frames JPEG como um stream multipart/x-mixed-replace.
    """
    def generate_frames():
        while True:
            with frame_lock:
                if latest_frame is not None:
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
    if jokenpo_game_state["mediapipe_processing_active"] and jokenpo_game_state["game_phase"] == "waiting_start":
        jokenpo_game_state["game_phase"] = "counting_down"
        jokenpo_game_state["result_message"] = "Contagem iniciada..."
        jokenpo_game_state["player_choice"] = "Nenhum"
        jokenpo_game_state["ai_choice"] = "Nenhum"
        jokenpo_game_state["countdown_message"] = "" # Limpa qualquer mensagem antiga
        return jsonify({"status": "success", "message": "Rodada de Jokenpo iniciada."})
    else:
        status_msg = "Processamento da mão não ativo ou rodada já em andamento."
        if not jokenpo_game_state["mediapipe_processing_active"]:
            status_msg = "Por favor, ative o processamento da mão antes de jogar."
        elif jokenpo_game_state["game_phase"] != "waiting_start":
            status_msg = "Uma rodada já está em andamento. Aguarde ou reinicie."
        return jsonify({"status": "error", "message": status_msg})

@app.route('/reset_jokenpo')
def reset_jokenpo():
    """Endpoint para resetar o placar do Jokenpo."""
    global jokenpo_game_state
    jokenpo_game_state["player_score"] = 0
    jokenpo_game_state["ai_score"] = 0
    jokenpo_game_state["rounds_played"] = 0
    jokenpo_game_state["player_choice"] = "Nenhum"
    jokenpo_game_state["ai_choice"] = "Nenhum"
    jokenpo_game_state["result_message"] = "Aguardando..."
    jokenpo_game_state["current_gesture_detected"] = "Nenhum"
    jokenpo_game_state["countdown_message"] = ""
    jokenpo_game_state["game_phase"] = "waiting_start"
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
        return jsonify({"status": "stopped", "message": "Processamento da mão parado."})
    return jsonify({"status": "invalid_action", "message": "Ação inválida."})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)