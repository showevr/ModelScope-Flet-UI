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

# ==========================================
#      【安全导入层】防止手机端崩溃
# ==========================================
try:
    from PIL import ImageGrab
    HAS_PIL_GRAB = True
except ImportError:
    HAS_PIL_GRAB = False
except OSError:
    HAS_PIL_GRAB = False

# ==========================================
#      【核心兼容层】自动适配 Flet 版本
# ==========================================
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

# ==========================================
#      辅助工具函数
# ==========================================
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

# ==========================================
#      元数据处理函数 (PNG Info)
# ==========================================
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

# ==========================================
#             配置与常量
# ==========================================

BASE_URL = 'https://api-inference.modelscope.cn/'
BAIDU_TRANSLATE_URL = 'https://fanyi-api.baidu.com/api/trans/vip/translate'
T2I_FOLDER = "T2I"

if not os.path.exists(T2I_FOLDER):
    try: os.makedirs(T2I_FOLDER)
    except: pass

MORANDI_COLORS = {
    "Red": "#C85C56", "Orange": "#D98656", "Gold": "#D0A467", "Green": "#709D78",
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

downloaded_urls = set()

# 背景颜色定义
BG_WARM = "#F5F0EB" # 米黄色
BG_LIGHT = "#FFFFFF" # 纯白色
BG_DARK = "#1C1C1E"  # 黑灰色
BG_DARK_DIALOG = "#2C2C2E" # 深色模式下弹窗背景色（比纯黑稍亮）

INPUT_HEIGHT = 40 
CUSTOM_BTN_WIDTH = 68
SEARCH_WIDTH = 70 

DEFAULT_MODEL_OPTIONS = [
    {"key": "Tongyi-MAI/Z-Image-Turbo", "text": "造相-Z-Image-Turbo"},
    {"key": "black-forest-labs/FLUX.2-dev", "text": "FLUX.2-dev"},
    {"key": "Qwen/Qwen-Image", "text": "Qwen-Image"},
    {"key": "Qwen/Qwen-Image-Edit", "text": "Qwen-Image-Edit"},
    {"key": "black-forest-labs/FLUX.1-Krea-dev", "text": "FLUX.1-Krea-dev"},
    {"key": "MusePublic/FLUX.1-Kontext-Dev", "text": "FLUX.1-Kontext-Dev"},
]

SIZE_OPTIONS = [
    {"key": "928x1664", "text": "928x1664 (竖屏)"},
    {"key": "1104x1472", "text": "1104x1472 (竖屏)"},
    {"key": "1328x1328", "text": "1328x1328 (方形)"},
    {"key": "1472x1104", "text": "1472x1104 (横屏)"},
    {"key": "1664x928", "text": "1664x928 (横屏)"},
    {"key": "2048x2048", "text": "2048x2048 (方形)"},
]

async def main(page: ft.Page):
    # ================= 1. 设置窗口属性 =================
    page.window.min_width = 380
    page.window.min_height = 600
    page.window.resizable = True   
    page.title = "魔塔AI大全"
    page.padding = 0
    page.spacing = 0
    page.appbar = None 
    try: page.expand = True 
    except: pass

    # ================= 2. 读取本地存储 (修复版：全异步读取) =================
    try:
        # 【修改】使用 await get_async 确保手机端能读到数据
        stored_api_keys_str = await page.client_storage.get_async("api_keys") or ""
        stored_baidu_config = await page.client_storage.get_async("baidu_config") or ""
        stored_color_name = await page.client_storage.get_async("theme_color") or "Gold"
        stored_mode = await page.client_storage.get_async("theme_mode") or "dark"
        stored_custom_models = await page.client_storage.get_async("custom_models") or ""
    except Exception as e:
        print(f"Error reading storage: {e}")
        stored_api_keys_str, stored_baidu_config = "", ""
        stored_color_name, stored_mode = "Gold", "dark"
        stored_custom_models = ""

    current_api_keys = [k.strip() for k in stored_api_keys_str.split('\n') if k.strip()]
    current_primary_color = MORANDI_COLORS.get(stored_color_name, "#D0A467")
    
    baidu_lines = stored_baidu_config.split('\n')
    current_baidu_appid = baidu_lines[0].strip() if len(baidu_lines) > 0 else ""
    current_baidu_key = baidu_lines[1].strip() if len(baidu_lines) > 1 else ""
    
    sidebar_offset = MyOffset(-1, 0) if MyOffset else None
    t2i_page_index = 0
    is_wide_mode = False
    left_panel_visible = True

    # ================= 3. 定义文件保存器 (修复版：解决0KB问题) =================
    
    # 【新增】用于临时存储待下载的二进制数据，不绑定在控件上
    pending_save_bytes = None

    def on_save_file_result(e: ft.FilePickerResultEvent):
        nonlocal pending_save_bytes
        if e.path:
            try:
                # 【修改】增加 flush 和 fsync 确保手机端写入物理硬盘
                if pending_save_bytes:
                    with open(e.path, "wb") as f:
                        f.write(pending_save_bytes)
                        f.flush()              # 强制清空缓冲区
                        os.fsync(f.fileno())   # 强制写入物理存储设备
                    
                    page.snack_bar = ft.SnackBar(ft.Text(f"✅ 图片已保存"), open=True)
                    # 保存后清空内存
                    pending_save_bytes = None
                else:
                     page.snack_bar = ft.SnackBar(ft.Text(f"❌ 保存失败：数据丢失"), open=True, bgcolor="red")
                
                page.update()
            except Exception as ex:
                print(f"Write Error: {ex}")
                page.snack_bar = ft.SnackBar(ft.Text(f"保存文件失败 (权限或路径错误): {ex}"), open=True, bgcolor="red")
                page.update()
        else:
            # 取消保存也清空
            pending_save_bytes = None
            pass

    save_file_picker = ft.FilePicker(on_result=on_save_file_result)
    page.overlay.append(save_file_picker)

    # ================= 4. 核心功能函数 =================

    # 【修改】改为异步保存函数
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

    def copy_image_src(src):
        page.set_clipboard(src)
        page.snack_bar = ft.SnackBar(ft.Text("图片路径已复制"), open=True)
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

    # --- 下载图片逻辑 (全平台通用稳健版) ---
    async def download_image(url, metadata=None):
        nonlocal pending_save_bytes
        if not url: return False
        try:
            # 1. 下载图片数据
            res = await asyncio.to_thread(requests.get, url, timeout=30)
            
            if res.status_code == 200:
                image_bytes = res.content
                if metadata:
                    image_bytes = add_metadata_to_png(image_bytes, metadata)
                
                # 2. 【修改】将数据存入外部变量，不挂载到控件上
                pending_save_bytes = image_bytes
                
                # 3. 触发保存流程
                timestamp = int(time.time())
                filename = f"img_{timestamp}_{random.randint(100,999)}.png"
                
                save_file_picker.save_file(dialog_title="保存图片", file_name=filename, allowed_extensions=["png"])
                
                downloaded_urls.add(url)
                return True
            else:
                page.snack_bar = ft.SnackBar(ft.Text("下载失败: 网络错误"), open=True)
                page.update()
                return False
        except Exception as err:
            page.snack_bar = ft.SnackBar(ft.Text(f"下载错误: {str(err)}"), open=True)
            page.update()
            return False

    # ================= UI 引用与组件定义 =================
    
    sidebar_icon_ref = ft.Icon("smart_toy", size=40)
    sidebar_title_ref = ft.Text("魔塔AI大全", size=18, weight="bold")
    sidebar_subtitle_ref = ft.Text("By_showevr", size=12)
    
    nav_highlight_ref = ft.Container(width=4, height=20, border_radius=2)
    nav_text_ref = ft.Text("  文生图", size=16, weight="bold")
    
    sidebar_div1 = ft.Divider(height=10, thickness=0.5, color="transparent")
    sidebar_div2 = ft.Divider(height=10, thickness=0.5, color="transparent")

    nav_container_ref = ft.Container(
        padding=ft.padding.symmetric(horizontal=20, vertical=12), 
        border_radius=30, 
        animate=MyAnimation(200, "easeOut") if MyAnimation else None
    )
    
    theme_dialog = ft.AlertDialog(title=ft.Text("显示与主题", weight="bold"), modal=True, surface_tint_color=ft.Colors.TRANSPARENT)
    settings_dialog = ft.AlertDialog(title=ft.Text("全局设置"), modal=True, surface_tint_color=ft.Colors.TRANSPARENT)

    # --- 图片查看器 ---
    
    def close_viewer(e=None):
        viewer_overlay.visible = False
        viewer_overlay.update()
        if t2i_page_index == 1:
            gallery_control_gesture.visible = True
            gallery_control_gesture.update()

    inner_viewer_img = ft.Image(src="", fit=ft.ImageFit.CONTAIN)

    image_content_wrapper = ft.Container(
        content=inner_viewer_img,
        on_click=lambda e: None, 
    )

    inner_img_container = ft.Container(
        content=image_content_wrapper,
        expand=True,
        alignment=ft.alignment.center,       
        clip_behavior=ft.ClipBehavior.NONE,  
        on_click=lambda e: close_viewer(e)
    )

    interactive_viewer = ft.InteractiveViewer(
        key="iv_viewer", 
        content=ft.Container(
            content=inner_img_container,
            expand=True,
            on_click=lambda e: close_viewer(e), 
            clip_behavior=ft.ClipBehavior.NONE 
        ),
        min_scale=0.1,
        max_scale=5.0,
        scale_enabled=True,
        pan_enabled=True, 
        expand=True,
        boundary_margin=ft.padding.all(5000) 
    )

    viewer_zoom_level = 1.0
    current_viewer_images = []
    current_viewer_metadata = []
    current_viewer_index = 0
    
    viewer_background_container = ft.Container(
        expand=True, 
        alignment=ft.alignment.center,
        content=interactive_viewer
    )

    def reset_viewer_zoom(update_ui=True):
        nonlocal viewer_zoom_level
        viewer_zoom_level = 1.0
        interactive_viewer.key = f"iv_viewer_{time.time()}" 
        interactive_viewer.scale = 1.0
        if update_ui: interactive_viewer.update()

    def adjust_zoom(delta):
        nonlocal viewer_zoom_level
        new_scale = max(0.5, min(5.0, viewer_zoom_level + delta))
        viewer_zoom_level = new_scale
        interactive_viewer.scale = new_scale
        interactive_viewer.update()

    viewer_dl_btn = ft.IconButton(
        icon="download", icon_color="white", icon_size=20, tooltip="下载原图", bgcolor="transparent"
    )

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
    ], scroll=ft.ScrollMode.ALWAYS, height=200) 

    viewer_info_container = ft.Container(
        content=viewer_text_col,
        padding=15,
        visible=False, 
        animate_opacity=200,
        bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
        blur=ft.Blur(20, 20, ft.BlurTileMode.MIRROR),
        border_radius=0
    )

    def toggle_viewer_info(e):
        viewer_info_container.visible = not viewer_info_container.visible
        if viewer_info_container.visible:
            btn_info.icon_color = current_primary_color
        else:
            btn_info.icon_color = current_primary_color 
        
        btn_info.update()
        viewer_info_container.update()
    
    last_tap_time = 0
    tap_count = 0

    def on_viewer_scroll(e: ft.ScrollEvent):
        factor = 0.2
        if e.scroll_delta_y < 0: adjust_zoom(factor)
        elif e.scroll_delta_y > 0: adjust_zoom(-factor)

    def on_viewer_stack_tap(e):
        nonlocal last_tap_time, tap_count
        now = time.time()
        if now - last_tap_time < 0.4:
            tap_count += 1
        else:
            tap_count = 1
        last_tap_time = now

        if tap_count == 3:
            close_viewer()
            tap_count = 0

    async def on_viewer_download(e):
        current_url = inner_viewer_img.src
        meta = None
        if 0 <= current_viewer_index < len(current_viewer_metadata):
            meta = current_viewer_metadata[current_viewer_index]
            
        # 调用新版下载
        await download_image(current_url, metadata=meta)

    viewer_dl_btn.on_click = on_viewer_download

    def update_viewer_dl_btn_state(src):
        # 始终允许下载，因为是弹出保存框
        viewer_dl_btn.icon = "download"
        viewer_dl_btn.icon_color = current_primary_color 
        viewer_dl_btn.disabled = False
        viewer_dl_btn.tooltip = "下载原图"
        viewer_dl_btn.update()
        
    def update_viewer_info_text():
        if 0 <= current_viewer_index < len(current_viewer_metadata):
            meta = current_viewer_metadata[current_viewer_index]
            if meta:
                viewer_info_prompt.value = meta.get("prompt", "无")
                viewer_info_neg.value = meta.get("negative_prompt", "无")
            else:
                viewer_info_prompt.value = "无数据"
                viewer_info_neg.value = "无数据"
        viewer_info_prompt.update()
        viewer_info_neg.update()

    def navigate_viewer(delta):
        nonlocal current_viewer_index
        if not current_viewer_images: return
        new_index = current_viewer_index + delta
        if 0 <= new_index < len(current_viewer_images):
            current_viewer_index = new_index
            src = current_viewer_images[current_viewer_index]
            inner_viewer_img.src = src
            reset_viewer_zoom(False)
            total = len(current_viewer_images)
            prev_btn.disabled = (current_viewer_index <= 0)
            next_btn.disabled = (current_viewer_index >= total - 1)
            update_viewer_dl_btn_state(src)
            update_viewer_info_text()
            inner_viewer_img.update()
            prev_btn.update()
            next_btn.update()
            interactive_viewer.update()

    prev_btn = ft.IconButton("chevron_left", icon_color="white", icon_size=30, bgcolor=get_opacity_color(0.3, "black"), on_click=lambda e: navigate_viewer(-1), visible=True, tooltip="上一张")
    next_btn = ft.IconButton("chevron_right", icon_color="white", icon_size=30, bgcolor=get_opacity_color(0.3, "black"), on_click=lambda e: navigate_viewer(1), visible=True, tooltip="下一张")

    viewer_control_btns = []
    def create_control_btn(icon_name, tooltip, func):
        btn = ft.IconButton(icon=icon_name, icon_color="white", icon_size=20, tooltip=tooltip, on_click=func, bgcolor="transparent")
        viewer_control_btns.append(btn)
        return btn
    
    btn_info = create_control_btn("info_outline", "显示/隐藏详细信息", toggle_viewer_info)
    btn_zoom_in = create_control_btn("zoom_in", "放大", lambda e: adjust_zoom(0.5))
    btn_zoom_out = create_control_btn("zoom_out", "缩小", lambda e: adjust_zoom(-0.5))
    btn_reset = create_control_btn("restart_alt", "重置大小", lambda e: reset_viewer_zoom(True))
    btn_copy_img = create_control_btn("content_copy", "复制图片", lambda e: copy_image_src(inner_viewer_img.src))
    btn_close = create_control_btn("close", "关闭", close_viewer)

    viewer_controls_row = ft.Row(
        controls=[btn_info, btn_zoom_in, btn_zoom_out, btn_reset, btn_copy_img, viewer_dl_btn, ft.Container(width=1, height=20, bgcolor="white54"), btn_close], 
        alignment=ft.MainAxisAlignment.END, 
        spacing=5
    )

    viewer_bottom_panel = ft.Container(
        content=ft.Column([
            viewer_info_container, 
            ft.Container(content=viewer_controls_row, padding=5) 
        ], spacing=0, tight=True),
        bgcolor=ft.Colors.TRANSPARENT,
        margin=0,
        padding=0,
        on_click=lambda e: None 
    )

    viewer_stack_content = ft.Stack([
        ft.Container(content=viewer_background_container, expand=True, on_click=on_viewer_stack_tap),
        ft.Container(content=prev_btn, left=15, top=0, bottom=0, alignment=ft.alignment.center_left, width=60),
        ft.Container(content=next_btn, right=15, top=0, bottom=0, alignment=ft.alignment.center_right, width=60),
        ft.Container(content=viewer_bottom_panel, bottom=0, left=0, right=0), 
    ], expand=True)
    
    viewer_stack = ft.GestureDetector(
        on_scroll=on_viewer_scroll,
        content=viewer_stack_content,
        expand=True
    )

    viewer_overlay = ft.Container(content=viewer_stack, visible=False, expand=True, bgcolor=BG_DARK, top=0, left=0, right=0, bottom=0)

    def show_image_viewer(src):
        if not src: return
        nonlocal current_viewer_images, current_viewer_index, current_viewer_metadata
        viewer_overlay.bgcolor = get_viewer_bgcolor_dynamic()
        viewer_background_container.bgcolor = get_viewer_bgcolor_dynamic()
        
        viewer_info_prompt.color = current_primary_color
        viewer_info_neg.color = current_primary_color
        viewer_copy_prompt_btn.icon_color = current_primary_color
        viewer_copy_neg_btn.icon_color = current_primary_color
        viewer_title_prompt.color = current_primary_color
        viewer_title_neg.color = current_primary_color
        
        current_viewer_images = []
        current_viewer_metadata = []
        for ctrl in results_grid.controls:
            try:
                stack = ctrl.content
                img_container = stack.controls[1]
                img = img_container.content
                if img.src:
                    current_viewer_images.append(img.src)
                    current_viewer_metadata.append(getattr(img, "data", None))
            except: pass
        try: current_viewer_index = current_viewer_images.index(src)
        except: current_viewer_index = 0
        reset_viewer_zoom(update_ui=False) 
        inner_viewer_img.src = src
        total = len(current_viewer_images)
        prev_btn.visible = (total > 1)
        next_btn.visible = (total > 1)
        prev_btn.disabled = (current_viewer_index <= 0)
        next_btn.disabled = (current_viewer_index >= total - 1)
        update_viewer_dl_btn_state(src)
        update_viewer_info_text() 
        viewer_info_container.visible = False
        
        viewer_bottom_panel.bgcolor = ft.Colors.TRANSPARENT
        viewer_bottom_panel.update()

        gallery_control_gesture.visible = False
        gallery_control_gesture.update()

        viewer_overlay.visible = True
        viewer_overlay.update()

    def get_all_models():
        custom_models = []
        try:
            # 这里的 get 暂时不动，因为主要是初始化用，但建议后续也优化，此处主要依赖 stored_custom_models 变量
            # 由于 stored_custom_models 在 main 开头已经异步读取了，所以这里直接解析变量即可
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

    # 【修改】变为异步
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
        title=ft.Text("自定义模型", weight="bold"),
        modal=True,
        surface_tint_color=ft.Colors.TRANSPARENT,
        content=ft.Container(width=380, content=ft.Column([ft.Text("模型列表（每行一个，格式：显示名称 模型地址）", size=12, color="grey"), ft.Container(height=8), custom_models_input], tight=True, spacing=0)),
        actions=[ft.TextButton("取消", on_click=lambda e: safe_close_dialog(custom_model_dialog)), ft.ElevatedButton("保存并应用", bgcolor=current_primary_color, color="white", on_click=save_custom_models)],
        actions_alignment="end"
    )

    def open_custom_model_dialog(e):
        try:
            custom_models_input.value = stored_custom_models
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

    model_search_field = ft.TextField(
        hint_text="搜索...", text_size=12, height=INPUT_HEIGHT,
        content_padding=ft.padding.symmetric(horizontal=10, vertical=0), border_radius=8, bgcolor="transparent",
        border_color=get_border_color(), border_width=1, on_change=on_model_search_change, width=SEARCH_WIDTH 
    )

    model_dropdown = ft.Dropdown(
        options=[ft.dropdown.Option(m["key"], m["text"]) for m in get_all_models()],
        value=DEFAULT_MODEL_OPTIONS[0]["key"], text_size=14, content_padding=ft.padding.only(left=10, right=10, bottom=5),
        border_color="transparent", border_width=0, fill_color=get_dropdown_bgcolor(), bgcolor=get_dropdown_fill_color(),
        focused_bgcolor=ft.Colors.TRANSPARENT, expand=True 
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

    def apply_metadata_to_ui(meta):
        if not meta: return
        count = 0
        if "prompt" in meta: 
            prompt_input.value = meta["prompt"]
            count += 1
        if "negative_prompt" in meta: neg_prompt_input.value = meta["negative_prompt"]
        if "seed" in meta: seed_input.value = str(meta["seed"])
        if "num_inference_steps" in meta: 
            steps_slider.value = float(meta["num_inference_steps"])
            steps_val_text.value = str(meta["num_inference_steps"])
        if "guidance_scale" in meta:
            guidance_slider.value = float(meta["guidance_scale"])
            guidance_val_text.value = str(meta["guidance_scale"])
        if "model" in meta:
            matched_model = False
            for opt in model_dropdown.options:
                if opt.key == meta["model"]:
                    model_dropdown.value = meta["model"]
                    matched_model = True
                    break
            if not matched_model:
                model_dropdown.options.insert(0, ft.dropdown.Option(meta["model"], meta["model"] + " (Meta)"))
                model_dropdown.value = meta["model"]
        if "size" in meta: size_dropdown.value = meta["size"]

        prompt_input.update()
        neg_prompt_input.update()
        seed_input.update()
        steps_slider.update()
        steps_val_text.update()
        guidance_slider.update()
        guidance_val_text.update()
        model_dropdown.update()
        size_dropdown.update()
        
        if count > 0:
            page.snack_bar = ft.SnackBar(ft.Text("成功读取元数据"), open=True)
            page.update()
        else:
            page.snack_bar = ft.SnackBar(ft.Text("图片中未发现有效元数据"), open=True)
            page.update()

    def apply_metadata_from_path(file_path):
        try:
            with open(file_path, "rb") as f: img_bytes = f.read()
            meta = extract_metadata_from_png(img_bytes)
            if meta: apply_metadata_to_ui(meta)
            else:
                 page.snack_bar = ft.SnackBar(ft.Text("该图片未包含可识别的元数据"), open=True)
                 page.update()
        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"读取失败: {ex}"), open=True)
            page.update()

    def process_clipboard_metadata(e=None):
        if not HAS_PIL_GRAB:
            page.snack_bar = ft.SnackBar(ft.Text("当前设备不支持读取剪贴板图片"), open=True)
            page.update()
            return
        try:
            content = ImageGrab.grabclipboard()
            meta = None
            found_something = False
            if isinstance(content, list):
                for path in content:
                    if path.lower().endswith('.png'):
                        found_something = True
                        with open(path, "rb") as f: img_bytes = f.read()
                        meta = extract_metadata_from_png(img_bytes)
                        if meta: break
            elif content: found_something = True
                
            if meta: apply_metadata_to_ui(meta)
            else:
                if not found_something: page.snack_bar = ft.SnackBar(ft.Text("剪贴板中没有图片或图片文件"), open=True)
                else: page.snack_bar = ft.SnackBar(ft.Text("剪贴板图片中未找到元数据 (请尝试复制文件而非图片内容)"), open=True)
                page.update()
        except Exception as ex:
            page.snack_bar = ft.SnackBar(ft.Text(f"读取剪贴板失败: {ex}"), open=True)
            page.update()

    def on_keyboard(e: ft.KeyboardEvent):
        if e.ctrl and e.key.lower() == "v":
            if HAS_PIL_GRAB:
                try:
                    check = ImageGrab.grabclipboard()
                    if check is not None: process_clipboard_metadata()
                except: pass
    
    page.on_keyboard_event = on_keyboard

    def on_meta_file_picked(e: ft.FilePickerResultEvent):
        if e.files: apply_metadata_from_path(e.files[0].path)

    meta_file_picker = ft.FilePicker(on_result=on_meta_file_picked)
    page.overlay.append(meta_file_picker)

    prompt_input = ft.TextField(
        hint_text="正面提示词 (支持粘贴带元数据图片)...", multiline=True, expand=True, text_size=13, bgcolor="transparent", 
        filled=False, border=ft.InputBorder.NONE, content_padding=ft.padding.only(left=10, top=10, right=10, bottom=32),
        on_focus=lambda e: show_prompt_actions(e, prompt_trans_row), on_blur=on_prompt_blur,
    )
    
    prompt_trans_row = ft.Row(
        [
         ft.IconButton("content_paste", icon_size=16, tooltip="读取剪贴板元数据", on_click=process_clipboard_metadata),
         ft.IconButton("folder_open", icon_size=16, tooltip="读取元数据文件", on_click=lambda _: meta_file_picker.pick_files(allow_multiple=False, allowed_extensions=["png"])),
         ft.IconButton("language", icon_size=16, tooltip="转英文", on_click=lambda e: handle_translate(e, prompt_input, "en")),
         ft.IconButton("translate", icon_size=16, tooltip="转中文", on_click=lambda e: handle_translate(e, prompt_input, "zh"))
        ], right=5, bottom=2, opacity=0, animate_opacity=300, visible=False 
    )

    prompt_container = ft.Container(
        content=ft.Stack([prompt_input, prompt_trans_row], expand=True), expand=True, 
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
        options=[ft.dropdown.Option(s["key"], s["text"]) for s in SIZE_OPTIONS], value=SIZE_OPTIONS[0]["key"],
        text_size=14, content_padding=ft.padding.only(left=10, right=10, bottom=5), border_color="transparent", border_width=0,
        fill_color=get_dropdown_bgcolor(), bgcolor=get_dropdown_fill_color(), focused_bgcolor=ft.Colors.TRANSPARENT, expand=True
    )
    
    size_dropdown_container = ft.Container(content=size_dropdown, height=INPUT_HEIGHT, border=ft.border.all(1, get_border_color()), border_radius=8, expand=True, alignment=ft.alignment.center_left)
    custom_size_w = ft.TextField(label="宽度", width=120, keyboard_type="number")
    custom_size_h = ft.TextField(label="高度", width=120, keyboard_type="number")

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
        title=ft.Text("自定义分辨率"),
        surface_tint_color=ft.Colors.TRANSPARENT,
        content=ft.Container(width=420, padding=ft.padding.symmetric(horizontal=20), content=ft.Row([custom_size_w, ft.Text("x"), custom_size_h], alignment="center")),
        actions=[ft.TextButton("取消", on_click=lambda e: safe_close_dialog(custom_size_dialog)), ft.ElevatedButton("确定", on_click=confirm_custom_size, bgcolor=current_primary_color, color="white")],
        actions_alignment="end"
    )

    custom_size_btn = ft.ElevatedButton("自定义", height=INPUT_HEIGHT, width=CUSTOM_BTN_WIDTH, bgcolor="transparent", color=current_primary_color, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=0, padding=0, side=ft.BorderSide(1, get_border_color())), on_click=lambda e: safe_open_dialog(custom_size_dialog))
    size_row = ft.Row([size_dropdown_container, custom_size_btn], spacing=5)

    def create_slider_row(label, min_v, max_v, def_v, step=1):
        slider = ft.Slider(min=min_v, max=max_v, divisions=None, value=def_v, label="{value}", expand=True, active_color=current_primary_color)
        val_text = ft.Text(str(def_v), width=35, size=12, text_align="center")
        def on_change(e):
            val_text.value = str(round(e.control.value, 1) if step < 1 else int(e.control.value))
            val_text.update()
        slider.on_change = on_change
        return ft.Row([ft.Text(label, size=12, width=60, color="grey"), slider, val_text], alignment="center", vertical_alignment="center"), slider, val_text

    initial_key_count = max(1, len(current_api_keys))
    batch_row, batch_slider, batch_val_text = create_slider_row("生图数量", 1, max(1, initial_key_count), initial_key_count)
    steps_row, steps_slider, steps_val_text = create_slider_row("生图步数", 1, 100, 100) 
    guidance_row, guidance_slider, guidance_val_text = create_slider_row("引导系数", 1, 20, 4.0, 0.1) 

    seed_input = ft.TextField(
        value="-1", text_size=12, height=INPUT_HEIGHT, content_padding=ft.padding.symmetric(horizontal=10, vertical=0),
        border_radius=8, bgcolor="transparent", border_color=get_border_color(), border_width=1, keyboard_type="number", expand=True
    )
    seed_row = ft.Row([ft.Text("随机种子", size=12, width=60, color="grey"), seed_input], alignment="center", vertical_alignment="center")

    generate_btn = ft.ElevatedButton(
        "开始生成", icon="brush", bgcolor=current_primary_color, color="white", height=50, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)), width=float("inf")
    )

    results_grid = ft.GridView(expand=True, runs_count=None, max_extent=350, child_aspect_ratio=1.0, spacing=10, run_spacing=10, padding=10)
    
    def create_result_card_ui(index):
        img = ft.Image(src="", fit=ft.ImageFit.CONTAIN, visible=False, expand=True, animate_opacity=300, border_radius=10)
        status = ft.Text(f"排队中...", size=12, color="grey", text_align="center")
        overlay_prompt = ft.Text("", size=11, color=current_primary_color, selectable=True)
        overlay_neg = ft.Text("", size=11, color=current_primary_color, selectable=True)
        
        def copy_overlay_text(txt): copy_text(txt)

        meta_overlay = ft.Container(
            visible=False,
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.WHITE), # 半透明白
            blur=ft.Blur(10, 10, ft.BlurTileMode.MIRROR), # 毛玻璃
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
        btn_copy = ft.IconButton(icon="content_copy", icon_color=current_primary_color, icon_size=18, tooltip="复制图片", visible=False, on_click=lambda e: copy_image_src(img.src))
        btn_dl = ft.IconButton(icon="download", icon_color=current_primary_color, icon_size=18, tooltip="下载图片", visible=False)

        async def on_dl_click(e):
            meta = getattr(img, "data", None)
            await download_image(img.src, metadata=meta)
            
        btn_dl.on_click = on_dl_click
        
        img_container = ft.Container(content=img, expand=True, border_radius=10, on_click=lambda e: show_image_viewer(img.src) if img.src else None)
        action_bar = ft.Row([btn_info, btn_copy, btn_dl], alignment="end", spacing=0)
        card_stack = ft.Stack([
            ft.Container(content=status, alignment=ft.alignment.center, bgcolor=get_opacity_color(0.05, "black"), border_radius=10, expand=True),
            img_container, meta_overlay, ft.Container(content=action_bar, right=0, bottom=0) 
        ], expand=True)

        card = ft.Container(content=card_stack, bgcolor="transparent", border_radius=10, clip_behavior=ft.ClipBehavior.HARD_EDGE)
        return card, img, status, btn_dl, btn_info, btn_copy

    async def run_gen(e):
        if is_wide_mode and left_panel_visible: toggle_left_panel(None)
        
        nonlocal current_api_keys
        keys = [k for k in current_api_keys if k]
        if not keys:
            safe_open_dialog(settings_dialog)
            return
        if not prompt_input.value:
            page.snack_bar = ft.SnackBar(ft.Text("请输入提示词"), open=True)
            page.update()
            return

        size_str = size_dropdown.value
        try:
            w_str, h_str = size_str.split()[0].split('x')
            aspect_ratio = float(w_str) / float(h_str)
            results_grid.child_aspect_ratio = aspect_ratio
        except: results_grid.child_aspect_ratio = 1.0
        
        switch_t2i_page(1)
            
        generate_btn.disabled = True
        batch_count = int(batch_slider.value)
        results_grid.controls.clear()
        
        tasks_ui = []
        for i in range(batch_count):
            card, img, status, btn_dl, btn_info, btn_copy = create_result_card_ui(i)
            results_grid.controls.append(card)
            tasks_ui.append((img, status, btn_dl, btn_info, btn_copy))
        
        results_grid.update()
        page.update()
        
        async def generate_single_image(idx, api_key, ui_refs):
            img_ref, status_ref, dl_ref, info_ref, copy_ref = ui_refs
            try:
                status_ref.value = "提交中..."
                status_ref.color = current_primary_color
                status_ref.update()
                headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
                seed_val = int(seed_input.value)
                if seed_val == -1: seed_val = random.randint(1, 10000000)
                current_seed = seed_val + idx 

                payload = {
                    "model": model_dropdown.value, "prompt": prompt_input.value, "negative_prompt": neg_prompt_input.value,
                    "size": size_dropdown.value, "num_inference_steps": int(steps_slider.value), "guidance_scale": float(guidance_slider.value),
                    "seed": current_seed
                }

                def do_post():
                    return requests.post(f"{BASE_URL}v1/images/generations", headers={**headers, "X-ModelScope-Async-Mode": "true"}, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'), timeout=20)
                
                res = await asyncio.to_thread(do_post)
                res.raise_for_status()
                task_id = res.json().get("task_id")
                if not task_id: raise Exception("无TaskID")

                for _ in range(60): 
                    await asyncio.sleep(2)
                    def do_poll():
                        return requests.get(f"{BASE_URL}v1/tasks/{task_id}", headers={**headers, "X-ModelScope-Task-Type": "image_generation"}, timeout=10)
                    res_poll = await asyncio.to_thread(do_poll)
                    data = res_poll.json()
                    raw_status = data.get("task_status")
                    cn_status = STATUS_TRANSLATIONS.get(raw_status, raw_status)
                    
                    if raw_status == "SUCCEED":
                        output_images = data.get("output_images", [])
                        if output_images:
                            img_ref.src = output_images[0]
                            img_ref.data = payload 
                            img_ref.visible = True
                            dl_ref.visible = True
                            info_ref.visible = True
                            copy_ref.visible = True
                            status_ref.value = "" 
                            img_ref.update()
                            dl_ref.update()
                            info_ref.update()
                            copy_ref.update()
                            status_ref.update()
                        return True
                    elif raw_status == "FAILED": raise Exception(data.get("message", "API Error"))
                    else:
                        status_ref.value = f"生成中...[{cn_status}]"
                        status_ref.update()
                raise Exception("超时")

            except Exception as e:
                status_ref.value = "失败"
                status_ref.tooltip = str(e)
                status_ref.color = "red"
                status_ref.update()
                return False

        tasks = []
        for i in range(batch_count):
            key_to_use = keys[i % len(keys)]
            tasks.append(asyncio.create_task(generate_single_image(i, key_to_use, tasks_ui[i])))
        
        await asyncio.gather(*tasks, return_exceptions=True)
        generate_btn.disabled = False
        generate_btn.update()

    generate_btn.on_click = run_gen

    def on_file_drop(e: ft.FilePickerResultEvent):
        files = e.files
        if not files: return
        apply_metadata_from_path(files[0].path)

    page.on_file_drop = on_file_drop

    page1_scroll_col = ft.Column([
            ft.Container(height=5),
            model_row,
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
            generate_btn,
            ft.Container(height=20), 
    ], spacing=0, horizontal_alignment="stretch", expand=True)

    page1_content = ft.Container(
        padding=ft.padding.symmetric(horizontal=5, vertical=10),
        expand=True,
        content=page1_scroll_col 
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

    # === 底部导航栏相关 ===
    
    nav_btn_settings_icon = ft.Icon("settings", size=24, color="grey")
    nav_btn_settings_text = ft.Text("设置", size=10, color="grey")
    nav_btn_gallery_icon = ft.Icon("image", size=24, color="grey")
    nav_btn_gallery_text = ft.Text("图库", size=10, color="grey")
    
    nav_item_menu = ft.IconButton(icon="menu", icon_size=24, on_click=lambda e: toggle_sidebar(True))
    
    nav_item_settings = ft.Container(
        content=ft.Column([nav_btn_settings_icon, nav_btn_settings_text], spacing=2, alignment="center", horizontal_alignment="center"),
        padding=5,
        on_click=lambda e: switch_t2i_page(0)
    )
    
    nav_item_gallery = ft.Container(
        content=ft.Column([nav_btn_gallery_icon, nav_btn_gallery_text], spacing=2, alignment="center", horizontal_alignment="center"),
        padding=5,
        on_click=lambda e: switch_t2i_page(1)
    )

    bottom_nav = ft.Container(
        bgcolor=get_dropdown_bgcolor(),
        padding=ft.padding.symmetric(vertical=5),
        border=ft.border.only(top=ft.BorderSide(0.5, "grey")),
        content=ft.Row([
            nav_item_menu,
            nav_item_settings,
            nav_item_gallery
        ], alignment="spaceAround", vertical_alignment="center"),
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
        
        # 更新底部导航栏状态
        if index == 0:
            nav_btn_settings_icon.color = current_primary_color
            nav_btn_settings_text.color = current_primary_color
            nav_btn_gallery_icon.color = "grey"
            nav_btn_gallery_text.color = "grey"
            view_switch_btn.icon = "image"
            view_switch_btn.tooltip = "查看生成结果"
            gallery_control_gesture.visible = False
        else:
            nav_btn_settings_icon.color = "grey"
            nav_btn_settings_text.color = "grey"
            nav_btn_gallery_icon.color = current_primary_color
            nav_btn_gallery_text.color = current_primary_color
            view_switch_btn.icon = "tune"
            view_switch_btn.tooltip = "返回设置"
            gallery_control_gesture.visible = True
            
        nav_item_settings.update()
        nav_item_gallery.update()
        view_switch_btn.update()
        gallery_control_gesture.update()

        if is_wide_mode: return 
        
        page1_container.visible = (index == 0)
        page2_container.visible = (index == 1)
        
        t2i_slider.offset = None 
        
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

    mask = ft.Container(
        bgcolor=get_opacity_color(0.3, "black"),
        expand=True, visible=False, animate_opacity=300, opacity=0,
        on_click=lambda e: toggle_sidebar(False)
    )

    api_keys_field = ft.TextField(
        label="ModelScope Keys (每行一个)", value=stored_api_keys_str, 
        multiline=True, text_size=12, content_padding=10
    )
    baidu_config_field = ft.TextField(
        label="百度翻译配置 (第一行AppID，第二行密钥)", 
        value=stored_baidu_config,
        multiline=True, text_size=12, content_padding=10
    )

    # 【修改】变为异步
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
        key_count = len(current_api_keys)
        new_max = max(1, key_count)
        batch_slider.max = new_max
        batch_slider.value = new_max 
        batch_val_text.value = str(new_max) 
        batch_slider.update()
        batch_val_text.update()
        safe_close_dialog(settings_dialog)
        page.update()
    
    settings_dialog.content = ft.Container(width=300, content=ft.Column([api_keys_field, baidu_config_field], tight=True, spacing=10))
    settings_dialog.actions = [ft.TextButton("保存", on_click=save_settings)]

    def build_theme_content():
        def color_dot(name, hex_c):
            is_selected = (hex_c == current_primary_color)
            return ft.Container(
                width=45, height=45, bgcolor=hex_c, border_radius=22,
                on_click=lambda e, n=name: update_theme(color_name=n),
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
                on_click=lambda e, m=mode_val: update_theme(mode=m)
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
        ], spacing=0, horizontal_alignment="start")

    # 【修改】变为异步
    async def update_theme(mode=None, color_name=None):
        nonlocal current_primary_color, stored_mode
        if color_name:
            hex_val = MORANDI_COLORS[color_name]
            current_primary_color = hex_val
            page.theme = ft.Theme(color_scheme_seed=hex_val)
            await save_config("theme_color", color_name)
            generate_btn.bgcolor = hex_val
            sidebar_icon_ref.color = hex_val
            sidebar_title_ref.color = hex_val
            sidebar_subtitle_ref.color = hex_val
            nav_text_ref.color = hex_val
            nav_highlight_ref.bgcolor = hex_val
            batch_slider.active_color = hex_val
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
                    action_bar_row = stack.controls[3].content
                    for btn in action_bar_row.controls:
                         if btn.icon != "check_circle": 
                             btn.icon_color = hex_val
                    
                    status_container = stack.controls[0]
                    status_text = status_container.content
                    status_text.color = hex_val 
                    status_text.update()

                    meta_overlay = stack.controls[2]
                    meta_col = meta_overlay.content
                    meta_col.controls[0].controls[0].color = hex_val
                    meta_col.controls[0].controls[1].icon_color = hex_val
                    meta_col.controls[1].color = hex_val
                    meta_col.controls[2].color = hex_val
                    meta_col.controls[3].controls[0].color = hex_val
                    meta_col.controls[3].controls[1].icon_color = hex_val
                    meta_col.controls[4].color = hex_val
                except: pass
            
            results_grid.update()

            for btn in viewer_control_btns:
                btn.icon_color = hex_val
                btn.update()
            
            prev_btn.icon_color = hex_val
            prev_btn.update()
            next_btn.icon_color = hex_val
            next_btn.update()
            
            viewer_info_prompt.color = hex_val
            viewer_info_neg.color = hex_val
            viewer_title_prompt.color = hex_val
            viewer_title_neg.color = hex_val
            viewer_copy_prompt_btn.icon_color = hex_val
            viewer_copy_neg_btn.icon_color = hex_val

            if viewer_info_container.visible:
                viewer_info_container.update()
            
            if viewer_dl_btn.icon == "download": viewer_dl_btn.icon_color = hex_val
            else: viewer_dl_btn.icon_color = "green"
            viewer_dl_btn.update()

        if mode:
            stored_mode = mode 
            await save_config("theme_mode", mode)
            fill = get_dropdown_bgcolor()
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
                viewer_bottom_panel.bgcolor = ft.Colors.TRANSPARENT 
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
                viewer_bottom_panel.bgcolor = ft.Colors.TRANSPARENT 
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
                viewer_bottom_panel.bgcolor = ft.Colors.TRANSPARENT 

            nav_container_ref.bgcolor = nav_bg_selected
            
            theme_dialog.bgcolor = dialog_bg
            settings_dialog.bgcolor = dialog_bg
            custom_model_dialog.bgcolor = dialog_bg
            custom_size_dialog.bgcolor = dialog_bg

            bottom_nav.bgcolor = fill 
            
            if viewer_overlay.visible:
                viewer_overlay.bgcolor = viewer_bg
                viewer_background_container.bgcolor = viewer_bg
                viewer_bottom_panel.update()

        if theme_dialog.open:
            theme_dialog.content = ft.Container(content=build_theme_content(), width=300, padding=ft.padding.only(top=10, left=10, right=10))
            theme_dialog.update()
            
        page.update()

    def open_theme_dialog(e):
        theme_dialog.content = ft.Container(content=build_theme_content(), width=300, padding=ft.padding.only(top=10, left=10, right=10))
        theme_dialog.actions = [ft.TextButton("确定", on_click=lambda e: safe_close_dialog(theme_dialog))]
        safe_open_dialog(theme_dialog)

    def on_sidebar_pan(e: ft.DragUpdateEvent):
        if e.delta_x < -10: 
            toggle_sidebar(False)

    sidebar_content = ft.Column([
            ft.Container(padding=ft.padding.symmetric(horizontal=20), on_click=lambda e: toggle_sidebar(False), content=ft.Row([sidebar_icon_ref, ft.Column([sidebar_title_ref, sidebar_subtitle_ref], spacing=2)])),
            sidebar_div1,
            ft.Divider(color="transparent", height=10),
            ft.Container(padding=ft.padding.symmetric(horizontal=10), content=nav_container_ref),
            ft.Container(expand=True),
            sidebar_div2,
            ft.Container(
                padding=ft.padding.symmetric(horizontal=20),
                content=ft.Row([
                    ft.IconButton("palette_outlined", tooltip="主题", on_click=open_theme_dialog),
                    ft.IconButton("settings_outlined", tooltip="设置", on_click=lambda e: safe_open_dialog(settings_dialog)),
                ], alignment="spaceEvenly")
            )
        ], expand=True)

    sidebar_gesture_detector = ft.GestureDetector(
        content=sidebar_content,
        on_pan_update=on_sidebar_pan
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
        items=[
            ft.PopupMenuItem(text="1列 (大图)", on_click=lambda e: set_gallery_columns(1)),
            ft.PopupMenuItem(text="2列", on_click=lambda e: set_gallery_columns(2)),
            ft.PopupMenuItem(text="3列", on_click=lambda e: set_gallery_columns(3)),
            ft.PopupMenuItem(text="4列 (小图)", on_click=lambda e: set_gallery_columns(4)),
        ]
    )

    gallery_control_btn_container = ft.Container(
        content=gallery_popup_menu,
        bgcolor="transparent", 
    )
    
    def on_gallery_btn_pan(e: ft.DragUpdateEvent):
        gallery_control_gesture.left = max(0, (gallery_control_gesture.left or 0) + e.delta_x)
        gallery_control_gesture.bottom = max(0, (gallery_control_gesture.bottom or 0) - e.delta_y) # bottom 逻辑相反
        gallery_control_gesture.update()

    gallery_control_gesture = ft.GestureDetector(
        content=gallery_control_btn_container,
        on_pan_update=on_gallery_btn_pan,
        left=20,
        bottom=100,
        visible=False
    )

    # ==========================================
    #      【核心逻辑】响应式布局调整
    # ==========================================
    def on_resize(e):
        nonlocal is_wide_mode
        # 优先使用 page.width 获取真实宽度
        pw = page.width if page.width else 0
        ph = page.height if page.height else 0

        # 如果还没加载好，直接跳过
        if pw == 0 or ph == 0:
            return

        sidebar_container.width = pw * 0.5
        sidebar_container.update()
        
        # 判断：宽 > 高 且 宽度 > 600 为宽屏模式（电脑/平板横屏）
        if pw > ph and pw > 600: 
            is_wide_mode = True
            t2i_slider.offset = MyOffset(0, 0)
            
            # 电脑模式：显示左右分栏
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
            
            # 电脑模式：GridView 自适应
            results_grid.max_extent = 300
            results_grid.runs_count = None 
            
            # 电脑模式：输入框自适应高度
            page1_scroll_col.scroll = None
            prompt_input.height = None
            prompt_input.expand = True
            
            custom_appbar.height = 50

        else: 
            # 手机模式：竖屏布局
            is_wide_mode = False
            t2i_slider.offset = None 
            
            top_menu_btn.visible = False 
            view_switch_btn.visible = False
            toggle_panel_btn.visible = False
            bottom_nav.visible = True 

            custom_appbar.height = 35 
            
            # 计算手机可视区
            view_height = ph - 90 
            if view_height < 400: view_height = 600 
            
            # 手机模式：一次显示一页
            page1_container.visible = (t2i_page_index == 0)
            page1_container.expand = False
            page1_container.width = pw
            page1_container.height = view_height  
            
            page2_container.visible = (t2i_page_index == 1)
            page2_container.expand = False
            page2_container.width = pw
            page2_container.height = view_height 
            
            dots_row.visible = False 
            
            # 手机模式：小图
            results_grid.max_extent = 160
            results_grid.runs_count = None 
            
            # 手机模式：输入框固定高度，页面滚动
            page1_scroll_col.scroll = ft.ScrollMode.HIDDEN 
            prompt_input.height = 160 
            prompt_input.expand = False

        page1_container.update()
        page2_container.update()
        t2i_slider.update()
        dots_row.update()
        sidebar_container.update()
        toggle_panel_btn.update()
        view_switch_btn.update()
        top_menu_btn.update()
        bottom_nav.update()
        prompt_input.update()
        custom_appbar.update()
        
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
        expand=True, bgcolor=BG_LIGHT, padding=0,
        content=ft.Column([
            custom_appbar,
            ft.Container(content=t2i_slider, expand=True, clip_behavior=ft.ClipBehavior.HARD_EDGE),
            ft.Container(content=dots_row, height=0 if not is_wide_mode else 35, alignment=ft.alignment.center),
            bottom_nav 
        ], spacing=0)
    )
    
    layout = ft.Stack([main_content_bg, mask, sidebar_container, viewer_overlay, gallery_control_gesture], expand=True)
    page.add(layout)
    
    nav_container_ref.content = ft.Row([nav_text_ref, ft.Container(expand=True), nav_highlight_ref], alignment="spaceBetween")
    
    switch_t2i_page(0) 
    # 【修改】初始化调用改为异步等待
    await update_theme(stored_mode, stored_color_name)
    
    await asyncio.sleep(0.5) 
    page.update()
    on_resize(None)

    if not current_api_keys:
        safe_open_dialog(settings_dialog)

ft.app(target=main)
