import time
import json
import os
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk import WebClient
from flask import Flask, request, jsonify
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv
load_dotenv()

# Zona horaria de Bogotá
BOGOTA_TZ = pytz.timezone("America/Bogota")

# Configurar horario de respuesta (entre las 5 PM y las 8 AM)
HORA_INICIO = 17  # 5 PM
HORA_FIN = 8      # 8 AM

USER_TOKEN = os.environ["USER_TOKEN"]
USER_ID = os.environ["USER_ID"]
SIGNING_SECRET = os.environ["SIGNING_SECRET"]

# Inicializar cliente de Slack con tu token de usuario
client = WebClient(token=USER_TOKEN)

# Archivo para almacenar usuarios a los que ya se ha respondido
RESPUESTAS_ARCHIVO = "usuarios_respondidos.json"

# Modo de prueba y usuario de prueba
MODO_PRUEBA = True
USUARIO_PRUEBA = "UUP6R71HB"  # ID del usuario de prueba 

# Timestamp de inicio del bot (solo responderá a mensajes posteriores a este tiempo)
INICIO_BOT = datetime.now(BOGOTA_TZ).timestamp()

# Cargar usuarios respondidos desde archivo
def cargar_usuarios_respondidos():
    if os.path.exists(RESPUESTAS_ARCHIVO):
        with open(RESPUESTAS_ARCHIVO, 'r') as f:
            try:
                return json.load(f)
            except:
                return {}
    return {}

# Guardar usuarios respondidos en archivo
def guardar_usuarios_respondidos(datos):
    with open(RESPUESTAS_ARCHIVO, 'w') as f:
        json.dump(datos, f)

# Usuarios a los que ya se ha respondido (formato: {"usuario_id": timestamp})
usuarios_respondidos = cargar_usuarios_respondidos()

# Función para verificar si está fuera del horario laboral (de 5 PM a 8 AM)
def fuera_de_horario():
    ahora = datetime.now(BOGOTA_TZ)
    hora_actual = ahora.hour
    
    # Verificar si la hora está entre las 5 PM y las 8 AM
    if hora_actual >= HORA_INICIO or hora_actual < HORA_FIN:
        return True
    return False

# Inicializar bot con Bolt
slack_app = App(token=USER_TOKEN, signing_secret=SIGNING_SECRET)

# Configurar Flask
app = Flask(__name__)
handler = SlackRequestHandler(slack_app)

# Endpoint para eventos de Slack
@app.route("/slack/events", methods=["POST"])
def slack_events():
    data = request.get_json()
    if "challenge" in data:
        return jsonify({"challenge": data["challenge"]})
    return handler.handle(request)

# Revisar periódicamente los mensajes directos
def revisar_mensajes():
    while True:
        try:
            # Obtener la lista de todos los DMs
            response = client.conversations_list(types="im")
            dms = response["channels"]
            
            for dm in dms:
                channel_id = dm["id"]
                dm_user = dm.get("user")  # Usuario con quien se tiene el DM
                
                # En modo prueba, solo revisar mensajes del usuario de prueba
                if MODO_PRUEBA and dm_user != USUARIO_PRUEBA:
                    continue
                
                # Si ya respondimos a este usuario hoy, saltamos
                if dm_user in usuarios_respondidos:
                    continue
                
                # Obtener mensajes recientes del DM (solo posteriores al inicio del bot)
                try:
                    latest = datetime.now(BOGOTA_TZ).timestamp()
                    
                    mensajes = client.conversations_history(
                        channel=channel_id, 
                        limit=5,
                        latest=str(latest),
                        oldest=str(INICIO_BOT)  # Solo mensajes después de iniciar el bot
                    )["messages"]
                    
                    # Filtrar solo mensajes del otro usuario
                    mensajes_usuario = [m for m in mensajes if m.get("user") == dm_user]
                    
                    # Si hay mensajes nuevos y estamos fuera de horario, responder
                    if mensajes_usuario and fuera_de_horario():
                        mensaje_reciente = mensajes_usuario[0]
                        ts = mensaje_reciente.get("ts")
                        
                        # Registrar en consola para debugging
                        msg_time = datetime.fromtimestamp(float(ts), BOGOTA_TZ)
                        print(f"[{datetime.now(BOGOTA_TZ)}] Respondiendo a {dm_user} (mensaje enviado a las {msg_time})")
                        
                        # Enviar mensaje como usuario
                        client.chat_postMessage(
                            channel=channel_id,
                            text="⏰ Estoy fuera de mi horario laboral. Responderé cuando esté disponible.",
                            as_user=True
                        )
                        
                        # Registrar que ya respondimos a este usuario
                        usuarios_respondidos[dm_user] = time.time()
                        guardar_usuarios_respondidos(usuarios_respondidos)
                        print(f"Usuario {dm_user} añadido a la lista de respondidos")
                
                except Exception as e:
                    print(f"Error al procesar DM {channel_id}: {e}")
            
            # Imprimir estado
            print(f"[{datetime.now(BOGOTA_TZ)}] Revisión completada. Usuarios respondidos: {len(usuarios_respondidos)}")
                    
            # Esperar antes de la siguiente revisión
            time.sleep(30)
            
        except Exception as e:
            print(f"Error al revisar mensajes: {e}")
            time.sleep(60)  # Esperar un minuto antes de reintentar

# Iniciar el bot y el proceso de revisión de mensajes
if __name__ == "__main__":
    from threading import Thread
    
    # Informar del inicio y modo
    print(f"Bot iniciado en modo {'PRUEBA' if MODO_PRUEBA else 'NORMAL'}")
    print(f"Responderá mensajes entre las {HORA_INICIO}:00 horas y las {HORA_FIN}:00 horas")
    print(f"Hora de inicio del bot: {datetime.fromtimestamp(INICIO_BOT, BOGOTA_TZ)}")
    if MODO_PRUEBA:
        print(f"Solo responderá al usuario de prueba: {USUARIO_PRUEBA}")
    print(f"Usuarios ya respondidos: {len(usuarios_respondidos)}")
    
    # Iniciar hilo de revisión de mensajes
    Thread(target=revisar_mensajes, daemon=True).start()
    
    # Iniciar servidor Flask en el puerto adecuado
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))  # Usa el puerto de Render
