import cv2
import mediapipe as mp
import random
import time

# Inicialização da Câmera
cap = cv2.VideoCapture(0)
cap.set(3, 640) # Largura
cap.set(4, 480) # Altura

# Inicialização do MediaPipe para Detecção de Mãos
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7)
mp_draw = mp.solutions.drawing_utils

# --- Funções de Jogo ---
def detectar_gesto(pontos):

    if len(pontos) < 21: 
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
    """O robô escolhe aleatoriamente Pedra, Papel ou Tesoura."""
    return random.choice(["Pedra", "Papel", "Tesoura"])

def resultado_jogo(jogador, robo):
    """Determina o resultado do jogo."""
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


# --- Variáveis de Estado do Jogo ---
vitorias_jogador = 0
vitorias_robo = 0
empates = 0
rodadas_jogadas = 0 # Adicionado para contabilizar rodadas totais

timer_start = None
tempo_espera = 3 # Segundos para a contagem regressiva para a jogada
tempo_exibicao_resultado = 5 # NOVO: Segundos para exibir o resultado final
contagem = ""
jogada_robo = None # Armazena a jogada da IA para exibição
resultado = "Aguardando..." # Mensagem de resultado da rodada
fase_finalizada = False # Controla se a rodada atual terminou (para exibir resultado por um tempo)

# Loop Principal do Jogo
while True:
    success, img = cap.read()
    if not success or img is None:
        print("Erro na captura da câmera")
        break

    img = cv2.flip(img, 1) # Espelha a imagem para visualização como um espelho

    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)
    h, w, _ = img.shape
    pontos = []
    
    # Gesto detectado no frame atual
    gesto_jogador_current_frame = "Nenhum" 

    # Se a mão for detectada
    if results.multi_hand_landmarks:
        for handLms in results.multi_hand_landmarks:
            mp_draw.draw_landmarks(img, handLms, mp_hands.HAND_CONNECTIONS)
            for id, lm in enumerate(handLms.landmark):
                cx, cy = int(lm.x * w), int(lm.y * h)
                pontos.append((cx, cy))
        
        # Se os pontos foram extraídos com sucesso, detecta o gesto
        if pontos:
            gesto_jogador_current_frame = detectar_gesto(pontos)
            
            # --- Lógica do Timer e Fases do Jogo ---
            if not fase_finalizada: # Se a rodada não terminou e estamos na fase de contagem
                if gesto_jogador_current_frame != "Indefinido" and timer_start is None:
                    # Inicia o timer se um gesto válido for detectado pela primeira vez
                    timer_start = time.time()
                    jogada_robo = None # Reseta a jogada da IA
                    resultado = "Contando..."
                    print(f"[DEBUG] Timer iniciado. Gesto atual: {gesto_jogador_current_frame}")

                if timer_start is not None:
                    tempo_passado = time.time() - timer_start
                    segundos_restantes = int(tempo_espera - tempo_passado) + 1 # +1 para contagem regressiva natural

                    if segundos_restantes > 0:
                        contagem = f"Jogue em... {segundos_restantes}"
                        # print(f"[DEBUG] Contagem: {contagem}")
                    else:
                        # Timer zerou, é hora de jogar!
                        if jogada_robo is None: # Garante que a IA jogue apenas uma vez por rodada
                            jogada_robo = escolher_jogada_robo()
                            resultado = resultado_jogo(gesto_jogador_current_frame, jogada_robo)
                            
                            rodadas_jogadas += 1 # Incrementa rodada
                            if "Voce venceu!" in resultado:
                                vitorias_jogador += 1
                            elif "Robo venceu!" in resultado:
                                vitorias_robo += 1
                            else: # Empate
                                empates += 1
                            
                            fase_finalizada = True # Marca a fase como finalizada
                            contagem = "Jogada!"
                            print(f"[DEBUG] RODADA ENCERRADA. Jogador: {gesto_jogador_current_frame}, Robô: {jogada_robo}, Resultado: {resultado}")
                            print(f"[DEBUG] Placar: J:{vitorias_jogador} | R:{vitorias_robo} | E:{empates} | Rodadas:{rodadas_jogadas}")
                            
                            timer_start = time.time() # Reinicia timer para contagem do tempo de exibição do resultado
                            
            else: # Fase finalizada, exibe o resultado por um tempo
                if time.time() - timer_start > tempo_exibicao_resultado: # NOVO: Exibe o resultado pelo tempo definido
                    # Reseta para uma nova rodada
                    timer_start = None
                    jogada_robo = None
                    resultado = "Aguardando..."
                    contagem = ""
                    fase_finalizada = False
                    print(f"[DEBUG] Nova rodada pronta.")
    
    else: # Nenhuma mão detectada ou pontos insuficientes
        # Reseta o estado do jogo se a mão sumir ou não for detectada
        timer_start = None
        jogada_robo = None
        resultado = "Aguardando..."
        contagem = ""
        fase_finalizada = False
        gesto_jogador_current_frame = "Nenhum" # Garante que o gesto seja "Nenhum" se não houver mão
        # print("[DEBUG] Nenhuma mão detectada. Jogo resetado para aguardar.")


    # --- Exibição de Texto na Tela do OpenCV ---
    # Coordenadas X e Y para os textos. Y aumenta para baixo.
    # Vamos centralizar os elementos no fundo da tela da câmera.

    # Altura inicial para o placar e mensagens (ajustado para mais centralizado e visível)
    text_y_start = h - 130 # Inicia 130 pixels acima do final da tela para ter espaço

    # Placar (Amarelo)
    cv2.putText(img, 
                f'J:{vitorias_jogador} | IA:{vitorias_robo} | E:{empates}', 
                (int(w/2) - 130, text_y_start), # Centraliza X, Y fixo
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2) # Amarelo (BGR)

    # Mensagem de Contagem Regressiva / Jogada! (Azul forte)
    if contagem:
        # Calcular posição X para centralizar dinamicamente
        (text_width, text_height) = cv2.getTextSize(contagem, cv2.FONT_HERSHEY_SIMPLEX, 1.2, 3)[0]
        text_x = int((w - text_width) / 2)
        cv2.putText(img, contagem, 
                    (text_x, text_y_start + 40), # Abaixo do placar, centralizado
                    cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 0, 0), 3) # Azul (BGR)

    # Mensagem de Resultado (Vitória/Derrota/Empate) (Cores dinâmicas)
    # Calcular posição X para centralizar dinamicamente
    (result_width, result_height) = cv2.getTextSize(resultado, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
    result_x = int((w - result_width) / 2)

    cor_resultado = (150, 0, 255) # Púrpura padrão (BGR)
    if "Voce venceu!" in resultado:
        cor_resultado = (0, 255, 0) # Verde (BGR)
    elif "Robo venceu!" in resultado:
        cor_resultado = (0, 0, 255) # Vermelho (BGR)
    elif "Empate!" in resultado:
        cor_resultado = (255, 255, 0) # Ciano (BGR)

    cv2.putText(img, resultado, 
                (result_x, text_y_start + 80), # Abaixo da contagem, centralizado
                cv2.FONT_HERSHEY_SIMPLEX, 1, cor_resultado, 2)
    
    # Jogada do Jogador (Branco, canto superior esquerdo)
    cv2.putText(img, f'Sua jogada: {gesto_jogador_current_frame}', 
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2) # Branco (BGR)

    # Jogada do Robô (Branco, canto superior esquerdo)
    cv2.putText(img, f'Jogada Robo: {jogada_robo if jogada_robo else "..."}', 
                (10, 70), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255,255,255), 2) # Branco (BGR)


    cv2.imshow("Jokenpô: Pessoa vs Robo", img)

    # Tecla 'q' para sair
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Libera a câmera e fecha todas as janelas do OpenCV
cap.release()
cv2.destroyAllWindows()