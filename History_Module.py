import flet as ft
import utils
import os

class History_View:
    def __init__(self, page: ft.Page, config: dict, viewer_callback):
        """
        :param page: Flet Page 对象
        :param config: 全局配置
        :param viewer_callback: 点击图片时的回调函数
        """
        self.page = page
        self.config = config
        self.viewer_callback = viewer_callback
        
        # 解构配置
        self.primary_color = utils.MORANDI_COLORS.get(config.get("theme_color_name"), "#D0A467")
        self.theme_mode = config.get("theme_mode", "dark")
        
        # 内部状态
        self.history_images_objs = [] # 存储图片对象，用于传递给查看器
        self.is_wide_mode = False
        self.current_columns = 3 # 默认3列
        
        # 初始化 UI
        self._init_components()

    def _init_components(self):
        # 1. 主滚动容器 (瀑布流的载体)
        # 我们使用一个 Row 包含多个 Column 来模拟瀑布流
        self.masonry_row = ft.Row(
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.START,
            spacing=10,
            expand=True # 让Row撑满容器
        )

        # 使用 Container 包裹 masonry_row 来设置内边距
        self.masonry_wrapper = ft.Container(
            content=self.masonry_row,
            padding=ft.padding.only(left=10, right=10, top=10, bottom=80), # 底部留白给悬浮条
            expand=False # 内容本身不强制expand，由外部Column控制滚动
        )

        self.scroll_container = ft.Column(
            controls=[self.masonry_wrapper],
            scroll=ft.ScrollMode.AUTO,
            expand=True,
            spacing=0
        )
        
        # 2. 空状态提示
        self.empty_text = ft.Text("暂无本次会话的历史记录", color="grey", size=14, visible=False)
        self.empty_icon = ft.Icon("history_toggle_off", color="grey", size=40, visible=False)
        
        self.empty_container = ft.Container(
            content=ft.Column([
                self.empty_icon,
                ft.Container(height=10),
                self.empty_text
            ], alignment="center", horizontal_alignment="center"),
            alignment=ft.alignment.center, 
            expand=True,
            visible=False
        )

        # 3. 底部悬浮控制栏 (刷新 + 滑块)
        self.refresh_btn = ft.IconButton(
            icon="refresh", 
            icon_color="white",
            bgcolor=self.primary_color, 
            on_click=lambda e: self.refresh_history(),
            tooltip="刷新历史记录"
        )
        
        self.size_slider = ft.Slider(
            min=1, max=6, divisions=5, value=3, 
            label="列数: {value}",
            active_color=self.primary_color,
            on_change_end=self._on_slider_change, # 拖动结束后再刷新布局
            width=150
        )

        self.control_bar = ft.Container(
            content=ft.Row([
                ft.Icon("photo_size_select_actual", size=16, color=utils.get_text_color(self.theme_mode)), # 大图图标 (1列)
                self.size_slider,
                ft.Icon("photo_size_select_large", size=16, color=utils.get_text_color(self.theme_mode)), # 小图图标 (多列)
                ft.VerticalDivider(width=10, color="transparent"),
                self.refresh_btn
            ], alignment="center", spacing=5),
            bgcolor=utils.get_dropdown_bgcolor(self.theme_mode),
            padding=ft.padding.symmetric(horizontal=15, vertical=5),
            border_radius=30,
            shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.with_opacity(0.2, "black")),
            border=ft.border.all(1, utils.get_border_color(self.theme_mode)),
            bottom=20, right=20
        )

        # 4. 主容器
        self.content = ft.Stack([
            self.scroll_container,
            self.empty_container,
            self.control_bar
        ], expand=True)

    def get_content(self):
        """返回主视图控件"""
        return self.content

    def _on_slider_change(self, e):
        """滑块回调：改变列数"""
        # 【修改逻辑】所见即所得：滑块数值 = 列数
        # 1 = 1列 (大图)
        # 6 = 6列 (小图)
        cols = int(e.control.value)
        
        if cols != self.current_columns:
            self.current_columns = cols
            self.refresh_history() # 重新布局

    def refresh_history(self):
        """读取本地缓存并刷新界面 (瀑布流布局)"""
        paths = utils.get_cached_history()
        
        self.history_images_objs = [] # 清空旧引用
        self.masonry_row.controls.clear() # 清空旧布局
        
        if not paths:
            self.empty_container.visible = True
            self.empty_text.visible = True
            self.empty_icon.visible = True
            self.scroll_container.visible = False
            self.scroll_container.update()
            self.empty_container.update()
            return

        self.empty_container.visible = False
        self.scroll_container.visible = True
        
        # 1. 创建 N 个列容器
        columns = [ft.Column(spacing=10, expand=True, alignment="start") for _ in range(self.current_columns)]
        
        # 2. 遍历图片并分发到列中
        for idx, path in enumerate(paths):
            # 尝试快速读取元数据
            meta = None
            try:
                with open(path, "rb") as f:
                    file_bytes = f.read()
                    meta = utils.extract_metadata_from_png(file_bytes)
            except: pass
            
            # 创建图片控件
            img = ft.Image(
                src=path,
                fit=ft.ImageFit.CONTAIN, 
                border_radius=10,
                gapless_playback=True,
                animate_opacity=300,
                expand=True # 宽度填满列
            )
            
            # 挂载数据
            img.data = meta
            img.is_downloaded = True 
            
            self.history_images_objs.append(img)
            
            # 包装卡片
            card = ft.Container(
                content=img,
                border_radius=10,
                on_click=lambda e, i=img: self._on_image_click(i),
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                shadow=ft.BoxShadow(blur_radius=5, color=ft.Colors.with_opacity(0.1, "black")),
                bgcolor=utils.get_dropdown_bgcolor(self.theme_mode) # 给个底色防止透明图看起来怪
            )
            
            # 简单的轮询分发 (Round-Robin)
            target_col = idx % self.current_columns
            columns[target_col].controls.append(card)
            
        # 3. 将列添加到 Row 中
        self.masonry_row.controls = columns
        
        self.masonry_row.update()
        self.scroll_container.update()
        self.empty_container.update()

    def _on_image_click(self, clicked_img):
        """点击图片，调用主程序的查看器"""
        if clicked_img in self.history_images_objs:
            idx = self.history_images_objs.index(clicked_img)
            self.viewer_callback(clicked_img.src, self.history_images_objs, idx)

    def update_theme(self, primary_color, theme_mode):
        """响应主题切换"""
        self.primary_color = primary_color
        self.theme_mode = theme_mode
        
        # 更新刷新按钮
        self.refresh_btn.bgcolor = primary_color
        self.size_slider.active_color = primary_color
        
        # 更新控制条背景
        self.control_bar.bgcolor = utils.get_dropdown_bgcolor(theme_mode)
        self.control_bar.border = ft.border.all(1, utils.get_border_color(theme_mode))
        
        # 更新图标颜色
        text_color = utils.get_text_color(theme_mode)
        self.control_bar.content.controls[0].color = text_color
        self.control_bar.content.controls[2].color = text_color
        
        # 更新现有卡片的底色
        if self.masonry_row.controls:
            for col in self.masonry_row.controls:
                for card in col.controls:
                    card.bgcolor = utils.get_dropdown_bgcolor(theme_mode)
        
        try: 
            self.refresh_btn.update()
            self.control_bar.update()
            self.masonry_row.update()
        except: pass

    def on_resize(self, is_wide, w, h):
        """响应式布局"""
        self.is_wide_mode = is_wide
        pass

    def set_grid_columns(self, cols):
        """兼容接口"""
        # 【修改逻辑】直接设置，不反转
        self.current_columns = cols
        self.size_slider.value = cols
        self.size_slider.update()
        self.refresh_history()