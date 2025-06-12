import cv2
import mediapipe as mp
import random
import time

cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

def detectar_gesto(pontos):
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
        return "Você venceu!"
    else:
        return "Robô venceu!"

timer_start = None
tempo_espera = 3
contagem = ""
jogada_robo = None
resultado = "Aguardando..."
fase_finalizada = False

while True:
    success, img = cap.read()
    if not success or img is None:
        print("Erro na captura da câmera")
        break

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)
    h, w, _ = img.shape
    pontos = []

    gesto_jogador = "Nenhum"

    if results.multi_hand_landmarks:
        for handLms in results.multi_hand_landmarks:
            mp_draw.draw_landmarks(img, handLms, mp_hands.HAND_CONNECTIONS)
            for id, lm in enumerate(handLms.landmark):
                cx, cy = int(lm.x * w), int(lm.y * h)
                pontos.append((cx, cy))

        if pontos:
            gesto_jogador = detectar_gesto(pontos)

            # Inicia timer se gesto for válido e ainda não começou
            if gesto_jogador != "Indefinido" and timer_start is None and not fase_finalizada:
                timer_start = time.time()
                jogada_robo = None
                resultado = "Contando..."

            # Se o timer estiver rodando
            if timer_start is not None and not fase_finalizada:
                tempo_passado = time.time() - timer_start
                segundos_restantes = int(tempo_espera - tempo_passado) + 1  # +1 para parecer mais natural

                if segundos_restantes > 0:
                    contagem = f"Jogue em... {segundos_restantes}"
                else:
                    # Timer zerou, robô joga
                    if jogada_robo is None:
                        jogada_robo = escolher_jogada_robo()
                        resultado = resultado_jogo(gesto_jogador, jogada_robo)
                        fase_finalizada = True
                    contagem = "Jogada!"

        else:
            # Sem pontos: resetar tudo
            timer_start = None
            jogada_robo = None
            resultado = "Aguardando..."
            contagem = ""
            fase_finalizada = False
    else:
        # Sem mão: resetar tudo
        timer_start = None
        jogada_robo = None
        resultado = "Aguardando..."
        contagem = ""
        fase_finalizada = False

    # Exibe textos na tela
    cv2.putText(img, f'Sua jogada: {gesto_jogador}', (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
    cv2.putText(img, f'Jogada robo: {jogada_robo if jogada_robo else "..." }', (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
    cv2.putText(img, f'Resultado: {resultado}', (10, 110), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,0,255), 2)

    # Exibe contagem regressiva grande no centro
    if contagem:
        cv2.putText(img, contagem, (int(w/2)-100, int(h/2)), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 0, 0), 4)

    cv2.imshow("Jokenpô: Pessoa vs Mão Robótica", img)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
