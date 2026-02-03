import flet as ft
import asyncio
import math
import time
import utils

# ==========================================
#      【兼容层】自动适配 Flet 版本
# ==========================================
# 1. 适配 Rotate
try:
    MyRotate = ft.Rotate
except AttributeError:
    try:
        MyRotate = ft.transform.Rotate
    except AttributeError:
        MyRotate = None

# 2. 适配 InteractiveViewer (大图缩放组件)
try:
    InteractiveViewerClass = ft.InteractiveViewer
    HAS_INTERACTIVE_VIEWER = True
except AttributeError:
    InteractiveViewerClass = ft.Container # 降级处理
    HAS_INTERACTIVE_VIEWER = False

class ImageViewer:
    def __init__(self, page: ft.Page, primary_color: str, theme_mode: str, on_edit_click=None, on_dismiss=None):
        """
        :param on_edit_click: 函数(src)，用于点击"发送到编辑"时触发
        :param on_dismiss: (新增) 函数()，当查看器关闭时触发，用于通知外部恢复UI状态
        """
        self.page = page
        self.primary_color = primary_color
        self.theme_mode = theme_mode
        self.on_edit_click = on_edit_click 
        self.on_dismiss = on_dismiss # 保存关闭回调
        
        # 内部状态
        self.is_open = False
        self.is_wide_mode = False
        self.current_images_data = [] # 存储图片对象列表
        self.current_index = 0
        self.target_folder = "" # 当前是 T2I 还是 I2I
        
        # 缩放、手势与旋转状态
        self.zoom_level = 1.0
        self._drag_offset_x = 0.0
        self.is_mobile_zoom_mode = False
        self.is_animating = False
        self.is_info_open = False # 信息面板是否展开
        self.current_rotate_angle = 0 # 当前旋转角度 (度)

        # ================= UI 组件初始化 =================
        self._init_ui_components()
        self._build_layout()

    def _init_ui_components(self):
        # 1. 图片显示组件 
        self.inner_img = ft.Image(src="", fit=ft.ImageFit.CONTAIN)
        
        # 【安全赋值】创建后尝试赋值旋转属性
        if MyRotate:
            try:
                self.inner_img.rotate = MyRotate(0, alignment=ft.alignment.center)
                if utils.MyAnimation:
                    self.inner_img.animate_rotation = utils.MyAnimation(300, "easeOut")
            except: 
                pass 

        self.preload_img = ft.Image(src="", fit=ft.ImageFit.CONTAIN, opacity=1)

        # 2. 缩放提示胶囊 (Toast)
        self.zoom_hint_text = ft.Text("大图模式", color="white", size=14, weight="bold")
        self.zoom_hint_container = ft.Container(
            content=self.zoom_hint_text,
            bgcolor=utils.get_opacity_color(0.7, self.primary_color), 
            padding=ft.padding.symmetric(horizontal=20, vertical=10),
            border_radius=30,
            opacity=0, visible=False,
            shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.with_opacity(0.3, "black"))
        )

        # 3. 翻页按钮
        self.btn_prev = ft.IconButton("chevron_left", icon_color="white", icon_size=30, bgcolor=utils.get_opacity_color(0.3, "black"), on_click=lambda e: self.navigate(-1), visible=False, tooltip="上一张")
        self.btn_next = ft.IconButton("chevron_right", icon_color="white", icon_size=30, bgcolor=utils.get_opacity_color(0.3, "black"), on_click=lambda e: self.navigate(1), visible=False, tooltip="下一张")

        # 4. 信息面板内容组件
        self.info_prompt = ft.Text("无", selectable=True, size=13, color=self.primary_color)
        self.info_neg = ft.Text("无", selectable=True, size=13, color=self.primary_color)
        
        self.title_prompt = ft.Text("正面提示", size=11, weight="bold", color=self.primary_color)
        self.title_neg = ft.Text("负面提示", size=11, weight="bold", color=self.primary_color)
        
        self.copy_prompt_btn = ft.IconButton("content_copy", icon_size=14, icon_color=self.primary_color, on_click=lambda e: utils.copy_text(self.page, self.info_prompt.value))
        self.copy_neg_btn = ft.IconButton("content_copy", icon_size=14, icon_color=self.primary_color, on_click=lambda e: utils.copy_text(self.page, self.info_neg.value))

        # 5. 底部控制栏按钮
        self.btn_info = self._create_control_btn("info_outline", "显示/隐藏详细信息", self._toggle_info)
        
        self.btn_reset = self._create_control_btn("restart_alt", "重置大小", lambda e: self.reset_zoom(True))
        self.btn_rot_l = self._create_control_btn("rotate_left", "向左旋转", lambda e: self._rotate_view(-90))
        self.btn_rot_r = self._create_control_btn("rotate_right", "向右旋转", lambda e: self._rotate_view(90))
        
        # 🟢 新增：发送到编辑按钮
        self.btn_edit = self._create_control_btn("auto_fix_high", "发送到图片编辑", self._on_edit)
        
        self.btn_save_local = self._create_control_btn("save_alt", "保存到本地", self._on_save_local)
        self.btn_browser_dl = self._create_control_btn("public", "浏览器下载", self._on_browser_dl)
        self.btn_close = self._create_control_btn("close", "关闭", self.hide)

        # 控制栏布局
        self.controls_row = ft.Row(
            controls=[
                self.btn_info, 
                self.btn_reset, 
                self.btn_rot_l, 
                self.btn_rot_r, 
                self.btn_edit, # 加入布局
                self.btn_browser_dl, 
                self.btn_save_local, 
                ft.Container(width=1, height=20, bgcolor="white54"), 
                self.btn_close
            ], 
            alignment=ft.MainAxisAlignment.END, spacing=2
        )
        self.controls_container = ft.Container(content=self.controls_row, padding=5, bgcolor=ft.Colors.TRANSPARENT)

        # 6. 信息面板结构 (Mobile & Desktop)
        self.info_col = ft.Column([], scroll=ft.ScrollMode.ALWAYS, expand=True, spacing=0) 
        
        self.info_container = ft.Container(
            content=self.info_col, 
            padding=15, 
            bgcolor="transparent", 
            border_radius=0, 
            shadow=ft.BoxShadow(blur_radius=15, color=ft.Colors.with_opacity(0.3, "black")),
            expand=True
        )
        self.info_wrapper_mobile = ft.Container(
            content=self.info_container, 
            height=0, # 默认收起
            animate=utils.MyAnimation(300, "easeOut") if utils.MyAnimation else None,
            clip_behavior=ft.ClipBehavior.HARD_EDGE, 
            bgcolor="transparent"
        )

        # Desktop: Sidebar 结构 (宽屏侧滑栏)
        # 【修改】初始化为宽度 0，移除描边，添加动画，背景色在 update_layout 中动态设置
        self.info_col_desktop = ft.Column([], scroll=ft.ScrollMode.ALWAYS, expand=True, spacing=0)
        self.info_sidebar_desktop = ft.Container(
            width=0, # 初始收起 (通过宽度控制动画)
            bgcolor="transparent",
            # border=ft.border.only(left=ft.BorderSide(1, "white24")), # 【修改】移除描边
            content=ft.Column([
                ft.Container(content=self.info_col_desktop, padding=15, expand=True),
                ft.Divider(height=1, color="white24"),
            ], spacing=0, expand=True),
            visible=True, # 保持Visible为True，仅操作Width
            animate=utils.MyAnimation(300, "easeOut") if utils.MyAnimation else None, # 【修改】添加滑出动画
            clip_behavior=ft.ClipBehavior.HARD_EDGE
        )

    def _create_control_btn(self, icon, tooltip, func):
        return ft.IconButton(icon=icon, icon_color="white", icon_size=20, tooltip=tooltip, on_click=func, bgcolor="transparent")

    def _build_layout(self):
        # --- 手势交互层 ---
        # 1. 内层缩放
        inner_gesture = ft.GestureDetector(
            content=ft.Container(content=self.inner_img, alignment=ft.alignment.center, expand=True),
            on_double_tap=self._on_inner_double_tap, expand=True
        )
        
        if HAS_INTERACTIVE_VIEWER:
            self.interactive_viewer = InteractiveViewerClass(
                content=inner_gesture, min_scale=0.2, max_scale=5.0, 
                scale_enabled=True, pan_enabled=True, expand=True,
                boundary_margin=ft.padding.all(800)
            )
        else:
            self.interactive_viewer = ft.Container(content=inner_gesture, expand=True)

        # 2. 滑动容器
        self.swipe_container = ft.Container(
            content=self.interactive_viewer,
            offset=utils.MyOffset(0, 0) if utils.MyOffset else None,
            animate_offset=utils.MyAnimation(300, "easeOut") if utils.MyAnimation else None,
            expand=True,
            on_click=self._toggle_ui_visibility
        )

        # 3. 预加载层
        self.preload_container = ft.Container(
            content=self.preload_img,
            offset=utils.MyOffset(1, 0) if utils.MyOffset else None,
            animate_offset=utils.MyAnimation(300, "easeOut") if utils.MyAnimation else None,
            alignment=ft.alignment.center, expand=True, visible=False
        )

        # 4. 外层手势
        self.outer_gesture = ft.GestureDetector(
            content=ft.Container(bgcolor=ft.Colors.TRANSPARENT, expand=True),
            on_double_tap=self._on_outer_double_tap,
            on_pan_update=self._on_pan_update,
            on_pan_end=self._on_pan_end,
            on_scroll=self._on_scroll,
            on_scale_update=self._on_scale_update,
            on_scale_end=self._on_scale_end,
            expand=True
        )

        # 5. 组合图片层
        self.image_stack = ft.Stack([
            self.preload_container,
            self.swipe_container,
            self.outer_gesture,
            self.zoom_hint_container 
        ], expand=True, alignment=ft.alignment.center)

        self.bg_container = ft.Container(expand=True, alignment=ft.alignment.center, content=self.image_stack)

        # --- 主布局构建 ---
        self.main_column = ft.Column(
            spacing=0,
            controls=[
                ft.Container(
                    content=ft.Stack([
                        self.bg_container,
                        ft.Container(content=self.btn_prev, left=15, top=0, bottom=0, alignment=ft.alignment.center_left, width=60),
                        ft.Container(content=self.btn_next, right=15, top=0, bottom=0, alignment=ft.alignment.center_right, width=60),
                    ], expand=True),
                    expand=True
                ),
                self.info_wrapper_mobile,
                ft.Container(content=self.controls_container, bgcolor="transparent")
            ], expand=True
        )

        self.ui = ft.Container(
            content=ft.Row([
                self.main_column,
                self.info_sidebar_desktop
            ], spacing=0, expand=True),
            visible=False, expand=True, bgcolor=utils.BG_DARK,
            top=0, left=0, right=0, bottom=0
        )

    # ================= 核心逻辑：显示与隐藏 =================
    
    def show(self, src, all_images, index, target_folder="T2I"):
        self.is_open = True
        self.current_images_data = all_images
        self.current_index = index
        self.target_folder = target_folder
        
        self.is_info_open = False
        self.btn_info.icon = "info_outline"
        self.inner_img.src = src
        self.reset_zoom(update_ui=False)
        
        self._update_info_content()
        self._sync_btn_state()
        self.update_theme(self.primary_color, self.theme_mode)
        self._update_layout_structure()
        self._update_reset_btn_visibility()
        
        self.ui.visible = True
        self.ui.update()

    def hide(self, e=None):
        self.is_open = False
        self.ui.visible = False
        self.ui.update()
        self.reset_zoom(update_ui=False)
        # 【新增】触发关闭回调
        if self.on_dismiss:
            self.on_dismiss()

    # ================= 逻辑：旋转 =================

    def _rotate_view(self, delta):
        self.current_rotate_angle += delta
        if hasattr(self.inner_img, "rotate") and self.inner_img.rotate:
            self.inner_img.rotate.angle = self.current_rotate_angle * math.pi / 180
            self.inner_img.update()
    
    # ================= 逻辑：发送到编辑 (新增) =================
    
    def _on_edit(self, e):
        if self.on_edit_click and self.inner_img.src:
            # 关闭查看器
            self.hide()
            # 触发回调
            self.page.run_task(self._trigger_edit_callback, self.inner_img.src)
            
    async def _trigger_edit_callback(self, src):
        if self.on_edit_click:
            await self.on_edit_click(src)

    # ================= 逻辑：导航与手势 =================
    
    def navigate(self, delta):
        self.page.run_task(self._navigate_async, delta)

    async def _navigate_async(self, delta):
        if self.is_animating or not self.current_images_data: return
        
        new_index = self.current_index + delta
        if new_index < 0 or new_index >= len(self.current_images_data):
            self._reset_drag_position()
            self.page.snack_bar = ft.SnackBar(ft.Text("没有更多图片了"), open=True)
            self.page.update()
            return

        self.is_animating = True
        target_obj = self.current_images_data[new_index]
        
        self.preload_img.src = target_obj.src
        self.preload_container.visible = True
        
        start_x = 1.0 if delta > 0 else -1.0
        end_x = -1.0 if delta > 0 else 1.0
        
        if self.swipe_container.offset.x == 0:
            self.preload_container.animate_offset = None
            if utils.MyOffset:
                self.preload_container.offset = utils.MyOffset(start_x, 0)
            self.preload_container.update()
        
        anim = utils.MyAnimation(300, "easeOut") if utils.MyAnimation else None
        self.swipe_container.animate_offset = anim
        self.preload_container.animate_offset = anim
        self.swipe_container.update()
        self.preload_container.update()
        
        await asyncio.sleep(0.05)
        
        if utils.MyOffset:
            self.swipe_container.offset = utils.MyOffset(end_x, 0)
            self.preload_container.offset = utils.MyOffset(0, 0)
        self.swipe_container.update()
        self.preload_container.update()
        
        await asyncio.sleep(0.35)
        
        self.current_index = new_index
        self.inner_img.src = target_obj.src
        self.reset_zoom(update_ui=False)
        
        self.swipe_container.animate_offset = None
        self.preload_container.animate_offset = None
        if utils.MyOffset:
            self.swipe_container.offset = utils.MyOffset(0, 0)
            self.preload_container.offset = utils.MyOffset(1.0, 0)
        self.preload_container.visible = False
        
        try:
            self.swipe_container.update()
            self.preload_container.update()
        except: pass
        
        self._update_info_content()
        self._sync_btn_state()
        self.is_animating = False
        self._drag_offset_x = 0

    def _on_pan_update(self, e: ft.DragUpdateEvent):
        if self.zoom_level > 1.1: return
        
        width = self.page.width if self.page.width else 360
        self._drag_offset_x += e.delta_x
        ratio = self._drag_offset_x / width
        
        if utils.MyOffset:
            self.swipe_container.animate_offset = None
            self.swipe_container.offset = utils.MyOffset(ratio, 0)
        
        if abs(self._drag_offset_x) > 10:
            self.preload_container.visible = True
            self.preload_container.animate_offset = None
            
            target_idx = -1
            start_x = 0.0
            
            if self._drag_offset_x < 0:
                target_idx = self.current_index + 1
                start_x = 1.0
            else:
                target_idx = self.current_index - 1
                start_x = -1.0
            
            if 0 <= target_idx < len(self.current_images_data):
                self.preload_img.src = self.current_images_data[target_idx].src
                if utils.MyOffset:
                    self.preload_container.offset = utils.MyOffset(start_x + ratio, 0)
            else:
                self.preload_img.src = ""
        
        try:
            self.swipe_container.update()
            self.preload_container.update()
        except: pass

    async def _on_pan_end_async(self, velocity):
        if self.zoom_level > 1.1: return

        threshold = 60
        should_next = (self._drag_offset_x < -threshold) or (velocity < -500)
        should_prev = (self._drag_offset_x > threshold) or (velocity > 500)
        
        if should_next and self.current_index < len(self.current_images_data) - 1:
            await self._navigate_async(1)
        elif should_prev and self.current_index > 0:
            await self._navigate_async(-1)
        else:
            self._reset_drag_position()
        self._drag_offset_x = 0

    def _on_pan_end(self, e: ft.DragEndEvent):
        self.page.run_task(self._on_pan_end_async, getattr(e, "velocity_x", 0))

    def _reset_drag_position(self):
        if utils.MyOffset:
            self.swipe_container.animate_offset = utils.MyAnimation(300, "easeOut") if utils.MyAnimation else None
            self.swipe_container.offset = utils.MyOffset(0, 0)
            self.preload_container.offset = utils.MyOffset(1, 0)
            try:
                self.swipe_container.update()
                self.preload_container.update()
            except: pass
            
            async def hide_later():
                await asyncio.sleep(0.3)
                self.preload_container.visible = False
                self.preload_container.update()
            self.page.run_task(hide_later)

    def _on_inner_double_tap(self, e):
        if self.is_wide_mode:
            self.reset_zoom(True)
        else:
            self._toggle_mobile_zoom(False)

    def _on_outer_double_tap(self, e):
        if self.is_wide_mode:
            self.reset_zoom(True)
        else:
            self._toggle_mobile_zoom(True)

    def _toggle_mobile_zoom(self, enable):
        if not HAS_INTERACTIVE_VIEWER:
             self._trigger_zoom_hint("当前版本不支持缩放")
             return

        self.is_mobile_zoom_mode = enable
        self.outer_gesture.visible = not enable
        
        if enable:
            # 进入大图模式
            self.btn_prev.visible = False
            self.btn_next.visible = False
            self.controls_container.visible = False
            
            self.is_info_open = False
            self.btn_info.icon = "info_outline"
            
            # --- 智能缩放核心逻辑 ---
            target_scale = 1.0
            hint_msg = "大图模式"
            
            if not self.is_wide_mode: 
                try:
                    # 获取当前图片尺寸信息
                    img_obj = self.current_images_data[self.current_index]
                    meta = getattr(img_obj, "data", {})
                    size_str = meta.get("size", "")
                    
                    # 解析图片宽高
                    img_w, img_h = 0.0, 0.0
                    if "x" in size_str:
                        parts = size_str.split()[0].split('x') 
                        if len(parts) >= 2:
                            img_w = float(parts[0])
                            img_h = float(parts[1])
                    
                    is_landscape_image = (img_w > img_h) if (img_w > 0 and img_h > 0) else False
                    
                    # 获取屏幕宽高
                    screen_w = float(self.page.width) if self.page.width else 360.0
                    screen_h = float(self.page.height) if self.page.height else 800.0
                    
                    # 1. 检测是否需要旋转 (竖屏下看横图)
                    if screen_w < screen_h and is_landscape_image:
                        if self.current_rotate_angle == 0:
                            self._rotate_view(90)
                        
                        # 【横图旋转铺满逻辑】
                        if screen_w > 0:
                            target_scale = screen_h / screen_w
                        else:
                            target_scale = 1.5 
                            
                        hint_msg = "大图模式 (已自适应旋转)"
                    
                    # 2. 【新增】竖图铺满逻辑 (竖屏下看竖图)
                    elif screen_w < screen_h and not is_landscape_image and img_w > 0 and img_h > 0:
                        # 计算宽高比
                        img_ratio = img_h / img_w      # 图片高宽比
                        screen_ratio = screen_h / screen_w # 屏幕高宽比
                        
                        if img_ratio < screen_ratio:
                            # 图片较矮胖，为了铺满高度，需要放大
                            target_scale = screen_ratio / img_ratio
                            hint_msg = "大图模式 (已铺满屏幕)"
                        elif img_ratio > screen_ratio:
                            # 图片较细长，为了铺满宽度，需要放大
                            target_scale = img_ratio / screen_ratio
                            hint_msg = "大图模式 (已铺满屏幕)"
                        
                        # 限制一下过大的缩放，避免糊得太厉害
                        target_scale = min(target_scale, 3.0)
                        
                        # 如果计算出的缩放很小（接近1），就不折腾了
                        if target_scale < 1.05: target_scale = 1.0
                        else: hint_msg = "大图模式 (已铺满屏幕)"

                except Exception as e:
                    print(f"Auto zoom error: {e}")
            
            self._trigger_zoom_hint(hint_msg)
            
            # 应用缩放
            self.interactive_viewer.min_scale = 0.5
            self.interactive_viewer.max_scale = max(5.0, target_scale * 2.0) # 确保最大缩放足够大
            self.interactive_viewer.scale = target_scale
            # ---------------------
                
        else:
            self.reset_zoom(update_ui=True) 
            
            if self.is_wide_mode:
                self.btn_prev.visible = True
                self.btn_next.visible = True
            self.controls_container.visible = True
            self._trigger_zoom_hint("退出缩放")
        
        try:
            if enable:
                if HAS_INTERACTIVE_VIEWER:
                    self.interactive_viewer.update()

            self.outer_gesture.update()
            self.swipe_container.update() 
            
            self.btn_prev.update()
            self.btn_next.update()
            self.controls_container.update()
            self.btn_info.update()
            self._update_layout_structure() 
        except: pass

    def _trigger_zoom_hint(self, text):
        async def task():
            self.zoom_hint_text.value = text
            self.zoom_hint_container.bgcolor = utils.get_opacity_color(0.7, self.primary_color)
            self.zoom_hint_container.visible = True
            self.zoom_hint_container.opacity = 1
            self.zoom_hint_container.update()
            await asyncio.sleep(0.5)
            self.zoom_hint_container.opacity = 0
            self.zoom_hint_container.update()
            await asyncio.sleep(0.3)
            self.zoom_hint_container.visible = False
            self.zoom_hint_container.update()
        self.page.run_task(task)

    def reset_zoom(self, update_ui=True):
        self.zoom_level = 1.0
        self._drag_offset_x = 0.0
        self.is_mobile_zoom_mode = False
        
        self.current_rotate_angle = 0
        if hasattr(self.inner_img, "rotate") and self.inner_img.rotate:
            self.inner_img.rotate.angle = 0
        
        if HAS_INTERACTIVE_VIEWER:
            self.interactive_viewer.scale = 1.0
            self.interactive_viewer.min_scale = 1.0
            self.interactive_viewer.max_scale = 1.0
            self.interactive_viewer.key = str(time.time())
        
        self.outer_gesture.visible = True
        self.preload_container.visible = False
        
        if utils.MyOffset:
            self.swipe_container.offset = utils.MyOffset(0, 0)
            self.preload_container.offset = utils.MyOffset(1, 0)
        
        if update_ui:
            try:
                self.inner_img.update() 
                if HAS_INTERACTIVE_VIEWER:
                    self.interactive_viewer.update() 
                self.outer_gesture.update()
                self.swipe_container.update()
            except: pass

    def _on_scroll(self, e: ft.ScrollEvent):
        # 【修改】PC端滚轮缩放逻辑优化：支持大幅度缩放 (1.0 - 5.0)
        if not self.is_wide_mode or not HAS_INTERACTIVE_VIEWER: return
        
        zoom_step = 0.2
        current_scale = self.interactive_viewer.scale
        
        # 判断滚轮方向: delta_y < 0 通常是向上滚动（放大），> 0 向下滚动（缩小）
        if e.scroll_delta_y < 0:
            new_scale = current_scale + zoom_step
        else:
            new_scale = current_scale - zoom_step
        
        # 限制范围
        new_scale = max(1.0, min(new_scale, 5.0))
        
        if new_scale != current_scale:
            self.interactive_viewer.scale = new_scale
            # 当放大时，隐藏外部手势层以允许拖动 (Pan)
            self.outer_gesture.visible = (new_scale <= 1.01)
            
            self.interactive_viewer.update()
            self.outer_gesture.update()

    def _on_scale_update(self, e: ft.ScaleUpdateEvent):
        if not self.is_wide_mode or not HAS_INTERACTIVE_VIEWER: return
        self.interactive_viewer.scale = max(1.0, e.scale)
        self.interactive_viewer.update()

    def _on_scale_end(self, e: ft.ScaleEndEvent):
        if not self.is_wide_mode or not HAS_INTERACTIVE_VIEWER: return
        if self.interactive_viewer.scale > 1.1:
            self.outer_gesture.visible = False
            self.outer_gesture.update()
        else:
            self.reset_zoom()

    def _toggle_ui_visibility(self, e):
        current = self.controls_container.visible
        new_vis = not current
        self.controls_container.visible = new_vis
        
        if self.is_wide_mode:
            self.btn_prev.visible = new_vis
            self.btn_next.visible = new_vis
            self.btn_prev.update()
            self.btn_next.update()
            
        self._update_layout_structure()

    # ================= 逻辑：信息与更新 =================

    def _update_info_content(self):
        if 0 <= self.current_index < len(self.current_images_data):
            img_obj = self.current_images_data[self.current_index]
            meta = getattr(img_obj, "data", None)
            if meta:
                self.info_prompt.value = meta.get("prompt", "无")
                self.info_neg.value = meta.get("negative_prompt", "无")
            else:
                self.info_prompt.value = "无数据"
                self.info_neg.value = "无数据"

    def _toggle_info(self, e):
        self.is_info_open = not self.is_info_open
        self.btn_info.icon = "info" if self.is_info_open else "info_outline"
        self._update_layout_structure()

    def _update_layout_structure(self):
        bg_color = utils.get_dropdown_bgcolor(self.theme_mode)
        
        self.info_wrapper_mobile.bgcolor = bg_color
        self.info_container.bgcolor = bg_color
        # info_sidebar_desktop 背景色动态逻辑稍后处理
        
        controls_list = [
            ft.Row([self.title_prompt, self.copy_prompt_btn], alignment="spaceBetween"),
            ft.Container(height=4), 
            ft.Container(content=self.info_prompt), 
            ft.Container(height=8),
            ft.Divider(height=1, thickness=1, color="white12"),
            ft.Container(height=8),
            ft.Row([self.title_neg, self.copy_neg_btn], alignment="spaceBetween"),
            ft.Container(height=4),
            ft.Container(content=self.info_neg),
        ]

        if self.is_wide_mode:
            # 【修改】宽屏模式：设置背景色差异，通过宽度动画控制显隐
            # 计算一个稍微不同的背景色 (在原背景基础上叠加一层淡淡的白色或黑色)
            sidebar_overlay = utils.get_opacity_color(0.05, "white") if self.theme_mode == "dark" else utils.get_opacity_color(0.05, "black")
            self.info_sidebar_desktop.bgcolor = sidebar_overlay
            
            # 使用 width 动画替代 visible 切换
            self.info_sidebar_desktop.width = 320 if self.is_info_open else 0
            
            self.main_column.controls[2].bgcolor = bg_color 
            self.info_col.controls = [] 
            self.info_col_desktop.controls = controls_list
            self.info_wrapper_mobile.height = 0
            self.btn_prev.visible = True
            self.btn_next.visible = True
        else:
            self.info_sidebar_desktop.width = 0 # 竖屏收起
            self.main_column.controls[2].bgcolor = bg_color if self.is_info_open else "transparent"
            self.info_col_desktop.controls = []
            self.info_col.controls = controls_list
            
            if self.is_info_open:
                self.info_wrapper_mobile.height = 200
                self.info_container.visible = True
                self.info_wrapper_mobile.opacity = 1
            else:
                self.info_wrapper_mobile.height = 0
                self.info_wrapper_mobile.opacity = 0
            
            self.btn_prev.visible = False
            self.btn_next.visible = False

        try:
            self.info_col.update()
            self.info_col_desktop.update()
            self.info_wrapper_mobile.update()
            self.main_column.update()
            self.info_sidebar_desktop.update()
            self.btn_info.update()
            self.btn_prev.update()
            self.btn_next.update()
        except: pass

    def update_theme(self, primary_color, theme_mode):
        self.primary_color = primary_color
        self.theme_mode = theme_mode
        
        bg = utils.BG_DARK if theme_mode == "dark" else (utils.BG_WARM if theme_mode == "warm" else utils.BG_LIGHT)
        self.ui.bgcolor = bg
        self.bg_container.bgcolor = bg
        
        for btn in [self.btn_info, self.btn_reset, self.btn_rot_l, self.btn_rot_r, self.btn_edit, self.btn_save_local, self.btn_browser_dl, self.btn_close, self.btn_prev, self.btn_next]:
            btn.icon_color = primary_color
            try: btn.update()
            except: pass
            
        self.info_prompt.color = primary_color
        self.info_neg.color = primary_color
        self.title_prompt.color = primary_color
        self.title_neg.color = primary_color
        self.copy_prompt_btn.icon_color = primary_color
        self.copy_neg_btn.icon_color = primary_color
        
        self.zoom_hint_container.bgcolor = utils.get_opacity_color(0.7, primary_color)
        
        self._update_layout_structure()

    def _update_reset_btn_visibility(self):
        self.btn_reset.visible = self.is_wide_mode
        try: self.btn_reset.update()
        except: pass

    def on_resize(self, is_wide, w, h):
        self.is_wide_mode = is_wide
        
        if is_wide:
            self.btn_save_local.visible = True
            self.btn_browser_dl.visible = False
        else:
            self.btn_save_local.visible = False
            self.btn_browser_dl.visible = True
            
        self._update_reset_btn_visibility()
        
        if self.is_open:
            self._update_layout_structure()
            self.btn_save_local.update()
            self.btn_browser_dl.update()

    # ================= 逻辑：下载 =================
    
    def _sync_btn_state(self):
        if 0 <= self.current_index < len(self.current_images_data):
            img_obj = self.current_images_data[self.current_index]
            is_downloaded = getattr(img_obj, "is_downloaded", False)
            
            if is_downloaded:
                self._mark_downloaded(self.btn_save_local)
                self._mark_downloaded(self.btn_browser_dl)
            else:
                self.btn_save_local.icon = "save_alt"
                self.btn_save_local.icon_color = self.primary_color
                self.btn_save_local.disabled = False
                self.btn_save_local.tooltip = f"保存到本地 ({self.target_folder})"
                
                self.btn_browser_dl.icon = "public"
                self.btn_browser_dl.icon_color = self.primary_color
                self.btn_browser_dl.disabled = False
                self.btn_browser_dl.tooltip = "浏览器下载"
            
            try: 
                self.btn_save_local.update()
                self.btn_browser_dl.update()
            except: pass

    def _mark_downloaded(self, btn):
        btn.icon = "check_circle"
        btn.icon_color = self.primary_color
        btn.tooltip = "已下载"
        btn.disabled = True

    def _update_grid_btn_status(self):
        try:
            img_obj = self.current_images_data[self.current_index]
            img_obj.is_downloaded = True
            if hasattr(img_obj, "associated_dl_btn") and img_obj.associated_dl_btn:
                self._mark_downloaded(img_obj.associated_dl_btn)
                img_obj.associated_dl_btn.update()
            if hasattr(img_obj, "associated_browser_btn") and img_obj.associated_browser_btn:
                self._mark_downloaded(img_obj.associated_browser_btn)
                img_obj.associated_browser_btn.update()
        except: pass

    async def _on_save_local(self, e):
        if self.inner_img.src:
            img_obj = self.current_images_data[self.current_index]
            meta = getattr(img_obj, "data", None)
            folder = utils.T2I_FOLDER if self.target_folder == "T2I" else utils.I2I_FOLDER
            
            success = await utils.save_image_to_local_folder(self.page, self.inner_img.src, folder, meta)
            if success:
                img_obj.is_downloaded = True
                self._sync_btn_state()
                self._update_grid_btn_status()

    async def _on_browser_dl(self, e):
        if self.inner_img.src:
            img_obj = self.current_images_data[self.current_index]
            meta = getattr(img_obj, "data", None)
            success = await utils.download_via_local_server(self.page, self.inner_img.src, meta)
            if success:
                img_obj.is_downloaded = True
                self._sync_btn_state()
                self._update_grid_btn_status()