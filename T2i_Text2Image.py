import flet as ft
import requests
import json
import asyncio
import random
import utils  # 引入公共工具模块

# ==========================================
#      T2I 功能模块封装 (去布局版)
# ==========================================

class T2I_View:
    def __init__(self, page: ft.Page, config: dict, viewer_callback, switch_view_callback, transfer_callback=None):
        """
        :param page: Flet Page 对象
        :param config: 来自 Main_App 的全局配置字典
        :param viewer_callback: 函数(src, all_images, index)，用于调用全局查看器
        :param switch_view_callback: 函数(target_index)，用于通知主程序切换页面 (0:参数, 1:结果)
        :param transfer_callback: (新增) 函数(image_src)，用于将图片发送到编辑模块
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
        self.generated_images_objs = [] # 存储结果Grid中的Image对象，用于传递给查看器

        # 常量定义
        self.DEFAULT_MODEL_OPTIONS = [
            {"key": "Tongyi-MAI/Z-Image-Turbo", "text": "造相-Z-Image-Turbo"},
            {"key": "black-forest-labs/FLUX.2-dev", "text": "FLUX.2-dev"},
            {"key": "Qwen/Qwen-Image", "text": "Qwen-Image"},
            {"key": "Qwen/Qwen-Image-Edit", "text": "Qwen-Image-Edit"},
            {"key": "black-forest-labs/FLUX.1-Krea-dev", "text": "FLUX.1-Krea-dev"},
            {"key": "MusePublic/FLUX.1-Kontext-Dev", "text": "FLUX.1-Kontext-Dev"},
        ]
        
        self.SIZE_OPTIONS = [
            {"key": "928x1664", "text": "928x1664 (竖屏)"},
            {"key": "1104x1472", "text": "1104x1472 (竖屏)"},
            {"key": "1328x1328", "text": "1328x1328 (方形)"},
            {"key": "1472x1104", "text": "1472x1104 (横屏)"},
            {"key": "1664x928", "text": "1664x928 (横屏)"},
            {"key": "2048x2048", "text": "2048x2048 (方形)"},
        ]

        # 初始化UI组件 (但不构建顶层布局)
        self._init_components()

    # ================= 外部接口 (供 Main_App 调用) =================

    def get_input_content(self):
        """返回参数输入区的 Column 容器"""
        # 注意：这里返回一个 Column，Main_App 会将其放入可滚动的容器中
        # generate_btn 不在这里，而是通过 get_generate_btn 单独获取，放在底部固定栏
        return self.page1_scroll_col

    def get_generate_btn(self):
        """返回生成按钮，供 Main_App 放置在底部固定栏"""
        return self.generate_btn

    def get_results_content(self):
        """返回结果展示 Grid"""
        return self.results_grid
    
    def set_grid_columns(self, cols):
        """设置 Grid 列数 (供 Main_App 的悬浮菜单调用)"""
        self.results_grid.runs_count = cols
        self.results_grid.max_extent = None
        self.results_grid.update()

    def update_config(self, new_config):
        """当 Main_App 设置改变时被调用"""
        self.config = new_config
        self.api_keys = new_config.get("api_keys", [])
        self.baidu_config = new_config.get("baidu_config", {})
        self.power_config = new_config.get("power_mode_config", {}) # 更新强力配置
        
        # --- 强力模式逻辑：更新 Slider 最大值与视觉样式 ---
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
        
        # 强制刷新一下 Batch Row 以显示文字变化
        try: self.batch_row.update()
        except: pass

    def update_theme(self, primary_color, theme_mode):
        """当 Main_App 主题改变时被调用"""
        self.primary_color = primary_color
        self.theme_mode = theme_mode
        
        # --- 新增：获取当前主题对应的文字颜色 ---
        text_c = utils.get_text_color(theme_mode)
        
        # 1. 更新生成按钮
        self.generate_btn.bgcolor = primary_color
        
        # 2. 更新 Slider 颜色
        # 【修改点】判断强力模式，防止主题切换覆盖红色警示
        is_power_mode = self.power_config.get("enabled", False)
        
        if not is_power_mode:
            # 普通模式：跟随主题色
            self.batch_slider.active_color = primary_color
            if hasattr(self, 'batch_row'): self.batch_row.controls[0].color = text_c
        else:
            # 强力模式：保持红色
            self.batch_slider.active_color = "red"
            if hasattr(self, 'batch_row'): self.batch_row.controls[0].color = "red"
            
        self.steps_slider.active_color = primary_color
        self.guidance_slider.active_color = primary_color

        # --- 新增：更新其他标签文字颜色 ---
        if hasattr(self, 'steps_row'): self.steps_row.controls[0].color = text_c
        if hasattr(self, 'guidance_row'): self.guidance_row.controls[0].color = text_c
        if hasattr(self, 'seed_row'): self.seed_row.controls[0].color = text_c
        
        # 3. 更新输入框边框颜色
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

        # 4. 更新结果 Grid 中的颜色 (Loading圈, 按钮等)
        for card in self.results_grid.controls: 
            try:
                stack = card.content
                # Loading 区域
                loading_bg = stack.controls[0]
                if isinstance(loading_bg.content, ft.Column):
                    col = loading_bg.content
                    col.controls[0].color = primary_color # Ring
                    col.controls[2].color = primary_color # Text
                
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
        """响应式布局调整 - 仅负责组件内部样式，不负责整体页面结构"""
        self.is_wide_mode = is_wide
        
        # 1. 更新 Grid 上的下载按钮显示 (宽屏显示下载icon, 窄屏显示地球icon)
        self._update_grid_buttons_visibility()

        # 2. 调整 Grid 布局参数
        if is_wide:
            self.results_grid.max_extent = 300
            # 宽屏模式下 Prompt 高度自适应
            self.page1_scroll_col.scroll = None # 宽屏下 Scroll 由外部容器(Main App)处理或不需要
            self.prompt_input.height = None
            self.prompt_input.expand = True
        else:
            self.results_grid.max_extent = 160
            # 竖屏模式下 Prompt 高度固定，Column 开启滚动
            self.page1_scroll_col.scroll = ft.ScrollMode.AUTO
            self.prompt_input.height = 200
            self.prompt_input.expand = False

        self.results_grid.update()
        self.page1_scroll_col.update()
        self.prompt_input.update()

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
            value=self.DEFAULT_MODEL_OPTIONS[0]["key"], text_size=14, content_padding=ft.padding.only(left=10, right=10, bottom=5),
            border_color="transparent", border_width=0, 
            fill_color=utils.get_dropdown_bgcolor(self.theme_mode), 
            bgcolor=utils.get_dropdown_fill_color(self.theme_mode),
            focused_bgcolor=ft.Colors.TRANSPARENT, expand=True 
        )
        
        self.model_dropdown_container = ft.Container(content=self.model_dropdown, height=40, border=ft.border.all(1, utils.get_border_color(self.theme_mode)), border_radius=8, expand=True, alignment=ft.alignment.center_left)
        self.custom_model_btn = ft.ElevatedButton("自定义", height=40, width=68, bgcolor="transparent", color=self.primary_color, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=0, padding=0, side=ft.BorderSide(1, utils.get_border_color(self.theme_mode))), on_click=self._open_custom_model_dialog)
        self.model_row = ft.Row([self.model_dropdown_container, self.model_search_field, self.custom_model_btn], spacing=5)

        # 2. 提示词区域
        self.meta_file_picker = ft.FilePicker(on_result=self._on_meta_file_picked)
        self.page.overlay.append(self.meta_file_picker)

        self.prompt_input = ft.TextField(
            hint_text="正面提示词 (支持粘贴带元数据图片)...", multiline=True, expand=True, text_size=13, bgcolor="transparent", 
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
            content=ft.Stack([self.prompt_input, self.prompt_trans_row], expand=True), expand=True, 
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

        # 3. 分辨率与自定义
        self.size_dropdown = ft.Dropdown(
            options=[ft.dropdown.Option(s["key"], s["text"]) for s in self.SIZE_OPTIONS], value=self.SIZE_OPTIONS[0]["key"],
            text_size=14, content_padding=ft.padding.only(left=10, right=10, bottom=5), border_color="transparent", border_width=0,
            fill_color=utils.get_dropdown_bgcolor(self.theme_mode), bgcolor=utils.get_dropdown_fill_color(self.theme_mode), focused_bgcolor=ft.Colors.TRANSPARENT, expand=True
        )
        self.size_dropdown_container = ft.Container(content=self.size_dropdown, height=40, border=ft.border.all(1, utils.get_border_color(self.theme_mode)), border_radius=8, expand=True, alignment=ft.alignment.center_left)
        self.custom_size_btn = ft.ElevatedButton("自定义", height=40, width=68, bgcolor="transparent", color=self.primary_color, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8), elevation=0, padding=0, side=ft.BorderSide(1, utils.get_border_color(self.theme_mode))), on_click=self._open_custom_size_dialog)
        self.size_row = ft.Row([self.size_dropdown_container, self.custom_size_btn], spacing=5)

        # 4. Sliders
        initial_key_count = max(1, len(self.api_keys))
        self.batch_row, self.batch_slider, self.batch_val_text = self._create_slider_row("生图数量", 1, max(1, initial_key_count), initial_key_count)
        self.steps_row, self.steps_slider, self.steps_val_text = self._create_slider_row("生图步数", 5, 100, 30, 5) 
        self.guidance_row, self.guidance_slider, self.guidance_val_text = self._create_slider_row("引导系数", 1, 20, 3.5, 0.5) 

        # 5. Seed
        self.seed_input = ft.TextField(
            value="-1", text_size=12, height=40, content_padding=ft.padding.symmetric(horizontal=10, vertical=0),
            border_radius=8, bgcolor="transparent", border_color=utils.get_border_color(self.theme_mode), border_width=1, keyboard_type="number", expand=True,
            on_blur=self._validate_seed  
        )
        self.seed_row = ft.Row([ft.Text("随机种子", size=14, width=60, color="grey"), self.seed_input], alignment="center", vertical_alignment="center")

        # 6. 生成按钮
        self.generate_btn = ft.ElevatedButton(
            "开始生成", icon="brush", bgcolor=self.primary_color, color="white", height=50, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=12)), width=float("inf"),
            on_click=self._run_gen
        )

        # 7. 结果区域
        self.results_grid = ft.GridView(expand=True, runs_count=None, max_extent=350, child_aspect_ratio=1.0, spacing=10, run_spacing=10, padding=10)

        # 8. 绑定 File Drop (注意：可能会被其他模块覆盖，需要在 Main App 中协调或由用户激活模块时触发)
        self.page.on_file_drop = self._on_meta_file_picked

        # 9. 构建参数输入区的列表容器 (page1_scroll_col)
        self.page1_scroll_col = ft.Column([
            self.model_row, ft.Container(height=8),
            self.prompt_container, ft.Container(height=8),
            self.neg_prompt_container, ft.Container(height=8),
            self.size_row, ft.Container(height=8),
            self.batch_row, ft.Container(height=5),
            self.steps_row, ft.Container(height=5),
            self.guidance_row, ft.Container(height=5),
            self.seed_row, ft.Container(height=15),
            # generate_btn 放在外部固定栏，这里不包含
        ], spacing=0, horizontal_alignment="stretch", expand=True, scroll=ft.ScrollMode.AUTO)

    # ================= 逻辑处理 =================

    async def _run_gen(self, e):
        # 宽屏模式下如果有折叠，先展开 (由 Main App 处理布局，这里只负责发信号或忽略)
        
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
            self.page.snack_bar = ft.SnackBar(ft.Text("请输入提示词"), open=True)
            self.page.update()
            return

        # 窄屏模式下，点击生成后自动跳转到结果页
        if not self.is_wide_mode and self.switch_view_callback:
            self.switch_view_callback(1)

        # 设置Grid比例
        size_str = self.size_dropdown.value
        try:
            w_str, h_str = size_str.split()[0].split('x')
            aspect_ratio = float(w_str) / float(h_str)
            self.results_grid.child_aspect_ratio = aspect_ratio
        except: self.results_grid.child_aspect_ratio = 1.0
        
        self.generate_btn.disabled = True
        self.generate_btn.update()
        
        batch_count = int(self.batch_slider.value)
        self.results_grid.controls.clear()
        self.generated_images_objs = [] # 清空数据引用
        
        tasks_ui = []
        for i in range(batch_count):
            # 注意：此处解构增加了 btn_edit
            card, img, status, btn_dl, btn_info, btn_browser, btn_edit = self._create_result_card_ui()
            self.results_grid.controls.append(card)
            # 存下 Image 对象引用用于查看器
            self.generated_images_objs.append(img)
            tasks_ui.append((img, status, btn_dl, btn_info, btn_browser, btn_edit))
        
        self.results_grid.update()
        
        # 异步生成
        tasks = []
        for i in range(batch_count):
            # 循环取 Key
            key_to_use = keys_to_use[i % len(keys_to_use)]
            
            tasks.append(asyncio.create_task(self._generate_single_image(i, key_to_use, tasks_ui[i])))
            
            # 【新增】可配置的延时，防止触发 QPS 限制
            delay_time = float(self.power_config.get("request_delay", 0.2))
            await asyncio.sleep(delay_time)
        
        await asyncio.gather(*tasks, return_exceptions=True)
        self.generate_btn.disabled = False
        self.generate_btn.update()

    async def _generate_single_image(self, idx, api_key, ui_refs):
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
            
            # Seed 处理
            raw_seed = self.seed_input.value
            try: seed_val = int(raw_seed) if raw_seed.strip() else -1
            except ValueError: seed_val = -1
            if seed_val == -1: seed_val = random.randint(1, 10000000)
            current_seed = seed_val + idx 

            payload = {
                "model": self.model_dropdown.value, 
                "prompt": self.prompt_input.value, 
                "negative_prompt": self.neg_prompt_input.value,
                "size": self.size_dropdown.value, 
                "num_inference_steps": int(self.steps_val_text.value),  
                "guidance_scale": float(self.guidance_val_text.value),  
                "seed": current_seed
            }

            def do_post():
                return requests.post(f"{utils.BASE_URL}v1/images/generations", headers={**headers, "X-ModelScope-Async-Mode": "true"}, data=json.dumps(payload, ensure_ascii=False).encode('utf-8'), timeout=20)
            
            res = await asyncio.to_thread(do_post)
            res.raise_for_status()
            task_id = res.json().get("task_id")
            if not task_id: raise Exception("无TaskID")

            for _ in range(60): 
                await asyncio.sleep(2)
                def do_poll():
                    return requests.get(f"{utils.BASE_URL}v1/tasks/{task_id}", headers={**headers, "X-ModelScope-Task-Type": "image_generation"}, timeout=10)
                res_poll = await asyncio.to_thread(do_poll)
                data = res_poll.json()
                raw_status = data.get("task_status")
                
                if raw_status == "SUCCEED":
                    toggle_ring(False)
                    output_images = data.get("output_images", [])
                    if output_images:
                        remote_url = output_images[0]
                        
                        # =================【关键修改】自动缓存逻辑 =================
                        status_ref.value = "缓存中..."
                        status_ref.update()
                        
                        # 下载并保存到临时缓存，注入元数据
                        local_cache_path = await utils.save_to_cache(remote_url, payload)
                        
                        if local_cache_path:
                            # 如果缓存成功，显示本地路径
                            img_ref.src = local_cache_path
                        else:
                            # 降级：如果缓存失败，显示远程链接
                            img_ref.src = remote_url
                        
                        # 无论哪种情况，数据对象都挂载上去
                        img_ref.data = payload 
                        img_ref.visible = True
                        
                        # 注意：虽然在缓存里，但对于“下载到 T2I 文件夹”这个按钮来说，它还没“下载”
                        # 但为了体验，我们不自动禁用下载按钮，让用户决定是否保存到 T2I
                        img_ref.is_downloaded = False
                        
                        info_ref.visible = True
                        edit_ref.visible = True 
                        
                        # 更新下载按钮可见性
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
        img = ft.Image(src="", fit=ft.ImageFit.CONTAIN, visible=False, expand=True, animate_opacity=300, border_radius=10)
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
        btn_dl = ft.IconButton(icon="save_alt", icon_color=self.primary_color, icon_size=18, tooltip="保存到T2I文件夹", visible=False)

        # 🟢 新增：发送到编辑按钮
        btn_edit = ft.IconButton(icon="auto_fix_high", icon_color=self.primary_color, icon_size=18, tooltip="发送到编辑", visible=False)

        async def on_edit_click(e):
            if img.src and self.transfer_callback:
                # 调用传入的回调函数，将图片URL发送过去
                await self.transfer_callback(img.src)
        
        btn_edit.on_click = on_edit_click

        # 绑定下载事件 (调用 utils)
        async def on_browser_click(e):
            if img.src:
                meta = getattr(img, "data", None)
                success = await utils.download_via_local_server(self.page, img.src, meta)
                if success:
                    img.is_downloaded = True
                    # 1. 强制更新当前点击的按钮 (确保反应)
                    e.control.icon = "check_circle"
                    e.control.disabled = True
                    e.control.update()
                    # 2. 同步更新两个按钮对象
                    self._mark_btn_downloaded(btn_browser)
                    self._mark_btn_downloaded(btn_dl)
        
        async def on_dl_click(e):
            if img.src:
                meta = getattr(img, "data", None)
                # 调用 utils.save_image_to_local_folder
                # 由于 img.src 现在是本地路径，utils 内部会自动处理为 copy 操作
                success = await utils.save_image_to_local_folder(self.page, img.src, utils.T2I_FOLDER, meta)
                if success:
                    img.is_downloaded = True
                    # 1. 强制更新当前点击的按钮
                    e.control.icon = "check_circle"
                    e.control.disabled = True
                    e.control.update()
                    # 2. 同步更新两个按钮对象
                    self._mark_btn_downloaded(btn_dl)
                    self._mark_btn_downloaded(btn_browser)

        btn_browser.on_click = on_browser_click
        btn_dl.on_click = on_dl_click
        
        img.associated_browser_btn = btn_browser
        img.associated_dl_btn = btn_dl
        
        # 核心：点击图片调用全局查看器
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
        # 过滤出所有 src 不为空的有效图片
        valid_imgs = [img for img in self.generated_images_objs if img.src and img.src.strip()]

        # 在有效列表中查找当前点击图片的索引
        if clicked_img in valid_imgs:
            idx = valid_imgs.index(clicked_img)
            # 仅将有效列表传递给查看器，避免显示红框报错
            self.viewer_callback(clicked_img.src, valid_imgs, idx)

    def _mark_btn_downloaded(self, btn):
        btn.icon = "check_circle"
        btn.icon_color = self.primary_color
        btn.disabled = True
        btn.update()

    # ================= 辅助逻辑 =================

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
        # 内部对话框
        input_field = ft.TextField(
            value=self.stored_custom_models, multiline=True, min_lines=10, max_lines=15, text_size=12, border_radius=10
        )
        async def save(e):
            self.stored_custom_models = input_field.value
            await utils.save_config_to_storage(self.page, "custom_models", self.stored_custom_models)
            # 刷新下拉框
            all_models = self._get_all_models()
            self.model_dropdown.options = [ft.dropdown.Option(m["key"], m["text"]) for m in all_models]
            self.model_dropdown.update()
            utils.safe_close_dialog(self.page, dlg)

        dlg = ft.AlertDialog(
            title=ft.Text("自定义模型", size=14),
            content=ft.Container(width=300, content=ft.Column([ft.Text("每行：名称 地址", size=12), input_field], tight=True)),
            actions=[ft.TextButton("取消", on_click=lambda e: utils.safe_close_dialog(self.page, dlg)), ft.ElevatedButton("保存", on_click=save)]
        )
        utils.safe_open_dialog(self.page, dlg)

    def _on_model_search_change(self, e):
        query = (e.control.value or "").lower().strip()
        all_models = self._get_all_models()
        filtered = [m for m in all_models if query in m["text"].lower() or query in m["key"].lower()] if query else all_models
        self.model_dropdown.options = [ft.dropdown.Option(m["key"], m["text"]) for m in filtered]
        if filtered and self.model_dropdown.value not in [m["key"] for m in filtered]:
             self.model_dropdown.value = filtered[0]["key"]
        self.model_dropdown.update()

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

    # 【新增】键盘事件处理 (改名为公开方法，供Main_App调用)
    def handle_keyboard_event(self, e: ft.KeyboardEvent):
        if e.ctrl and e.key.lower() == "v":
            if utils.HAS_PIL:
                try:
                    # 尝试处理剪贴板图片元数据
                    self._process_clipboard_metadata()
                except: pass

    # 翻译与提示词辅助
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

    def _handle_translate(self, e, field, lang):
        text = field.value
        if text:
            res = utils.translate_text(self.page, text, self.baidu_config.get("appid"), self.baidu_config.get("key"), lang)
            if res:
                field.value = res
                field.update()

    def _process_clipboard_metadata(self, e=None):
        if not utils.HAS_PIL: return
        try:
            content = utils.ImageGrab.grabclipboard()
            meta = None
            if isinstance(content, list): # 文件列表
                for path in content:
                    if path.lower().endswith('.png'):
                        with open(path, "rb") as f: meta = utils.extract_metadata_from_png(f.read())
                        if meta: break
            elif content: # 图片对象
                self.page.snack_bar = ft.SnackBar(ft.Text("仅支持复制PNG文件，不支持直接复制图片内容"), open=True)
                self.page.update()
                return

            if meta: self._apply_metadata(meta)
            else:
                self.page.snack_bar = ft.SnackBar(ft.Text("未发现元数据"), open=True)
                self.page.update()
        except Exception as ex: print(ex)

    def _on_meta_file_picked(self, e):
        if e.files:
            with open(e.files[0].path, "rb") as f:
                meta = utils.extract_metadata_from_png(f.read())
                if meta: self._apply_metadata(meta)

    def _apply_metadata(self, meta):
        if "prompt" in meta: self.prompt_input.value = meta["prompt"]
        if "negative_prompt" in meta: self.neg_prompt_input.value = meta["negative_prompt"]
        if "seed" in meta: self.seed_input.value = str(meta["seed"])
        if "num_inference_steps" in meta:
            self.steps_slider.value = float(meta["num_inference_steps"])
            self.steps_val_text.value = str(meta["num_inference_steps"])
        if "guidance_scale" in meta:
            self.guidance_slider.value = float(meta["guidance_scale"])
            self.guidance_val_text.value = str(meta["guidance_scale"])
        if "model" in meta:
             # 简单的模型匹配逻辑
             self.model_dropdown.value = meta["model"] # 如果不在列表中也赋值
             
        self.prompt_input.update()
        self.neg_prompt_input.update()
        self.seed_input.update()
        self.steps_slider.update()
        self.steps_val_text.update()
        self.guidance_slider.update()
        self.guidance_val_text.update()
        self.model_dropdown.update()
        self.page.snack_bar = ft.SnackBar(ft.Text("已读取元数据"), open=True)
        self.page.update()

    def _open_custom_size_dialog(self, e):
        w = ft.TextField(label="W", width=100)
        h = ft.TextField(label="H", width=100)
        def confirm(e):
            if w.value and h.value:
                k = f"{w.value}x{h.value}"
                self.size_dropdown.options.insert(0, ft.dropdown.Option(k, f"{k} (自定义)"))
                self.size_dropdown.value = k
                self.size_dropdown.update()
            utils.safe_close_dialog(self.page, dlg)
        dlg = ft.AlertDialog(content=ft.Row([w, ft.Text("x"), h]), actions=[ft.ElevatedButton("确定", on_click=confirm)])
        utils.safe_open_dialog(self.page, dlg)

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