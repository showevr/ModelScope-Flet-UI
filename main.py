import flet as ft
import requests
import json
import asyncio
import os
import time
import random
import hashlib
import struct
import zlib
import io
import http.server
import socketserver
import threading
import uuid
from PIL import ImageGrab 
try:
    HAS_PIL_GRAB = True
except ImportError:
    HAS_PIL_GRAB = False
except OSError:
    HAS_PIL_GRAB = False

try:
    MyAnimation = ft.Animation
    MyOffset = ft.Offset
    MyScale = ft.Scale
except AttributeError:
    try:
        MyAnimation = ft.animation.Animation
        MyOffset = ft.transform.Offset
        MyScale = ft.transform.Scale
    except:
        MyAnimation = None
        MyOffset = None
        MyScale = None

LOCAL_IMAGE_CACHE = {}
LOCAL_SERVER_PORT = 28989

class LocalImageHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/image/"):
            try:
                token = self.path.split('/')[-1].split('.')[0]
                if token in LOCAL_IMAGE_CACHE:
                    image_data = LOCAL_IMAGE_CACHE[token]
                    self.send_response(200)
                    self.send_header("Content-type", "image/png")
                    self.send_header("Content-Length", str(len(image_data)))
                    self.send_header("Content-Disposition", f'attachment; filename="AI_{token[:8]}.png"')
                    self.end_headers()
                    self.wfile.write(image_data)
                else:
                    self.send_error(404, "Image not found or expired")
            except Exception as e:
                pass
        else:
            self.send_error(404, "Not Found")

    def log_message(self, format, *args):
        pass

def start_local_server():
    try:
        socketserver.TCPServer.allow_reuse_address = True
        with socketserver.TCPServer(("127.0.0.1", LOCAL_SERVER_PORT), LocalImageHandler) as httpd:
            print(f"Local Image Server running at port {LOCAL_SERVER_PORT}")
            httpd.serve_forever()
    except Exception as e:
        print(f"Failed to start local server: {e}")

threading.Thread(target=start_local_server, daemon=True).start()

BASE_URL = 'https://api-inference.modelscope.cn/'
BAIDU_TRANSLATE_URL = 'https://fanyi-api.baidu.com/api/trans/vip/translate'
I2I_FOLDER = "I2I_Edits"

if not os.path.exists(I2I_FOLDER):
    try: os.makedirs(I2I_FOLDER)
    except: pass

MODELS_REQUIRING_LIST_INPUT = [
    'Qwen/Qwen-Image-Edit-2509',
    'black-forest-labs/FLUX.2-dev',
    'Qwen/Qwen-Image-Edit-2511',
]

file_upload_cache = {}

MORANDI_COLORS = {    "Red": "#C85C56", "Orange": "#D98656", "Gold": "#D0A467", "Green": "#709D78",
    "Teal": "#5C969C", "Blue": "#5D7EA8", "Purple": "#8C73A6"
}

STATUS_TRANSLATIONS = {
    "PENDING": "排队中",
    "RUNNING": "生成中",
    "PROCESSING": "处理中",
    "SUCCEED": "成功",
    "FAILED": "失败",
    "CANCELED": "已取消",
    "UNKNOWN": "未知"
}

BG_WARM = "#F5F0EB"
BG_LIGHT = "#FFFFFF"
BG_DARK = "#1C1C1E"
BG_DARK_DIALOG = "#2C2C2E"

INPUT_HEIGHT = 40 
CUSTOM_BTN_WIDTH = 68
SEARCH_WIDTH = 70 

DEFAULT_MODEL_OPTIONS = [
    {"key": "Qwen/Qwen-Image-Edit-2511", "text": "Qwen-Image-Edit-2511 (新)"},
    {"key": "Qwen/Qwen-Image-Edit-2509", "text": "Qwen-Image-Edit-2509"},
    {"key": "black-forest-labs/FLUX.2-dev", "text": "FLUX.2-dev"},
    {"key": "Qwen/Qwen-Image-Edit", "text": "Qwen/Qwen-Image-Edit (默认)"},
    {"key": "MusePublic/FLUX.1-Kontext-Dev", "text": "FLUX.1-Kontext-Dev"},
    {"key": "google/gemini-2.0-flash-exp", "text": "Gemini 2.0 Flash (Google)"},
]

SIZE_OPTIONS = [
    {"key": "AutoSize", "text": "AutoSize (自动检测)"},
    {"key": "928x1664", "text": "928x1664 (竖屏)"},
    {"key": "1104x1472", "text": "1104x1472 (竖屏)"},
    {"key": "1328x1328", "text": "1328x1328 (方形)"},
    {"key": "1472x1104", "text": "1472x1104 (横屏)"},
    {"key": "1664x928", "text": "1664x928 (横屏)"},
    {"key": "2048x2048", "text": "2048x2048 (方形)"},
]

def get_opacity_color(opacity, hex_color):
    if not hex_color: return None
    if hex_color == "black": hex_color = "#000000"
    if hex_color == "white": hex_color = "#FFFFFF"
    if hex_color == "transparent": return "transparent"
    if hex_color.startswith("#"):
        if len(hex_color) == 7:
            alpha = int(opacity * 255)
            alpha_hex = f"{alpha:02x}"
            return f"#{alpha_hex}{hex_color.lstrip('#')}"
    return hex_color

def add_metadata_to_png(image_bytes, metadata):
    try:
        png_signature = b'\x89PNG\r\n\x1a\n'
        if not image_bytes.startswith(png_signature):
            return image_bytes

        metadata_payload = {
            "source": "ZhaishengyuanAI",
            "data": metadata
        }
        metadata_json = json.dumps(metadata_payload, ensure_ascii=False)
        keyword = "zsyAI"
        text_data = f"{keyword}\x00{metadata_json}"
        chunk_type = b'tEXt'
        chunk_data = text_data.encode('utf-8')
        chunk_length = struct.pack('>I', len(chunk_data))
        chunk_crc = struct.pack('>I', zlib.crc32(chunk_type + chunk_data) & 0xffffffff)
        
        iend_pos = image_bytes.rfind(b'IEND')
        if iend_pos == -1:
            return image_bytes

        new_image_data = (
            image_bytes[:iend_pos-4] + 
            chunk_length +
            chunk_type +
            chunk_data +
            chunk_crc +
            image_bytes[iend_pos-4:] 
        )
        return new_image_data
    except Exception as e:
        print(f"Error adding metadata: {e}")
        return image_bytes

def extract_metadata_from_png(image_bytes):
    try:
        offset = 8 
        while offset < len(image_bytes):
            if offset + 8 > len(image_bytes): break
            chunk_length = struct.unpack('>I', image_bytes[offset:offset+4])[0]
            chunk_type = image_bytes[offset+4:offset+8]
            
            if offset + 12 + chunk_length > len(image_bytes): break
            
            chunk_data_start = offset + 8
            chunk_data_end = chunk_data_start + chunk_length
            chunk_data = image_bytes[chunk_data_start:chunk_data_end]
            
            if chunk_type in [b'tEXt', b'zTXt']:
                try:
                    decoded_text = ""
                    if chunk_type == b'zTXt':
                        parts = chunk_data.split(b'\x00', 1)
                        if len(parts) >= 2:
                            if len(parts[1]) > 1:
                                compressed_data = parts[1][1:]
                                decoded_text = zlib.decompress(compressed_data).decode('utf-8')
                    else:
                        decoded_text = chunk_data.decode('utf-8', errors='ignore')
                    
                    if '\x00' in decoded_text:
                        keyword, metadata_str = decoded_text.split('\x00', 1)
                        if keyword in ["ZhaishengyuanAI", "zsyAI"]:
                            try:
                                metadata = json.loads(metadata_str)
                                if isinstance(metadata, dict) and 'data' in metadata:
                                    return metadata['data']
                                else:
                                    return metadata
                            except json.JSONDecodeError:
                                continue
                except Exception:
                    continue
            
            if chunk_type == b'IEND':
                break
            offset += 12 + chunk_length
        return None
    except Exception as e:
        print(f"Error extracting metadata: {e}")
        return None

def get_image_size(file_path):
    try:
        with open(file_path, 'rb') as f:
            head = f.read(24)
            if len(head) != 24: return None
            if head.startswith(b'\x89PNG\r\n\x1a\n'):
                w, h = struct.unpack('>II', head[16:24])
                return w, h
            elif head.startswith(b'\xff\xd8'):
                f.seek(0)
                while True:
                    byte = f.read(1)
                    if not byte: break
                    if byte == b'\xff':
                        byte = f.read(1)
                        if not byte: break
                        if byte[0] >= 0xc0 and byte[0] <= 0xcf and byte[0] != 0xc4 and byte[0] != 0xc8 and byte[0] != 0xcc:
                            f.read(3)
                            h, w = struct.unpack('>HH', f.read(4))
                            return w, h
                        else:
                            f.read(int.from_bytes(f.read(2), 'big') - 2)
    except:
        return None
    return None

async def upload_image_to_host(file_path):
    if file_path in file_upload_cache:
        return file_upload_cache[file_path]
    try:
        filename = os.path.basename(file_path)
        with open(file_path, 'rb') as f:
            files = {'files[]': (filename, f, 'image/png')}
            res = await asyncio.to_thread(requests.post, "https://uguu.se/upload", files=files, timeout=60)
        if res.status_code == 200:
            data = res.json()
            if data.get('success'):
                url = data['files'][0]['url'].replace('\\', '')
                file_upload_cache[file_path] = url
                return url
        return None
    except Exception as e:
        print(f"Upload failed: {e}")
        return None

async def main(page: ft.Page):
    page.window.min_width = 380
    page.window.min_height = 600
    page.window.resizable = True   
    page.title = "魔塔AI大全 - 图片编辑"
    page.padding = 0
    page.spacing = 0
    page.appbar = None 
    try: page.expand = True 
    except: pass

    uploaded_files = []

    try:
        stored_api_keys_str = await page.client_storage.get_async("api_keys") or ""
        stored_baidu_config = await page.client_storage.get_async("baidu_config") or ""
        stored_color_name = await page.client_storage.get_async("theme_color") or "Gold"
        stored_mode = await page.client_storage.get_async("theme_mode") or "dark"
        stored_custom_models = await page.client_storage.get_async("custom_models") or ""
        stored_power_config = await page.client_storage.get_async("power_mode_config")
    except Exception as e:
        print(f"Error reading storage: {e}")
        stored_api_keys_str, stored_baidu_config = "", ""
        stored_color_name, stored_mode = "Gold", "dark"
        stored_custom_models = ""
        stored_power_config = None

    if not stored_power_config or not isinstance(stored_power_config, dict):
        stored_power_config = {
            "enabled": False,
            "batch_size": 10,
            "selected_keys": [],
            "daily_limit": 200,
            "request_delay": 0.2
        }

    current_api_keys = [k.strip() for k in stored_api_keys_str.split('\n') if k.strip()]
    current_primary_color = MORANDI_COLORS.get(stored_color_name, "#D0A467")
    
    baidu_lines = stored_baidu_config.split('\n')
    current_baidu_appid = baidu_lines[0].strip() if len(baidu_lines) > 0 else ""
    current_baidu_key = baidu_lines[1].strip() if len(baidu_lines) > 1 else ""
    
    sidebar_offset = MyOffset(-1, 0) if MyOffset else None
    t2i_page_index = 0
    is_wide_mode = False
    left_panel_visible = True

    async def save_config(key, value):
        try: await page.client_storage.set_async(key, value)
        except: pass

    def safe_open_dialog(dlg):
        try: page.open(dlg)
        except: 
            page.dialog = dlg
            dlg.open = True
            page.update()

    def safe_close_dialog(dlg):
        try: page.close(dlg)
        except: 
            dlg.open = False
            page.update()

    def get_dropdown_fill_color():
        if stored_mode == "dark": return "#3C3C3E"
        elif stored_mode == "warm": return "#FFFBF6"
        else: return "#FFFFFF"

    def get_dropdown_bgcolor():
        if stored_mode == "dark": return "#3C3C3E"
        elif stored_mode == "warm": return "#FFFBF6"
        else: return "#FFFFFF"
        
    def get_border_color():
        if stored_mode == "dark": return "#525252"
        return "#d9d9d9"
        
    def get_viewer_bgcolor_dynamic():
        if stored_mode == "dark": return BG_DARK
        elif stored_mode == "warm": return BG_WARM
        else: return BG_LIGHT

    def copy_text(text):
        page.set_clipboard(text)
        page.snack_bar = ft.SnackBar(ft.Text("已复制到剪贴板"), open=True)
        page.update()

    def translate_text(text, to_lang="en"):
        nonlocal current_baidu_appid, current_baidu_key
        if not current_baidu_appid or not current_baidu_key:
            page.snack_bar = ft.SnackBar(ft.Text("请先在设置中配置百度翻译 Key"), open=True)
            page.update()
            return None
        try:
            salt = str(random.randint(32768, 65536))
            sign_str = current_baidu_appid + text + salt + current_baidu_key
            sign = hashlib.md5(sign_str.encode()).hexdigest()
            res = requests.post(BAIDU_TRANSLATE_URL, data={
                'q': text, 'from': 'auto', 'to': to_lang,
                'appid': current_baidu_appid, 'salt': salt, 'sign': sign
            }, timeout=5)
            data = res.json()
            if 'trans_result' in data: return data['trans_result'][0]['dst']
            else:
                page.snack_bar = ft.SnackBar(ft.Text(f"翻译错误: {data.get('error_msg')}"), open=True)
                page.update()
                return None
        except Exception as e:
            page.snack_bar = ft.SnackBar(ft.Text(f"翻译请求失败: {str(e)}"), open=True)
            page.update()
            return None

    async def save_image_to_local_folder(url, metadata=None):
        if not url: return False
        try:
            res = await asyncio.to_thread(requests.get, url, timeout=30)
            if res.status_code == 200:
                image_bytes = res.content
                if metadata:
                    image_bytes = add_metadata_to_png(image_bytes, metadata)
                timestamp = int(time.time())
                filename = f"img_{timestamp}_{random.randint(100,999)}.png"
                save_path = os.path.join(I2I_FOLDER, filename)
                with open(save_path, "wb") as f:
                    f.write(image_bytes)
                page.snack_bar = ft.SnackBar(ft.Text(f"✅ 图片已保存至: {save_path}"), open=True)
                page.update()
                return True
            else:
                page.snack_bar = ft.SnackBar(ft.Text("下载失败: 网络错误"), open=True)
                page.update()
                return False
        except Exception as err:
            page.snack_bar = ft.SnackBar(ft.Text(f"保存错误: {str(err)}"), open=True)
            page.update()
            return False

    async def download_via_local_server(url, metadata=None):
        if not url: return False
        try:
            page.snack_bar = ft.SnackBar(ft.Text("正在调用浏览器下载..."), open=True)
            page.update()
            res = await asyncio.to_thread(requests.get, url, timeout=30)
            if res.status_code != 200:
                raise Exception("图片下载失败")
            image_bytes = res.content
            if metadata:
                image_bytes = add_metadata_to_png(image_bytes, metadata)
            token = str(uuid.uuid4())
            LOCAL_IMAGE_CACHE[token] = image_bytes
            local_url = f"http://127.0.0.1:{LOCAL_SERVER_PORT}/image/{token}.png"
            page.launch_url(local_url)
            return True
        except Exception as err:
            page.snack_bar = ft.SnackBar(ft.Text(f"处理失败: {str(err)}"), open=True)
            page.update()
            return False

    def mark_btn_downloaded(btn):
        if btn:
            btn.icon = "check_circle"
            btn.icon_color = current_primary_color
            btn.tooltip = "已下载/已保存"
            btn.disabled = True
            try: btn.update()
            except: pass

    sidebar_icon_ref = ft.Icon("smart_toy", size=40, color="grey")
    sidebar_title_ref = ft.Text("魔塔AI大全", size=18, weight="bold", color="grey")
    sidebar_subtitle_ref = ft.Text("By_showevr", size=12, color="grey")
    
    nav_highlight_ref = ft.Container(width=4, height=20, border_radius=2)
    nav_icon_ref = ft.Icon("palette", color="grey", size=20) 
    nav_text_ref = ft.Text("文生图", size=16, weight="bold", color="grey")
    
    sidebar_div1 = ft.Divider(height=10, thickness=0.5, color="transparent")
    sidebar_div2 = ft.Divider(height=10, thickness=0.5, color="transparent")

    nav_container_ref = ft.Container(
        content=ft.Row([
            ft.Row([nav_icon_ref, ft.Container(width=10), nav_text_ref]), 
            ft.Container(expand=True), 
            nav_highlight_ref
        ], alignment="spaceBetween"),
        padding=ft.padding.symmetric(horizontal=20, vertical=12), 
        border_radius=30, 
        animate=MyAnimation(200, "easeOut") if MyAnimation else None
    )
    
    theme_dialog = ft.AlertDialog(title=ft.Text("显示与主题", weight="bold", size=14), modal=True, surface_tint_color=ft.Colors.TRANSPARENT)
    settings_dialog = ft.AlertDialog(title=ft.Text("全局设置", size=14), modal=True, surface_tint_color=ft.Colors.TRANSPARENT)
    power_mode_dialog = ft.AlertDialog(title=ft.Row([ft.Icon("flash_on", color="amber"), ft.Text("强力生图模式", weight="bold", size=14)]), modal=True, surface_tint_color=ft.Colors.TRANSPARENT)

    is_viewer_info_open = False 
    viewer_zoom_level = 1.0
    _viewer_drag_offset_x = 0.0

    def close_viewer(e=None):
        nonlocal is_viewer_info_open, viewer_zoom_level, _viewer_drag_offset_x
        is_viewer_info_open = False 
        viewer_overlay.visible = False
        if not is_wide_mode and t2i_page_index == 1:
            gallery_control_gesture.visible = True
            gallery_control_gesture.update()
        try: viewer_overlay.update()
        except: pass
        reset_viewer_zoom(update_ui=False)

    inner_viewer_img = ft.Image(src="", fit=ft.ImageFit.CONTAIN, gapless_playback=True)
    preload_viewer_img = ft.Image(src="", fit=ft.ImageFit.CONTAIN, gapless_playback=True, opacity=1)

    zoom_hint_text = ft.Text("大图模式", color="white", size=14, weight="bold")
    zoom_hint_container = ft.Container(
        content=zoom_hint_text,
        bgcolor=get_opacity_color(0.7, current_primary_color), 
        padding=ft.padding.symmetric(horizontal=20, vertical=10),
        border_radius=30,
        opacity=0, 
        animate_opacity=300, 
        visible=False,
        shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.with_opacity(0.3, "black"))
    )

    async def show_zoom_hint_task(text):
        zoom_hint_text.value = text
        zoom_hint_container.bgcolor = get_opacity_color(0.7, current_primary_color)
        zoom_hint_container.visible = True
        zoom_hint_container.opacity = 1
        zoom_hint_container.update()
        await asyncio.sleep(0.5)
        zoom_hint_container.opacity = 0
        zoom_hint_container.update()
        await asyncio.sleep(0.3)
        zoom_hint_container.visible = False
        zoom_hint_container.update()

    def trigger_zoom_hint(text):
        page.run_task(show_zoom_hint_task, text)

    is_mobile_zoom_mode = False

    def toggle_mobile_zoom_mode(enable):
        nonlocal is_mobile_zoom_mode
        is_mobile_zoom_mode = enable
        
        outer_gesture_detector.visible = not enable
        if enable:
            interactive_viewer.scale = 1.2
            prev_btn.visible = False
            next_btn.visible = False
            viewer_controls_container.visible = False
            trigger_zoom_hint("大图模式")
        else:
            interactive_viewer.scale = 1.0
            if is_wide_mode:
                prev_btn.visible = True
                next_btn.visible = True
            viewer_controls_container.visible = True
            trigger_zoom_hint("退出缩放")
        
        try:
            outer_gesture_detector.update()
            interactive_viewer.update()
            prev_btn.update()
            next_btn.update()
            viewer_controls_container.update()
            update_viewer_layout_content()
        except: pass

    def on_inner_double_tap(e):
        if is_wide_mode:
            reset_viewer_zoom(True)
        else:
            toggle_mobile_zoom_mode(False)

    inner_gesture = ft.GestureDetector(
        content=ft.Container(
            content=inner_viewer_img,
            alignment=ft.alignment.center, 
            expand=True 
        ),
        on_double_tap=on_inner_double_tap,
        expand=True 
    )

    interactive_viewer = ft.InteractiveViewer(
        key="iv_viewer", 
        content=inner_gesture, 
        min_scale=0.2, 
        max_scale=5.0, 
        scale_enabled=True, 
        pan_enabled=True,      
        expand=True,
        boundary_margin=ft.padding.all(800)
    )

    swipe_anim_container = ft.Container(
        content=interactive_viewer,
        offset=MyOffset(0, 0) if MyOffset else None,
        animate_offset=MyAnimation(300, "easeOut") if MyAnimation else None,
        expand=True,
        on_click=lambda e: toggle_overlay_ui(e)
    )

    preload_container = ft.Container(
        content=preload_viewer_img,
        offset=MyOffset(1, 0) if MyOffset else None, 
        animate_offset=MyAnimation(300, "easeOut") if MyAnimation else None,
        alignment=ft.alignment.center,
        expand=True,
        visible=False 
    )

    def on_outer_double_tap(e):
        if is_wide_mode:
            reset_viewer_zoom(True)
        else:
            toggle_mobile_zoom_mode(True)

    def on_outer_scroll(e: ft.ScrollEvent):
        if not is_wide_mode: return 
        if e.scroll_delta_y != 0:
            if interactive_viewer.scale < 1.1:
                 interactive_viewer.scale = 1.2
                 outer_gesture_detector.visible = False
                 try: 
                     interactive_viewer.update()
                     outer_gesture_detector.update()
                 except: pass

    def on_outer_scale_update(e: ft.ScaleUpdateEvent):
        if not is_wide_mode: return 
        current_preview_scale = max(1.0, e.scale)
        interactive_viewer.scale = current_preview_scale
        try: interactive_viewer.update()
        except: pass

    def on_outer_scale_end(e: ft.ScaleEndEvent):
        if not is_wide_mode: return
        if interactive_viewer.scale > 1.1:
            outer_gesture_detector.visible = False
            try: outer_gesture_detector.update()
            except: pass
        else:
            reset_viewer_zoom()

    def on_outer_pan_update(e: ft.DragUpdateEvent):
        nonlocal _viewer_drag_offset_x
        if viewer_zoom_level > 1.1: return 
        width = page.width if page.width and page.width > 0 else 360
        _viewer_drag_offset_x += e.delta_x
        ratio = _viewer_drag_offset_x / width
        
        if MyOffset:
            swipe_anim_container.animate_offset = None 
            swipe_anim_container.offset = MyOffset(ratio, 0)
        
        if abs(_viewer_drag_offset_x) > 10: 
            preload_container.visible = True
            preload_container.animate_offset = None
            target_index = -1
            preload_start_x = 0.0
            
            if _viewer_drag_offset_x < 0: 
                target_index = current_viewer_index + 1
                preload_start_x = 1.0 
            else: 
                target_index = current_viewer_index - 1
                preload_start_x = -1.0
            
            if 0 <= target_index < len(current_viewer_grid_images):
                preload_viewer_img.src = current_viewer_grid_images[target_index].src
                preload_container.offset = MyOffset(preload_start_x + ratio, 0)
            else:
                preload_viewer_img.src = ""
        
        try: 
            swipe_anim_container.update()
            preload_container.update()
        except: pass

    async def on_outer_pan_end(e: ft.DragEndEvent):
        nonlocal _viewer_drag_offset_x
        if viewer_zoom_level > 1.1: return
        width = page.width if page.width and page.width > 0 else 360
        threshold = 60
        anim = MyAnimation(300, "easeOut") if MyAnimation else None
        swipe_anim_container.animate_offset = anim
        preload_container.animate_offset = anim
        
        velocity = getattr(e, "velocity_x", 0)
        should_switch_next = (_viewer_drag_offset_x < -threshold) or (velocity < -500)
        should_switch_prev = (_viewer_drag_offset_x > threshold) or (velocity > 500)

        if should_switch_next and current_viewer_index < len(current_viewer_grid_images) - 1:
            await navigate_viewer(1)
        elif should_switch_prev and current_viewer_index > 0:
            await navigate_viewer(-1)
        else:
            reset_drag_position()
        _viewer_drag_offset_x = 0

    def reset_drag_position():
        if MyOffset:
            swipe_anim_container.offset = MyOffset(0, 0)
            preload_container.offset = MyOffset(1, 0) 
            try: 
                swipe_anim_container.update()
                preload_container.update()
            except: pass
            page.run_task(hide_preload_later)

    async def hide_preload_later():
        await asyncio.sleep(0.3)
        preload_container.visible = False
        try: preload_container.update()
        except: pass

    outer_gesture_detector = ft.GestureDetector(
        content=ft.Container(bgcolor=ft.Colors.TRANSPARENT, expand=True), 
        on_double_tap=on_outer_double_tap,
        on_pan_update=on_outer_pan_update,
        on_pan_end=on_outer_pan_end,
        on_scroll=on_outer_scroll,           
        on_scale_update=on_outer_scale_update, 
        on_scale_end=on_outer_scale_end,     
        expand=True,
        visible=True 
    )

    def reset_viewer_zoom(update_ui=True):
        nonlocal viewer_zoom_level, _viewer_drag_offset_x, is_mobile_zoom_mode
        viewer_zoom_level = 1.0
        _viewer_drag_offset_x = 0.0
        is_mobile_zoom_mode = False 
        
        interactive_viewer.scale = 1.0
        outer_gesture_detector.visible = True 
        preload_container.visible = False
        
        if MyOffset:
            swipe_anim_container.offset = MyOffset(0, 0)
            swipe_anim_container.animate_offset = MyAnimation(300, "easeOut") if MyAnimation else None
            preload_container.offset = MyOffset(1, 0)
        
        if update_ui:
            try:
                interactive_viewer.update()
                outer_gesture_detector.update()
                swipe_anim_container.update()
                preload_container.update()
            except: pass

    current_viewer_grid_images = [] 
    current_viewer_index = 0
    is_animating = False 
    
    viewer_image_stack_content = ft.Stack([
        preload_container,       
        swipe_anim_container,    
        outer_gesture_detector,
        zoom_hint_container  
    ], expand=True, alignment=ft.alignment.center)

    viewer_background_container = ft.Container(
        expand=True, alignment=ft.alignment.center, content=viewer_image_stack_content
    )

    def toggle_overlay_ui(e):
        current_vis = viewer_controls_container.visible
        new_vis = not current_vis
        
        viewer_controls_container.visible = new_vis
        prev_btn.visible = new_vis and is_wide_mode 
        next_btn.visible = new_vis and is_wide_mode
        
        update_viewer_layout_content()


    viewer_info_prompt = ft.Text("无", selectable=True, size=13, color=current_primary_color)
    viewer_info_neg = ft.Text("无", selectable=True, size=13, color=current_primary_color)
    viewer_title_prompt = ft.Text("Prompt", size=11, weight="bold", color=current_primary_color)
    viewer_title_neg = ft.Text("Negative", size=11, weight="bold", color=current_primary_color)

    viewer_copy_prompt_btn = ft.IconButton("content_copy", icon_size=14, icon_color=current_primary_color, on_click=lambda e: copy_text(viewer_info_prompt.value))
    viewer_copy_neg_btn = ft.IconButton("content_copy", icon_size=14, icon_color=current_primary_color, on_click=lambda e: copy_text(viewer_info_neg.value))

    viewer_text_col = ft.Column([
        ft.Row([viewer_title_prompt, viewer_copy_prompt_btn], alignment="spaceBetween"),
        ft.Container(content=viewer_info_prompt, padding=ft.padding.only(bottom=5)), 
        ft.Divider(height=10, color="white24"),
        ft.Row([viewer_title_neg, viewer_copy_neg_btn], alignment="spaceBetween"),
        ft.Container(content=viewer_info_neg),
    ], scroll=ft.ScrollMode.ALWAYS, expand=True)

    viewer_info_container = ft.Container(
        content=viewer_text_col,
        padding=15, 
        bgcolor=get_dropdown_bgcolor(),
        border_radius=ft.border_radius.only(top_left=15, top_right=15),
        shadow=ft.BoxShadow(blur_radius=15, color=ft.Colors.with_opacity(0.3, "black")),
        expand=True,
        visible=False, 
        animate_opacity=200,
        opacity=0
    )
    
    async def navigate_viewer(delta):
        nonlocal current_viewer_index, is_animating, _viewer_drag_offset_x
        if is_animating: return 
        if not current_viewer_grid_images: return
        new_index = current_viewer_index + delta
        
        if new_index < 0:
            reset_drag_position()
            page.snack_bar = ft.SnackBar(ft.Text("已经是第一张了"), open=True)
            page.update()
            return
        if new_index >= len(current_viewer_grid_images):
            reset_drag_position()
            page.snack_bar = ft.SnackBar(ft.Text("已经是最后一张了"), open=True)
            page.update()
            return

        is_animating = True
        target_img_obj = current_viewer_grid_images[new_index]
        preload_viewer_img.src = target_img_obj.src
        preload_container.visible = True
        
        start_preload_x = 1.0 if delta > 0 else -1.0
        end_main_x = -1.0 if delta > 0 else 1.0
        
        if swipe_anim_container.offset.x == 0:
            preload_container.animate_offset = None
            preload_container.offset = MyOffset(start_preload_x, 0)
            preload_container.update()
        
        anim_setting = MyAnimation(300, "easeOut") if MyAnimation else None
        swipe_anim_container.animate_offset = anim_setting
        preload_container.animate_offset = anim_setting
        
        swipe_anim_container.update()
        preload_container.update()
        await asyncio.sleep(0.05)
        
        swipe_anim_container.offset = MyOffset(end_main_x, 0)
        preload_container.offset = MyOffset(0, 0)
        
        try:
            swipe_anim_container.update()
            preload_container.update()
        except: pass
        
        await asyncio.sleep(0.35)
        
        current_viewer_index = new_index
        inner_viewer_img.src = target_img_obj.src 
        reset_viewer_zoom(update_ui=False)
        
        swipe_anim_container.animate_offset = None
        preload_container.animate_offset = None
        
        swipe_anim_container.offset = MyOffset(0, 0) 
        preload_container.offset = MyOffset(1.0, 0)  
        preload_container.visible = False
        
        try:
            swipe_anim_container.update()
            preload_container.update()
        except: pass
        
        meta = getattr(target_img_obj, "data", None)
        if meta:
            viewer_info_prompt.value = meta.get("prompt", "无")
            viewer_info_neg.value = meta.get("negative_prompt", "无")
        else:
            viewer_info_prompt.value = "无数据"
            viewer_info_neg.value = "无数据"
        
        sync_viewer_btns_state()
        
        total = len(current_viewer_grid_images)
        prev_btn.disabled = (current_viewer_index <= 0)
        next_btn.disabled = (current_viewer_index >= total - 1)
        try: viewer_overlay.update()
        except: pass
        
        is_animating = False
        _viewer_drag_offset_x = 0

    async def on_prev_click(e):
        await navigate_viewer(-1)

    async def on_next_click(e):
        await navigate_viewer(1)

    prev_btn = ft.IconButton("chevron_left", icon_color="white", icon_size=30, bgcolor=get_opacity_color(0.3, "black"), on_click=on_prev_click, visible=False, tooltip="上一张")
    next_btn = ft.IconButton("chevron_right", icon_color="white", icon_size=30, bgcolor=get_opacity_color(0.3, "black"), on_click=on_next_click, visible=False, tooltip="下一张")
    
    viewer_control_btns = []
    def create_control_btn(icon_name, tooltip, func):
        btn = ft.IconButton(icon=icon_name, icon_color="white", icon_size=20, tooltip=tooltip, on_click=func, bgcolor="transparent")
        viewer_control_btns.append(btn)
        return btn
    
    async def on_viewer_save_local(e):
        if inner_viewer_img.src:
            img_obj = current_viewer_grid_images[current_viewer_index]
            meta = getattr(img_obj, "data", None)
            success = await save_image_to_local_folder(inner_viewer_img.src, meta)
            if success:
                img_obj.is_downloaded = True
                sync_viewer_btns_state() 
                try: viewer_overlay.update()
                except: pass
                if hasattr(img_obj, "associated_dl_btn"): mark_btn_downloaded(img_obj.associated_dl_btn)
                if hasattr(img_obj, "associated_browser_btn"): mark_btn_downloaded(img_obj.associated_browser_btn)

    async def on_viewer_browser_dl(e):
        if inner_viewer_img.src:
            img_obj = current_viewer_grid_images[current_viewer_index]
            meta = getattr(img_obj, "data", None)
            success = await download_via_local_server(inner_viewer_img.src, meta)
            if success:
                img_obj.is_downloaded = True
                sync_viewer_btns_state()
                try: viewer_overlay.update()
                except: pass
                if hasattr(img_obj, "associated_dl_btn"): mark_btn_downloaded(img_obj.associated_dl_btn)
                if hasattr(img_obj, "associated_browser_btn"): mark_btn_downloaded(img_obj.associated_browser_btn)

    def toggle_viewer_info(e):
        nonlocal is_viewer_info_open
        is_viewer_info_open = not is_viewer_info_open
        btn_info.icon = "info" if is_viewer_info_open else "info_outline"
        update_viewer_layout_content()
    
    def sync_viewer_btns_state():
        if 0 <= current_viewer_index < len(current_viewer_grid_images):
            img_obj = current_viewer_grid_images[current_viewer_index]
            is_downloaded = getattr(img_obj, "is_downloaded", False)
            if is_downloaded:
                mark_btn_downloaded(viewer_dl_btn)
                mark_btn_downloaded(btn_browser_dl)
            else:
                viewer_dl_btn.icon = "save_alt"
                viewer_dl_btn.icon_color = current_primary_color
                viewer_dl_btn.disabled = False
                viewer_dl_btn.tooltip = "保存到本地 (T2I目录)"
                btn_browser_dl.icon = "public"
                btn_browser_dl.icon_color = current_primary_color
                btn_browser_dl.disabled = False
                btn_browser_dl.tooltip = "浏览器下载"
                
                try: viewer_dl_btn.update()
                except: pass
                try: btn_browser_dl.update()
                except: pass

    btn_info = create_control_btn("info_outline", "显示/隐藏详细信息", toggle_viewer_info)
    btn_reset = create_control_btn("restart_alt", "重置大小", lambda e: reset_viewer_zoom(True))
    viewer_dl_btn = create_control_btn("save_alt", "保存到本地 (I2I_Edits)", on_viewer_save_local)
    btn_browser_dl = create_control_btn("public", "浏览器下载", on_viewer_browser_dl)
    btn_close = create_control_btn("close", "关闭", close_viewer)

    viewer_controls_row = ft.Row(
        controls=[btn_info, btn_reset, btn_browser_dl, viewer_dl_btn, ft.Container(width=1, height=20, bgcolor="white54"), btn_close], 
        alignment=ft.MainAxisAlignment.END, spacing=5
    )
    
    viewer_controls_container = ft.Container(
        content=viewer_controls_row,
        padding=5,
        bgcolor=ft.Colors.TRANSPARENT 
    )

    viewer_text_col = ft.Column([], scroll=ft.ScrollMode.ALWAYS, expand=True)

    viewer_info_container = ft.Container(
        content=viewer_text_col,
        padding=15, 
        bgcolor=ft.Colors.TRANSPARENT, 
        border_radius=ft.border_radius.only(top_left=15, top_right=15),
        expand=True
    )

    viewer_info_wrapper = ft.Container(
        content=viewer_info_container,
        height=0, 
        animate=MyAnimation(300, "easeOut") if MyAnimation else None,
        clip_behavior=ft.ClipBehavior.HARD_EDGE, 
        bgcolor=ft.Colors.TRANSPARENT,
    )

    viewer_main_column = ft.Column(
        spacing=0,
        controls=[
            ft.Container(
                content=ft.Stack([
                    viewer_background_container, 
                    ft.Container(content=prev_btn, left=15, top=0, bottom=0, alignment=ft.alignment.center_left, width=60),
                    ft.Container(content=next_btn, right=15, top=0, bottom=0, alignment=ft.alignment.center_right, width=60),
                ], expand=True),
                expand=True, 
            ),
            viewer_info_wrapper, 
            ft.Container(content=viewer_controls_container, bgcolor=ft.Colors.TRANSPARENT)
        ],
        expand=True
    )

    wide_sidebar_info_col = ft.Column(scroll=ft.ScrollMode.ALWAYS, expand=True)

    wide_sidebar_container = ft.Container(
        width=320,
        bgcolor=ft.Colors.TRANSPARENT,
        border=ft.border.only(left=ft.BorderSide(1, "white24")),
        content=ft.Column([
            ft.Container(content=wide_sidebar_info_col, padding=15, expand=True),
            ft.Divider(height=1, color="white24"),
        ], spacing=0, expand=True),
        visible=False 
    )

    final_viewer_layout = ft.Row(
        controls=[
            viewer_main_column,
            wide_sidebar_container
        ],
        spacing=0,
        expand=True
    )

    def update_viewer_layout_content():
        bg_color = get_dropdown_bgcolor()
        viewer_info_wrapper.bgcolor = bg_color
        viewer_info_container.bgcolor = bg_color
        wide_sidebar_container.bgcolor = bg_color
        
        info_controls_list = [
            ft.Row([viewer_title_prompt, viewer_copy_prompt_btn], alignment="spaceBetween"),
            ft.Container(content=viewer_info_prompt, padding=ft.padding.only(bottom=5)), 
            ft.Divider(height=10, color="white24"),
            ft.Row([viewer_title_neg, viewer_copy_neg_btn], alignment="spaceBetween"),
            ft.Container(content=viewer_info_neg),
        ]

        if is_wide_mode:
            wide_sidebar_container.visible = is_viewer_info_open 
            viewer_main_column.controls[2].bgcolor = bg_color
            viewer_text_col.controls.clear() 
            wide_sidebar_info_col.controls = info_controls_list 
            viewer_info_wrapper.height = 0
            prev_btn.visible = True
            next_btn.visible = True

        else:
            wide_sidebar_container.visible = False
            if is_viewer_info_open:
                viewer_main_column.controls[2].bgcolor = bg_color 
            else:
                viewer_main_column.controls[2].bgcolor = ft.Colors.TRANSPARENT
            wide_sidebar_info_col.controls.clear() 
            viewer_text_col.controls = info_controls_list 
            if is_viewer_info_open:
                viewer_info_wrapper.height = 200 
                viewer_info_container.visible = True
                viewer_info_wrapper.opacity = 1
            else:
                viewer_info_wrapper.height = 0   
                viewer_info_wrapper.opacity = 0
            prev_btn.visible = False
            next_btn.visible = False

        try:
            viewer_text_col.update()
            wide_sidebar_info_col.update()
            if viewer_overlay.visible: viewer_overlay.update()
            viewer_info_wrapper.update()
            viewer_main_column.update()
            wide_sidebar_container.update()
        except: pass

    viewer_overlay = ft.Container(
        content=final_viewer_layout, 
        visible=False, 
        expand=True, 
        bgcolor=BG_DARK, 
        top=0, left=0, right=0, bottom=0
    )

    def show_image_viewer(src):
        if not src: return
        nonlocal current_viewer_grid_images, current_viewer_index, is_viewer_info_open
        
        is_viewer_info_open = False 
        btn_info.icon = "info_outline"
        
        bg = get_viewer_bgcolor_dynamic()
        viewer_overlay.bgcolor = bg
        viewer_background_container.bgcolor = bg
        
        current_viewer_grid_images = []
        target_index = 0
        idx_counter = 0

        for ctrl in results_grid.controls:
            try:
                stack = ctrl.content
                img_container = stack.controls[1]
                img_obj = img_container.content
                if img_obj.src:
                    current_viewer_grid_images.append(img_obj)
                    if img_obj.src == src:
                        target_index = idx_counter
                    idx_counter += 1
            except: pass
        
        current_viewer_index = target_index
        inner_viewer_img.src = src
        reset_viewer_zoom(update_ui=False) 
        
        img_obj = current_viewer_grid_images[current_viewer_index]
        meta = getattr(img_obj, "data", None)
        if meta:
            viewer_info_prompt.value = meta.get("prompt", "无")
            viewer_info_neg.value = meta.get("negative_prompt", "无")
        else:
            viewer_info_prompt.value = "无数据"
            viewer_info_neg.value = "无数据"
            
        if is_wide_mode:
            viewer_dl_btn.visible = True
            btn_browser_dl.visible = False
        else:
            viewer_dl_btn.visible = False
            btn_browser_dl.visible = True
            
        update_viewer_layout_content()
        sync_viewer_btns_state()

        if not is_wide_mode:
            gallery_control_gesture.visible = False
            gallery_control_gesture.update()

        viewer_overlay.visible = True
        viewer_overlay.update()

    def get_all_models():
        custom_models = []
        try:
            custom_text = stored_custom_models
            for line in custom_text.strip().split('\n'):
                if not line.strip(): continue
                parts = line.strip().split(None, 1)
                if len(parts) >= 2:
                    custom_models.append({"key": parts[1], "text": parts[0]})
        except: pass
        return DEFAULT_MODEL_OPTIONS + custom_models

    def refresh_model_dropdown():
        all_models = get_all_models()
        model_dropdown.options = [ft.dropdown.Option(m["key"], m["text"]) for m in all_models]
        if model_dropdown.value and not any(m["key"] == model_dropdown.value for m in all_models):
            model_dropdown.value = all_models[0]["key"] if all_models else None
        model_dropdown.update()

    custom_models_input = ft.TextField(
        hint_text="请输入模型，每行一个，格式：\n模型显示名称 模型地址",
        multiline=True, min_lines=10, max_lines=15, text_size=12, border_radius=10, 
    )

    async def save_custom_models(e):
        nonlocal stored_custom_models
        text = custom_models_input.value or ""
        stored_custom_models = text
        await save_config("custom_models", text)
        refresh_model_dropdown()
        safe_close_dialog(custom_model_dialog)
        page.snack_bar = ft.SnackBar(ft.Text("自定义模型已保存"), open=True)
        page.update()

    custom_model_dialog = ft.AlertDialog(
        title=ft.Text("自定义模型", weight="bold", size=14),
        modal=True, surface_tint_color=ft.Colors.TRANSPARENT,
        content=ft.Container(
            width=300, 
            content=ft.Column([
                ft.Text("模型列表（每行一个，格式：显示名称 模型地址）", size=12, color="grey"), 
                ft.Container(height=8), 
                custom_models_input
            ], tight=True, spacing=0)
        ),
        actions=[
            ft.TextButton("取消", on_click=lambda e: safe_close_dialog(custom_model_dialog)), 
            ft.ElevatedButton("保存并应用", bgcolor=current_primary_color, color="white", on_click=save_custom_models)
        ],
        actions_alignment="end"
    )

    def open_custom_model_dialog(e):
        try: custom_models_input.value = stored_custom_models
        except: pass
        safe_open_dialog(custom_model_dialog)

    def on_model_search_change(e):
        query = (e.control.value or "").lower().strip()
        all_models = get_all_models()
        if query: filtered = [m for m in all_models if query in m["text"].lower() or query in m["key"].lower()]
        else: filtered = all_models
        model_dropdown.options = [ft.dropdown.Option(m["key"], m["text"]) for m in filtered]
        current_value = model_dropdown.value
        if filtered:
            if not any(m["key"] == current_value for m in filtered): model_dropdown.value = filtered[0]["key"]
        else: model_dropdown.value = None
        model_dropdown.update()

    def on_model_change(e):
        update_upload_area()

    model_search_field = ft.TextField(
        hint_text="搜索...", text_size=12, height=INPUT_HEIGHT,
        content_padding=ft.padding.symmetric(horizontal=10, vertical=0), border_radius=8, bgcolor="transparent",
        border_color=get_border_color(), border_width=1, on_change=on_model_search_change, width=SEARCH_WIDTH 
    )

    model_dropdown = ft.Dropdown(
        options=[ft.dropdown.Option(m["key"], m["text"]) for m in get_all_models()],
        value=DEFAULT_MODEL_OPTIONS[0]["key"], 
        text_size=14, content_padding=ft.padding.only(left=10, right=10, bottom=5),
        border_color="transparent", border_width=0, fill_color=get_dropdown_bgcolor(), bgcolor=get_dropdown_fill_color(),
        focused_bgcolor=ft.Colors.TRANSPARENT, expand=True,
        on_change=on_model_change 
    )
    
    model_dropdown_container = ft.Container(content=model_dropdown, height=INPUT_HEIGHT, border=ft.border.all(1, get_border_color()), border_radius=8, expand=True, alignment=ft.alignment.center_left)
    custom_model_btn = ft.ElevatedButton("自定义", height=INPUT_HEIGHT, width=CUSTOM_BTN_WIDTH, bgcolor="transparent", color=current_primary_color, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=0, padding=0, side=ft.BorderSide(1, get_border_color())), on_click=open_custom_model_dialog)
    model_row = ft.Row([model_dropdown_container, model_search_field, custom_model_btn], spacing=5)

    def handle_translate(e, input_field, to_lang):
        text = input_field.value
        if not text: return
        res = translate_text(text, to_lang)
        if res:
            input_field.value = res
            input_field.update()

    def show_prompt_actions(e, action_row):
        action_row.visible = True 
        action_row.update()
        action_row.opacity = 1    
        action_row.update()

    async def hide_prompt_actions(e, action_row):
        await asyncio.sleep(0.2)
        action_row.opacity = 0    
        action_row.update()
        await asyncio.sleep(0.35) 
        action_row.visible = False 
        action_row.update()

    async def on_prompt_blur(e): await hide_prompt_actions(e, prompt_trans_row)
    async def on_neg_blur(e): await hide_prompt_actions(e, neg_trans_row)

    def apply_metadata_from_path(file_path):
        if not file_path: return
        try:
            with open(file_path, 'rb') as f:
                image_bytes = f.read()
            
            meta = extract_metadata_from_png(image_bytes)
            
            if meta and isinstance(meta, dict):
                has_update = False
                if "prompt" in meta:
                    prompt_input.value = meta["prompt"]
                    has_update = True
                if "negative_prompt" in meta:
                    neg_prompt_input.value = meta["negative_prompt"]
                    has_update = True
                
                if has_update:
                    prompt_input.update()
                    neg_prompt_input.update()
                    page.snack_bar = ft.SnackBar(ft.Text("✅ 已读取元数据"), open=True)
                    page.update()
        except Exception as e:
            print(f"元数据读取失败: {e}")

    upload_content_container = ft.Container()

    def remove_image(idx):
        if 0 <= idx < len(uploaded_files):
            uploaded_files.pop(idx)
            update_upload_area()

    def update_upload_area():
        is_multi_mode = model_dropdown.value in MODELS_REQUIRING_LIST_INPUT
        
        placeholder = ft.Column([
            ft.Icon("cloud_upload", size=30, color="grey"),
            ft.Text("点击上传图片", size=12, color="grey"), 
            ft.Text("支持多图模式" if is_multi_mode else "单图模式", size=10, color="grey")
        ], alignment="center", horizontal_alignment="center", spacing=2)

        if not uploaded_files:
            upload_content_container.content = ft.Container(
                content=placeholder, 
                alignment=ft.alignment.center,
                on_click=lambda _: upload_file_picker.pick_files(
                    allow_multiple=is_multi_mode, 
                    allowed_extensions=["png", "jpg", "jpeg", "webp"]
                )
            )
            try: upload_content_container.update()
            except: pass
            return

        if not is_multi_mode:
            file_path = uploaded_files[0]
            img_view = ft.Image(src=file_path, fit=ft.ImageFit.CONTAIN, border_radius=8)
            clear_btn = ft.Container(
                content=ft.IconButton(icon="close", icon_size=20, icon_color="red", on_click=lambda e: remove_image(0)),
                top=5, right=5
            )
            upload_content_container.content = ft.Stack([
                ft.Container(content=img_view, padding=5, alignment=ft.alignment.center),
                clear_btn
            ])
            upload_content_container.on_click = lambda _: upload_file_picker.pick_files(allow_multiple=False, allowed_extensions=["png", "jpg", "jpeg", "webp"])
        else:
            thumbs = []
            for i, path in enumerate(uploaded_files):
                img_thumb = ft.Image(src=path, fit=ft.ImageFit.COVER, width=100, height=100, border_radius=8)
                rm_btn = ft.Container(
                    content=ft.IconButton(icon="close", icon_size=16, icon_color="white", on_click=lambda e, idx=i: remove_image(idx)),
                    bgcolor="#88000000", border_radius=15, width=24, height=24, top=2, right=2
                )
                thumb_container = ft.Container(
                    width=100, height=100,
                    content=ft.Stack([img_thumb, rm_btn]),
                    border=ft.border.all(1, get_border_color()),
                    border_radius=8
                )
                thumbs.append(thumb_container)

            add_btn = ft.Container(
                width=100, height=100,
                border=ft.border.all(1, get_border_color()),
                border_radius=8,
                bgcolor=get_opacity_color(0.1, current_primary_color),
                alignment=ft.alignment.center,
                content=ft.Icon("add", size=30, color="grey"),
                on_click=lambda _: upload_file_picker.pick_files(allow_multiple=True, allowed_extensions=["png", "jpg", "jpeg", "webp"])
            )
            thumbs.append(add_btn)
            
            upload_content_container.content = ft.Row(
                thumbs, scroll=ft.ScrollMode.AUTO, spacing=10, alignment="start"
            )
            upload_content_container.on_click = None

        try: upload_content_container.update()
        except: pass

    def on_upload_file_picked(e: ft.FilePickerResultEvent):
        if e.files:
            try:
                is_multi = model_dropdown.value in MODELS_REQUIRING_LIST_INPUT
                new_paths = [f.path for f in e.files]
                if is_multi:
                    uploaded_files.extend(new_paths)
                else:
                    uploaded_files.clear()
                    uploaded_files.append(new_paths[0])
            except Exception as err:
                print(f"文件处理错误: {err}")
            update_upload_area()

    upload_file_picker = ft.FilePicker(on_result=on_upload_file_picked)
    page.overlay.append(upload_file_picker)

    upload_container = ft.Container(
        content=upload_content_container,
        height=140,
        border=ft.border.all(1, get_border_color()),
        border_radius=10,
        bgcolor=get_dropdown_bgcolor(),
        padding=10,
        animate=MyAnimation(300, "easeOut") if MyAnimation else None
    )

    meta_file_picker = ft.FilePicker(on_result=lambda e: apply_metadata_from_path(e.files[0].path) if e.files else None)
    page.overlay.append(meta_file_picker)

    prompt_input = ft.TextField(
        hint_text="编辑指令 (例如: 把衣服改成红色)...", multiline=True, expand=True, text_size=13, bgcolor="transparent", 
        filled=False, border=ft.InputBorder.NONE, content_padding=ft.padding.only(left=10, top=10, right=10, bottom=32),
        on_focus=lambda e: show_prompt_actions(e, prompt_trans_row), on_blur=on_prompt_blur,
    )
    
    prompt_trans_row = ft.Row(
        [
         ft.IconButton("folder_open", icon_size=16, tooltip="读取元数据文件", on_click=lambda _: meta_file_picker.pick_files(allow_multiple=False, allowed_extensions=["png"])),
         ft.IconButton("language", icon_size=16, tooltip="转英文", on_click=lambda e: handle_translate(e, prompt_input, "en")),
         ft.IconButton("translate", icon_size=16, tooltip="转中文", on_click=lambda e: handle_translate(e, prompt_input, "zh"))
        ], right=5, bottom=2, opacity=0, animate_opacity=300, visible=False 
    )

    prompt_container = ft.Container(
        content=ft.Stack([prompt_input, prompt_trans_row], expand=True), 
        height=120,  
        border=ft.border.all(1, get_border_color()), border_radius=10, on_click=lambda e: prompt_input.focus()
    )

    neg_prompt_input = ft.TextField(
        hint_text="负面提示词...", multiline=True, min_lines=2, max_lines=6, value="噪点，模糊，低画质，色调艳丽，过曝，细节模糊不清，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指",
        text_size=13, bgcolor="transparent", filled=False, border=ft.InputBorder.NONE, content_padding=ft.padding.only(left=10, top=10, right=10, bottom=32),
        on_focus=lambda e: show_prompt_actions(e, neg_trans_row), on_blur=on_neg_blur 
    )

    neg_trans_row = ft.Row(
        [
         ft.IconButton("language", icon_size=16, tooltip="转英文", on_click=lambda e: handle_translate(e, neg_prompt_input, "en")),
         ft.IconButton("translate", icon_size=16, tooltip="转中文", on_click=lambda e: handle_translate(e, neg_prompt_input, "zh"))
        ], right=5, bottom=2, opacity=0, animate_opacity=300, visible=False 
    )

    neg_prompt_container = ft.Container(
        content=ft.Stack([neg_prompt_input, neg_trans_row]), border=ft.border.all(1, get_border_color()), border_radius=10, alignment=ft.alignment.top_left, on_click=lambda e: neg_prompt_input.focus()
    )

    size_dropdown = ft.Dropdown(
        options=[ft.dropdown.Option(s["key"], s["text"]) for s in SIZE_OPTIONS], value="AutoSize", 
        text_size=14, content_padding=ft.padding.only(left=10, right=10, bottom=5), border_color="transparent", border_width=0,
        fill_color=get_dropdown_bgcolor(), bgcolor=get_dropdown_fill_color(), focused_bgcolor=ft.Colors.TRANSPARENT, expand=True
    )
    
    size_dropdown_container = ft.Container(content=size_dropdown, height=INPUT_HEIGHT, border=ft.border.all(1, get_border_color()), border_radius=8, expand=True, alignment=ft.alignment.center_left)
    
    custom_size_w = ft.TextField(label="宽度", expand=True, keyboard_type="number", text_size=12, height=40, content_padding=10)
    custom_size_h = ft.TextField(label="高度", expand=True, keyboard_type="number", text_size=12, height=40, content_padding=10)

    def confirm_custom_size(e):
        w = custom_size_w.value
        h = custom_size_h.value
        if w and h:
            new_key = f"{w}x{h}"
            exists = False
            for opt in size_dropdown.options:
                if opt.key == new_key:
                    exists = True
                    break
            if not exists: size_dropdown.options.insert(0, ft.dropdown.Option(new_key, f"{new_key} (自定义)"))
            size_dropdown.value = new_key
            size_dropdown.update()
        safe_close_dialog(custom_size_dialog)

    custom_size_dialog = ft.AlertDialog(
        title=ft.Text("自定义分辨率", size=14), surface_tint_color=ft.Colors.TRANSPARENT,
        content=ft.Container(
            width=300, padding=ft.padding.symmetric(horizontal=10),
            content=ft.Row([custom_size_w, ft.Text("x", size=14), custom_size_h], alignment="center")
        ),
        actions=[
            ft.TextButton("取消", on_click=lambda e: safe_close_dialog(custom_size_dialog)), 
            ft.ElevatedButton("确定", on_click=confirm_custom_size, bgcolor=current_primary_color, color="white")
        ],
        actions_alignment="end"
    )

    custom_size_btn = ft.ElevatedButton("自定义", height=INPUT_HEIGHT, width=CUSTOM_BTN_WIDTH, bgcolor="transparent", color=current_primary_color, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=0, padding=0, side=ft.BorderSide(1, get_border_color())), on_click=lambda e: safe_open_dialog(custom_size_dialog))
    size_row = ft.Row([size_dropdown_container, custom_size_btn], spacing=5)

    def create_slider_row(label, min_v, max_v, def_v, step=1):
        slider = ft.Slider(
            min=min_v, 
            max=max_v, 
            value=def_v, 
            label="{value}", 
            expand=True, 
            active_color=current_primary_color
        )
        val_text = ft.Text(str(def_v), width=40, size=14, text_align="center")

        def on_change(e):
            raw_val = e.control.value
            snapped_val = round(raw_val / step) * step
            if step < 1:
                val_text.value = f"{snapped_val:.1f}"
            else:
                val_text.value = str(int(snapped_val))
            val_text.update()
            
        slider.on_change = on_change
        return ft.Row([ft.Text(label, size=14, width=60, color="grey"), slider, val_text], alignment="center", vertical_alignment="center"), slider, val_text

    initial_key_count = max(1, len(current_api_keys))
    batch_row, batch_slider, batch_val_text = create_slider_row("生图数量", 1, max(1, initial_key_count), initial_key_count)
    steps_row, steps_slider, steps_val_text = create_slider_row("生图步数", 5, 100, 30, 5) 
    guidance_row, guidance_slider, guidance_val_text = create_slider_row("引导系数", 1, 20, 3.5, 0.5) 

    def validate_seed(e):
        if not seed_input.value or not seed_input.value.strip():
            seed_input.value = "-1"
            seed_input.update()
    seed_input = ft.TextField(
        value="-1", 
        text_size=12, 
        height=INPUT_HEIGHT, 
        content_padding=ft.padding.symmetric(horizontal=10, vertical=0),
        border_radius=8, 
        bgcolor="transparent", 
        border_color=get_border_color(), 
        border_width=1, 
        keyboard_type="number", 
        expand=True,
        on_blur=validate_seed  
    )
    seed_row = ft.Row([ft.Text("随机种子", size=14, width=60, color="grey"), seed_input], alignment="center", vertical_alignment="center")

    generate_btn = ft.ElevatedButton(
        "开始编辑", icon="auto_fix_high", bgcolor=current_primary_color, color="white", height=50, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)), width=float("inf")
    )

    results_grid = ft.GridView(expand=True, runs_count=None, max_extent=350, child_aspect_ratio=1.0, spacing=10, run_spacing=10, padding=10)
    
    def create_result_card_ui(index):
        img = ft.Image(src="", fit=ft.ImageFit.COVER, visible=False, expand=True, animate_opacity=300, border_radius=10)
        img.is_downloaded = False 
        
        loading_ring = ft.ProgressRing(width=25, height=25, stroke_width=3, color=current_primary_color)
        status_text = ft.Text(f"排队中...", size=11, color=current_primary_color, text_align="center")
        status_text.associated_ring = loading_ring 

        loading_col = ft.Column(
            controls=[
                loading_ring,
                ft.Container(height=5),
                status_text
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=0
        )

        overlay_prompt = ft.Text("", size=11, color=current_primary_color, selectable=True)
        overlay_neg = ft.Text("", size=11, color=current_primary_color, selectable=True)
        
        def copy_overlay_text(txt): copy_text(txt)

        meta_overlay = ft.Container(
            visible=False,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.WHITE), 
            blur=ft.Blur(10, 10, ft.BlurTileMode.MIRROR), 
            padding=10, alignment=ft.alignment.top_left,
            content=ft.Column([
                ft.Row([ft.Text("Prompt", size=10, color=current_primary_color, weight="bold"), ft.IconButton("content_copy", icon_size=12, icon_color=current_primary_color, on_click=lambda e: copy_overlay_text(overlay_prompt.value))], alignment="spaceBetween"),
                overlay_prompt, 
                ft.Divider(height=10, color=current_primary_color),
                ft.Row([ft.Text("Negative", size=10, color=current_primary_color, weight="bold"), ft.IconButton("content_copy", icon_size=12, icon_color=current_primary_color, on_click=lambda e: copy_overlay_text(overlay_neg.value))], alignment="spaceBetween"),
                overlay_neg
            ], scroll=ft.ScrollMode.HIDDEN), on_click=lambda e: None 
        )

        def toggle_meta_overlay(e):
            meta = getattr(img, "data", {})
            if meta:
                overlay_prompt.value = meta.get("prompt", "")
                overlay_neg.value = meta.get("negative_prompt", "")
                meta_overlay.visible = not meta_overlay.visible
                meta_overlay.update()
        
        btn_info = ft.IconButton(icon="info_outline", icon_color=current_primary_color, icon_size=18, tooltip="显示提示词", visible=False, on_click=toggle_meta_overlay)
        
        btn_browser = ft.IconButton(icon="public", icon_color=current_primary_color, icon_size=18, tooltip="浏览器下载", visible=False)
        btn_dl = ft.IconButton(icon="save_alt", icon_color=current_primary_color, icon_size=18, tooltip="保存到T2I文件夹", visible=False)

        async def on_browser_click(e):
            if img.src:
                meta = getattr(img, "data", None)
                success = await download_via_local_server(img.src, metadata=meta)
                if success:
                    img.is_downloaded = True
                    mark_btn_downloaded(btn_browser)
                    mark_btn_downloaded(btn_dl)
        
        async def on_dl_click(e):
            if img.src:
                meta = getattr(img, "data", None)
                success = await save_image_to_local_folder(img.src, metadata=meta)
                if success:
                    img.is_downloaded = True
                    mark_btn_downloaded(btn_dl)
                    mark_btn_downloaded(btn_browser) 

        btn_browser.on_click = on_browser_click
        btn_dl.on_click = on_dl_click
        
        img.associated_browser_btn = btn_browser
        img.associated_dl_btn = btn_dl
        
        img_container = ft.Container(content=img, expand=True, border_radius=10, on_click=lambda e: show_image_viewer(img.src) if img.src else None)
        action_bar = ft.Row([btn_info, btn_browser, btn_dl], alignment="end", spacing=0)
        
        card_stack = ft.Stack([
            ft.Container(content=loading_col, alignment=ft.alignment.center, bgcolor=get_opacity_color(0.05, "black"), border_radius=10, expand=True),
            img_container, meta_overlay, ft.Container(content=action_bar, right=0, bottom=0) 
        ], expand=True)

        card = ft.Container(content=card_stack, bgcolor="transparent", border_radius=10, clip_behavior=ft.ClipBehavior.HARD_EDGE)

        return card, img, status_text, btn_dl, btn_info, btn_browser

    async def run_gen(e):
        nonlocal current_api_keys
        
        if not prompt_input.value:
            page.snack_bar = ft.SnackBar(ft.Text("请输入编辑指令"), open=True)
            page.update()
            return
        
        is_power_mode = stored_power_config.get("enabled", False)
        keys_to_use = []
        clean_api_keys = [k.strip() for k in current_api_keys if k and k.strip()]
        
        if is_power_mode:
            selected = stored_power_config.get("selected_keys", [])
            clean_selected = [k.strip() for k in selected if k and k.strip()]
            keys_to_use = [k for k in clean_api_keys if k in clean_selected]
            if not keys_to_use:
                page.snack_bar = ft.SnackBar(ft.Text("❌ 强力模式已开启，但未检测到有效勾选的 API Key"), open=True)
                page.update()
                return
        else:
            keys_to_use = clean_api_keys

        if not keys_to_use:
            page.snack_bar = ft.SnackBar(ft.Text("请先设置 API Key"), open=True)
            page.update()
            return

        generate_btn.disabled = True
        generate_btn.text = "上传图片中..."
        generate_btn.update()
        
        target_size = size_dropdown.value
        aspect_ratio = 1.0
        
        try:
            if target_size == "AutoSize":
                if uploaded_files:
                    dims = get_image_size(uploaded_files[0])
                    if dims and dims[1] != 0:
                        aspect_ratio = dims[0] / dims[1]
            else:
                clean_size = target_size.split()[0]
                parts = clean_size.split('x')
                if len(parts) == 2:
                    aspect_ratio = float(parts[0]) / float(parts[1])
        except Exception:
            aspect_ratio = 1.0

        results_grid.child_aspect_ratio = aspect_ratio
        results_grid.update()
        
        image_url_param = None
        current_model = model_dropdown.value
        is_multi = current_model in MODELS_REQUIRING_LIST_INPUT
        
        try:
            uploaded_urls_list = []
            for path in uploaded_files:
                url = await upload_image_to_host(path)
                if url:
                    uploaded_urls_list.append(url)
                else:
                    raise Exception(f"图片上传失败: {os.path.basename(path)}")
            
            if is_multi:
                image_url_param = uploaded_urls_list
            else:
                image_url_param = uploaded_urls_list[0]
                
        except Exception as up_err:
            page.snack_bar = ft.SnackBar(ft.Text(str(up_err)), open=True)
            generate_btn.disabled = False
            generate_btn.text = "开始编辑"
            generate_btn.update()
            return
        
        if is_wide_mode and left_panel_visible: 
            toggle_left_panel(None)
        
        if not is_wide_mode:
            switch_t2i_page(1)
            
        generate_btn.text = "任务提交中..."
        generate_btn.update()

        batch_count = int(batch_slider.value)
        results_grid.controls.clear()
        
        tasks_ui = []
        for i in range(batch_count):
            card, img, status, btn_dl, btn_info, btn_browser = create_result_card_ui(i)
            results_grid.controls.append(card)
            tasks_ui.append((img, status, btn_dl, btn_info, btn_browser))
        
        results_grid.update()
        page.update()
        
        async def generate_single_image(idx, api_key, ui_refs):
            img_ref, status_ref, dl_ref, info_ref, browser_ref = ui_refs
            
            def toggle_ring(visible):
                if hasattr(status_ref, "associated_ring"):
                    status_ref.associated_ring.visible = visible
                    try: status_ref.associated_ring.update()
                    except: pass

            try:
                toggle_ring(True)
                status_ref.value = "提交中..."
                status_ref.color = current_primary_color
                status_ref.update()
                
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                
                raw_seed = seed_input.value
                if not raw_seed or not raw_seed.strip():
                    seed_val = -1
                else:
                    try: seed_val = int(raw_seed)
                    except ValueError: seed_val = -1
                
                if seed_val == -1: seed_val = random.randint(1, 10000000)
                current_seed = seed_val + idx 

                payload = {
                    "model": current_model,
                    "image_url": image_url_param, 
                    "prompt": prompt_input.value,
                    "negative_prompt": neg_prompt_input.value,
                    "num_inference_steps": int(steps_val_text.value), 
                    "guidance_scale": float(guidance_val_text.value),
                    "num_images_per_prompt": 1, 
                    "seed": current_seed
                }
                
                if size_dropdown.value != "AutoSize":
                    payload["size"] = size_dropdown.value

                def do_post():
                    return requests.post(
                        f"{BASE_URL}v1/images/generations",
                        headers={**headers, "X-ModelScope-Async-Mode": "true"},
                        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
                        timeout=20
                    )
                
                res = await asyncio.to_thread(do_post)
                res.raise_for_status()
                task_id = res.json().get("task_id")
                
                if not task_id: raise Exception("无TaskID")

                for _ in range(60): 
                    await asyncio.sleep(2)
                    def do_poll():
                        return requests.get(
                            f"{BASE_URL}v1/tasks/{task_id}", 
                            headers={**headers, "X-ModelScope-Task-Type": "image_generation"}, 
                            timeout=10
                        )
                    res_poll = await asyncio.to_thread(do_poll)
                    data = res_poll.json()
                    
                    raw_status = data.get("task_status")
                    cn_status = STATUS_TRANSLATIONS.get(raw_status, raw_status)
                    
                    if raw_status == "SUCCEED":
                        toggle_ring(False)

                        output_images = data.get("output_images", [])
                        if not output_images and "results" in data: output_images = data["results"] 
                        
                        if output_images:
                            final_url = output_images[0].get("url", output_images[0]) if isinstance(output_images[0], dict) else output_images[0]
                            img_ref.src = final_url
                            
                            payload["task_type"] = "image-edit"
                            img_ref.data = payload 
                            
                            img_ref.visible = True
                            info_ref.visible = True
                            
                            if is_wide_mode:
                                dl_ref.visible = True
                                browser_ref.visible = False
                            else:
                                dl_ref.visible = False
                                browser_ref.visible = True

                            status_ref.value = "" 
                            img_ref.update()
                            dl_ref.update()
                            info_ref.update()
                            browser_ref.update()
                            status_ref.update()
                        return True
                    elif raw_status == "FAILED":
                        raise Exception(data.get("message", "API Error"))
                    else:
                        status_ref.value = f"{cn_status}..."
                        status_ref.update()
                raise Exception("超时")

            except Exception as e:
                toggle_ring(False)
                status_ref.value = "失败"
                status_ref.tooltip = str(e)
                status_ref.color = "red"
                status_ref.update()
                return False

        tasks = []
        delay_time = float(stored_power_config.get("request_delay", 0.2))

        for i in range(batch_count):
            key_to_use = keys_to_use[i % len(keys_to_use)]
            tasks.append(asyncio.create_task(generate_single_image(i, key_to_use, tasks_ui[i])))
            await asyncio.sleep(delay_time)
        
        await asyncio.gather(*tasks, return_exceptions=True)
        generate_btn.disabled = False
        generate_btn.text = "开始编辑"
        generate_btn.update()

    generate_btn.on_click = run_gen

    def on_file_drop(e: ft.FilePickerResultEvent):
        files = e.files
        if not files: return
        uploaded_files.clear()
        uploaded_files.append(files[0].path)
        update_upload_area()
        apply_metadata_from_path(files[0].path)

    page.on_file_drop = on_file_drop

    page1_scroll_col = ft.Column([
            model_row,
            ft.Container(height=8),
            upload_container,   
            ft.Container(height=8),
            prompt_container,
            ft.Container(height=8),
            neg_prompt_container, 
            ft.Container(height=8),
            size_row, 
            ft.Container(height=8),
            batch_row,
            ft.Container(height=5),
            steps_row,
            ft.Container(height=5),
            guidance_row,
            ft.Container(height=5),
            seed_row,
            ft.Container(height=15),
    ], spacing=0, horizontal_alignment="stretch", expand=True, scroll=ft.ScrollMode.AUTO)

    fixed_bottom_action_bar = ft.Container(
        content=generate_btn,
        padding=ft.padding.symmetric(horizontal=0, vertical=10),
        bgcolor=ft.Colors.TRANSPARENT, 
        border=None,
    )

    page1_content = ft.Container(
        padding=ft.padding.symmetric(horizontal=5, vertical=0),
        expand=True,
        content=ft.Column([
            ft.Container(
                content=page1_scroll_col, 
                expand=True, 
                padding=ft.padding.only(top=10, bottom=10)
            ),
            fixed_bottom_action_bar
        ], spacing=0, expand=True) 
    )

    page2_content = ft.Container(
        padding=ft.padding.symmetric(horizontal=15, vertical=10),
        expand=True,
        content=ft.Column([
            results_grid,  
        ], expand=True, spacing=0) 
    )

    page1_container = ft.Container(content=page1_content, expand=False)
    page2_container = ft.Container(content=page2_content, expand=False)
    
    t2i_slider = ft.Row(
        controls=[page1_container, page2_container],
        spacing=0, alignment="start", vertical_alignment="start", expand=True,
        offset=MyOffset(0, 0) if MyOffset else None,
        animate_offset=MyAnimation(300, "easeOut") if MyAnimation else None
    )

    dot1 = ft.Container(width=10, height=10, border_radius=5, bgcolor=current_primary_color, animate=MyAnimation(200, "easeOut") if MyAnimation else None)
    dot2 = ft.Container(width=10, height=10, border_radius=5, bgcolor="grey", animate=MyAnimation(200, "easeOut") if MyAnimation else None)
    dots_row = ft.Row([dot1, dot2], alignment="center", spacing=8)

    nav_btn_menu_icon = ft.Icon("menu", size=24, color="grey")
    nav_btn_menu_text = ft.Text("菜单", size=10, color="grey")
    nav_btn_func_icon = ft.Icon("palette", size=24, color="grey")
    nav_btn_func_text = ft.Text("文生图", size=10, color="grey")
    nav_btn_gallery_icon = ft.Icon("image", size=24, color="grey")
    nav_btn_gallery_text = ft.Text("图库", size=10, color="grey")
    
    def on_nav_click(index):
        toggle_sidebar(False) 
        switch_t2i_page(index)
    
    def on_menu_btn_click(e):
        if mask.visible: 
            toggle_sidebar(False)
            switch_t2i_page(0)
        else:
            toggle_sidebar(True)

    def create_nav_item(icon, text, on_click_func):
        return ft.Container(
            content=ft.Column(
                [icon, text], 
                spacing=2, 
                alignment=ft.MainAxisAlignment.CENTER, 
                horizontal_alignment=ft.CrossAxisAlignment.CENTER
            ),
            expand=1, 
            alignment=ft.alignment.center,
            padding=ft.padding.symmetric(vertical=5),
            bgcolor=ft.Colors.TRANSPARENT,
            ink=False,
            on_click=on_click_func
        )

    nav_item_menu = create_nav_item(nav_btn_menu_icon, nav_btn_menu_text, on_menu_btn_click)
    nav_item_func = create_nav_item(nav_btn_func_icon, nav_btn_func_text, lambda e: on_nav_click(0))
    nav_item_gallery = create_nav_item(nav_btn_gallery_icon, nav_btn_gallery_text, lambda e: on_nav_click(1))

    bottom_nav_content = ft.Container(
        height=56, 
        bgcolor=get_dropdown_bgcolor(),
        padding=0, 
        border=ft.border.only(top=ft.BorderSide(0.5, "grey")),
        content=ft.Row([
            nav_item_menu,
            nav_item_func, 
            nav_item_gallery
        ], 
        alignment="start",
        spacing=0, 
        expand=True
        ),
    )

    bottom_nav_drag_buffer = 0

    def on_bottom_nav_pan_update(e: ft.DragUpdateEvent):
        nonlocal bottom_nav_drag_buffer
        bottom_nav_drag_buffer += e.delta_x

    def on_bottom_nav_pan_end(e: ft.DragEndEvent):
        nonlocal bottom_nav_drag_buffer
        velocity = getattr(e, "velocity_x", 0)
        DIST_THRESHOLD = 50      
        VELOCITY_THRESHOLD = 800 

        if bottom_nav_drag_buffer < -DIST_THRESHOLD or velocity < -VELOCITY_THRESHOLD:
             if mask.visible: 
                 toggle_sidebar(False)
             elif t2i_page_index == 0: 
                 switch_t2i_page(1)
        elif bottom_nav_drag_buffer > DIST_THRESHOLD or velocity > VELOCITY_THRESHOLD:
             if t2i_page_index == 1: 
                 switch_t2i_page(0)
             elif t2i_page_index == 0 and not mask.visible: 
                 toggle_sidebar(True)
        bottom_nav_drag_buffer = 0

    bottom_nav = ft.GestureDetector(
        content=bottom_nav_content,
        on_pan_update=on_bottom_nav_pan_update,
        on_pan_end=on_bottom_nav_pan_end,
        visible=False
    )

    def update_dots():
        dot1.bgcolor = current_primary_color if t2i_page_index == 0 else "grey"
        dot2.bgcolor = current_primary_color if t2i_page_index == 1 else "grey"
        dot1.update()
        dot2.update()

    def switch_t2i_page(index):
        nonlocal t2i_page_index
        t2i_page_index = index
        
        if mask.visible:
            toggle_sidebar(False)

        if index == 0:
            nav_btn_func_icon.color = current_primary_color
            nav_btn_func_text.color = current_primary_color
            nav_btn_gallery_icon.color = "grey"
            nav_btn_gallery_text.color = "grey"
            view_switch_btn.icon = "image"
            view_switch_btn.tooltip = "查看生成结果"
        else:
            nav_btn_func_icon.color = "grey"
            nav_btn_func_text.color = "grey"
            nav_btn_gallery_icon.color = current_primary_color
            nav_btn_gallery_text.color = current_primary_color
            view_switch_btn.icon = "tune"
            view_switch_btn.tooltip = f"返回{nav_btn_func_text.value}"
            
        nav_item_func.update()
        nav_item_gallery.update()
        view_switch_btn.update()
        
        if is_wide_mode: return 
        
        page1_container.visible = (index == 0)
        page2_container.visible = (index == 1)
        
        t2i_slider.offset = None 
        
        if not is_wide_mode:
            gallery_control_gesture.visible = (index == 1)
            gallery_control_gesture.update()

        page1_container.update()
        page2_container.update()
        t2i_slider.update()
        update_dots()

    def toggle_sidebar(open_it):
        if MyOffset:
            sidebar_container.offset = MyOffset(0 if open_it else -1, 0)
            sidebar_container.update()
        mask.visible = open_it
        mask.opacity = 1 if open_it else 0
        mask.update()
        
        nav_btn_menu_icon.color = current_primary_color if open_it else "grey"
        nav_btn_menu_text.color = current_primary_color if open_it else "grey"
        nav_btn_menu_icon.update()
        nav_btn_menu_text.update()

        if not is_wide_mode:
            if open_it:
                nav_btn_func_icon.color = "grey"
                nav_btn_func_text.color = "grey"
                nav_btn_gallery_icon.color = "grey"
                nav_btn_gallery_text.color = "grey"
            else:
                if t2i_page_index == 0:
                    nav_btn_func_icon.color = current_primary_color
                    nav_btn_func_text.color = current_primary_color
                    nav_btn_gallery_icon.color = "grey"
                    nav_btn_gallery_text.color = "grey"
                else:
                    nav_btn_func_icon.color = "grey"
                    nav_btn_func_text.color = "grey"
                    nav_btn_gallery_icon.color = current_primary_color
                    nav_btn_gallery_text.color = current_primary_color
            
            nav_item_func.update()
            nav_item_gallery.update()

    mask = ft.Container(
        bgcolor=get_opacity_color(0.3, "black"),
        left=0, right=0, top=0, bottom=0, 
        visible=False, animate_opacity=300, opacity=0,
        on_click=lambda e: toggle_sidebar(False)
    )

    api_keys_field = ft.TextField(
        label="ModelScope Keys (每行一个)", 
        value=stored_api_keys_str, 
        multiline=True, 
        min_lines=10, 
        max_lines=25,  
        text_size=12, 
        content_padding=15,
        border_color=get_border_color() 
    )

    baidu_config_field = ft.TextField(
        label="百度翻译配置 (第一行AppID，第二行密钥)", 
        value=stored_baidu_config,
        multiline=True, 
        text_size=12, 
        content_padding=10,
        height=90,    
        border_color=get_border_color()
    )

    async def save_settings(e):
        nonlocal current_api_keys, stored_api_keys_str, stored_baidu_config, current_baidu_appid, current_baidu_key
        stored_api_keys_str = api_keys_field.value
        stored_baidu_config = baidu_config_field.value
        await save_config("api_keys", stored_api_keys_str)
        await save_config("baidu_config", stored_baidu_config)
        current_api_keys = [k.strip() for k in stored_api_keys_str.split('\n') if k.strip()]
        lines = stored_baidu_config.split('\n')
        current_baidu_appid = lines[0].strip() if len(lines) > 0 else ""
        current_baidu_key = lines[1].strip() if len(lines) > 1 else ""
        
        is_pm = stored_power_config.get("enabled", False)
        if not is_pm:
            key_count = len(current_api_keys)
            new_max = max(1, key_count)
            batch_slider.max = new_max
            if batch_slider.value > new_max: batch_slider.value = new_max 
            batch_val_text.value = str(int(batch_slider.value)) 
            batch_slider.update()
            batch_val_text.update()

        safe_close_dialog(settings_dialog)
        page.update()
    
    settings_dialog.content = ft.Column(
        controls=[
            api_keys_field, 
            ft.Container(height=15), 
            baidu_config_field
        ], 
        tight=True,  
        scroll=ft.ScrollMode.AUTO,
        width=300,
        spacing=0
    )
    
    settings_dialog.actions = [ft.TextButton("保存", on_click=save_settings)]

    pm_enabled_switch = ft.Switch(label="启用强力生图", value=False, active_color="amber")
    pm_batch_slider = ft.Slider(min=1, max=50, divisions=49, label="{value}", value=10, active_color="amber")
    pm_delay_slider = ft.Slider(min=0.1, max=3.0, divisions=29, label="{value}秒", value=0.2, active_color="amber")
    pm_keys_container = ft.Column([], spacing=2)
    pm_limit_field = ft.TextField(label="每日API Key可调用的次数 (仅本地统计)", value="200", keyboard_type="number", text_size=12, height=40, content_padding=10)

    async def save_power_mode_settings(e=None):
        nonlocal stored_power_config
        selected_keys_list = []
        for chk in pm_keys_container.controls:
            if isinstance(chk, ft.Checkbox) and chk.value:
                if chk.data: selected_keys_list.append(chk.data.strip())
        
        try: daily_limit = int(pm_limit_field.value)
        except: daily_limit = 200

        new_power_config = {
            "enabled": pm_enabled_switch.value,
            "batch_size": int(pm_batch_slider.value),
            "selected_keys": selected_keys_list,
            "daily_limit": daily_limit,
            "request_delay": float(pm_delay_slider.value)
        }
        
        await save_config("power_mode_config", new_power_config)
        stored_power_config = new_power_config
        
        if new_power_config["enabled"]:
            new_max = int(new_power_config["batch_size"])
            new_max = max(1, new_max)
            batch_slider.max = new_max
            batch_slider.label = "{value} ⚡"
            batch_slider.active_color = "red"
            batch_row.controls[0].value = "⚡ 强力"
            batch_row.controls[0].color = "red"
            batch_row.controls[0].weight = "bold"
        else:
            key_count = len(current_api_keys)
            new_max = max(1, key_count)
            batch_slider.max = new_max
            batch_slider.label = "{value}"
            batch_slider.active_color = current_primary_color
            batch_row.controls[0].value = "生图数量"
            batch_row.controls[0].color = "grey"
            batch_row.controls[0].weight = "normal"
            
        if batch_slider.value > batch_slider.max: batch_slider.value = batch_slider.max
        batch_val_text.value = str(int(batch_slider.value))
        
        safe_close_dialog(power_mode_dialog)
        page.snack_bar = ft.SnackBar(ft.Text("强力模式配置已保存"), open=True)
        page.update()

    async def _init_power_mode_ui():
        pm_enabled_switch.value = stored_power_config.get("enabled", False)
        pm_batch_slider.value = float(stored_power_config.get("batch_size", 10))
        pm_delay_slider.value = float(stored_power_config.get("request_delay", 0.2))
        pm_limit_field.value = str(stored_power_config.get("daily_limit", 200))
        saved_selected = [k.strip() for k in stored_power_config.get("selected_keys", []) if k]
        
        controls_list = []
        
        if not current_api_keys:
            controls_list.append(ft.Text("请先在 API Key 设置中添加 Key", color="red", size=12))
        else:
            for idx, raw_k in enumerate(current_api_keys):
                k = raw_k.strip() 
                if not k: continue
                is_checked = False
                if not saved_selected: is_checked = True 
                else: is_checked = (k in saved_selected)
                chk = ft.Checkbox(label=f"Key {idx+1}", value=is_checked, data=k)
                controls_list.append(chk)
        
        pm_keys_container.controls = controls_list
        power_mode_dialog.content.update()

    def open_power_mode_dialog(e):
        power_mode_dialog.content = ft.Container(
            width=320,
            content=ft.Column([
                ft.Container(height=10),
                pm_enabled_switch,
                ft.Container(height=10),
                ft.Text("您一次想生成的图片数量:", size=12),
                pm_batch_slider,
                ft.Container(height=5),
                ft.Text("任务创建间隔 (防止QPS超限):", size=12),
                pm_delay_slider,
                ft.Divider(height=20, thickness=0.5),
                ft.Text("配置 API Key:", size=12),
                ft.Container(
                    content=pm_keys_container,
                    height=150, 
                    border=ft.border.all(1, get_border_color()),
                    border_radius=5,
                    padding=10,
                ), 
                ft.Container(height=10),
                pm_limit_field,
            ], tight=True, scroll=ft.ScrollMode.AUTO)
        )
        pm_keys_container.scroll = ft.ScrollMode.AUTO
        power_mode_dialog.actions = [
            ft.TextButton("取消", on_click=lambda e: safe_close_dialog(power_mode_dialog)),
            ft.ElevatedButton("保存", on_click=lambda e: page.run_task(save_power_mode_settings), bgcolor="amber", color="black")
        ]
        safe_open_dialog(power_mode_dialog)
        page.run_task(_init_power_mode_ui)

    def open_settings_dialog(e):
        safe_open_dialog(settings_dialog)

    def build_theme_content():
        def handle_color_click(name):
            return lambda e: page.run_task(update_theme, color_name=name)

        def handle_mode_click(mode):
            return lambda e: page.run_task(update_theme, mode=mode)

        def color_dot(name, hex_c):
            is_selected = (hex_c == current_primary_color)
            return ft.Container(
                width=45, height=45, bgcolor=hex_c, border_radius=22,
                on_click=handle_color_click(name),
                border=ft.border.all(3, current_primary_color) if is_selected else None,
                scale=MyScale(1.1 if is_selected else 1.0) if MyScale else None,
                animate_scale=MyAnimation(200, "easeOut") if MyAnimation else None
            )
        def mode_pill(text, mode_val):
            is_active = (mode_val == stored_mode)
            return ft.Container(
                content=ft.Text(text, color=current_primary_color if is_active else "grey", size=14),
                padding=ft.padding.symmetric(horizontal=18, vertical=8),
                border=ft.border.all(1.5, current_primary_color if is_active else "grey"),
                border_radius=20,
                bgcolor=get_opacity_color(0.1, current_primary_color) if is_active else None,
                on_click=handle_mode_click(mode_val)
            )
        return ft.Column([
            ft.Text("莫兰迪色系", size=13, color="grey"),
            ft.Divider(height=10, color="transparent"), 
            ft.Row([color_dot(n, h) for n, h in list(MORANDI_COLORS.items())[:4]], spacing=12, alignment="start"),
            ft.Container(height=8),
            ft.Row([color_dot(n, h) for n, h in list(MORANDI_COLORS.items())[4:]], spacing=12, alignment="start"),
            ft.Divider(height=30, thickness=0.5, color=get_opacity_color(0.2, "grey")), 
            ft.Text("主题模式", size=13, color="grey"),
            ft.Divider(height=10, color="transparent"),
            ft.Row([mode_pill("护眼", "warm"), mode_pill("浅色", "light"), mode_pill("深色", "dark")], alignment="start", spacing=10)
        ], spacing=0, horizontal_alignment="start", tight=True)

    sidebar_theme_icon = ft.Icon("contrast", color="grey", size=24)
    sidebar_theme_text = ft.Text("主题设置", color="grey", size=16)
    sidebar_key_icon = ft.Icon("vpn_key", color="grey", size=24)
    sidebar_key_text = ft.Text("Api_key", color="grey", size=16)
    sidebar_power_icon = ft.Icon("flash_on", color="grey", size=24)
    sidebar_power_text = ft.Text("强力生图模式", color="grey", size=16)

    async def update_theme(mode=None, color_name=None):
        nonlocal current_primary_color, stored_mode
        if color_name:
            hex_val = MORANDI_COLORS[color_name]
            current_primary_color = hex_val
            page.theme = ft.Theme(
                color_scheme_seed=hex_val,
                dialog_theme=ft.DialogTheme(surface_tint_color=ft.Colors.TRANSPARENT),
                slider_theme=ft.SliderTheme(
                    active_tick_mark_color=ft.Colors.TRANSPARENT,
                    inactive_tick_mark_color=ft.Colors.TRANSPARENT
                )
            )
            
            await save_config("theme_color", color_name)
            generate_btn.bgcolor = hex_val
            
            nav_text_ref.color = hex_val
            nav_icon_ref.color = hex_val 
            nav_highlight_ref.bgcolor = hex_val
            
            sidebar_theme_icon.color = "grey" 
            
            is_pm = stored_power_config.get("enabled", False)
            if not is_pm:
                batch_slider.active_color = hex_val
                batch_row.controls[0].color = "grey"
            else:
                batch_slider.active_color = "red"
                batch_row.controls[0].color = "red"
            
            steps_slider.active_color = hex_val
            guidance_slider.active_color = hex_val
            custom_model_btn.color = hex_val
            custom_size_btn.color = hex_val
            
            sidebar_div1.color = get_opacity_color(0.2, hex_val)
            sidebar_div2.color = get_opacity_color(0.2, hex_val)
            sidebar_div1.update()
            sidebar_div2.update()

            update_dots()
            switch_t2i_page(t2i_page_index)

            for card in results_grid.controls:
                try:
                    stack = card.content
                    loading_bg_container = stack.controls[0] 
                    if isinstance(loading_bg_container.content, ft.Column):
                        loading_col = loading_bg_container.content
                        loading_col.controls[0].color = hex_val 
                        loading_col.controls[2].color = hex_val
                    
                    meta_overlay = stack.controls[2]
                    meta_col = meta_overlay.content
                    meta_col.controls[0].controls[0].color = hex_val
                    meta_col.controls[0].controls[1].icon_color = hex_val
                    meta_col.controls[1].color = hex_val
                    meta_col.controls[2].color = hex_val
                    meta_col.controls[3].controls[0].color = hex_val
                    meta_col.controls[3].controls[1].icon_color = hex_val
                    meta_col.controls[4].color = hex_val

                    action_bar_container = stack.controls[3]
                    action_bar_row = action_bar_container.content 
                    for btn in action_bar_row.controls:
                         btn.icon_color = hex_val
                         if btn.icon == "check_circle": 
                             btn.icon_color = hex_val
                except Exception as e: 
                    pass
            
            results_grid.update()

            for btn in viewer_control_btns:
                btn.icon_color = hex_val
                try: btn.update()
                except: pass
            
            prev_btn.icon_color = hex_val
            try: prev_btn.update()
            except: pass
            
            next_btn.icon_color = hex_val
            try: next_btn.update()
            except: pass
            
            viewer_info_prompt.color = hex_val
            viewer_info_neg.color = hex_val
            viewer_title_prompt.color = hex_val
            viewer_title_neg.color = hex_val
            viewer_copy_prompt_btn.icon_color = hex_val
            viewer_copy_neg_btn.icon_color = hex_val

            try: viewer_info_container.update()
            except: pass
            
            viewer_dl_btn.icon_color = hex_val
            btn_browser_dl.icon_color = hex_val
            try: viewer_dl_btn.update()
            except: pass
            try: btn_browser_dl.update()
            except: pass 
            
            zoom_hint_container.bgcolor = get_opacity_color(0.7, hex_val)
            try: zoom_hint_container.update()
            except: pass

        if mode:
            stored_mode = mode 
            await save_config("theme_mode", mode)
            fill = get_dropdown_bgcolor()
            
            fixed_bottom_action_bar.bgcolor = ft.Colors.TRANSPARENT
            
            model_dropdown.fill_color = fill
            model_dropdown.bgcolor = get_dropdown_fill_color() 
            size_dropdown.fill_color = fill
            size_dropdown.bgcolor = get_dropdown_fill_color()
            border_c = get_border_color()
            model_search_field.border_color = border_c
            model_dropdown_container.border = ft.border.all(1, border_c) 
            size_dropdown_container.border = ft.border.all(1, border_c)
            custom_model_btn.style.side = ft.BorderSide(1, border_c)
            custom_size_btn.style.side = ft.BorderSide(1, border_c)
            seed_input.border_color = border_c
            prompt_container.border = ft.border.all(1, border_c)
            neg_prompt_container.border = ft.border.all(1, border_c)
            
            if mode == "dark":
                viewer_bg = BG_DARK 
                sidebar_bg = BG_DARK_DIALOG 
                nav_bg_selected = "#333333" 
                dialog_bg = BG_DARK_DIALOG
                text_color = "white"
                try: page.theme_mode = ft.ThemeMode.DARK
                except: page.theme_mode = "dark"
                page.bgcolor = BG_DARK
                main_content_bg.bgcolor = BG_DARK
                sidebar_container.bgcolor = sidebar_bg
            elif mode == "warm":
                viewer_bg = BG_WARM 
                sidebar_bg = "#F5F0EB" 
                nav_bg_selected = "#EBE6E1" 
                dialog_bg = BG_WARM
                text_color = "#333333"
                try: page.theme_mode = ft.ThemeMode.LIGHT
                except: page.theme_mode = "light"
                page.bgcolor = BG_WARM
                main_content_bg.bgcolor = BG_WARM
                sidebar_container.bgcolor = sidebar_bg
            else: 
                viewer_bg = BG_LIGHT 
                sidebar_bg = "white" 
                nav_bg_selected = "#F0F0F0" 
                dialog_bg = "white"
                text_color = "#333333"
                try: page.theme_mode = ft.ThemeMode.LIGHT
                except: page.theme_mode = "light"
                page.bgcolor = BG_LIGHT
                main_content_bg.bgcolor = BG_LIGHT
                sidebar_container.bgcolor = "white"

            nav_container_ref.bgcolor = nav_bg_selected
            
            theme_dialog.bgcolor = dialog_bg
            settings_dialog.bgcolor = dialog_bg
            custom_model_dialog.bgcolor = dialog_bg
            custom_size_dialog.bgcolor = dialog_bg
            gallery_popup_menu.bgcolor = dialog_bg 
            power_mode_dialog.bgcolor = dialog_bg

            bottom_nav_content.bgcolor = sidebar_bg
            
            if viewer_overlay.visible:
                viewer_overlay.bgcolor = viewer_bg
                viewer_background_container.bgcolor = viewer_bg
                update_viewer_layout_content() 

        if theme_dialog.open:
            theme_dialog.content = ft.Container(content=build_theme_content(), width=300, padding=ft.padding.only(top=10, left=10, right=10))
            theme_dialog.update()
            
        page.update()

    def open_theme_dialog(e):
        theme_dialog.content = ft.Container(content=build_theme_content(), width=300, padding=ft.padding.only(top=10, left=10, right=10))
        theme_dialog.actions = [ft.TextButton("确定", on_click=lambda e: safe_close_dialog(theme_dialog))]
        safe_open_dialog(theme_dialog)

    sidebar_theme_item = ft.Container(
        content=ft.Row([sidebar_theme_icon, ft.Container(width=10), sidebar_theme_text]),
        padding=ft.padding.symmetric(vertical=15, horizontal=20),
        on_click=open_theme_dialog,
        ink=True
    )
    
    sidebar_key_item = ft.Container(
        content=ft.Row([sidebar_key_icon, ft.Container(width=10), sidebar_key_text]),
        padding=ft.padding.symmetric(vertical=15, horizontal=20),
        on_click=open_settings_dialog,
        ink=True
    )
    
    sidebar_power_item = ft.Container(
        content=ft.Row([sidebar_power_icon, ft.Container(width=10), sidebar_power_text]),
        padding=ft.padding.symmetric(vertical=15, horizontal=20),
        on_click=open_power_mode_dialog,
        ink=True
    )

    sidebar_drag_buffer = 0

    def on_sidebar_pan_update(e: ft.DragUpdateEvent):
        nonlocal sidebar_drag_buffer
        sidebar_drag_buffer += e.delta_x

    def on_sidebar_pan_end(e: ft.DragEndEvent):
        nonlocal sidebar_drag_buffer
        velocity = getattr(e, "velocity_x", 0)
        
        if sidebar_drag_buffer < -50 or velocity < -800:
            toggle_sidebar(False)
        
        sidebar_drag_buffer = 0

    sidebar_content = ft.Column([
            ft.Container(padding=ft.padding.symmetric(horizontal=20), on_click=lambda e: toggle_sidebar(False), content=ft.Row([sidebar_icon_ref, ft.Column([sidebar_title_ref, sidebar_subtitle_ref], spacing=2)])),
            sidebar_div1,
            ft.Divider(color="transparent", height=10),
            ft.Container(padding=ft.padding.symmetric(horizontal=10), content=nav_container_ref),
            ft.Container(expand=True),
            sidebar_div2,
            ft.Column([
                sidebar_theme_item,
                sidebar_power_item,
                sidebar_key_item
            ], spacing=0)
        ], expand=True)

    sidebar_gesture_detector = ft.GestureDetector(
        content=sidebar_content,
        on_pan_update=on_sidebar_pan_update, 
        on_pan_end=on_sidebar_pan_end        
    )

    sidebar_container = ft.Container(
        width=200, top=0, bottom=0, bgcolor="white",
        padding=ft.padding.only(top=50, bottom=20), offset=sidebar_offset,
        animate_offset=MyAnimation(300, "easeOut") if MyAnimation else None,
        content=sidebar_gesture_detector 
    )

    def toggle_left_panel(e):
        nonlocal left_panel_visible
        left_panel_visible = not left_panel_visible
        toggle_panel_btn.icon = "keyboard_double_arrow_right" if not left_panel_visible else "keyboard_double_arrow_left"
        toggle_panel_btn.tooltip = "展开参数栏" if not left_panel_visible else "折叠参数栏"
        on_resize(None)
        custom_appbar.update()

    toggle_panel_btn = ft.IconButton("keyboard_double_arrow_left", tooltip="折叠参数栏", on_click=toggle_left_panel, visible=False)
    
    top_menu_btn = ft.IconButton("menu", icon_size=24, on_click=lambda e: toggle_sidebar(True))
    
    view_switch_btn = ft.IconButton(
        icon="image", tooltip="查看生成结果", visible=False,
        on_click=lambda e: switch_t2i_page(1 if t2i_page_index == 0 else 0)
    )

    def set_gallery_columns(cols):
        results_grid.runs_count = cols
        results_grid.max_extent = None 
        results_grid.update()

    gallery_popup_menu = ft.PopupMenuButton(
        icon="circle_outlined",
        icon_size=30,
        tooltip="调整图库布局",
        surface_tint_color=ft.Colors.TRANSPARENT, 
        items=[
            ft.PopupMenuItem(text="1列 (大图)", on_click=lambda e: set_gallery_columns(1)),
            ft.PopupMenuItem(text="2列", on_click=lambda e: set_gallery_columns(2)),
            ft.PopupMenuItem(text="3列", on_click=lambda e: set_gallery_columns(3)),
            ft.PopupMenuItem(text="4列 (小图)", on_click=lambda e: set_gallery_columns(4)),
        ]
    )
    
    gallery_simple_icon = ft.Icon(name="circle_outlined", size=30, color=current_primary_color)

    gallery_control_btn_container = ft.Container(
        content=None,
        bgcolor="transparent", 
    )
    
    def update_gallery_controller_content():
        gallery_control_btn_container.content = gallery_popup_menu
    
    def on_gallery_btn_pan(e: ft.DragUpdateEvent):
        safe_w = float(page.width) if page.width else 360.0
        safe_h = float(page.height) if page.height else 640.0

        sidebar_w = 0
        if is_wide_mode:
             sidebar_w = 300 
             if safe_w * 0.5 > 300: sidebar_w = safe_w * 0.5 
             else: sidebar_w = 300
        
        min_left = sidebar_w + 10 
        max_left = safe_w - 60    

        raw_left = gallery_control_gesture.left
        if raw_left is None or raw_left == "":
            current_left = float(max_left - 20) 
            gallery_control_gesture.right = None 
        else:
            try:
                current_left = float(raw_left)
            except ValueError:
                current_left = float(max_left - 20)

        raw_bottom = gallery_control_gesture.bottom
        if raw_bottom is None or raw_bottom == "":
            current_bottom = 100.0
        else:
            try:
                current_bottom = float(raw_bottom)
            except ValueError:
                current_bottom = 100.0

        new_left = current_left + e.delta_x
        new_bottom = current_bottom - e.delta_y 

        if new_left < min_left: new_left = min_left
        if new_left > max_left: new_left = max_left

        min_bottom = 20
        max_bottom = safe_h - 120 
        
        if new_bottom < min_bottom: new_bottom = min_bottom
        if new_bottom > max_bottom: new_bottom = max_bottom

        gallery_control_gesture.left = new_left
        gallery_control_gesture.bottom = new_bottom
        gallery_control_gesture.update()

    gallery_control_gesture = ft.GestureDetector(
        content=gallery_control_btn_container,
        on_pan_update=on_gallery_btn_pan,
        right=20,   
        left=None,  
        bottom=100, 
        visible=False 
    )

    def on_resize(e):
        nonlocal is_wide_mode
        pw = page.width if page.width else 390 
        ph = page.height if page.height else 844

        new_is_wide = (pw > ph and pw > 600)
        mode_changed = (new_is_wide != is_wide_mode)
        is_wide_mode = new_is_wide

        for card in results_grid.controls:
            try:
                stack = card.content
                action_row = stack.controls[3].content 
                btn_browser = action_row.controls[1]
                btn_dl = action_row.controls[2]
                
                img_obj = stack.controls[1].content
                if img_obj.src:
                    if is_wide_mode:
                        btn_dl.visible = True
                        btn_browser.visible = False
                    else:
                        btn_dl.visible = False
                        btn_browser.visible = True
                    btn_dl.update()
                    btn_browser.update()
            except: pass
        
        if is_wide_mode:
            viewer_dl_btn.visible = True
            btn_browser_dl.visible = False
        else:
            viewer_dl_btn.visible = False
            btn_browser_dl.visible = True
        
        if viewer_overlay.visible:
            try: viewer_dl_btn.update()
            except: pass
            try: btn_browser_dl.update()
            except: pass

        if is_wide_mode:
            t2i_slider.offset = MyOffset(0, 0)
            
            sidebar_container.width = pw * 0.5 if pw * 0.5 < 300 else 300 
            sidebar_container.bottom = 0
            mask.bottom = 0
            
            if left_panel_visible:
                page1_container.visible = True
                page1_container.width = None
                page1_container.expand = 1 
                page2_container.visible = True
                page2_container.width = None
                page2_container.expand = 2 
            else:
                page1_container.visible = False
                page1_container.expand = 0 
                page2_container.visible = True
                page2_container.width = None
                page2_container.expand = 1 
            
            dots_row.visible = False
            toggle_panel_btn.visible = True 
            view_switch_btn.visible = False
            top_menu_btn.visible = True
            bottom_nav.visible = False 
            
            results_grid.max_extent = 300
            results_grid.runs_count = None 
            
            page1_scroll_col.scroll = ft.ScrollMode.AUTO 
            
            custom_appbar.height = 50
            fixed_bottom_action_bar.visible = True

        else: 
            t2i_slider.offset = None 
            
            sidebar_container.width = pw 
            sidebar_container.bottom = 56
            mask.bottom = 56
            
            top_menu_btn.visible = False 
            view_switch_btn.visible = False
            toggle_panel_btn.visible = False
            bottom_nav.visible = True 

            custom_appbar.height = 1 
            
            page1_container.visible = (t2i_page_index == 0)
            page1_container.expand = True 
            page1_container.width = pw
            page1_container.height = None 
            
            page2_container.visible = (t2i_page_index == 1)
            page2_container.expand = True
            page2_container.width = pw
            page2_container.height = None
            
            dots_row.visible = False 
            
            results_grid.max_extent = 160
            results_grid.runs_count = None 
            
            page1_scroll_col.scroll = ft.ScrollMode.AUTO 
            
            fixed_bottom_action_bar.visible = True

        update_gallery_controller_content()

        current_safe_w = pw
        sidebar_edge = 0
        if is_wide_mode:
            sidebar_edge = 300 if pw * 0.5 < 300 else pw * 0.5

        btn_left = gallery_control_gesture.left

        need_reset = False
        if btn_left is not None:
            if btn_left < sidebar_edge: need_reset = True 
            if btn_left > current_safe_w - 50: need_reset = True 
        
        if mode_changed or need_reset:
            gallery_control_gesture.left = None 
            gallery_control_gesture.right = 20  
            gallery_control_gesture.bottom = 100 
            gallery_control_gesture.update()

        if is_wide_mode:
            gallery_control_gesture.visible = True
        else:
            gallery_control_gesture.visible = (t2i_page_index == 1) and (not viewer_overlay.visible)
        
        page1_container.update()
        page2_container.update()
        t2i_slider.update()
        dots_row.update()
        sidebar_container.update()
        toggle_panel_btn.update()
        view_switch_btn.update()
        top_menu_btn.update()
        bottom_nav.update()
        mask.update()
        prompt_input.update()
        custom_appbar.update()
        gallery_control_gesture.update()
        
        if viewer_overlay.visible:
            update_viewer_layout_content()
        
    page.on_resize = on_resize

    custom_appbar = ft.Container(
        height=50, padding=ft.padding.only(left=10, right=10),
        content=ft.Row([
            top_menu_btn,
            toggle_panel_btn,
            ft.Container(expand=True),
            view_switch_btn 
        ], alignment="start")
    )

    main_content_bg = ft.Container(
        expand=True, 
        bgcolor=BG_LIGHT, 
        padding=0,
        content=ft.SafeArea(
            content=ft.Column([
                custom_appbar,
                ft.Container(content=t2i_slider, expand=True, clip_behavior=ft.ClipBehavior.HARD_EDGE),
                ft.Container(content=dots_row, height=0 if not is_wide_mode else 35, alignment=ft.alignment.center),
                bottom_nav 
            ], spacing=0),
            bottom=True, 
            top=True     
        )
    )
    
    layout = ft.Stack([main_content_bg, mask, sidebar_container, viewer_overlay, gallery_control_gesture], expand=True)
    page.add(layout)

    on_resize(None) 
    
    nav_container_ref.content = ft.Row([
        ft.Row([nav_icon_ref, ft.Container(width=10), nav_text_ref]), 
        ft.Container(expand=True), 
        nav_highlight_ref
    ], alignment="spaceBetween")
    
    switch_t2i_page(0) 
    
    page.update() 

    await update_theme(stored_mode, stored_color_name)
    update_upload_area()
    
    await asyncio.sleep(0.5) 
    
    nav_text_ref.value = "  图片编辑"
    nav_btn_func_text.value = "图片编辑"
    view_switch_btn.tooltip = "查看编辑结果"
    
    is_pm = stored_power_config.get("enabled", False)
    if is_pm:
        new_max = int(stored_power_config.get("batch_size", 10))
        new_max = max(1, new_max)
        batch_slider.max = new_max
        batch_slider.label = "{value} ⚡"
        batch_slider.active_color = "red"
        batch_row.controls[0].value = "⚡ 强力"
        batch_row.controls[0].color = "red"
        batch_row.controls[0].weight = "bold"
        if batch_slider.value > new_max: batch_slider.value = new_max
        batch_val_text.value = str(int(batch_slider.value))
    
    page.update()

    if not current_api_keys:
        safe_open_dialog(settings_dialog)

ft.app(target=main)
