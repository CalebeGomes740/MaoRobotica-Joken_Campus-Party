from flask import Flask, render_template, Response, jsonify
import cv2
import mediapipe as mp
import threading
import time
import random

app = Flask(__name__)

# --- Variáveis Globais para Estado da Aplicação e Stream de Vídeo ---
latest_frame = None
frame_lock = threading.Lock()

jokenpo_game_state = {
    "player_score": 0,
    "ai_score": 0,
    "rounds_played": 0,
    "player_choice": "Nenhum", # Pedra, Papel, Tesoura, Nenhum
    "ai_choice": "Nenhum",     # Pedra, Papel, Tesoura, Nenhum
    "result": "Aguardando Jogada", # Ganhou, Perdeu, Empate, Aguardando Jogada
    "hand_detected": False, # Indica se uma mão está sendo detectada pelo MediaPipe
    "camera_is_active": False, # Indica se a câmera do backend está funcionando
    "current_gesture": "Nenhum" # O gesto atual detectado pela câmera (para depuração/feedback)
}

mediapipe_processing_active = False

# --- Lógica do Jogo de Jokenpo ---
def determine_winner(player_choice, ai_choice):
    if player_choice == ai_choice:
        return "Empate"
    elif (player_choice == "Pedra" and ai_choice == "Tesoura") or \
         (player_choice == "Papel" and ai_choice == "Pedra") or \
         (player_choice == "Tesoura" and ai_choice == "Papel"):
        return "Ganhou"
    else:
        return "Perdeu"

def get_jokenpo_choice_from_hand_landmarks(pontos):
    """
    Tenta determinar a jogada de Jokenpo a partir dos pontos da mão.
    Retorna "Pedra", "Papel", "Tesoura" ou "Nenhum" se não for claro.
    """
    # Pontas dos dedos: 8 (Indicador), 12 (Médio), 16 (Anelar), 20 (Mínimo)
    # Bases dos dedos: 5 (Indicador), 9 (Médio), 13 (Anelar), 17 (Mínimo)
    # Ponta do Polegar: 4
    # Base do Polegar: 2
    
    is_thumb_open = abs(pontos[4][0] - pontos[5][0]) > 40
    is_index_open = (pontos[5][1] - pontos[8][1]) > 20
    is_middle_open = (pontos[9][1] - pontos[12][1]) > 20
    is_ring_open = (pontos[13][1] - pontos[16][1]) > 20
    is_pinky_open = (pontos[17][1] - pontos[20][1]) > 20

    open_fingers_count = sum([is_index_open, is_middle_open, is_ring_open, is_pinky_open])

    # Tesoura: Apenas Indicador e Médio abertos (e polegar pode estar de lado)
    if is_index_open and is_middle_open and not is_ring_open and not is_pinky_open:
        if not is_thumb_open or abs(pontos[4][1] - pontos[8][1]) < 30: # Polegar próximo ao indicador
            return "Tesoura"
    
    # Papel: Todos os dedos abertos
    if open_fingers_count >= 4 and is_thumb_open:
        return "Papel"
    
    # Pedra: Todos os dedos fechados
    if open_fingers_count == 0 and not is_thumb_open:
        return "Pedra"
    
    return "Nenhum"

# --- Thread para Captura de Câmera e Processamento MediaPipe ---
def camera_and_hand_processing_thread():
    global latest_frame, mediapipe_processing_active, jokenpo_game_state

    cap = None
    
    hands_mp = mp.solutions.hands
    mp_hands = hands_mp.Hands(max_num_hands=1, min_detection_confidence=0.7, min_tracking_confidence=0.5)
    mp_drawing = mp.solutions.drawing_utils

    print("Iniciando thread de câmera e processamento de mão...")

    while True:
        if cap is None or not cap.isOpened():
            print("Tentando abrir a câmera (cv2.VideoCapture(0))...")
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                print("Erro: Não foi possível abrir a câmera. Verifique se ela está conectada, não está em uso por outro aplicativo e se as permissões estão corretas. Tentando novamente em 2 segundos...")
                jokenpo_game_state["camera_is_active"] = False
                time.sleep(2)
                continue
            else:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                print("Câmera aberta com sucesso.")
                jokenpo_game_state["camera_is_active"] = True

        success, img = cap.read()
        if not success or img is None:
            print("Erro: Não foi possível capturar a imagem da câmera ou o frame está vazio! Liberando e reabrindo câmera...")
            if cap:
                cap.release()
            cap = None
            jokenpo_game_state["camera_is_active"] = False
            time.sleep(0.5)
            continue

        img = cv2.flip(img, 1)

        frameRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        jokenpo_game_state["hand_detected"] = False
        current_pontos = []
        current_gesture = "Nenhum"

        if mediapipe_processing_active:
            results = mp_hands.process(frameRGB)
            handPoints = results.multi_hand_landmarks

            h, w, _ = img.shape

            if handPoints:
                jokenpo_game_state["hand_detected"] = True
                for points in handPoints:
                    mp_drawing.draw_landmarks(img, points, hands_mp.HAND_CONNECTIONS)

                    for id, cord in enumerate(points.landmark):
                        cx, cy = int(cord.x * w), int(cord.y * h)
                        current_pontos.append((cx, cy))
                
                if current_pontos:
                    current_gesture = get_jokenpo_choice_from_hand_landmarks(current_pontos)
            
            jokenpo_game_state["current_gesture"] = current_gesture
        else:
            jokenpo_game_state["hand_detected"] = False
            jokenpo_game_state["current_gesture"] = "Nenhum"


        ret, buffer = cv2.imencode('.jpg', img)
        if not ret:
            print("Erro: Falha ao codificar o frame para JPEG!")
            continue

        frame_bytes = buffer.tobytes()
        with frame_lock:
            latest_frame = frame_bytes

        time.sleep(0.01)

    if cap:
        cap.release()
    print("Thread de câmera e processamento de mão finalizada.")

camera_thread = threading.Thread(target=camera_and_hand_processing_thread)
camera_thread.daemon = True
camera_thread.start()

# --- Rotas do Flask ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
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
    global jokenpo_game_state, mediapipe_processing_active
    state_copy = jokenpo_game_state.copy()
    state_copy["mediapipe_processing_active"] = mediapipe_processing_active
    return jsonify(state_copy)

@app.route('/play_jokenpo/<player_choice>')
def play_jokenpo(player_choice):
    global jokenpo_game_state

    valid_choices = ["Pedra", "Papel", "Tesoura"]
    if player_choice not in valid_choices:
        return jsonify({"status": "error", "message": "Jogada inválida. Escolha Pedra, Papel ou Tesoura."})

    ai_choice = random.choice(valid_choices)
    
    result = determine_winner(player_choice, ai_choice)

    jokenpo_game_state["player_choice"] = player_choice
    jokenpo_game_state["ai_choice"] = ai_choice
    jokenpo_game_state["result"] = result
    jokenpo_game_state["rounds_played"] += 1

    if result == "Ganhou":
        jokenpo_game_state["player_score"] += 1
    elif result == "Perdeu":
        jokenpo_game_state["ai_score"] += 1
    
    return jsonify({
        "status": "success",
        "player_choice": player_choice,
        "ai_choice": ai_choice,
        "result": result,
        "game_state": jokenpo_game_state.copy()
    })

@app.route('/reset_jokenpo')
def reset_jokenpo():
    global jokenpo_game_state
    jokenpo_game_state["player_score"] = 0
    jokenpo_game_state["ai_score"] = 0
    jokenpo_game_state["rounds_played"] = 0
    jokenpo_game_state["player_choice"] = "Nenhum"
    jokenpo_game_state["ai_choice"] = "Nenhum"
    jokenpo_game_state["result"] = "Aguardando Jogada"
    jokenpo_game_state["current_gesture"] = "Nenhum"
    return jsonify({"status": "success", "message": "Placar do Jokenpo resetado."})


@app.route('/control_processing/<action>')
def control_processing(action):
    global mediapipe_processing_active
    if action == "start":
        mediapipe_processing_active = True
        return jsonify({"status": "started", "message": "Processamento da mão iniciado."})
    elif action == "stop":
        mediapipe_processing_active = False
        jokenpo_game_state["hand_detected"] = False
        jokenpo_game_state["current_gesture"] = "Nenhum"
        return jsonify({"status": "stopped", "message": "Processamento da mão parado."})
    return jsonify({"status": "invalid_action", "message": "Ação inválida."})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)