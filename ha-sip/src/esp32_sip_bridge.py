"""
ESP32 SIP Bridge Module
This module integrates the ESP32 SIP bridge functionality into the ha-sip project.
It creates a bidirectional audio bridge between ESP32 and SIP endpoints.
"""

import asyncio
import aioesphomeapi
from aioesphomeapi.api_pb2 import MediaPlayerCommand
import logging
import aiohttp
from aiohttp import web
import threading
import time
import queue
import pjsua2 as pj
import numpy as np
import scipy.signal
import struct
import os
from typing import Optional

# --- Настройка логирования ---
# Отключаем логи PJSIP
pj_log_level = 0  # 0 = Нет логов, 1 = Ошибки, 2 = Предупреждения, 3 = Информация, 4 = Дебаг

# Создаем свои логгеры для лучшей фильтрации
audio_logger = logging.getLogger('audio')
sip_logger = logging.getLogger('sip')
queue_logger = logging.getLogger('queue')
bridge_logger = logging.getLogger('bridge')

# Настраиваем уровни для разных логгеров
audio_logger.setLevel(logging.INFO)
sip_logger.setLevel(logging.INFO)
queue_logger.setLevel(logging.INFO)
bridge_logger.setLevel(logging.INFO)

# --- Глобальные переменные ---
global_call_state = None
global_sip_to_esp_queue = queue.Queue(maxsize=2000) # Стали 100 может надо тоже протестить на 100
server_runner = None
stop_stream_event = None
global_stream_handler_running = False

# Флаг для отслеживания завершения вызова
call_terminated = False

def log_timing(message):
    """Логирует сообщение с относительным временем от начала работы."""
    if 'BRIDGE_START_TIME' in globals() and BRIDGE_START_TIME is not None:
        elapsed = time.time() - BRIDGE_START_TIME
        bridge_logger.info(f"T+{elapsed:.3f}s - {message}")
    else:
        bridge_logger.info(f"[NO START TIME] - {message}")

# --- Классы SIP Call и AudioMediaPort ---
class SIPAudioMediaPort(pj.AudioMediaPort):
    def __init__(self, esp_to_sip_queue, sip_to_esp_queue, esp_clock_rate=16000):
        pj.AudioMediaPort.__init__(self)
        self.esp_to_sip_queue = esp_to_sip_queue
        self.sip_to_esp_queue = sip_to_esp_queue
        self.esp_clock_rate = esp_clock_rate
        self.sip_clock_rate = 16000  # Устанавливаем 16 кГц как в оригинальном коде
        self.samples_per_20ms_esp = int(self.esp_clock_rate * 0.020)
        self.bytes_per_20ms_esp = self.samples_per_20ms_esp * 2
        self.samples_per_20ms_sip = int(self.sip_clock_rate * 0.020)
        self.bytes_per_20ms_sip = self.samples_per_20ms_sip * 2
        
        # Буфер для накопления данных
        self.buffer = bytearray()
        self.frame_counter = 0
        self.last_log_time = time.time()
        
        audio_logger.info(f"🔧 SIPAudioMediaPort создан: ESP={self.esp_clock_rate}Hz, SIP={self.sip_clock_rate}Hz")

    def onFrameRequested(self, frame):
        """SIP запрашивает аудио данные от ESP32"""
        self.frame_counter += 1
        
        if frame.size == 0:
            return
            
        needed_bytes = self.bytes_per_20ms_sip
        
        # Собираем данные из очереди ESP32 -> SIP
        collected_bytes = bytearray()
        
        # Проверяем буфер
        if len(self.buffer) > 0:
            take_bytes = min(len(self.buffer), needed_bytes)
            collected_bytes.extend(self.buffer[:take_bytes])
            self.buffer = self.buffer[take_bytes:]
        
        # Добираем из очереди, если нужно
        while len(collected_bytes) < needed_bytes:
            try:
                raw_audio_bytes = self.esp_to_sip_queue.get_nowait()
                
                remaining = needed_bytes - len(collected_bytes)
                if len(raw_audio_bytes) <= remaining:
                    collected_bytes.extend(raw_audio_bytes)
                else:
                    collected_bytes.extend(raw_audio_bytes[:remaining])
                    # Сохраняем остаток в буфер
                    self.buffer.extend(raw_audio_bytes[remaining:])
                    
            except queue.Empty:
                # Если очередь пуста, дополняем тишиной
                silence_needed = needed_bytes - len(collected_bytes)
                if silence_needed > 0:
                    collected_bytes.extend(b'\x00' * silence_needed)
                break
        
        # Если собрали больше чем нужно (маловероятно), обрезаем
        if len(collected_bytes) > needed_bytes:
            collected_bytes = collected_bytes[:needed_bytes]
        
        # Обработка звука для предотвращения клиппинга
        try:
            if len(collected_bytes) >= 2:
                audio_data = np.frombuffer(collected_bytes, dtype=np.int16)
                max_val = np.max(np.abs(audio_data))
                if max_val > 28000:  # Более безопасный порог
                    gain = 28000.0 / max_val
                    audio_data = (audio_data * gain).astype(np.int16)
                    collected_bytes = audio_data.tobytes()
                    
                    # Логируем только раз в 100 фреймов
                    if self.frame_counter % 100 == 0:
                        current_time = time.time()
                        if current_time - self.last_log_time > 2:
                            audio_logger.debug(f"📥 Применен gain {gain:.3f}")
                            self.last_log_time = current_time
        except Exception:
            # Игнорируем ошибки обработки
            pass
        
        # Заполняем фрейм
        frame.buf = pj.ByteVector()
        frame.buf.resize(len(collected_bytes))
        for i, byte_val in enumerate(collected_bytes):
            frame.buf[i] = byte_val
        frame.size = len(collected_bytes)
        frame.type = pj.PJMEDIA_FRAME_TYPE_AUDIO
        
        # Логируем статистику раз в 200 фреймов
        if self.frame_counter % 200 == 0:
            current_time = time.time()
            if current_time - self.last_log_time > 5:
                queue_size = self.esp_to_sip_queue.qsize()
                audio_logger.debug(f"📥 ESP->SIP очередь: {queue_size}, буфер: {len(self.buffer)} байт")
                self.last_log_time = current_time

    def onFrameReceived(self, frame):
        """Получение аудио данных от SIP для отправки в ESP32"""
        if frame.size == 0 or frame.type != pj.PJMEDIA_FRAME_TYPE_AUDIO:
            return
        
        received_bytes = bytes([frame.buf[i] for i in range(frame.size)])
        
        # Обработка звука от SIP
        try:
            if len(received_bytes) >= 2:
                audio_data = np.frombuffer(received_bytes, dtype=np.int16)
                
                # Нормализация громкости
                max_val = np.max(np.abs(audio_data))
                if max_val > 0:
                    if max_val < 10000:  # Слишком тихий звук
                        gain = 3.0
                        audio_data = (audio_data * gain).astype(np.int16)
                    elif max_val > 28000:  # Слишком громкий
                        gain = 28000.0 / max_val
                        audio_data = (audio_data * gain).astype(np.int16)
                
                received_bytes = audio_data.tobytes()
        except Exception:
            # Игнорируем ошибки обработки
            pass
        
        # Отправляем в очередь SIP->ESP
        global global_sip_to_esp_queue
        try:
            global_sip_to_esp_queue.put_nowait(received_bytes)
        except queue.Full:
            try:
                # Очищаем старые данные и добавляем новые
                global_sip_to_esp_queue.get_nowait()
                global_sip_to_esp_queue.put_nowait(received_bytes)
                if self.frame_counter % 100 == 0:
                    audio_logger.warning("⚠️ Очередь SIP->ESP переполнена")
            except queue.Empty:
                pass


class SIPCall(pj.Call):
    def __init__(self, acc, call_id=-1, bridge=None):
        pj.Call.__init__(self, acc, call_id)
        self.bridge = bridge
        self.connected = False
        self.audio_media = None
        self.call_start_time = None

    def onCallState(self, prm):
        ci = self.getInfo()
        global global_call_state
        global_call_state = ci.state
        
        if ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
            self.connected = True
            self.call_start_time = time.time()
            sip_logger.info("✅ Звонок принят (CONFIRMED)!")
            if self.bridge:
                asyncio.run_coroutine_threadsafe(
                    self.bridge.on_call_connected(),
                    self.bridge.loop
                )

        elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            self.connected = False
            call_duration = time.time() - self.call_start_time if self.call_start_time else 0
            sip_logger.info(f"❌ Звонок завершен (DISCONNECTED), длительность: {call_duration:.1f}с")
            global call_terminated
            call_terminated = True
            if stop_stream_event:
                stop_stream_event.set()
            
            # Отправляем команду STOP на ESP32
            if self.bridge:
                asyncio.run_coroutine_threadsafe(
                    self.bridge.send_stop_to_esp32(),
                    self.bridge.loop
                )

    def onCallMediaState(self, prm):
        ci = self.getInfo()
        for mi in ci.media:
            if mi.type == pj.PJMEDIA_TYPE_AUDIO and mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE:
                self.audio_media = self.getAudioMedia(mi.index)
                sip_logger.info("🎵 Аудио медиа активировано")
                if self.bridge:
                    asyncio.run_coroutine_threadsafe(
                        self.bridge.setup_audio_bridge_and_send_play(self.audio_media),
                        self.bridge.loop
                    )


class ESP32SIPAudioBridge:
    def __init__(self, esp_host, esp_port, esp_password, sip_target_uri, sip_account, esp_clock_rate=16000):
        self.esp_host = esp_host
        self.esp_port = esp_port
        self.esp_password = esp_password
        self.cli = None
        self.voice_assistant_active = False
        self.conversation_id = None
        self.unsubscribe_callback = None
        
        self.sip_target_uri = sip_target_uri
        self.sip_account = sip_account  # Add reference to the SIP account from ha-sip
        self.ep = None
        self.acc = None
        self.call = None
        self.sip_audio_media = None
        self.sip_audio_port = None
        
        # Очередь с мониторингом
        self.esp_to_sip_queue = queue.Queue(maxsize=2000)
        
        self.loop = asyncio.get_event_loop()
        self.device_activated = False
        self.audio_bridge_setup = False
        self.esp_clock_rate = esp_clock_rate
        self.stream_server_running = False
        self.media_player_key = None

        # Флаги и счетчики
        self.play_command_sent = False
        self.connection_time = None
        self.audio_frame_count = 0
        self.last_audio_log_time = time.time()
        
        # Для проигрывания аудио при вызове
        self.call_stream_url = f"http://192.168.0.106:8991/call.wav"
        self.busy_stream_url = f"http://192.168.0.106:8991/busy.wav"
        
        # Отслеживание времени последнего запуска call.wav
        self.last_call_start_time = 0
        
        bridge_logger.info(f"🔧 ESP32SIPAudioBridge инициализирован")
        bridge_logger.info(f"  ESP32: {esp_host}:{esp_port}")
        bridge_logger.info(f"  SIP цель: {sip_target_uri}")

    def create_wav_header(self, sample_rate=16000, num_channels=1, bits_per_sample=16):
        """Создает WAV заголовок для стриминга"""
        byte_rate = sample_rate * num_channels * bits_per_sample // 8
        block_align = num_channels * bits_per_sample // 8
        
        # WAV заголовок (44 байта)
        header = b'RIFF'
        header += struct.pack('<I', 0xFFFFFFFF)  # Размер файла (неизвестно)
        header += b'WAVE'
        
        # fmt subchunk
        header += b'fmt '
        header += struct.pack('<I', 16)  # Размер fmt подзаголовка
        header += struct.pack('<H', 1)   # Аудиоформат (1 = PCM)
        header += struct.pack('<H', num_channels)
        header += struct.pack('<I', sample_rate)
        header += struct.pack('<I', byte_rate)
        header += struct.pack('<H', block_align)
        header += struct.pack('<H', bits_per_sample)
        
        # data subchunk
        header += b'data'
        header += struct.pack('<I', 0xFFFFFFFF)  # Размер данных (неизвестно)
        
        return header

    async def stream_sip_audio_to_esp(self):
        """Стриминг аудио от SIP к ESP32"""
        # Use the stream port from config if available, otherwise default to 8991
        STREAM_PORT = 8991
        from config import ESP32_STREAM_PORT
        try:
            STREAM_PORT = int(ESP32_STREAM_PORT)
        except:
            pass  # Use default if config value is invalid
        
        async def stream_handler(request):
            global global_stream_handler_running
            
            if global_stream_handler_running:
                bridge_logger.warning("🔄 stream_handler: Уже запущен, отклоняем подключение")
                return web.Response(status=503, text="Only one stream allowed")
            
            global_stream_handler_running = True
            bridge_logger.info("🔄 stream_handler: Новое подключение к стриму")
            
            # Создаем WAV заголовок
            wav_header = self.create_wav_header(
                sample_rate=16000,
                num_channels=1,
                bits_per_sample=16
            )
            
            response = web.StreamResponse(
                status=200,
                reason='OK',
                headers={
                    'Content-Type': 'audio/wav',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
            )
            await response.prepare(request)
            await response.write(wav_header)
            
            frames_sent = 0
            last_log_time = time.time()
            last_activity_time = time.time()
            
            try:
                while (self.stream_server_running and 
                       not stop_stream_event.is_set()):
                    
                    # Проверяем, что звонок все еще активен
                    global global_call_state
                    if global_call_state == pj.PJSIP_INV_STATE_DISCONNECTED:
                        bridge_logger.info("🔄 stream_handler: Звонок завершен, останавливаем стрим")
                        break
                    
                    # Проверяем активность
                    current_time = time.time()
                    if current_time - last_activity_time > 30:
                        bridge_logger.warning("🔄 stream_handler: Нет активности 30 секунд, останавливаем")
                        break
                    
                    # Собираем данные из очереди
                    chunks = []
                    total_bytes = 0
                    
                    # Собираем до 1280/4 байт (40мс) или ждем 20мс
                    while total_bytes < 1280/4 and len(chunks) < 500: # Было 10 чанков.
                        try:
                            chunk = global_sip_to_esp_queue.get_nowait()
                            chunks.append(chunk)
                            total_bytes += len(chunk)
                            last_activity_time = current_time
                        except queue.Empty:
                            break
                    
                    if chunks:
                        pcm_data = b''.join(chunks)
                        frames_sent += 1
                        
                        # Логируем каждые 100 фреймов
                        if frames_sent % 100 == 0:
                            current_time = time.time()
                            if current_time - last_log_time > 5:
                                bridge_logger.debug(f"📤 Отправлено {len(pcm_data)} байт, фреймов: {frames_sent}")
                                last_log_time = current_time
                        
                        await response.write(pcm_data)
                    else:
                        # Если данных нет, спим немного
                        await asyncio.sleep(0.001)
                        
            except asyncio.CancelledError:
                bridge_logger.info("🔄 stream_handler отменен")
            except Exception as e:
                bridge_logger.error(f"❌ Ошибка в stream_handler: {e}")
            finally:
                global_stream_handler_running = False
                bridge_logger.info(f"🔄 stream_handler завершен")
            
            return response
        
        # Запуск HTTP сервера
        app = web.Application()
        app.router.add_get('/stream_sip.wav', stream_handler)
        
        # Добавляем маршруты для файлов call.wav и busy.wav
        async def call_handler(request):
            # Отправляем файл call.wav
            if os.path.exists('call.wav'):
                return web.FileResponse('call.wav', headers={'Content-Type': 'audio/wav'})
            else:
                # Если файл не найден, возвращаем пустой WAV
                response = web.StreamResponse(
                    status=200,
                    reason='OK',
                    headers={'Content-Type': 'audio/wav'}
                )
                await response.prepare(request)
                return response
        
        async def busy_handler(request):
            # Отправляем файл busy.wav
            if os.path.exists('busy.wav'):
                return web.FileResponse('busy.wav', headers={'Content-Type': 'audio/wav'})
            else:
                # Если файл не найден, возвращаем пустой WAV
                response = web.StreamResponse(
                    status=200,
                    reason='OK',
                    headers={'Content-Type': 'audio/wav'}
                )
                await response.prepare(request)
                return response
        
        app.router.add_get('/call.wav', call_handler)
        app.router.add_get('/busy.wav', busy_handler)
        
        runner = web.AppRunner(app)
        try:
            await runner.setup()
            site = web.TCPSite(runner, '0.0.0.0', STREAM_PORT)
            await site.start()
        except OSError as e:
            if e.errno == 98:  # Address already in use
                bridge_logger.error(f"❌ Порт {STREAM_PORT} уже используется. Пожалуйста, закройте другие процессы использующие этот порт.")
                raise
            else:
                raise
        
        bridge_logger.info(f"🔄 SIP->ESP стриминг-сервер запущен на порту {STREAM_PORT}")
        
        global server_runner
        server_runner = runner
        self.stream_server_running = True
        
        try:
            # Ждем завершения звонка или остановки
            while (self.stream_server_running and 
                   not stop_stream_event.is_set()):
                await asyncio.sleep(1)
                
        except asyncio.CancelledError:
            bridge_logger.info("🔄 Задача стрима отменена")
        except Exception as e:
            bridge_logger.error(f"❌ Ошибка в задаче стрима: {e}")
        finally:
            bridge_logger.info("🔄 Остановка SIP->ESP стриминг-сервера...")
            self.stream_server_running = False
            
            await asyncio.sleep(0.5)
            try:
                await runner.cleanup()
            except Exception as e:
                bridge_logger.error(f"❌ Ошибка при очистке runner: {e}")
            bridge_logger.info("🔄 SIP->ESP стриминг-сервер остановлен")

    async def connect_esp32(self):
        log_timing("🔌 Начало подключения к ESP32")
        try:
            if self.cli:
                try:
                    await self.cli.disconnect()
                except:
                    pass
                self.cli = None

            self.cli = aioesphomeapi.APIClient(self.esp_host, self.esp_port, self.esp_password)
            await self.cli.connect(login=True)
            log_timing(f"✅ Подключено к ESP32")

            device_info = await self.cli.device_info()
            log_timing(f"📍 Устройство: {device_info.name}")

            self.media_player_key = None
            entities, _ = await self.cli.list_entities_services()
            for entity in entities:
                if type(entity).__name__ == 'MediaPlayerInfo' and getattr(entity, 'object_id', None) == 'media_player':
                    self.media_player_key = entity.key
                    log_timing(f"🎵 Найден медиаплеер: key={self.media_player_key}")
                    break

            if self.media_player_key is None:
                log_timing("❌ Медиаплеер не найден на ESP32!")
                return False

            return True
        except Exception as e:
            log_timing(f"❌ Ошибка подключения к ESP32: {e}")
            self.cli = None
            self.media_player_key = None
            return False

    async def handle_audio(self, audio_data: bytes):
        """Обработка аудио от ESP32"""
        self.audio_frame_count += 1
        current_time = time.time()
        
        # Логируем каждые 100 фреймов или каждые 5 секунд
        if (self.audio_frame_count % 100 == 0 or 
            current_time - self.last_audio_log_time > 5):
            queue_size = self.esp_to_sip_queue.qsize()
            audio_logger.debug(f"🎙️ Получено {len(audio_data)} байт, очередь: {queue_size}")
            self.last_audio_log_time = current_time
        
        # Проверяем состояние звонка и готовность моста
        if (self.voice_assistant_active and 
            len(audio_data) > 0 and 
            self.call and
            self.sip_audio_media and 
            self.sip_audio_port and 
            self.audio_bridge_setup):
            
            try:
                # Безопасная проверка состояния звонка
                global call_terminated
                if call_terminated:
                    audio_logger.debug("Звонок завершен, пропускаем аудио")
                    return
                    
                call_info = self.call.getInfo()
                current_state = call_info.state
                
                if current_state == pj.PJSIP_INV_STATE_CONFIRMED:
                    # Обработка аудио перед отправкой
                    try:
                        if len(audio_data) >= 2:
                            audio_int16 = np.frombuffer(audio_data, dtype=np.int16)
                            
                            # Увеличение громкости если нужно
                            max_val = np.max(np.abs(audio_int16))
                            if max_val < 10000:
                                gain = 2.0
                                audio_int16 = (audio_int16 * gain).astype(np.int16)
                                audio_data = audio_int16.tobytes()
                    except Exception as e:
                        audio_logger.debug(f"Ошибка обработки аудио от ESP32: {e}")
                    
                    # Отправка в очередь
                    try:
                        self.esp_to_sip_queue.put_nowait(audio_data)
                    except queue.Full:
                        try:
                            self.esp_to_sip_queue.get_nowait()
                            self.esp_to_sip_queue.put_nowait(audio_data)
                            if self.audio_frame_count % 50 == 0:
                                audio_logger.warning("⚠️ Очередь ESP->SIP переполнена")
                        except queue.Empty:
                            pass
                else:
                    audio_logger.debug(f"Звонок не в CONFIRMED ({current_state}), пропускаем аудио")
                    
            except Exception as e:
                # Безопасно игнорируем ошибки получения состояния звонка
                if "already terminated" not in str(e):
                    audio_logger.debug(f"Ошибка получения состояния звонка: {e}")
                return

    def setup_sip(self):
        log_timing("🔧 Начало инициализации SIP")
        try:
            # Создаем endpoint с минимальным логированием
            self.ep = pj.Endpoint()
            self.ep.libCreate()
            
            # Настраиваем минимальное логирование PJSIP
            ep_cfg = pj.EpConfig()
            ep_cfg.logConfig.level = 0  # Устанавливаем минимальный уровень логирования
            ep_cfg.logConfig.consoleLevel = 0
            self.ep.libInit(ep_cfg)
            
            # Отключаем звуковые устройства
            aud_mgr = self.ep.audDevManager()
            aud_mgr.setNullDev()
            log_timing("🔇 Звуковые устройства отключены (режим моста)")
            
            # Создаем транспорт
            tp_cfg = pj.TransportConfig()
            tp_cfg.port = 0
            self.ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, tp_cfg)
            log_timing("🚪 UDP транспорт создан")
            
            # Запускаем библиотеку
            self.ep.libStart()
            log_timing("▶️ PJSIP запущен")
            
            # Создаем аккаунт
            acc_cfg = pj.AccountConfig()
            acc_cfg.idUri = "sip:9000@192.168.128.22:5061"
            acc_cfg.registrarUri = "sip:192.168.128.22:5061"
            cred = pj.AuthCredInfo("digest", "asterisk", "9000", 0, "3d12d14b415b5b8b2667820156c0a306")
            acc_cfg.sipConfig.authCreds.append(cred)
            
            self.acc = pj.Account()
            self.acc.create(acc_cfg)
            
            log_timing("✅ SIP библиотека инициализирована в режиме моста")
            return True
        except Exception as e:
            log_timing(f"❌ Ошибка инициализации SIP: {e}")
            return False

    async def make_call(self):
        log_timing(f"📞 Начало вызова на {self.sip_target_uri}")
        try:
            await asyncio.sleep(1)
            
            call_prm = pj.CallOpParam()
            call_prm.opt.audioCount = 1
            call_prm.opt.videoCount = 0
            
            self.call = SIPCall(self.acc, bridge=self)
            self.call.makeCall(self.sip_target_uri, call_prm)
            log_timing(f"📞 Вызов отправлен")
            
            log_timing("🕐 Ожидание ответа...")
            call_answered = False
            max_wait = 30
            call_start_time = time.time()
            
            # Отправляем файл вызова (call.wav) сразу после вызова
            if self.cli and self.media_player_key:
                try:
                    await self.cli.device_info()
                    self.cli.media_player_command(
                        key=self.media_player_key,
                        command=MediaPlayerCommand.MEDIA_PLAYER_COMMAND_PLAY,
                        media_url=self.call_stream_url
                    )
                    self.last_call_start_time = time.time()
                    log_timing(f"🔊 Отправка команды PLAY (call.wav) на ESP32: {self.call_stream_url}")
                except Exception as e:
                    log_timing(f"❌ Ошибка отправки PLAY (call.wav): {e}")
            
            for i in range(max_wait):
                if not self.call:
                    break
                
                try:
                    call_info = self.call.getInfo()
                    
                    if i % 5 == 0:
                        log_timing(f"📊 Статус: {call_info.stateText}")
                    
                    if call_info.state == pj.PJSIP_INV_STATE_CONFIRMED and not call_answered:
                        call_answered = True
                        log_timing("🎉 СОЕДИНЕНИЕ УСТАНОВЛЕНО!")
                        
                        # Отправляем STOP, чтобы остановить проигрывание call.wav и подготовиться к стриму
                        if self.cli and self.media_player_key:
                            try:
                                await self.cli.device_info()
                                self.cli.media_player_command(
                                    key=self.media_player_key,
                                    command=MediaPlayerCommand.MEDIA_PLAYER_COMMAND_STOP
                                )
                                log_timing("⏹️ Отправка команды STOP на ESP32 (остановка call.wav)")
                                
                                # Ждем немного, чтобы STOP обработался
                                await asyncio.sleep(0.5)
                                
                                # Теперь отправляем PLAY для стрима
                                stream_url = f"http://192.168.0.106:8991/stream_sip.wav"
                                self.cli.media_player_command(
                                    key=self.media_player_key,
                                    command=MediaPlayerCommand.MEDIA_PLAYER_COMMAND_PLAY,
                                    media_url=stream_url
                                )
                                log_timing(f"🔊 Отправка команды PLAY на ESP32: {stream_url}")
                                
                            except Exception as e:
                                log_timing(f"❌ Ошибка отправки STOP/PLAY: {e}")
                        
                        break
                    
                    elif call_info.state == pj.PJSIP_INV_STATE_DISCONNECTED:
                        log_timing("📞 Звонок завершен")
                        # Отправляем STOP, чтобы остановить проигрывание call.wav или busy.wav
                        if self.cli and self.media_player_key:
                            try:
                                await self.cli.device_info()
                                self.cli.media_player_command(
                                    key=self.media_player_key,
                                    command=MediaPlayerCommand.MEDIA_PLAYER_COMMAND_STOP
                                )
                                log_timing("⏹️ Отправка команды STOP на ESP32 (по завершении звонка)")
                            except Exception as e:
                                log_timing(f"❌ Ошибка отправки STOP: {e}")
                        break
                    
                except Exception:
                    pass  # Игнорируем временные ошибки
                
                await asyncio.sleep(1)
                
                # Проверяем, прошло ли 22 секунды с последнего запуска call.wav и нужно ли перезапустить
                current_time = time.time()
                if current_time - self.last_call_start_time >= 22 and not call_answered:
                    # Перезапускаем call.wav
                    if self.cli and self.media_player_key:
                        try:
                            await self.cli.device_info()
                            self.cli.media_player_command(
                                key=self.media_player_key,
                                command=MediaPlayerCommand.MEDIA_PLAYER_COMMAND_PLAY,
                                media_url=self.call_stream_url
                            )
                            self.last_call_start_time = current_time
                            log_timing(f"🔊 Повторный запуск call.wav (22 секунды прошло с последнего запуска)")
                        except Exception as e:
                            log_timing(f"❌ Ошибка повторного запуска call.wav: {e}")
            
            # Если звонок не принят за 30 секунд, проигрываем busy.wav
            if not call_answered:
                log_timing("⚠️ Звонок не ответили за 30 секунд")
                # Отправляем busy.wav
                if self.cli and self.media_player_key:
                    try:
                        await self.cli.device_info()
                        self.cli.media_player_command(
                            key=self.media_player_key,
                            command=MediaPlayerCommand.MEDIA_PLAYER_COMMAND_PLAY,
                            media_url=self.busy_stream_url
                        )
                        log_timing(f"🔊 Отправка команды PLAY (busy.wav) на ESP32: {self.busy_stream_url}")
                        
                        # Ждем немного и отправляем STOP, чтобы остановить busy.wav
                        await asyncio.sleep(2)  # Ждем, пока busy.wav проиграет
                        self.cli.media_player_command(
                            key=self.media_player_key,
                            command=MediaPlayerCommand.MEDIA_PLAYER_COMMAND_STOP
                        )
                        log_timing("⏹️ Отправка команды STOP на ESP32 (остановка busy.wav)")
                        
                    except Exception as e:
                        log_timing(f"❌ Ошибка отправки PLAY/STOP (busy.wav): {e}")
            
            return call_answered
        except Exception as e:
            log_timing(f"❌ Ошибка совершения звонка: {e}")
            return False

    async def setup_audio_bridge_and_send_play(self, audio_media):
        log_timing("🔧 Настройка аудио моста (ESP32 <-> SIP)...")
        try:
            self.sip_audio_media = audio_media
            
            self.sip_audio_port = SIPAudioMediaPort(
                self.esp_to_sip_queue,
                global_sip_to_esp_queue,
                esp_clock_rate=self.esp_clock_rate
            )
            
            port_name = "ESP32SIPPort"
            fmt = pj.MediaFormatAudio()
            fmt.type = pj.PJMEDIA_TYPE_AUDIO
            fmt.id = pj.PJMEDIA_FORMAT_L16
            fmt.clockRate = 16000  # Устанавливаем 16 кГц как в оригинальном коде
            fmt.channelCount = 1
            fmt.bitsPerSample = 16
            fmt.frameTimeUsec = 20000
            fmt.avgBps = 16000 * 1 * 16
            fmt.maxBps = fmt.avgBps
            
            self.sip_audio_port.createPort(port_name, fmt)
            log_timing(f"🎤 Создан пользовательский аудио порт: {port_name}, 16kHz")
            
            # ESP32 -> SIP
            tx_param = pj.AudioMediaTransmitParam()
            tx_param.level = 1.0
            self.sip_audio_port.startTransmit2(self.sip_audio_media, tx_param)
            
            # SIP -> ESP32
            self.sip_audio_media.startTransmit(self.sip_audio_port)
            
            self.audio_bridge_setup = True
            log_timing("✅ Аудио мост настроен (двунаправленный)")
            
            # Ждем завершения звонка
            try:
                while (self.call and 
                       not stop_stream_event.is_set()):
                    await asyncio.sleep(1)
            except asyncio.CancelledError:
                log_timing("🔄 Задача ожидания завершения звонка отменена.")
            finally:
                # Устанавливаем флаг только один раз
                if not stop_stream_event.is_set():
                    stop_stream_event.set()
                    log_timing("🔄 Установлен флаг остановки стрима.")
                
        except Exception as e:
            log_timing(f"❌ Ошибка настройки аудио моста: {e}")
            import traceback
            traceback.print_exc()

    async def on_call_connected(self):
        log_timing("🔗 Звонок установлен, готов к передаче аудио")
        self.connection_time = time.time()
        log_timing("⏱️ Время подключения зафиксировано")

    async def send_stop_to_esp32(self):
        """Отправляет команду STOP на ESP32 при завершении вызова"""
        log_timing("⏹️ Отправка команды STOP на ESP32...")
        
        if self.cli and self.media_player_key:
            try:
                await self.cli.device_info()
                self.cli.media_player_command(
                    key=self.media_player_key,
                    command=MediaPlayerCommand.MEDIA_PLAYER_COMMAND_STOP
                )
                log_timing("✅ Команда STOP отправлена на ESP32.")
            except Exception as e:
                log_timing(f"❌ Ошибка отправки STOP: {e}")
        else:
            log_timing("⚠️ ESP32 клиент или медиаплеер не инициализированы для отправки STOP")

    async def start_bridge(self):
        global BRIDGE_START_TIME, call_terminated, stop_stream_event
        BRIDGE_START_TIME = time.time()
        call_terminated = False
        # Инициализируем stop_stream_event в начале
        stop_stream_event = asyncio.Event()
        log_timing("🚀 ЗАПУСК ДВУНАПРАВЛЕННОГО МОСТА ESP32 <-> SIP")
        
        # Сначала запускаем HTTP-сервер, чтобы файлы были доступны
        log_timing("🔄 Запуск HTTP-сервера...")
        stream_task = asyncio.create_task(self.stream_sip_audio_to_esp())
        
        if not await self.connect_esp32():
            log_timing("❌ Не удалось подключиться к ESP32")
            return
        
        # Подписываемся на аудио
        log_timing("🎙️ Подписка на аудио с ESP32...")
        
        async def handle_start(conversation_id: str, flags: int, audio_settings, wake_word_phrase: str | None):
            self.conversation_id = conversation_id
            self.voice_assistant_active = True
            self.device_activated = True
            log_timing(f"🎙️ Устройство активировано: {conversation_id}")
            return 0
        
        async def handle_stop(expected_stop: bool):
            log_timing("⏹️ Прием аудио с ESP32 остановлен")
            self.voice_assistant_active = False
        
        self.unsubscribe_callback = self.cli.subscribe_voice_assistant(
            handle_start=handle_start,
            handle_stop=handle_stop,
            handle_audio=self.handle_audio
        )
        log_timing("✅ Подписка на аудио с ESP32 установлена.")
        
        # Активируем устройство для продолжения работы
        self.device_activated = True
        log_timing("✅ Устройство считается активированным для продолжения работы.")
        
        if not self.setup_sip():
            log_timing("❌ Не удалось инициализировать SIP")
            return
        
        # Создаем звонок
        if not await self.make_call():
            log_timing("❌ Не удалось установить звонок")
            return
        
        # Ждем завершения звонка
        try:
            while (self.call and 
                   not call_terminated and
                   not stop_stream_event.is_set()):
                await asyncio.sleep(0.5)
        except KeyboardInterrupt:
            log_timing("\n🛑 Остановка по запросу пользователя...")
        finally:
            if stop_stream_event and not stop_stream_event.is_set():
                stop_stream_event.set()
        
        await self.stop_bridge()

    async def stop_bridge(self):
        log_timing("🧹 Начало завершения работы...")
        global server_runner, call_terminated
        
        self.stream_server_running = False
        self.audio_bridge_setup = False
        
        if self.sip_audio_port and self.sip_audio_media:
            try:
                self.sip_audio_port.stopTransmit(self.sip_audio_media)
                log_timing("📤 Передача аудио ESP32->SIP остановлена")
            except Exception:
                pass
        
        if self.sip_audio_port:
            try:
                pass  # Закрытие порта
            except Exception:
                pass
            self.sip_audio_port = None
        
        if self.call:
            try:
                log_timing("📞 Попытка завершить звонок...")
                self.call.hangup(pj.CallOpParam())
            except:
                pass
        
        if self.unsubscribe_callback:
            self.unsubscribe_callback()
            self.unsubscribe_callback = None
        
        if self.ep:
            try:
                self.ep.libDestroy()
            except:
                pass
        
        if self.cli:
            try:
                await self.cli.disconnect()
            except:
                pass
            self.cli = None
            self.media_player_key = None
        
        if server_runner:
            try:
                await server_runner.cleanup()
                log_timing("🔄 Глобальный стриминг-сервер остановлен.")
            except:
                pass
            server_runner = None
        
        call_terminated = True
        log_timing("👋 Работа завершена")


async def create_esp32_sip_bridge(esp_host, esp_port, esp_password, sip_target_uri, sip_account):
    """
    Creates an ESP32 SIP bridge that connects an ESP32 device to a SIP endpoint.
    This allows making and receiving calls through the ESP32 device.
    """
    bridge = ESP32SIPAudioBridge(
        esp_host=esp_host,
        esp_port=esp_port,
        esp_password=esp_password,
        sip_target_uri=sip_target_uri,
        sip_account=sip_account
    )
    
    return bridge