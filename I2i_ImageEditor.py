import flet as ft
import requests
import json
import asyncio
import random
import os
import utils  # 引入公共工具模块

# ==========================================
#      I2I 功能模块封装 (去布局版)
# ==========================================

class I2I_View:
    def __init__(self, page: ft.Page, config: dict, viewer_callback, switch_view_callback, transfer_callback=None):
        """
        :param page: Flet Page 对象
        :param config: 来自 Main_App 的全局配置字典
        :param viewer_callback: 函数(src, all_images, index)，用于调用全局查看器
        :param switch_view_callback: 函数(target_index)，用于通知主程序切换页面 (0:参数, 1:结果)
        :param transfer_callback: (新增) 函数(image_src)，用于将图片回传/互传到编辑区
        """
        self.page = page
        self.config = config
        self.viewer_callback = viewer_callback
        self.switch_view_callback = switch_view_callback
        self.transfer_callback = transfer_callback # 保存回调

        # 解构配置
        self.api_keys = config.get("api_keys", [])
        self.baidu_config = config.get("baidu_config", {})
        self.primary_color = utils.MORANDI_COLORS.get(config.get("theme_color_name"), "#D0A467")
        self.theme_mode = config.get("theme_mode", "dark")
        self.stored_custom_models = config.get("custom_models", "")
        self.power_config = config.get("power_mode_config", {}) # 新增：强力模式配置

        # 内部状态
        self.is_wide_mode = False
        self.generated_images_objs = []
        self.uploaded_files = [] # 存储本地文件路径列表

        # 常量定义
        self.MODELS_REQUIRING_LIST_INPUT = [
            'Qwen/Qwen-Image-Edit-2509',
            'black-forest-labs/FLUX.2-dev',
            'Qwen/Qwen-Image-Edit-2511',  
        ]

        self.DEFAULT_MODEL_OPTIONS = [
            {"key": "Qwen/Qwen-Image-Edit-2511", "text": "Qwen-Image-Edit-2511 (新)"},
            {"key": "Qwen/Qwen-Image-Edit-2509", "text": "Qwen-Image-Edit-2509"},
            {"key": "black-forest-labs/FLUX.2-dev", "text": "FLUX.2-dev"},
            {"key": "Qwen/Qwen-Image-Edit", "text": "Qwen/Qwen-Image-Edit"},
            {"key": "MusePublic/FLUX.1-Kontext-Dev", "text": "FLUX.1-Kontext-Dev"},
            {"key": "google/gemini-2.0-flash-exp", "text": "Gemini 2.0 Flash (Google)"},
        ]

        self.SIZE_OPTIONS = [
            {"key": "AutoSize", "text": "AutoSize (自动检测)"},
            {"key": "928x1664", "text": "928x1664 (竖屏)"},
            {"key": "1104x1472", "text": "1104x1472 (竖屏)"},
            {"key": "1328x1328", "text": "1328x1328 (方形)"},
            {"key": "1472x1104", "text": "1472x1104 (横屏)"},
            {"key": "1664x928", "text": "1664x928 (横屏)"},
            {"key": "2048x2048", "text": "2048x2048 (方形)"},
        ]

        # 初始化UI组件
        self._init_components()
        
        # 初始化上传区域显示
        self._update_upload_area()

    # ================= 外部接口 (供 Main_App 调用) =================

    def get_input_content(self):
        """返回参数输入区的 Column 容器"""
        return self.page1_scroll_col

    def get_generate_btn(self):
        """返回生成按钮，供 Main_App 放置在底部固定栏"""
        return self.generate_btn

    def get_results_content(self):
        """返回结果展示 Grid"""
        return self.results_grid

    def set_grid_columns(self, cols):
        """设置 Grid 列数"""
        self.results_grid.runs_count = cols
        self.results_grid.max_extent = None
        self.results_grid.update()

    # (新增) 设置输入图片接口
    def set_input_image(self, file_path):
        """
        外部调用：设置输入图片并刷新UI
        常用于从 T2I 或 结果区 回传图片到这里进行编辑
        """
        if not file_path: return
        
        # 即使是多图模式，回传通常也只传一张，所以这里策略是覆盖
        self.uploaded_files.clear()
        self.uploaded_files.append(file_path)
        
        self._update_upload_area()
        # 尝试自动读取元数据
        self._apply_metadata_from_path(file_path)

    def update_config(self, new_config):
        self.config = new_config
        self.api_keys = new_config.get("api_keys", [])
        self.baidu_config = new_config.get("baidu_config", {})
        self.power_config = new_config.get("power_mode_config", {}) # 更新强力配置
        
        # --- 强力模式逻辑：更新 Slider 最大值 ---
        is_power_mode = self.power_config.get("enabled", False)
        
        if is_power_mode:
            # 强力模式下，最大值由配置决定 (1-50)
            new_max = int(self.power_config.get("batch_size", 10))
            new_max = max(1, new_max)
            
            # 【修改点】更新滑块视觉样式
            self.batch_slider.label = "{value} ⚡"
            self.batch_slider.active_color = "red" # 视觉警告

            # 【修改点】更新左侧标题样式
            if hasattr(self, 'batch_row'):
                self.batch_row.controls[0].value = "⚡ 强力"
                self.batch_row.controls[0].color = "red"
                self.batch_row.controls[0].weight = "bold"
        else:
            # 普通模式下，最大值由 Key 数量决定
            key_count = len(self.api_keys)
            new_max = max(1, key_count)
            
            # 恢复默认样式
            self.batch_slider.label = "{value}"
            self.batch_slider.active_color = self.primary_color 

            # 恢复左侧标题样式
            if hasattr(self, 'batch_row'):
                self.batch_row.controls[0].value = "生图数量"
                self.batch_row.controls[0].color = utils.get_text_color(self.theme_mode)
                self.batch_row.controls[0].weight = "normal"

        self.batch_slider.max = new_max
        # 如果当前值超过新最大值，重置为最大值
        if self.batch_slider.value > new_max: 
            self.batch_slider.value = new_max
            
        self.batch_val_text.value = str(int(self.batch_slider.value))
        
        # 强制刷新一下界面以应用文字变化
        try: self.batch_row.update()
        except: pass

    def update_theme(self, primary_color, theme_mode):
        self.primary_color = primary_color
        self.theme_mode = theme_mode
        
        # --- 新增：获取当前主题对应的文字颜色 ---
        text_c = utils.get_text_color(theme_mode)
        
        # 1. 更新生成按钮
        self.generate_btn.bgcolor = primary_color
        
        # 2. 更新 Slider 
        # 【修改点】判断强力模式，防止主题切换覆盖红色警示
        is_power_mode = self.power_config.get("enabled", False)
        if not is_power_mode:
            self.batch_slider.active_color = primary_color
            if hasattr(self, 'batch_row'): self.batch_row.controls[0].color = text_c
        else:
            self.batch_slider.active_color = "red"
            if hasattr(self, 'batch_row'): self.batch_row.controls[0].color = "red"
            
        self.steps_slider.active_color = primary_color
        self.guidance_slider.active_color = primary_color

        # --- 新增：更新其他标签文字颜色 ---
        if hasattr(self, 'steps_row'): self.steps_row.controls[0].color = text_c
        if hasattr(self, 'guidance_row'): self.guidance_row.controls[0].color = text_c
        if hasattr(self, 'seed_row'): self.seed_row.controls[0].color = text_c

        # 3. 更新输入框边框与背景
        border_c = utils.get_border_color(theme_mode)
        fill_c = utils.get_dropdown_fill_color(theme_mode)
        bg_c = utils.get_dropdown_bgcolor(theme_mode)

        self.model_dropdown.fill_color = bg_c
        self.model_dropdown.bgcolor = fill_c
        self.model_search_field.border_color = border_c
        self.model_dropdown_container.border = ft.border.all(1, border_c)
        
        self.size_dropdown.fill_color = bg_c
        self.size_dropdown.bgcolor = fill_c
        self.size_dropdown_container.border = ft.border.all(1, border_c)
        
        self.custom_model_btn.style.side = ft.BorderSide(1, border_c)
        self.custom_model_btn.color = primary_color
        self.custom_size_btn.style.side = ft.BorderSide(1, border_c)
        self.custom_size_btn.color = primary_color
        
        self.prompt_container.border = ft.border.all(1, border_c)
        self.neg_prompt_container.border = ft.border.all(1, border_c)
        self.seed_input.border_color = border_c

        # 4. 更新上传区域
        self.upload_container.border = ft.border.all(1, border_c)
        self.upload_container.bgcolor = bg_c
        # 刷新上传区域内部组件的颜色（如添加按钮背景）
        self._update_upload_area()

        # 5. 更新结果 Grid
        for card in self.results_grid.controls:
            try:
                stack = card.content
                # Loading
                loading_bg = stack.controls[0]
                if isinstance(loading_bg.content, ft.Column):
                    col = loading_bg.content
                    col.controls[0].color = primary_color
                    col.controls[2].color = primary_color
                
                # Meta Overlay
                meta_overlay = stack.controls[2]
                meta_col = meta_overlay.content
                meta_col.controls[0].controls[0].color = primary_color
                meta_col.controls[0].controls[1].icon_color = primary_color
                meta_col.controls[1].color = primary_color
                meta_col.controls[2].color = primary_color
                meta_col.controls[3].controls[0].color = primary_color
                meta_col.controls[3].controls[1].icon_color = primary_color
                meta_col.controls[4].color = primary_color
                
                # Action Bar
                action_bar = stack.controls[3].content
                for btn in action_bar.controls:
                    btn.icon_color = primary_color
            except: pass
        
        # 强制刷新一下界面以应用文字颜色
        try:
            self.batch_row.update()
            self.steps_row.update()
            self.guidance_row.update()
            self.seed_row.update()
        except: pass

    def on_resize(self, is_wide, w, h):
        """响应式布局调整"""
        self.is_wide_mode = is_wide
        self._update_grid_buttons_visibility()

        if is_wide:
            self.results_grid.max_extent = 300
            # 宽屏 Prompt 自适应
            self.page1_scroll_col.scroll = None
            self.prompt_input.height = None
            self.prompt_input.expand = True
        else:
            self.results_grid.max_extent = 160
            # 竖屏 Prompt 固定高度，开启滚动
            self.page1_scroll_col.scroll = ft.ScrollMode.AUTO
            self.prompt_input.height = None
            self.prompt_input.expand = True

        self.results_grid.update()
        self.page1_scroll_col.update()

    # ================= 内部组件构建 =================

    def _init_components(self):
        # 1. 模型选择
        self.model_search_field = ft.TextField(
            hint_text="搜索...", text_size=12, height=40,
            content_padding=ft.padding.symmetric(horizontal=10, vertical=0), border_radius=8, bgcolor="transparent",
            border_color=utils.get_border_color(self.theme_mode), border_width=1, on_change=self._on_model_search_change, width=70 
        )

        self.model_dropdown = ft.Dropdown(
            options=[ft.dropdown.Option(m["key"], m["text"]) for m in self._get_all_models()],
            value=self.DEFAULT_MODEL_OPTIONS[0]["key"], 
            text_size=14, content_padding=ft.padding.only(left=10, right=10, bottom=5),
            border_color="transparent", border_width=0, 
            fill_color=utils.get_dropdown_bgcolor(self.theme_mode), 
            bgcolor=utils.get_dropdown_fill_color(self.theme_mode),
            focused_bgcolor=ft.Colors.TRANSPARENT, expand=True,
            on_change=self._on_model_change # 绑定变更事件以刷新上传区域
        )
        
        self.model_dropdown_container = ft.Container(content=self.model_dropdown, height=40, border=ft.border.all(1, utils.get_border_color(self.theme_mode)), border_radius=8, expand=True, alignment=ft.alignment.center_left)
        self.custom_model_btn = ft.ElevatedButton("自定义", height=40, width=68, bgcolor="transparent", color=self.primary_color, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=0, padding=0, side=ft.BorderSide(1, utils.get_border_color(self.theme_mode))), on_click=self._open_custom_model_dialog)
        self.model_row = ft.Row([self.model_dropdown_container, self.model_search_field, self.custom_model_btn], spacing=5)

        # 2. 上传区域
        self.upload_content_container = ft.Container()
        self.upload_file_picker = ft.FilePicker(on_result=self._on_upload_file_picked)
        self.page.overlay.append(self.upload_file_picker)

        self.upload_container = ft.Container(
            content=self.upload_content_container,
            height=140,
            border=ft.border.all(1, utils.get_border_color(self.theme_mode)),
            border_radius=10,
            bgcolor=utils.get_dropdown_bgcolor(self.theme_mode),
            padding=10,
            animate=utils.MyAnimation(300, "easeOut") if utils.MyAnimation else None
        )

        # 3. 提示词
        self.meta_file_picker = ft.FilePicker(on_result=lambda e: self._apply_metadata_from_path(e.files[0].path) if e.files else None)
        self.page.overlay.append(self.meta_file_picker)

        self.prompt_input = ft.TextField(
            hint_text="编辑指令 (例如: 把衣服改成红色)...", multiline=True, expand=True, text_size=13, bgcolor="transparent", 
            filled=False, border=ft.InputBorder.NONE, content_padding=ft.padding.only(left=10, top=10, right=10, bottom=32),
            on_focus=lambda e: self.page.run_task(self._show_prompt_actions, e, self.prompt_trans_row), 
            on_blur=self._on_prompt_blur,
        )
        
        self.prompt_trans_row = ft.Row(
            [
             ft.IconButton("content_paste", icon_size=16, tooltip="读取剪贴板元数据", on_click=self._process_clipboard_metadata),
             ft.IconButton("folder_open", icon_size=16, tooltip="读取元数据文件", on_click=lambda _: self.meta_file_picker.pick_files(allow_multiple=False, allowed_extensions=["png"])),
             ft.IconButton("language", icon_size=16, tooltip="转英文", on_click=lambda e: self._handle_translate(e, self.prompt_input, "en")),
             ft.IconButton("translate", icon_size=16, tooltip="转中文", on_click=lambda e: self._handle_translate(e, self.prompt_input, "zh"))
            ], right=5, bottom=2, opacity=0, animate_opacity=300, visible=False 
        )

        self.prompt_container = ft.Container(
            content=ft.Stack([self.prompt_input, self.prompt_trans_row], 
            expand=True), 
            height=120, # 固定高度
            border=ft.border.all(1, utils.get_border_color(self.theme_mode)), border_radius=10, on_click=lambda e: self.prompt_input.focus()
        )

        # 负面提示词
        self.neg_prompt_input = ft.TextField(
            hint_text="负面提示词...", multiline=True, min_lines=2, max_lines=6, value="噪点，模糊，低画质，色调艳丽，过曝，细节模糊不清，整体发灰，最差质量，低质量，JPEG压缩残留，丑陋的，残缺的，多余的手指",
            text_size=13, bgcolor="transparent", filled=False, border=ft.InputBorder.NONE, content_padding=ft.padding.only(left=10, top=10, right=10, bottom=32),
            on_focus=lambda e: self.page.run_task(self._show_prompt_actions, e, self.neg_trans_row), 
            on_blur=self._on_neg_blur 
        )

        self.neg_trans_row = ft.Row(
            [
             ft.IconButton("language", icon_size=16, tooltip="转英文", on_click=lambda e: self._handle_translate(e, self.neg_prompt_input, "en")),
             ft.IconButton("translate", icon_size=16, tooltip="转中文", on_click=lambda e: self._handle_translate(e, self.neg_prompt_input, "zh"))
            ], right=5, bottom=2, opacity=0, animate_opacity=300, visible=False 
        )

        self.neg_prompt_container = ft.Container(
            content=ft.Stack([self.neg_prompt_input, self.neg_trans_row]), border=ft.border.all(1, utils.get_border_color(self.theme_mode)), border_radius=10, alignment=ft.alignment.top_left, on_click=lambda e: self.neg_prompt_input.focus()
        )

        # 4. 分辨率
        self.size_dropdown = ft.Dropdown(
            options=[ft.dropdown.Option(s["key"], s["text"]) for s in self.SIZE_OPTIONS], value="AutoSize", 
            text_size=14, content_padding=ft.padding.only(left=10, right=10, bottom=5), border_color="transparent", border_width=0,
            fill_color=utils.get_dropdown_bgcolor(self.theme_mode), bgcolor=utils.get_dropdown_fill_color(self.theme_mode), focused_bgcolor=ft.Colors.TRANSPARENT, expand=True
        )
        self.size_dropdown_container = ft.Container(content=self.size_dropdown, height=40, border=ft.border.all(1, utils.get_border_color(self.theme_mode)), border_radius=8, expand=True, alignment=ft.alignment.center_left)
        self.custom_size_btn = ft.ElevatedButton("自定义", height=40, width=68, bgcolor="transparent", color=self.primary_color, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=0, padding=0, side=ft.BorderSide(1, utils.get_border_color(self.theme_mode))), on_click=self._open_custom_size_dialog)
        self.size_row = ft.Row([self.size_dropdown_container, self.custom_size_btn], spacing=5)

        # 5. Sliders & Seed
        initial_key_count = max(1, len(self.api_keys))
        self.batch_row, self.batch_slider, self.batch_val_text = self._create_slider_row("生图数量", 1, max(1, initial_key_count), initial_key_count)
        self.steps_row, self.steps_slider, self.steps_val_text = self._create_slider_row("生图步数", 5, 100, 30, 5) 
        self.guidance_row, self.guidance_slider, self.guidance_val_text = self._create_slider_row("引导系数", 1, 20, 3.5, 0.5) 

        self.seed_input = ft.TextField(
            value="-1", text_size=12, height=40, content_padding=ft.padding.symmetric(horizontal=10, vertical=0),
            border_radius=8, bgcolor="transparent", border_color=utils.get_border_color(self.theme_mode), border_width=1, keyboard_type="number", expand=True,
            on_blur=self._validate_seed  
        )
        self.seed_row = ft.Row([ft.Text("随机种子", size=14, width=60, color="grey"), self.seed_input], alignment="center", vertical_alignment="center")

        # 6. 生成按钮
        self.generate_btn = ft.ElevatedButton(
            "开始编辑", icon="auto_fix_high", bgcolor=self.primary_color, color="white", height=50, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)), width=float("inf"),
            on_click=self._run_gen
        )

        # 7. 结果区域
        self.results_grid = ft.GridView(expand=True, runs_count=None, max_extent=350, child_aspect_ratio=1.0, spacing=10, run_spacing=10, padding=10)

        # 8. 图库控制器 (悬浮按钮 - I2I 模块也需要控制自己的 Grid)
        self.gallery_popup_menu = ft.PopupMenuButton(
            icon="circle_outlined", icon_size=30, tooltip="调整图库布局", surface_tint_color=ft.Colors.TRANSPARENT, 
            items=[
                ft.PopupMenuItem(text="1列 (大图)", on_click=lambda e: self.set_grid_columns(1)),
                ft.PopupMenuItem(text="2列", on_click=lambda e: self.set_grid_columns(2)),
                ft.PopupMenuItem(text="3列", on_click=lambda e: self.set_grid_columns(3)),
                ft.PopupMenuItem(text="4列 (小图)", on_click=lambda e: self.set_grid_columns(4)),
            ]
        )
        self.gallery_control_gesture = ft.GestureDetector(
            content=ft.Container(content=self.gallery_popup_menu, bgcolor="transparent"),
            on_pan_update=self._on_gallery_btn_pan,
            right=20, left=None, bottom=100, visible=False
        )

        # 9. 文件拖拽监听 (附加到页面)
        self.page.on_file_drop = self._on_file_drop
        
        # 10. 构建参数列表容器
        self.page1_scroll_col = ft.Column([
            self.model_row, ft.Container(height=8),
            self.upload_container, ft.Container(height=8),
            self.prompt_container, ft.Container(height=8),
            self.neg_prompt_container, ft.Container(height=8),
            self.size_row, ft.Container(height=8),
            self.batch_row, ft.Container(height=5),
            self.steps_row, ft.Container(height=5),
            self.guidance_row, ft.Container(height=5),
            self.seed_row, ft.Container(height=15),
            # generate_btn 在底部固定
        ], spacing=0, horizontal_alignment="stretch", expand=True, scroll=ft.ScrollMode.AUTO)

    # ================= 业务逻辑：上传与显示 =================

    def _update_upload_area(self):
        is_multi_mode = self.model_dropdown.value in self.MODELS_REQUIRING_LIST_INPUT
        
        placeholder = ft.Column([
            ft.Icon("cloud_upload", size=30, color="grey"),
            ft.Text("点击上传图片", size=12, color="grey"), 
            ft.Text("支持多图模式" if is_multi_mode else "单图模式", size=10, color="grey")
        ], alignment="center", horizontal_alignment="center", spacing=2)

        if not self.uploaded_files:
            self.upload_content_container.content = ft.Container(
                content=placeholder, 
                alignment=ft.alignment.center,
                on_click=lambda _: self.upload_file_picker.pick_files(
                    allow_multiple=is_multi_mode, 
                    allowed_extensions=["png", "jpg", "jpeg", "webp"]
                )
            )
            try:
                self.upload_content_container.update()
            except:
                pass
            return

        if not is_multi_mode:
            # 单图模式
            file_path = self.uploaded_files[0]
            img_view = ft.Image(src=file_path, fit=ft.ImageFit.CONTAIN, border_radius=8)
            clear_btn = ft.Container(
                content=ft.IconButton(icon="close", icon_size=20, icon_color="red", on_click=lambda e: self._remove_image(0)),
                top=5, right=5
            )
            self.upload_content_container.content = ft.Stack([
                ft.Container(content=img_view, padding=5, alignment=ft.alignment.center),
                clear_btn
            ])
            self.upload_content_container.on_click = lambda _: self.upload_file_picker.pick_files(allow_multiple=False, allowed_extensions=["png", "jpg", "jpeg", "webp"])
        else:
            # 多图模式
            thumbs = []
            for i, path in enumerate(self.uploaded_files):
                img_thumb = ft.Image(src=path, fit=ft.ImageFit.COVER, width=100, height=100, border_radius=8)
                rm_btn = ft.Container(
                    content=ft.IconButton(icon="close", icon_size=16, icon_color="white", on_click=lambda e, idx=i: self._remove_image(idx)),
                    bgcolor="#88000000", border_radius=15, width=24, height=24, top=2, right=2
                )
                thumb_container = ft.Container(
                    width=100, height=100,
                    content=ft.Stack([img_thumb, rm_btn]),
                    border=ft.border.all(1, utils.get_border_color(self.theme_mode)),
                    border_radius=8
                )
                thumbs.append(thumb_container)

            add_btn = ft.Container(
                width=100, height=100,
                border=ft.border.all(1, utils.get_border_color(self.theme_mode)),
                border_radius=8,
                bgcolor=utils.get_opacity_color(0.1, self.primary_color),
                alignment=ft.alignment.center,
                content=ft.Icon("add", size=30, color="grey"),
                on_click=lambda _: self.upload_file_picker.pick_files(allow_multiple=True, allowed_extensions=["png", "jpg", "jpeg", "webp"])
            )
            thumbs.append(add_btn)
            
            self.upload_content_container.content = ft.Row(thumbs, scroll=ft.ScrollMode.AUTO, spacing=10, alignment="start")
            self.upload_content_container.on_click = None

        try:
            self.upload_content_container.update()
        except:
            pass

    def _remove_image(self, idx):
        if 0 <= idx < len(self.uploaded_files):
            self.uploaded_files.pop(idx)
            self._update_upload_area()

    # 🟢 修正点：移除了类型提示 ft.FilePickerResultEvent
    def _on_upload_file_picked(self, e):
        if e.files:
            try:
                is_multi = self.model_dropdown.value in self.MODELS_REQUIRING_LIST_INPUT
                new_paths = [f.path for f in e.files]
                if is_multi: self.uploaded_files.extend(new_paths)
                else:
                    self.uploaded_files.clear()
                    self.uploaded_files.append(new_paths[0])
            except Exception as err: print(f"File error: {err}")
            self._update_upload_area()

    # 🟢 修正点：移除了类型提示 ft.FilePickerResultEvent
    def _on_file_drop(self, e):
        # 简单的文件拖拽处理
        if e.files:
            # 默认作为图片上传
            self.uploaded_files.clear()
            self.uploaded_files.append(e.files[0].path)
            self._update_upload_area()
            # 顺便尝试读取元数据
            self._apply_metadata_from_path(e.files[0].path)

    # ================= 业务逻辑：生成 =================

    async def _run_gen(self, e):
        # 宽屏模式展开Panel由MainApp负责
        
        # 校验
        if not self.uploaded_files:
            self.page.snack_bar = ft.SnackBar(ft.Text("请先上传图片"), open=True)
            self.page.update()
            return

        # --- 强力模式 Key 选择逻辑 (修复版) ---
        is_power_mode = self.power_config.get("enabled", False)
        keys_to_use = []
        
        # 清洗全局 api keys，去除空格
        clean_api_keys = [k.strip() for k in self.api_keys if k and k.strip()]
        
        if is_power_mode:
            # 强力模式：优先使用勾选的 Keys
            selected = self.power_config.get("selected_keys", [])
            # 清洗 selected keys
            clean_selected = [k.strip() for k in selected if k and k.strip()]
            
            # 严格过滤：只使用既在 selected 中又在 clean_api_keys 中的 key
            keys_to_use = [k for k in clean_api_keys if k in clean_selected]
            
            # ⭐️ 修复重点：如果开启了强力模式但 keys_to_use 为空，直接报错，禁止回退！
            if not keys_to_use:
                self.page.snack_bar = ft.SnackBar(ft.Text("❌ 强力模式已开启，但未检测到有效勾选的 API Key，请在设置中检查。"), open=True)
                self.page.update()
                return
        else:
            # 普通模式：使用所有 Key
            keys_to_use = clean_api_keys

        if not keys_to_use:
            self.page.snack_bar = ft.SnackBar(ft.Text("请先设置 API Key"), open=True)
            self.page.update()
            return
            
        if not self.prompt_input.value:
            self.page.snack_bar = ft.SnackBar(ft.Text("请输入编辑指令"), open=True)
            self.page.update()
            return

        self.generate_btn.disabled = True
        self.generate_btn.text = "上传图片中..."
        self.generate_btn.update()

        # ================= 修复开始：更强健的比例计算与刷新 =================
        target_size = self.size_dropdown.value
        aspect_ratio = 1.0 # 默认正方形

        try:
            if target_size == "AutoSize":
                if self.uploaded_files:
                    # 尝试读取第一张图片的尺寸
                    dims = utils.get_image_size(self.uploaded_files[0])
                    if dims and dims[1] != 0: 
                        aspect_ratio = dims[0] / dims[1]
            else:
                # 兼容 "928x1664 (竖屏)" 这种带后缀的格式
                clean_size = target_size.split()[0] 
                parts = clean_size.split('x')
                if len(parts) == 2: 
                    aspect_ratio = float(parts[0]) / float(parts[1])
        except Exception as ex:
            print(f"Ratio calculation failed: {ex}")
            aspect_ratio = 1.0

        # 关键步骤：立即应用比例并 update
        self.results_grid.child_aspect_ratio = aspect_ratio
        self.results_grid.update()
        # ================= 修复结束 =================

        # 2. 上传图片
        image_url_param = None
        current_model = self.model_dropdown.value
        is_multi = current_model in self.MODELS_REQUIRING_LIST_INPUT

        try:
            uploaded_urls = []
            for path in self.uploaded_files:
                url = await utils.upload_image_to_host(path)
                if url: uploaded_urls.append(url)
                else: raise Exception(f"上传失败: {os.path.basename(path)}")
            
            if is_multi: image_url_param = uploaded_urls
            else: image_url_param = uploaded_urls[0]

        except Exception as err:
            self.page.snack_bar = ft.SnackBar(ft.Text(str(err)), open=True)
            self.generate_btn.disabled = False
            self.generate_btn.text = "开始编辑"
            self.generate_btn.update()
            return

        # 切换页面 (如果是窄屏)
        if not self.is_wide_mode and self.switch_view_callback:
            self.switch_view_callback(1)
            
        self.generate_btn.text = "任务提交中..."
        self.generate_btn.update()

        # 3. 准备任务
        batch_count = int(self.batch_slider.value)
        self.results_grid.controls.clear()
        self.generated_images_objs = []
        
        tasks_ui = []
        for i in range(batch_count):
            # 注意：此处解构增加了 btn_edit
            card, img, status, btn_dl, btn_info, btn_browser, btn_edit = self._create_result_card_ui()
            self.results_grid.controls.append(card)
            self.generated_images_objs.append(img)
            tasks_ui.append((img, status, btn_dl, btn_info, btn_browser, btn_edit))
        
        self.results_grid.update()

        # 4. 执行生成
        tasks = []
        for i in range(batch_count):
            # 循环使用 Key
            key_to_use = keys_to_use[i % len(keys_to_use)]
            tasks.append(asyncio.create_task(
                self._generate_single_image(i, key_to_use, tasks_ui[i], image_url_param, current_model)
            ))
            # 【新增】可配置的延时，防止触发 QPS 限制
            delay_time = float(self.power_config.get("request_delay", 0.2))
            await asyncio.sleep(delay_time)
        
        await asyncio.gather(*tasks, return_exceptions=True)
        self.generate_btn.disabled = False
        self.generate_btn.text = "开始编辑"
        self.generate_btn.update()

    async def _generate_single_image(self, idx, api_key, ui_refs, image_url_val, model_val):
        img_ref, status_ref, dl_ref, info_ref, browser_ref, edit_ref = ui_refs
        
        def toggle_ring(visible):
            if hasattr(status_ref, "associated_ring"):
                status_ref.associated_ring.visible = visible
                try: status_ref.associated_ring.update()
                except: pass

        try:
            toggle_ring(True)
            status_ref.value = "提交中..."
            status_ref.color = self.primary_color
            status_ref.update()

            headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
            
            raw_seed = self.seed_input.value
            try: seed_val = int(raw_seed) if raw_seed.strip() else -1
            except: seed_val = -1
            if seed_val == -1: seed_val = random.randint(1, 10000000)
            current_seed = seed_val + idx

            payload = {
                "model": model_val,
                "image_url": image_url_val, 
                "prompt": self.prompt_input.value,
                "negative_prompt": self.neg_prompt_input.value,
                "num_inference_steps": int(self.steps_val_text.value), 
                "guidance_scale": float(self.guidance_val_text.value),
                "num_images_per_prompt": 1, 
                "seed": current_seed
            }
            if self.size_dropdown.value != "AutoSize":
                payload["size"] = self.size_dropdown.value

            def do_post():
                return requests.post(
                    f"{utils.BASE_URL}v1/images/generations",
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
                        f"{utils.BASE_URL}v1/tasks/{task_id}", 
                        headers={**headers, "X-ModelScope-Task-Type": "image_generation"}, 
                        timeout=10
                    )
                res_poll = await asyncio.to_thread(do_poll)
                data = res_poll.json()
                raw_status = data.get("task_status")
                
                if raw_status == "SUCCEED":
                    toggle_ring(False)
                    output_images = data.get("output_images", [])
                    if not output_images and "results" in data: output_images = data["results"]
                    
                    if output_images:
                        final_url = output_images[0].get("url", output_images[0]) if isinstance(output_images[0], dict) else output_images[0]
                        
                        # 构建包含尺寸信息的元数据
                        final_meta = payload.copy()
                        final_meta["task_type"] = "image-edit"
                        if "size" not in final_meta and self.uploaded_files:
                            try:
                                dims = utils.get_image_size(self.uploaded_files[0])
                                if dims:
                                    final_meta["size"] = f"{dims[0]}x{dims[1]}"
                            except Exception as e:
                                print(f"Size injection failed: {e}")

                        # =================【关键修改】自动缓存逻辑 =================
                        status_ref.value = "缓存中..."
                        status_ref.update()

                        # 下载并保存到临时缓存
                        local_cache_path = await utils.save_to_cache(final_url, final_meta)

                        if local_cache_path:
                            # 缓存成功，使用本地路径
                            img_ref.src = local_cache_path
                        else:
                            # 降级：使用远程链接
                            img_ref.src = final_url

                        img_ref.data = final_meta
                        
                        img_ref.visible = True
                        info_ref.visible = True
                        edit_ref.visible = True 
                        
                        if self.is_wide_mode:
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
                        edit_ref.update()
                        status_ref.update()

                        # 记录 API Key 使用次数
                        await utils.increment_api_usage(self.page, api_key)

                    return True
                elif raw_status == "FAILED": raise Exception(data.get("message", "API Error"))
                else:
                    status_ref.value = f"{utils.STATUS_TRANSLATIONS.get(raw_status, raw_status)}..."
                    status_ref.update()
            raise Exception("超时")

        except Exception as e:
            toggle_ring(False)
            status_ref.value = "失败"
            status_ref.tooltip = str(e)
            status_ref.color = "red"
            status_ref.update()
            return False

    def _create_result_card_ui(self):
        # 🟢 修正点：改为 COVER，强制填满卡片，消除边缘留白
        img = ft.Image(src="", fit=ft.ImageFit.COVER, visible=False, expand=True, animate_opacity=300, border_radius=10)
        img.is_downloaded = False
        
        loading_ring = ft.ProgressRing(width=25, height=25, stroke_width=3, color=self.primary_color)
        status_text = ft.Text(f"排队中...", size=11, color=self.primary_color, text_align="center")
        status_text.associated_ring = loading_ring 

        loading_col = ft.Column(
            controls=[loading_ring, ft.Container(height=5), status_text],
            alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0
        )

        overlay_prompt = ft.Text("", size=11, color=self.primary_color, selectable=True)
        overlay_neg = ft.Text("", size=11, color=self.primary_color, selectable=True)
        
        meta_overlay = ft.Container(
            visible=False, bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.WHITE), blur=ft.Blur(10, 10, ft.BlurTileMode.MIRROR), 
            padding=10, alignment=ft.alignment.top_left,
            content=ft.Column([
                ft.Row([ft.Text("Prompt", size=10, color=self.primary_color, weight="bold"), ft.IconButton("content_copy", icon_size=12, icon_color=self.primary_color, on_click=lambda e: utils.copy_text(self.page, overlay_prompt.value))], alignment="spaceBetween"),
                overlay_prompt, 
                ft.Divider(height=10, color=self.primary_color),
                ft.Row([ft.Text("Negative", size=10, color=self.primary_color, weight="bold"), ft.IconButton("content_copy", icon_size=12, icon_color=self.primary_color, on_click=lambda e: utils.copy_text(self.page, overlay_neg.value))], alignment="spaceBetween"),
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
        
        btn_info = ft.IconButton(icon="info_outline", icon_color=self.primary_color, icon_size=18, tooltip="显示提示词", visible=False, on_click=toggle_meta_overlay)
        btn_browser = ft.IconButton(icon="public", icon_color=self.primary_color, icon_size=18, tooltip="浏览器下载", visible=False)
        btn_dl = ft.IconButton(icon="save_alt", icon_color=self.primary_color, icon_size=18, tooltip="保存到I2I文件夹", visible=False)

        # 🟢 新增：发送到编辑按钮 (图片回传)
        btn_edit = ft.IconButton(icon="auto_fix_high", icon_color=self.primary_color, icon_size=18, tooltip="发送到编辑", visible=False)

        async def on_edit_click(e):
            if img.src and self.transfer_callback:
                # 调用传入的回调函数，将图片URL回传
                await self.transfer_callback(img.src)

        btn_edit.on_click = on_edit_click

        async def on_browser_click(e):
            if img.src:
                meta = getattr(img, "data", None)
                success = await utils.download_via_local_server(self.page, img.src, meta)
                if success:
                    img.is_downloaded = True
                    # 1. 强制更新当前点击的按钮
                    e.control.icon = "check_circle"
                    e.control.disabled = True
                    e.control.update()
                    # 2. 同步更新
                    self._mark_btn_downloaded(btn_browser)
                    self._mark_btn_downloaded(btn_dl)
        
        async def on_dl_click(e):
            if img.src:
                meta = getattr(img, "data", None)
                # 使用 I2I 文件夹
                # 如果 img.src 已经是本地缓存，utils 内部会自动处理为复制操作
                success = await utils.save_image_to_local_folder(self.page, img.src, utils.I2I_FOLDER, meta)
                if success:
                    img.is_downloaded = True
                    # 1. 强制更新当前点击的按钮
                    e.control.icon = "check_circle"
                    e.control.disabled = True
                    e.control.update()
                    # 2. 同步更新
                    self._mark_btn_downloaded(btn_dl)
                    self._mark_btn_downloaded(btn_browser)

        btn_browser.on_click = on_browser_click
        btn_dl.on_click = on_dl_click
        
        img.associated_browser_btn = btn_browser
        img.associated_dl_btn = btn_dl
        
        img_container = ft.Container(content=img, expand=True, border_radius=10, 
                                     on_click=lambda e: self._on_image_click(img))

        # 将编辑按钮加入操作栏
        action_bar = ft.Row([btn_info, btn_edit, btn_browser, btn_dl], alignment="end", spacing=0)
        
        card_stack = ft.Stack([
            ft.Container(content=loading_col, alignment=ft.alignment.center, bgcolor=utils.get_opacity_color(0.05, "black"), border_radius=10, expand=True),
            img_container, meta_overlay, ft.Container(content=action_bar, right=0, bottom=0) 
        ], expand=True)

        card = ft.Container(content=card_stack, bgcolor="transparent", border_radius=10, clip_behavior=ft.ClipBehavior.HARD_EDGE)
        
        # 返回值增加了 btn_edit
        return card, img, status_text, btn_dl, btn_info, btn_browser, btn_edit

    def _on_image_click(self, clicked_img):
        if not clicked_img.src: return
        
        # --- 修复逻辑：只传递已生成成功的图片给查看器 ---
        # 过滤出所有 src 不为空的有效图片 (增加 strip() 确保非空字符串)
        valid_imgs = [img for img in self.generated_images_objs if img.src and img.src.strip()]
        
        # 在有效列表中查找当前点击图片的索引
        if clicked_img in valid_imgs:
            idx = valid_imgs.index(clicked_img)
            # 仅将有效列表传递给查看器
            self.viewer_callback(clicked_img.src, valid_imgs, idx)

    def _mark_btn_downloaded(self, btn):
        btn.icon = "check_circle"
        btn.icon_color = self.primary_color
        btn.disabled = True
        btn.update()

    # ================= 辅助函数 =================

    def _get_all_models(self):
        custom = []
        try:
            for line in self.stored_custom_models.strip().split('\n'):
                if not line.strip(): continue
                parts = line.strip().split(None, 1)
                if len(parts) >= 2: custom.append({"key": parts[1], "text": parts[0]})
        except: pass
        return self.DEFAULT_MODEL_OPTIONS + custom

    def _open_custom_model_dialog(self, e):
        input_field = ft.TextField(value=self.stored_custom_models, multiline=True, min_lines=10, max_lines=15, text_size=12, border_radius=10)
        async def save(e):
            self.stored_custom_models = input_field.value
            await utils.save_config_to_storage(self.page, "custom_models", self.stored_custom_models)
            all_models = self._get_all_models()
            self.model_dropdown.options = [ft.dropdown.Option(m["key"], m["text"]) for m in all_models]
            self.model_dropdown.update()
            utils.safe_close_dialog(self.page, dlg)
        dlg = ft.AlertDialog(title=ft.Text("自定义模型"), content=ft.Container(width=300, content=ft.Column([ft.Text("每行：名称 地址"), input_field], tight=True)), actions=[ft.TextButton("取消", on_click=lambda e: utils.safe_close_dialog(self.page, dlg)), ft.ElevatedButton("保存", on_click=save)])
        utils.safe_open_dialog(self.page, dlg)

    def _on_model_search_change(self, e):
        query = (e.control.value or "").lower().strip()
        all_models = self._get_all_models()
        filtered = [m for m in all_models if query in m["text"].lower() or query in m["key"].lower()] if query else all_models
        self.model_dropdown.options = [ft.dropdown.Option(m["key"], m["text"]) for m in filtered]
        if filtered and self.model_dropdown.value not in [m["key"] for m in filtered]: self.model_dropdown.value = filtered[0]["key"]
        self.model_dropdown.update()

    def _on_model_change(self, e):
        # 切换模型时刷新上传区域(单图/多图)
        self._update_upload_area()

    def _create_slider_row(self, label, min_v, max_v, def_v, step=1):
        slider = ft.Slider(min=min_v, max=max_v, value=def_v, label="{value}", expand=True, active_color=self.primary_color)
        val_text = ft.Text(str(def_v), width=40, size=14, text_align="center")
        def on_change(e):
            snapped = round(e.control.value / step) * step
            val_text.value = f"{snapped:.1f}" if step < 1 else str(int(snapped))
            val_text.update()
        slider.on_change = on_change
        return ft.Row([ft.Text(label, size=14, width=60, color="grey"), slider, val_text], alignment="center", vertical_alignment="center"), slider, val_text

    def _validate_seed(self, e):
        if not self.seed_input.value.strip():
            self.seed_input.value = "-1"
            self.seed_input.update()

    async def _show_prompt_actions(self, e, row):
        row.visible = True
        row.update()
        row.opacity = 1
        row.update()

    async def _on_prompt_blur(self, e): await self._hide_prompt_actions(self.prompt_trans_row)
    async def _on_neg_blur(self, e): await self._hide_prompt_actions(self.neg_trans_row)

    async def _hide_prompt_actions(self, row):
        await asyncio.sleep(0.2)
        row.opacity = 0
        row.update()
        await asyncio.sleep(0.35)
        row.visible = False
        row.update()

    # 【新增】键盘监听 (改名为公开方法，供Main_App调用)
    def handle_keyboard_event(self, e: ft.KeyboardEvent):
        if e.ctrl and e.key.lower() == "v":
            if utils.HAS_PIL:
                try: self._process_clipboard_metadata()
                except: pass

    # 【新增】处理剪贴板元数据
    def _process_clipboard_metadata(self, e=None):
        if not utils.HAS_PIL: return
        try:
            content = utils.ImageGrab.grabclipboard()
            meta = None
            if isinstance(content, list): # 复制的是文件
                for path in content:
                    if path.lower().endswith('.png'):
                        with open(path, "rb") as f: meta = utils.extract_metadata_from_png(f.read())
                        if meta: break
            elif content: # 复制的是图片位图
                self.page.snack_bar = ft.SnackBar(ft.Text("仅支持复制PNG文件读取元数据，不支持直接复制图片内容"), open=True)
                self.page.update()
                return

            if meta: self._apply_metadata(meta)
            else:
                self.page.snack_bar = ft.SnackBar(ft.Text("未发现元数据"), open=True)
                self.page.update()
        except Exception as ex: print(ex)

    # 【新增】应用元数据到输入框
    def _apply_metadata(self, meta):
        if isinstance(meta, dict):
            if "prompt" in meta: self.prompt_input.value = meta["prompt"]
            if "negative_prompt" in meta: self.neg_prompt_input.value = meta["negative_prompt"]
            if "seed" in meta: self.seed_input.value = str(meta["seed"])
            # I2I 也可以尝试读取步数和引导系数
            if "num_inference_steps" in meta:
                self.steps_slider.value = float(meta["num_inference_steps"])
                self.steps_val_text.value = str(meta["num_inference_steps"])
            if "guidance_scale" in meta:
                self.guidance_slider.value = float(meta["guidance_scale"])
                self.guidance_val_text.value = str(meta["guidance_scale"])
                
            self.prompt_input.update()
            self.neg_prompt_input.update()
            self.seed_input.update()
            self.steps_slider.update()
            self.steps_val_text.update()
            self.guidance_slider.update()
            self.guidance_val_text.update()
            
            self.page.snack_bar = ft.SnackBar(ft.Text("✅ 已读取元数据"), open=True)
            self.page.update()

    def _handle_translate(self, e, field, lang):
        text = field.value
        if text:
            res = utils.translate_text(self.page, text, self.baidu_config.get("appid"), self.baidu_config.get("key"), lang)
            if res:
                field.value = res
                field.update()

    def _apply_metadata_from_path(self, path):
        if not path: return
        try:
            with open(path, 'rb') as f: meta = utils.extract_metadata_from_png(f.read())
            if meta and isinstance(meta, dict):
                if "prompt" in meta: self.prompt_input.value = meta["prompt"]
                if "negative_prompt" in meta: self.neg_prompt_input.value = meta["negative_prompt"]
                self.prompt_input.update()
                self.neg_prompt_input.update()
                self.page.snack_bar = ft.SnackBar(ft.Text("✅ 已读取元数据"), open=True)
                self.page.update()
        except Exception as e: print(f"Meta error: {e}")

    def _open_custom_size_dialog(self, e):
        w = ft.TextField(label="W", width=100)
        h = ft.TextField(label="H", width=100)
        def confirm(e):
            if w.value and h.value:
                k = f"{w.value}x{h.value}"
                # 修复后的代码：
                self.size_dropdown.options.insert(0, ft.dropdown.Option(k, f"{k} (自定义)"))
                self.size_dropdown.value = k
                self.size_dropdown.update()
            utils.safe_close_dialog(self.page, dlg)
        dlg = ft.AlertDialog(content=ft.Row([w, ft.Text("x"), h]), actions=[ft.ElevatedButton("确定", on_click=confirm)])
        utils.safe_open_dialog(self.page, dlg)

    def _on_gallery_btn_pan(self, e: ft.DragUpdateEvent):
        # 简单的拖动逻辑，坐标由 GestureDetector 管理
        pass

    def _update_grid_buttons_visibility(self):
        for card in self.results_grid.controls:
            try:
                action_bar = card.content.controls[3].content
                btn_browser = action_bar.controls[2] # 注意：索引变化，因为加入了 edit 按钮
                btn_dl = action_bar.controls[3]
                if self.is_wide_mode:
                    btn_dl.visible = True
                    btn_browser.visible = False
                else:
                    btn_dl.visible = False
                    btn_browser.visible = True
            except: pass
        self.results_grid.update()
