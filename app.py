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

    print("[CAMERA THREAD] Iniciando thread de câmara e processamento de mão...")

    # Variáveis de controlo de jogo para a thread (temporizadores e flags)
    tempo_espera_countdown = 3 # Segundos para a contagem regressiva da jogada

    timer_control_start = None 
    
    while True: # LOOP PRINCIPAL DA THREAD DA CÂMERA
        # Tenta abrir a câmara se não estiver aberta
        if cap_obj is None or not cap_obj.isOpened():
            print("[CAMERA THREAD] Tentando abrir a câmara (cv2.VideoCapture(0))...")
            try:
                cap_obj = cv2.VideoCapture(0)
                if not cap_obj.isOpened():
                    raise IOError("Não foi possível abrir a câmara. Verifique se está em uso ou as permissões.")
                
                cap_obj.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap_obj.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                print("[CAMERA THREAD] Câmara aberta com sucesso.")
                jokenpo_game_state["camera_is_active"] = True
            except Exception as e:
                print(f"[CAMERA THREAD] Erro ao iniciar a câmara: {e}. Tentando novamente em 2 segundos...")
                jokenpo_game_state["camera_is_active"] = False
                if cap_obj: # Tenta liberar recursos da câmera se algo deu errado após a abertura
                    cap_obj.release()
                cap_obj = None # Garante que será tentada nova inicialização
                time.sleep(2)
                continue # Volta para o início do loop para tentar novamente

        success, img = cap_obj.read()
        if not success or img is None:
            print("[CAMERA THREAD] Erro: Não foi possível capturar a imagem da câmara ou o frame está vazio! Reabrindo...")
            if cap_obj: cap_obj.release() 
            cap_obj = None # Força a reinicialização
            jokenpo_game_state["camera_is_active"] = False
            time.sleep(0.5) 
            continue 

        img = cv2.flip(img, 1) # Espelha a imagem para visualização

        frameRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Reseta o estado de deteção da mão para o frame atual
        jokenpo_game_state["hand_detected"] = False
        pontos = []
        
        # Gesto detectado em tempo real (para feedback ao usuário)
        current_gesture_live_detection = "Nenhum" 

        # Somente processa MediaPipe se a flag estiver ativa
        if jokenpo_game_state["mediapipe_processing_active"]:
            results = hands_detector.process(frameRGB)
            handPoints = results.multi_hand_landmarks

            if handPoints: 
                jokenpo_game_state["hand_detected"] = True
                for points in handPoints:
                    mp_draw.draw_landmarks(img, points, mp_hands_sol.HAND_CONNECTIONS)
                    for id, lm in enumerate(points.landmark):
                        pontos.append((int(lm.x * img.shape[1]), int(lm.y * img.shape[0])))
                
                if pontos: 
                    current_gesture_live_detection = detectar_gesto(pontos)
                else: 
                    current_gesture_live_detection = "Indefinido" 
            
            # Atualiza o estado global com o gesto detectado em tempo real
            jokenpo_game_state["current_gesture_detected"] = current_gesture_live_detection

            # --- Lógica de Fases do Jogo ---
            if jokenpo_game_state["game_phase"] == "counting_down":
                if timer_control_start is None: 
                    timer_control_start = time.time()
                    jokenpo_game_state["result_message"] = "Contando..."
                    jokenpo_game_state["player_choice"] = "Nenhum" 
                    jokenpo_game_state["ai_choice"] = "Nenhum"
                    print(f"[CAMERA THREAD] DEBUG: Contagem regressiva iniciada.")

                time_elapsed = time.time() - timer_control_start
                segundos_restantes = int(tempo_espera_countdown - time_elapsed) + 1

                if segundos_restantes > 0:
                    jokenpo_game_state["countdown_message"] = f"Jogue em... {segundos_restantes}"
                else:
                    # Timer de contagem regressiva zerou: Fim da jogada do jogador
                    jokenpo_game_state["countdown_message"] = "Jogada!"
                    jokenpo_game_state["game_phase"] = "round_finished"
                    print(f"[CAMERA THREAD] DEBUG: Timer de jogada zerou. Fase: round_finished.")
                    
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
                    
                    print(f"[CAMERA THREAD] DEBUG: Jogador: {jokenpo_game_state['player_choice']}, IA: {jokenpo_game_state['ai_choice']}, Resultado: {result_msg}")
                    print(f"[CAMERA THREAD] DEBUG: Placar - J:{jokenpo_game_state['player_score']} | IA:{jokenpo_game_state['ai_score']} | E:{jokenpo_game_state['ties']}")
                    
                    timer_control_start = None 
            
            elif jokenpo_game_state["game_phase"] == "round_finished":
                jokenpo_game_state["countdown_message"] = "" 
            
            elif jokenpo_game_state["game_phase"] == "waiting_start":
                jokenpo_game_state["result_message"] = "Pressione 'Jogar Rodada' para começar!"
                jokenpo_game_state["countdown_message"] = ""
                jokenpo_game_state["player_choice"] = "Nenhum"
                jokenpo_game_state["ai_choice"] = "Nenhum"
                timer_control_start = None 
        
        else: # MediaPipe está ativo, mas NENHUMA mão é detectada (handPoints é None)
            jokenpo_game_state["hand_detected"] = False
            jokenpo_game_state["current_gesture_detected"] = "Nenhum"
            if jokenpo_game_state["game_phase"] == "waiting_start":
                jokenpo_game_state["countdown_message"] = ""
                jokenpo_game_state["result_message"] = "Pressione 'Jogar Rodada' para começar!"
                jokenpo_game_state["player_choice"] = "Nenhum"
                jokenpo_game_state["ai_choice"] = "Nenhum"
                timer_control_start = None
    
    # MediaPipe processing is NOT active (user stopped it com os botões "Parar Processamento")
    else: 
        jokenpo_game_state["hand_detected"] = False
        jokenpo_game_state["current_gesture_detected"] = "Nenhum"
        jokenpo_game_state["countdown_message"] = ""
        jokenpo_game_state["game_phase"] = "waiting_start" 
        jokenpo_game_state["result_message"] = "Processamento Inativo. Ative para jogar."
        jokenpo_game_state["player_choice"] = "Nenhum"
        jokenpo_game_state["ai_choice"] = "Nenhum"
        timer_control_start = None

    # Converte o frame OpenCV para o formato JPEG para transmissão HTTP.
    ret, buffer = cv2.imencode('.jpg', img)
    if not ret:
        print("[CAMERA THREAD] Erro: Falha ao codificar o frame para JPEG! Pode ser um frame vazio ou problema de dados.")
        pass # Apenas passa para a próxima iteração.

    frame_bytes = buffer.tobytes()
    with frame_lock:
        latest_frame = frame_bytes

    time.sleep(0.01) # Pequena pausa para evitar consumo excessivo da CPU

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
    print(f"[FLASK APP] /play_jokenpo chamado. Fase atual: {jokenpo_game_state['game_phase']}, Processamento ativo: {jokenpo_game_state['mediapipe_processing_active']}")
    if jokenpo_game_state["mediapipe_processing_active"] and jokenpo_game_state["game_phase"] == "waiting_start":
        jokenpo_game_state["game_phase"] = "counting_down"
        jokenpo_game_state["result_message"] = "Contagem iniciada..."
        jokenpo_game_state["player_choice"] = "Nenhum"
        jokenpo_game_state["ai_choice"] = "Nenhum"
        jokenpo_game_state["countdown_message"] = "" 
        print(f"[FLASK APP] DEBUG: Rodada iniciada. Nova fase: {jokenpo_game_state['game_phase']}")
        return jsonify({"status": "success", "message": "Rodada de Jokenpo iniciada."})
    else:
        status_msg = "Processamento da mão não ativo ou rodada já em andamento."
        if not jokenpo_game_state["mediapipe_processing_active"]:
            status_msg = "Por favor, ative o processamento da mão antes de jogar."
        elif jokenpo_game_state["game_phase"] != "waiting_start":
            status_msg = "Uma rodada já está em andamento. Aguarde ou reinicie."
        print(f"[FLASK APP] DEBUG: Erro ao iniciar rodada: {status_msg}")
        return jsonify({"status": "error", "message": status_msg})

@app.route('/reset_jokenpo')
def reset_jokenpo():
    """Endpoint para resetar o placar do Jokenpo."""
    global jokenpo_game_state
    jokenpo_game_state["player_score"] = 0
    jokenpo_game_state["ai_score"] = 0
    jokenpo_game_state["ties"] = 0 
    jokenpo_game_state["rounds_played"] = 0
    jokenpo_game_state["player_choice"] = "Nenhum"
    jokenpo_game_state["ai_choice"] = "Nenhum"
    jokenpo_game_state["result_message"] = "Aguardando..."
    jokenpo_game_state["current_gesture_detected"] = "Nenhum"
    jokenpo_game_state["countdown_message"] = ""
    jokenpo_game_state["game_phase"] = "waiting_start" 
    print(f"[FLASK APP] DEBUG: Placar resetado.")
    return jsonify({"status": "success", "message": "Placar do Jokenpo resetado."})

@app.route('/finish_round') 
def finish_round():
    """Endpoint para terminar a rodada atual e voltar para o estado de espera."""
    global jokenpo_game_state
    print(f"[FLASK APP] /finish_round chamado. Fase atual: {jokenpo_game_state['game_phase']}")
    if jokenpo_game_state["game_phase"] == "round_finished":
        jokenpo_game_state["game_phase"] = "waiting_start"
        jokenpo_game_state["countdown_message"] = ""
        jokenpo_game_state["result_message"] = "Pressione 'Jogar Rodada' para começar!"
        jokenpo_game_state["player_choice"] = "Nenhum"
        jokenpo_game_state["ai_choice"] = "Nenhum"
        print(f"[FLASK APP] DEBUG: Rodada finalizada manualmente, voltando para waiting_start.")
        return jsonify({"status": "success", "message": "Rodada terminada. Pronto para a próxima."})
    else:
        status_msg = "Nenhuma rodada para terminar no momento."
        print(f"[FLASK APP] DEBUG: Erro ao terminar rodada: {status_msg}")
        return jsonify({"status": "error", "message": status_msg})


@app.route('/control_processing/<action>')
def control_processing(action):
    """
    Endpoint para controlar se o processamento MediaPipe está ativo ou não.
    """
    global jokenpo_game_state
    print(f"[FLASK APP] /control_processing/{action} chamado.")
    if action == "start":
        jokenpo_game_state["mediapipe_processing_active"] = True
        jokenpo_game_state["game_phase"] = "waiting_start" 
        jokenpo_game_state["countdown_message"] = ""
        jokenpo_game_state["result_message"] = "Pressione 'Jogar Rodada' para começar!" 
        jokenpo_game_state["player_choice"] = "Nenhum"
        jokenpo_game_state["ai_choice"] = "Nenhum"
        print(f"[FLASK APP] DEBUG: Processamento iniciado. Fase: {jokenpo_game_state['game_phase']}")
        return jsonify({"status": "started", "message": "Processamento da mão iniciado."})
    elif action == "stop":
        jokenpo_game_state["mediapipe_processing_active"] = False
        jokenpo_game_state["hand_detected"] = False
        jokenpo_game_state["current_gesture_detected"] = "Nenhum"
        jokenpo_game_state["countdown_message"] = ""
        jokenpo_game_state["game_phase"] = "waiting_start" 
        jokenpo_game_state["result_message"] = "Aguardando..." 
        jokenpo_game_state["player_choice"] = "Nenhum"
        jokenpo_game_state["ai_choice"] = "Nenhum"
        print(f"[FLASK APP] DEBUG: Processamento parado. Fase: {jokenpo_game_state['game_phase']}")
        return jsonify({"status": "stopped", "message": "Processamento da mão parado."})
    return jsonify({"status": "invalid_action", "message": "Ação inválida."})

if __name__ == '__main__':
    print("[FLASK APP] Iniciando servidor Flask...")
    try:
        app.run(debug=False, host='0.0.0.0', port=5000)
    except Exception as e:
        print(f"[FLASK APP] ERRO FATAL ao iniciar o Flask: {e}")
        print("[FLASK APP] Verifique se a porta 5000 está livre ou se há outro problema de rede.")