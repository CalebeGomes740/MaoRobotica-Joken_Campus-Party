from flask import Flask, render_template, Response, jsonify
import cv2
import mediapipe as mp
import threading
import time

app = Flask(__name__)

# --- Variáveis Globais para Estado da Aplicação e Stream de Vídeo ---
latest_frame = None  # Armazena o último frame da câmera processado, em formato JPEG.
frame_lock = threading.Lock()  # Um bloqueio de thread para garantir que 'latest_frame' seja acessado de forma segura.

# Variáveis de estado para a simulação da mão robótica.
robot_arm_state = {
    "joint_base": 0,    # Rotação da base (para futuro uso, agora fixo)
    "joint_shoulder": 0, # Articulação do ombro (para futuro uso, agora fixo)
    "joint_elbow": 0,    # Articulação do cotovelo (para futuro uso, agora fixo)
    "finger_thumb": 0,   # 0 degrees = fechado, 45 degrees = aberto (simulação)
    "finger_index": 0,
    "finger_middle": 0,
    "finger_ring": 0,
    "finger_pinky": 0,
    "hand_detected": False, # Indica se uma mão está sendo detectada pelo MediaPipe
    "camera_is_active": False # Indica se a câmera do backend está funcionando
}

# Flag para controlar se o processamento do MediaPipe está ativo (controlado pelo frontend).
mediapipe_processing_active = False

# --- Mock do módulo 'servo_braco3d' e a função 'mao.abrir_fechar' ---
# Como não temos o hardware real, simulamos a função 'abrir_fechar'
# para que ela atualize o nosso 'robot_arm_state' global.
class MockMao:
    def __init__(self, state_dict):
        self.state = state_dict
        # Mapeamento dos pinos (ids) do seu código original para as chaves do nosso estado.
        self.pin_to_finger_map = {
            10: "finger_thumb",
            9: "finger_index",
            8: "finger_middle",
            7: "finger_ring",
            6: "finger_pinky"
        }
        self.angle_closed = 0   # Ângulo para dedo 'fechado' na simulação.
        self.angle_open = 45    # Ângulo para dedo 'aberto' na simulação.

    def abrir_fechar(self, pin, action):
        """
        Simula a abertura/fechamento de um dedo da mão robótica.
        Atualiza o estado global 'robot_arm_state'.
        """
        finger_key = self.pin_to_finger_map.get(pin)
        if finger_key:
            if action == 1: # Abrir
                self.state[finger_key] = self.angle_open
            elif action == 0: # Fechar
                self.state[finger_key] = self.angle_closed
            # print(f"MockMao: {finger_key} set to {self.state[finger_key]}") # Descomente para depuração

# Cria uma instância do nosso mock de 'mao'
mao = MockMao(robot_arm_state)

# --- Thread para Captura de Câmera e Processamento MediaPipe ---
def camera_and_hand_processing_thread():
    """
    Função executada em uma thread separada para capturar vídeo,
    processar com MediaPipe e atualizar o estado da mão robótica.
    """
    global latest_frame, mediapipe_processing_active, robot_arm_state

    cap_obj = None # Usar um nome diferente para evitar conflito com a global 'cap' se houver
    
    # Inicializa o MediaPipe Hands e Drawing Utils APENAS UMA VEZ
    hands = mp.solutions.hands
    Hands = hands.Hands(max_num_hands=1, min_detection_confidence=0.7, min_tracking_confidence=0.5)
    mpDwaw = mp.solutions.drawing_utils

    print("Iniciando thread de câmera e processamento de mão...")

    while True:
        # Se a câmera não estiver aberta, tenta abri-la
        if cap_obj is None or not cap_obj.isOpened():
            print("Tentando abrir a câmera (cv2.VideoCapture(0))...")
            # Usando cv2.CAP_DSHOW opcionalmente se o backend estiver no Windows e houver problemas
            # cap_obj = cv2.VideoCapture(0, cv2.CAP_DSHOW)
            cap_obj = cv2.VideoCapture(0) # 0 para a webcam padrão
            if not cap_obj.isOpened():
                print("Erro: Não foi possível abrir a câmera. Verifique se ela está conectada, não está em uso por outro aplicativo e se as permissões estão corretas. Tentando novamente em 2 segundos...")
                robot_arm_state["camera_is_active"] = False
                time.sleep(2) # Espera antes de tentar novamente
                continue
            else:
                # Configura a resolução da câmera como no seu código original
                cap_obj.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap_obj.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                print("Câmera aberta com sucesso.")
                robot_arm_state["camera_is_active"] = True

        success, img = cap_obj.read() # Usa cap_obj aqui
        if not success or img is None:
            print("Erro: Não foi possível capturar a imagem da câmera ou o frame está vazio! Liberando e reabrindo câmera...")
            if cap_obj:
                cap_obj.release()
            cap_obj = None # Define como None para forçar a reinicialização na próxima iteração
            robot_arm_state["camera_is_active"] = False
            time.sleep(0.5) # Pequena pausa antes da próxima tentativa
            continue

        # Inverte a imagem horizontalmente para uma visualização espelhada (como um espelho)
        img = cv2.flip(img, 1)

        frameRGB = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Reinicia o estado de detecção de mão antes de cada frame de processamento
        robot_arm_state["hand_detected"] = False
        pontos = []

        if mediapipe_processing_active:
            # Processa o frame com o MediaPipe
            results = Hands.process(frameRGB)
            handPoints = results.multi_hand_landmarks

            h, w, _ = img.shape

            if handPoints:
                robot_arm_state["hand_detected"] = True
                for points in handPoints:
                    # Desenha os landmarks da mão na imagem original
                    mpDwaw.draw_landmarks(img, points, hands.HAND_CONNECTIONS)

                    # Extrai as coordenadas dos pontos da mão
                    for id, cord in enumerate(points.landmark):
                        cx, cy = int(cord.x * w), int(cord.y * h)
                        cv2.circle(img, (cx, cy), 4, (255, 0, 0), -1) # Desenha círculos nos pontos
                        pontos.append((cx, cy))

                if pontos:
                    # Calcula as distâncias entre pontos específicos para simular o movimento dos dedos.
                    distPolegar = abs(pontos[17][0] - pontos[4][0]) # Distância X entre base do mínimo e ponta do polegar
                    distIndicador = pontos[5][1] - pontos[8][1]     # Distância Y entre base do indicador e ponta
                    distMedio = pontos[9][1] - pontos[12][1]       # Distância Y entre base do médio e ponta
                    distAnelar = pontos[13][1] - pontos[16][1]     # Distância Y entre base do anelar e ponta
                    distMinimo = pontos[17][1] - pontos[20][1]     # Distância Y entre base do mínimo e ponta

                    # Traduz as distâncias para ações de 'abrir' (1) ou 'fechar' (0) e atualiza o mock de 'mao'.
                    if distPolegar < 80:
                        mao.abrir_fechar(10, 0)  # Polegar fechado
                    else:
                        mao.abrir_fechar(10, 1)  # Polegar aberto

                    if distIndicador >= 1:
                        mao.abrir_fechar(9, 1)   # Indicador aberto
                    else:
                        mao.abrir_fechar(9, 0)   # Indicador fechado

                    if distMedio >= 1:
                        mao.abrir_fechar(8, 1)   # Médio aberto
                    else:
                        mao.abrir_fechar(8, 0)   # Médio fechado

                    if distAnelar >= 1:
                        mao.abrir_fechar(7, 1)   # Anelar aberto
                    else:
                        mao.abrir_fechar(7, 0)   # Anelar fechado

                    if distMinimo >= 1:
                        mao.abrir_fechar(6, 1)   # Mínimo aberto
                    else:
                        mao.abrir_fechar(6, 0)   # Mínimo fechado
                else:
                    # Se não houver pontos válidos, feche os dedos (dentro do processamento ativo)
                    mao.abrir_fechar(10, 0)
                    mao.abrir_fechar(9, 0)
                    mao.abrir_fechar(8, 0)
                    mao.abrir_fechar(7, 0)
                    mao.abrir_fechar(6, 0)
                    robot_arm_state["hand_detected"] = False

            else: # Nenhuma mão foi detectada (handPoints é None)
                mao.abrir_fechar(10, 0)
                mao.abrir_fechar(9, 0)
                mao.abrir_fechar(8, 0)
                mao.abrir_fechar(7, 0)
                mao.abrir_fechar(6, 0)
                robot_arm_state["hand_detected"] = False

        else: # mediapipe_processing_active é False
            # Se o processamento não estiver ativo, resetamos o estado dos dedos e a flag de mão detectada.
            mao.abrir_fechar(10, 0)
            mao.abrir_fechar(9, 0)
            mao.abrir_fechar(8, 0)
            mao.abrir_fechar(7, 0)
            mao.abrir_fechar(6, 0)
            robot_arm_state["hand_detected"] = False

        # Converte o frame OpenCV para o formato JPEG para transmissão HTTP.
        ret, buffer = cv2.imencode('.jpg', img)
        if not ret:
            print("Erro: Falha ao codificar o frame para JPEG!")
            continue

        frame_bytes = buffer.tobytes()
        with frame_lock:
            latest_frame = frame_bytes

        time.sleep(0.01) # Pequena pausa para evitar consumo excessivo da CPU

    if cap_obj: # Garante que 'cap_obj' existe antes de liberar
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

@app.route('/robot_arm_status')
def robot_arm_status():
    """Endpoint para retornar o estado atual da simulação da mão robótica como JSON."""
    global robot_arm_state, mediapipe_processing_active
    # Adiciona a flag de processamento ao estado para o frontend
    state_copy = robot_arm_state.copy()
    state_copy["mediapipe_processing_active"] = mediapipe_processing_active
    return jsonify(state_copy)

@app.route('/control_processing/<action>')
def control_processing(action):
    """
    Endpoint para controlar se o processamento MediaPipe está ativo ou não.
    """
    global mediapipe_processing_active
    if action == "start":
        mediapipe_processing_active = True
        return jsonify({"status": "started", "message": "Processamento da mão robótica iniciado."})
    elif action == "stop":
        mediapipe_processing_active = False
        # Quando parar, reseta os dedos para fechado
        mao.abrir_fechar(10, 0)
        mao.abrir_fechar(9, 0)
        mao.abrir_fechar(8, 0)
        mao.abrir_fechar(7, 0)
        mao.abrir_fechar(6, 0)
        robot_arm_state["hand_detected"] = False
        return jsonify({"status": "stopped", "message": "Processamento da mão robótica parado."})
    return jsonify({"status": "invalid_action", "message": "Ação inválida."})

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)