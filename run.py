import socket
import time
from pydub import AudioSegment
from pydub.playback import play
import pyaudio 
import threading
import RPi.GPIO as GPIO
from pynput import keyboard
from pynput.keyboard import Controller
import random

left_ctrl_pressed = False
keyboard_controller = Controller()
server_ip = '0.0.0.0'
server_port = 6000
last_relay_off_time = 0
server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((server_ip, server_port))
server_socket.listen(3)

FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 4096
MAX_PACKET_SIZE = 4096
audio = pyaudio.PyAudio()
reciever_stream = audio.open(format=FORMAT, rate = RATE, output=True, channels=CHANNELS, frames_per_buffer = CHUNK)
sender_stream = audio.open(format=FORMAT, rate = RATE, input=True, channels=CHANNELS, frames_per_buffer=CHUNK)

print(f"Server listening on {server_ip}:{server_port}")


send_audio_event = threading.Event()

client_address = None
client_socket = None
send_audio_flag = False


# #gpio pin setup
GPIO.setmode(GPIO.BCM)
gpio_pin = 17
GPIO.setup(gpio_pin, GPIO.OUT)
GPIO.output(gpio_pin, GPIO.HIGH)

numberOfConnection = 0

timeout_duration = 0.5
last_data_time = time.time()

relay_status = 0


def check_timeout_and_turn_off_relay():
    global last_data_time, relay_status
    while True:
        # Calculate the time elapsed since the last data was received
        time_elapsed = time.time() - last_data_time
        # If no new data received for more than the timeout duration, turn off the relay
        if time_elapsed >= timeout_duration:
            GPIO.output(gpio_pin, GPIO.HIGH) #realy band karti pra   
            relay_status = 0 #matlb relay band hogi 
            print('relay turned off')
        # Sleep for a short interval before checking again
        time.sleep(0.1)


def on_key_release(key):
    global left_ctrl_pressed, relay_status 
    if relay_status == 1 or key == keyboard.Key.ctrl_l:
        left_ctrl_pressed = False
        print('key released')

def on_key_press(key):
    global left_ctrl_pressed, relay_status
    if relay_status==0 or key == keyboard.Key.ctrl_l:
        left_ctrl_pressed = True
        print('key pressed')

def check_keypresses():
    with keyboard.Listener(on_release= on_key_release, on_press = on_key_press) as listener:
        listener.join()

def send_audio():
    global relay_status, client_socket, left_ctrl_pressed, send_audio_flag
    while True:
        if relay_status == 0 and send_audio_flag and client_socket is not None:
            try:
                # Flush any existing audio data
                while sender_stream.get_read_available() >= CHUNK:
                    sender_stream.read(CHUNK)
                
                while send_audio_flag:  # Only send audio if the flag is set and client is connected
                    data = sender_stream.read(CHUNK)
                    if data:  # Check if there's audio data to send
                        client_socket.send(data)
                        print("Sending audio:", len(data), "bytes")
            except Exception as e:
                print(f"Error sending audio: {e}")
        else:
            # Sleep for a short interval to avoid busy-waiting when not sending audio
            time.sleep(0.1)

def recieve_audio():
    while True:
        try:
            global client_address, relay_status, last_data_time, client_socket, last_relay_off_time, send_audio_flag
            if (numberOfConnection < 4):
                client_socket, client_address = server_socket.accept()
                print(f"Accepted connection from {client_address}")
                send_audio_flag = True  # Set the flag to start sending audio after connection
        except Exception as e:
            print(f'connection closed :{e}')

        try:
            while True:
                data = client_socket.recv(1024)
                data = data.strip()
                if len(data) == 4:
                    print("\nrelay on", type(data))
                    if time.time() - last_relay_off_time >= timeout_duration:
                        relay_status = False
                        GPIO.output(gpio_pin, GPIO.LOW)
                        # Set the event to pause sending audio
                        send_audio_event.clear()
                if len(data) == 3:
                    print("\nrelay off", type(data))
                    relay_status = True
                    GPIO.output(gpio_pin, GPIO.HIGH)
                    # Update the last relay off time
                    last_relay_off_time = time.time()
                    # Set the event to resume sending audio
                    send_audio_event.set()
                if not data:
                    break

                if relay_status == GPIO.LOW:
                    reciever_stream.write(data)
                    last_data_time = time.time()

        except Exception as e:
            GPIO.cleanup()
            client_socket.close()
            print(f"Error: {e}")

        finally:
            GPIO.cleanup()
            client_socket.close()
            server_socket.close()
            print("Connection closed")

recieving_thread = threading.Thread(target=recieve_audio)
timeout_thread = threading.Thread(target=check_timeout_and_turn_off_relay)
check_thread = threading.Thread(target=check_keypresses)
sender_audio_thread = threading.Thread(target=send_audio)

recieving_thread.start()
timeout_thread.start()
check_thread.start()
sender_audio_thread.start()
