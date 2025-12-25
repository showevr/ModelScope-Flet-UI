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
import datetime
import shutil  # 用于删除文件夹
import glob    # 用于文件查找

# ==========================================
#      【安全导入层】防止手机端崩溃
# ==========================================
try:
    # 尝试导入 Pillow 的 Image 组件用于格式转换
    from PIL import ImageGrab, Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False
except OSError:
    HAS_PIL = False

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
#      【全局常量配置】
# ==========================================
BASE_URL = 'https://api-inference.modelscope.cn/'
BAIDU_TRANSLATE_URL = 'https://fanyi-api.baidu.com/api/trans/vip/translate'

# 文件夹定义
T2I_FOLDER = "T2I"
I2I_FOLDER = "I2I_Edits"
TEMP_CACHE_FOLDER = "Temp_Session_Cache" # 会话临时缓存
TEMP_TRANSFER_FOLDER = "temp_transfer"   # 模块间传输临时文件夹

# 确保持久化文件夹存在
if not os.path.exists(T2I_FOLDER):
    try: os.makedirs(T2I_FOLDER)
    except: pass

if not os.path.exists(I2I_FOLDER):
    try: os.makedirs(I2I_FOLDER)
    except: pass

# 莫兰迪色表
MORANDI_COLORS = {
    "Red": "#C85C56", "Orange": "#D98656", "Gold": "#D0A467", "Green": "#709D78",
    "Teal": "#5C969C", "Blue": "#5D7EA8", "Purple": "#8C73A6"
}

# 状态翻译
STATUS_TRANSLATIONS = {
    "PENDING": "排队中",
    "RUNNING": "生成中",
    "PROCESSING": "处理中",
    "SUCCEED": "成功",
    "FAILED": "失败",
    "CANCELED": "已取消",
    "UNKNOWN": "未知"
}

# 背景色常量
BG_WARM = "#fff7e8"  
BG_LIGHT = "#FFFFFF"
BG_DARK = "#1C1C1E"
BG_DARK_DIALOG = "#2C2C2E"

# ==========================================
#      【缓存系统逻辑 (修改版)】
# ==========================================

def init_cache_system():
    """初始化缓存系统：启动时清空所有临时文件夹"""
    
    # 1. 清理会话缓存 (历史记录用)
    if os.path.exists(TEMP_CACHE_FOLDER):
        try:
            shutil.rmtree(TEMP_CACHE_FOLDER)
            print(f"✅ 会话缓存已清理: {TEMP_CACHE_FOLDER}")
        except Exception as e:
            print(f"❌ 会话缓存清理失败: {e}")
    
    # 2. 【新增】清理传输缓存 (编辑中转用)
    # 获取 temp_transfer 的绝对路径，确保在手机/电脑都能找到
    transfer_path = os.path.join(os.getcwd(), TEMP_TRANSFER_FOLDER)
    if os.path.exists(transfer_path):
        try:
            shutil.rmtree(transfer_path)
            print(f"✅ 传输缓存已清理: {transfer_path}")
        except Exception as e:
            print(f"❌ 传输缓存清理失败: {e}")

    # 等待文件系统释放句柄
    time.sleep(0.1)
    
    # 重新创建必要的缓存文件夹
    if not os.path.exists(TEMP_CACHE_FOLDER):
        try: os.makedirs(TEMP_CACHE_FOLDER)
        except: pass

async def save_to_cache(url, metadata=None):
    """
    下载图片并保存到临时缓存文件夹，注入元数据
    返回本地绝对路径
    """
    if not url: return None
    try:
        # 下载图片
        res = await asyncio.to_thread(requests.get, url, timeout=30)
        if res.status_code == 200:
            image_bytes = res.content
            # 注入元数据
            if metadata:
                image_bytes = add_metadata_to_png(image_bytes, metadata)
            
            # 生成文件名 (使用时间戳确保唯一)
            filename = f"cache_{int(time.time())}_{random.randint(1000,9999)}.png"
            save_path = os.path.join(TEMP_CACHE_FOLDER, filename)
            abs_path = os.path.abspath(save_path)

            # 写入文件
            with open(abs_path, "wb") as f:
                f.write(image_bytes)
            
            return abs_path
        return None
    except Exception as e:
        print(f"Cache save error: {e}")
        return None

def get_cached_history():
    """获取缓存文件夹内的所有图片，按时间倒序排列"""
    if not os.path.exists(TEMP_CACHE_FOLDER): return []
    try:
        # 获取所有 png 文件
        files = glob.glob(os.path.join(TEMP_CACHE_FOLDER, "*.png"))
        # 按修改时间倒序排列 (最新的在前)
        files.sort(key=os.path.getmtime, reverse=True)
        # 返回绝对路径列表
        return [os.path.abspath(f) for f in files]
    except Exception as e:
        print(f"History load error: {e}")
        return []

# ==========================================
#      【本地微型图片服务器】(解决0KB问题)
# ==========================================
LOCAL_IMAGE_CACHE = {}
# 默认端口，但我们会动态更新它
LOCAL_SERVER_PORT = 28989 
_server_started = False

class LocalImageHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith("/image/"):
            try:
                # 解析 URL 中的 token
                token = self.path.split('/')[-1].split('.')[0]
                if token in LOCAL_IMAGE_CACHE:
                    image_data = LOCAL_IMAGE_CACHE[token]
                    self.send_response(200)
                    self.send_header("Content-type", "image/png")
                    self.send_header("Content-Length", str(len(image_data)))
                    # 设置下载文件名
                    self.send_header("Content-Disposition", f'attachment; filename="AI_{token[:8]}.png"')
                    self.end_headers()
                    self.wfile.write(image_data)
                else:
                    self.send_error(404, "Image not found or expired")
            except Exception as e:
                print(f"Server Error: {e}")
                pass
        else:
            self.send_error(404, "Not Found")

    def log_message(self, format, *args):
        # 屏蔽日志输出，保持控制台清爽
        pass

def start_local_server():
    global _server_started
    if _server_started: return
    
    def run():
        global LOCAL_SERVER_PORT
        # 尝试一系列端口，防止与旧版程序冲突
        ports_to_try = [28989, 28990, 28991, 28992, 28993, 28999]
        
        for port in ports_to_try:
            try:
                socketserver.TCPServer.allow_reuse_address = True
                # 尝试绑定端口
                httpd = socketserver.TCPServer(("127.0.0.1", port), LocalImageHandler)
                
                # 如果成功绑定，更新全局端口变量
                LOCAL_SERVER_PORT = port
                print(f"✅ 本地图片服务器启动成功，端口: {LOCAL_SERVER_PORT}")
                httpd.serve_forever()
                return # 启动成功，退出函数
            except OSError:
                print(f"⚠️ 端口 {port} 被占用 (可能是旧版程序在运行)，尝试下一个端口...")
                continue
            except Exception as e:
                print(f"❌ 服务器启动未知错误: {e}")
                return
        
        print("❌ 无法找到可用端口，浏览器下载功能将无法使用！")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    
    # 给线程一点时间来确定端口
    time.sleep(0.1)
    _server_started = True

# ==========================================
#      【元数据处理函数】(PNG Info)
# ==========================================
def add_metadata_to_png(image_bytes, metadata):
    try:
        png_signature = b'\x89PNG\r\n\x1a\n'
        
        # 1. 检查是否为 PNG，如果不是且有 PIL，则尝试转换
        if not image_bytes.startswith(png_signature):
            if HAS_PIL:
                try:
                    # 将字节流转换为 PIL Image 对象
                    img_obj = Image.open(io.BytesIO(image_bytes))
                    # 创建新的字节流缓冲
                    buf = io.BytesIO()
                    # 强制保存为 PNG 格式
                    img_obj.save(buf, format="PNG")
                    # 获取转换后的字节
                    image_bytes = buf.getvalue()
                except Exception as e:
                    print(f"Format conversion failed: {e}")
                    return image_bytes # 转换失败，返回原图
            else:
                # 不是PNG且没有PIL，无法注入元数据
                return image_bytes

        # 2. 准备元数据
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
        
        # 3. 寻找 IEND 块并插入元数据
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
#      【I2I 专用工具函数】
# ==========================================
file_upload_cache = {}

def get_image_size(file_path):
    """简单的获取图片宽高函数，用于AutoSize逻辑"""
    try:
        with open(file_path, 'rb') as f:
            head = f.read(24)
            if len(head) != 24: return None
            if head.startswith(b'\x89PNG\r\n\x1a\n'):
                w, h = struct.unpack('>II', head[16:24])
                return w, h
            elif head.startswith(b'\xff\xd8'):
                f.seek(0)
                ftype = 0
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
    # 智能复用：先检查缓存
    if file_path in file_upload_cache:
        print(f"Reuse cached URL for: {file_path}")
        return file_upload_cache[file_path]

    try:
        filename = os.path.basename(file_path)
        with open(file_path, 'rb') as f:
            files = {'files[]': (filename, f, 'image/png')}
            # 使用 ungu.se 作为临时图床
            res = await asyncio.to_thread(requests.post, "https://uguu.se/upload", files=files, timeout=60)
        if res.status_code == 200:
            data = res.json()
            if data.get('success'):
                url = data['files'][0]['url'].replace('\\', '')
                # 存入缓存
                file_upload_cache[file_path] = url
                return url
        return None
    except Exception as e:
        print(f"Upload failed: {e}")
        return None

# ==========================================
#      【通用辅助函数】
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

def copy_text(page, text):
    page.set_clipboard(text)
    page.snack_bar = ft.SnackBar(ft.Text("已复制到剪贴板"), open=True)
    page.update()

def translate_text(page, text, appid, secret_key, to_lang="en"):
    if not appid or not secret_key:
        page.snack_bar = ft.SnackBar(ft.Text("请先在设置中配置百度翻译 Key"), open=True)
        page.update()
        return None
    try:
        salt = str(random.randint(32768, 65536))
        sign_str = appid + text + salt + secret_key
        sign = hashlib.md5(sign_str.encode()).hexdigest()
        res = requests.post(BAIDU_TRANSLATE_URL, data={
            'q': text, 'from': 'auto', 'to': to_lang,
            'appid': appid, 'salt': salt, 'sign': sign
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

# ==========================================
#      【UI 样式辅助】
# ==========================================
def get_dropdown_fill_color(mode):
    if mode == "dark": return "#3C3C3E"
    elif mode == "warm": return "#fffbf0" 
    else: return "#FFFFFF"

def get_dropdown_bgcolor(mode):
    return get_dropdown_fill_color(mode)
    
def get_border_color(mode):
    if mode == "dark": return "#525252"
    if mode == "warm": return "#eacba6"   
    return "#d9d9d9"

def get_dialog_bgcolor(mode):
    if mode == "dark": return BG_DARK_DIALOG
    elif mode == "warm": return BG_WARM
    else: return "white"

def get_sidebar_bgcolor(mode):
    if mode == "dark": return BG_DARK_DIALOG
    elif mode == "warm": return "#fff7e8" 
    else: return "white"

def get_text_color(mode):
    if mode == "dark": return "#9E9E9E"   
    elif mode == "warm": return "#8c7b70" 
    else: return "#757575"                

def safe_open_dialog(page, dlg):
    try: page.open(dlg)
    except: 
        page.dialog = dlg
        dlg.open = True
        page.update()

def safe_close_dialog(page, dlg):
    try: page.close(dlg)
    except: 
        dlg.open = False
        page.update()

# ==========================================
#      【下载与保存】
# ==========================================

async def save_image_to_local_folder(page, url, target_folder, metadata=None):
    if not url: return False
    # 如果 URL 已经是本地路径（缓存文件），直接复制
    if os.path.exists(url) and os.path.isfile(url):
        try:
            timestamp = int(time.time())
            filename = f"img_{timestamp}_{random.randint(100,999)}.png"
            save_path = os.path.join(target_folder, filename)
            shutil.copy2(url, save_path)
            page.snack_bar = ft.SnackBar(ft.Text(f"✅ 图片已保存至: {save_path}"), open=True)
            page.update()
            return True
        except Exception as e:
            page.snack_bar = ft.SnackBar(ft.Text(f"保存错误: {str(e)}"), open=True)
            page.update()
            return False

    try:
        res = await asyncio.to_thread(requests.get, url, timeout=30)
        if res.status_code == 200:
            image_bytes = res.content
            # 尝试注入元数据 (内部会自动处理 JPG转PNG)
            if metadata:
                image_bytes = add_metadata_to_png(image_bytes, metadata)
            
            # 生成文件名
            timestamp = int(time.time())
            filename = f"img_{timestamp}_{random.randint(100,999)}.png"
            save_path = os.path.join(target_folder, filename)
            
            # 写入文件
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

async def download_via_local_server(page, url, metadata=None):
    if not url: return False
    
    # 如果是本地缓存路径，先读入内存
    image_bytes = None
    if os.path.exists(url) and os.path.isfile(url):
        try:
            with open(url, "rb") as f:
                image_bytes = f.read()
        except Exception as e:
            page.snack_bar = ft.SnackBar(ft.Text(f"读取本地缓存失败: {e}"), open=True)
            page.update()
            return False
            
    if image_bytes is None:
        try:
            page.snack_bar = ft.SnackBar(ft.Text("正在调用浏览器下载..."), open=True)
            page.update()
            
            # 1. 先下载图片到内存
            res = await asyncio.to_thread(requests.get, url, timeout=30)
            if res.status_code != 200:
                raise Exception("图片下载失败")
                
            image_bytes = res.content
            # 尝试注入元数据 (内部会自动处理 JPG转PNG)
            if metadata:
                image_bytes = add_metadata_to_png(image_bytes, metadata)
        except Exception as err:
            page.snack_bar = ft.SnackBar(ft.Text(f"处理失败: {str(err)}"), open=True)
            page.update()
            return False
    
    try:
        # 2. 存入全局缓存 (注意：这里的LOCAL_IMAGE_CACHE是当前进程的)
        token = str(uuid.uuid4())
        LOCAL_IMAGE_CACHE[token] = image_bytes
        
        # 3. 生成下载链接，务必使用当前动态确定的端口
        local_url = f"http://127.0.0.1:{LOCAL_SERVER_PORT}/image/{token}.png"
        
        # 4. 调用浏览器打开
        page.launch_url(local_url)
        return True
        
    except Exception as err:
        page.snack_bar = ft.SnackBar(ft.Text(f"处理失败: {str(err)}"), open=True)
        page.update()
        return False

async def save_temp_image_from_url(url):
    """
    (新增) 将 URL 图片下载并保存为临时文件，返回本地绝对路径
    用于模块间图片传递
    """
    if not url: return None
    
    # 优化：如果本来就是本地文件，直接返回绝对路径
    if os.path.exists(url) and os.path.isfile(url):
        return os.path.abspath(url)
        
    try:
        # 定义临时目录
        temp_dir = os.path.join(os.getcwd(), TEMP_TRANSFER_FOLDER)
        if not os.path.exists(temp_dir):
            os.makedirs(temp_dir)
            
        # 下载
        res = await asyncio.to_thread(requests.get, url, timeout=30)
        if res.status_code == 200:
            filename = f"transfer_{int(time.time())}_{random.randint(100,999)}.png"
            save_path = os.path.join(temp_dir, filename)
            
            with open(save_path, "wb") as f:
                f.write(res.content)
                
            return os.path.abspath(save_path)
        return None
    except Exception as e:
        print(f"Temp save error: {e}")
        return None

# ==========================================
#      【配置加载与存储】
# ==========================================
async def load_global_config(page):
    """
    统一读取 client_storage 并返回一个配置字典
    """
    try:
        stored_api_keys_str = await page.client_storage.get_async("api_keys") or ""
        stored_baidu_config = await page.client_storage.get_async("baidu_config") or ""
        stored_color_name = await page.client_storage.get_async("theme_color") or "Gold"
        stored_mode = await page.client_storage.get_async("theme_mode") or "dark"
        stored_custom_models = await page.client_storage.get_async("custom_models") or ""
        
        # 读取强力模式配置
        # 结构: {"enabled": bool, "batch_size": int, "selected_keys": [list], "daily_limit": int, "request_delay": float}
        stored_power_config = await page.client_storage.get_async("power_mode_config")
    except Exception as e:
        print(f"Error reading storage: {e}")
        stored_api_keys_str, stored_baidu_config = "", ""
        stored_color_name, stored_mode = "Gold", "dark"
        stored_custom_models = ""
        stored_power_config = None

    current_api_keys = [k.strip() for k in stored_api_keys_str.split('\n') if k.strip()]
    
    baidu_lines = stored_baidu_config.split('\n')
    current_baidu_appid = baidu_lines[0].strip() if len(baidu_lines) > 0 else ""
    current_baidu_key = baidu_lines[1].strip() if len(baidu_lines) > 1 else ""

    # 初始化强力模式默认值
    if not stored_power_config or not isinstance(stored_power_config, dict):
        stored_power_config = {
            "enabled": False,
            "batch_size": 10,
            "selected_keys": [], # 默认空列表，逻辑上视为空时使用全部Keys
            "daily_limit": 200,
            "request_delay": 0.2  # 新增：默认每次请求间隔 0.2秒
        }

    return {
        "api_keys": current_api_keys,
        "baidu_config": {"appid": current_baidu_appid, "key": current_baidu_key},
        "theme_color_name": stored_color_name,
        "theme_mode": stored_mode,
        "custom_models": stored_custom_models,
        "power_mode_config": stored_power_config
    }

async def save_config_to_storage(page, key, value):
    try: await page.client_storage.set_async(key, value)
    except: pass

# ==========================================
#      【API 使用次数统计 (强力模式专用)】
# ==========================================
async def _get_today_str():
    return datetime.datetime.now().strftime("%Y-%m-%d")

async def get_api_usage(page, api_key):
    """
    获取指定 Key 今日的已使用次数
    会自动处理跨天重置逻辑 (只读操作，不会重写Storage，除非需要重置)
    """
    try:
        data = await page.client_storage.get_async("api_usage_data")
        today = await _get_today_str()
        
        if not data or not isinstance(data, dict):
            return 0
        
        # 如果记录的日期不是今天，说明是新的一天，返回0
        if data.get("date") != today:
            return 0
            
        counts = data.get("counts", {})
        return counts.get(api_key, 0)
    except:
        return 0

async def increment_api_usage(page, api_key):
    """
    增加指定 Key 的使用次数 +1
    会自动处理跨天重置逻辑
    """
    try:
        data = await page.client_storage.get_async("api_usage_data")
        today = await _get_today_str()
        
        if not data or not isinstance(data, dict):
            data = {"date": today, "counts": {}}
        
        # 跨天检查：如果存储的日期不是今天，重置所有数据
        if data.get("date") != today:
            data = {"date": today, "counts": {}}
        
        # 增加计数
        current_count = data["counts"].get(api_key, 0)
        data["counts"][api_key] = current_count + 1
        
        await page.client_storage.set_async("api_usage_data", data)
    except Exception as e:
        print(f"Usage update error: {e}")