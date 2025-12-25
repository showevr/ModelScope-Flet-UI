import flet as ft
import asyncio
import utils
from components import ImageViewer

# 引入功能模块
import T2i_Text2Image as T2I_Module
import I2i_ImageEditor as I2I_Module
import History_Module # 新增：引入历史模块
import time

async def main(page: ft.Page):
    # ================= 1. 基础窗口设置 =================
    page.window.min_width = 380
    page.window.min_height = 600
    page.window.resizable = True   
    page.title = "魔塔AI大全"
    page.padding = 0
    page.spacing = 0
    page.appbar = None
    
    # 启动本地图片服务器
    utils.start_local_server()
    
    # 【新增】启动时初始化缓存系统 (清理旧缓存)
    utils.init_cache_system()

    # ================= 2. 读取全局配置 =================
    config = await utils.load_global_config(page)
    
    # 全局变量初始化
    current_api_keys = config["api_keys"]
    current_baidu_config = config["baidu_config"]
    current_theme_color_name = config["theme_color_name"]
    current_theme_mode = config["theme_mode"]
    current_power_config = config["power_mode_config"] 
    
    current_primary_color = utils.MORANDI_COLORS.get(current_theme_color_name, "#D0A467")
    current_text_color = utils.get_text_color(current_theme_mode)

    # ================= 3. 全局状态定义 =================
    
    # 定义应用清单 (用于双击切换逻辑)
    # 【修改】加入历史记录
    APP_MAP = {
        "t2i": {"name": "文生图", "icon": "palette"},
        "i2i": {"name": "图片编辑", "icon": "auto_fix_high"},
        "history": {"name": "历史记录", "icon": "history"}
    }

    current_app_key = "t2i" 
    t2i_page_index = 0      
    is_wide_mode = False
    left_panel_visible = True
    is_sidebar_open = False 
    
    # ------------------ 功能切换浮层 ------------------
    func_menu_content = ft.Column(spacing=2)
    
    anim_style = utils.MyAnimation(200, "easeOut") if utils.MyAnimation else None
    scale_style = utils.MyScale(0.9) if utils.MyScale else None

    func_menu_card = ft.Container(
        content=func_menu_content,
        bgcolor=utils.get_dropdown_bgcolor(current_theme_mode),
        border_radius=0, 
        border=ft.border.only(bottom=ft.BorderSide(1, ft.Colors.with_opacity(0.1, "on_surface"))), 
        padding=5,
        shadow=ft.BoxShadow(blur_radius=20, color=ft.Colors.with_opacity(0.3, "black")),
        visible=False, 
        bottom=56,       
        left=0, right=0, 
        alignment=ft.alignment.center,
        animate_opacity=200,
        animate_scale=anim_style,
        scale=scale_style,
        opacity=0
    )

    def open_func_menu(e):
        """双击底部导航中间按钮触发：显示切换菜单"""
        func_menu_card.width = None 
        func_menu_card.left = 0
        func_menu_card.right = 0
        
        items = []
        for key, info in APP_MAP.items():
            if key == current_app_key: continue 
            
            item = ft.Container(
                content=ft.Row([
                    ft.Icon(info['icon'], size=20, color=current_primary_color), 
                    ft.Text(info['name'], size=14, color=current_text_color)
                ], alignment="center", spacing=10),
                padding=ft.padding.symmetric(vertical=12, horizontal=10),
                border_radius=8,
                ink=True,
                on_click=lambda e, k=key: switch_app(k)
            )
            items.append(item)

        if not items:
            items.append(ft.Container(content=ft.Text("无其他功能", size=12, color="grey"), padding=10, alignment=ft.alignment.center))

        func_menu_content.controls = items
        
        func_menu_card.visible = True
        func_menu_card.opacity = 1
        func_menu_card.scale = 1.0 
        func_menu_card.update()

    def close_func_menu():
        """关闭功能菜单"""
        if func_menu_card.visible:
            func_menu_card.opacity = 0
            func_menu_card.scale = 0.9
            func_menu_card.update()
            func_menu_card.visible = False
            page.update()

    # -------------------------------------------------------

    # 前置声明 switch_app
    def switch_app(key):
        nonlocal current_app_key, t2i_page_index
        
        close_func_menu()
        current_app_key = key
        toggle_sidebar(False)
        
        is_t2i = (key == 't2i')
        is_i2i = (key == 'i2i')
        is_history = (key == 'history')
        
        # 1. 核心区域显隐切换
        # 如果是 T2I/I2I，显示 Slider；如果是 History，显示 History Container
        if is_history:
            t2i_slider_container.visible = False
            history_container.visible = True
            # History 模式下不需要底部生成按钮栏
            fixed_bottom_action_bar.visible = False
            # 也不需要分页点
            dots_row.visible = False
            
            # 刷新历史记录
            history_app.refresh_history()
        else:
            t2i_slider_container.visible = True
            history_container.visible = False
            fixed_bottom_action_bar.visible = True
            
            # 恢复 Dots (根据宽屏模式)
            dots_row.visible = not is_wide_mode

            # T2I / I2I 内部切换
            t2i_input_wrapper.visible = is_t2i
            i2i_input_wrapper.visible = is_i2i
            
            t2i_btn_wrapper.visible = is_t2i
            i2i_btn_wrapper.visible = is_i2i
            
            t2i_result_wrapper.visible = is_t2i
            i2i_result_wrapper.visible = is_i2i
            
            # 键盘事件绑定
            module = t2i_app if is_t2i else i2i_app
            page.on_keyboard_event = module.handle_keyboard_event
            
            # 更新模块布局
            module.update_theme(current_primary_color, current_theme_mode)
            module.on_resize(is_wide_mode, page.width, page.height)
            
            if not is_wide_mode:
                t2i_page_index = 0
                switch_t2i_page(0)

        # 2. 更新底部导航图标和文字
        info = APP_MAP.get(key, {"name": "未知", "icon": "help"})
        nav_btn_func_icon.name = info["icon"]
        nav_btn_func_text.value = info["name"]
        
        # 3. 更新侧边栏选中状态
        sidebar_items_container.controls = [
            build_sidebar_item("palette", "文生图", "t2i", is_t2i),
            build_sidebar_item("auto_fix_high", "图片编辑", "i2i", is_i2i),
            build_sidebar_item("history", "历史记录", "history", is_history)
        ]
        
        page.update()

    # ================= 核心：图片流转逻辑 =================
    
    async def handle_transfer_to_edit(image_src):
        if not image_src: return
        page.snack_bar = ft.SnackBar(ft.Text("正在准备图片数据..."), open=True)
        page.update()

        final_path = image_src
        # 如果是网络图片，先下载；如果是本地缓存(History)，直接用
        if image_src.startswith("http"):
            local_path = await utils.save_temp_image_from_url(image_src)
            if local_path:
                final_path = local_path
            else:
                page.snack_bar = ft.SnackBar(ft.Text("图片下载失败，无法发送到编辑"), open=True)
                page.update()
                return

        i2i_app.set_input_image(final_path)
        switch_app('i2i')
        page.snack_bar = ft.SnackBar(ft.Text("✅ 图片已发送到编辑"), open=True)
        page.update()
        
    def update_gallery_btn_visibility():
        # 历史模式下，不需要显示结果切换按钮
        if current_app_key == 'history':
            gallery_control_gesture.visible = False
            gallery_control_gesture.update()
            return

        is_on_result_view = (is_wide_mode or t2i_page_index == 1)
        should_show = is_on_result_view and (not is_sidebar_open) and (not image_viewer.is_open)
        
        if gallery_control_gesture.visible != should_show:
            gallery_control_gesture.visible = should_show
            gallery_control_gesture.update()

    # 初始化 ImageViewer
    image_viewer = ImageViewer(
        page, 
        current_primary_color, 
        current_theme_mode, 
        on_edit_click=handle_transfer_to_edit,
        on_dismiss=lambda: update_gallery_btn_visibility() 
    )

    def show_viewer_callback(src, all_images_data, current_index):
        # 根据当前 APP Key 决定文件夹名称 (History 模式特殊处理)
        folder = "History" if current_app_key == "history" else ("T2I" if current_app_key == "t2i" else "I2I_Edits")
        image_viewer.show(src, all_images_data, current_index, target_folder=folder)
        update_gallery_btn_visibility()

    def switch_view_page_callback(target_index):
        if not is_wide_mode:
            switch_t2i_page(target_index)

    # ================= 4. 初始化功能模块 =================
    
    t2i_app = T2I_Module.T2I_View(page, config, show_viewer_callback, switch_view_page_callback, transfer_callback=handle_transfer_to_edit)
    i2i_app = I2I_Module.I2I_View(page, config, show_viewer_callback, switch_view_page_callback, transfer_callback=handle_transfer_to_edit)
    # 【新增】初始化历史模块
    history_app = History_Module.History_View(page, config, show_viewer_callback)

    # ================= 5. 构建 UI 骨架 =================

    # --- 5.1 T2I/I2I 视图堆叠 ---
    t2i_input_wrapper = ft.Container(content=t2i_app.get_input_content(), visible=True, expand=True)
    i2i_input_wrapper = ft.Container(content=i2i_app.get_input_content(), visible=False, expand=True)
    page1_stack = ft.Stack([t2i_input_wrapper, i2i_input_wrapper], expand=True)

    t2i_btn_wrapper = ft.Container(content=t2i_app.get_generate_btn(), visible=True)
    i2i_btn_wrapper = ft.Container(content=i2i_app.get_generate_btn(), visible=False)
    bottom_btn_stack = ft.Stack([t2i_btn_wrapper, i2i_btn_wrapper])

    fixed_bottom_action_bar = ft.Container(
        content=bottom_btn_stack,
        padding=ft.padding.symmetric(horizontal=0, vertical=10),
        bgcolor=ft.Colors.TRANSPARENT,
    )

    t2i_result_wrapper = ft.Container(content=t2i_app.get_results_content(), visible=True, expand=True)
    i2i_result_wrapper = ft.Container(content=i2i_app.get_results_content(), visible=False, expand=True)
    page2_stack = ft.Stack([t2i_result_wrapper, i2i_result_wrapper], expand=True)

    # --- 5.2 遮罩层 ---
    mask = ft.Container(
        bgcolor=utils.get_opacity_color(0.3, "black"),
        left=0, right=0, top=0, bottom=0, 
        visible=False, animate_opacity=300, opacity=0,
        on_click=lambda e: toggle_sidebar(False) 
    )
    
    # --- 5.3 组装 T2I/I2I 页面容器 ---
    page1_content_col = ft.Column([
        ft.Container(content=page1_stack, expand=True, padding=ft.padding.only(top=10, bottom=10)), 
        fixed_bottom_action_bar
    ], spacing=0, expand=True)

    page1_content = ft.Container(
        padding=ft.padding.symmetric(horizontal=5, vertical=0),
        expand=True, content=page1_content_col,
        on_click=lambda e: close_func_menu() 
    )

    page2_content = ft.Container(
        padding=ft.padding.symmetric(horizontal=15, vertical=10),
        expand=True, content=page2_stack,
        on_click=lambda e: close_func_menu() 
    )

    page1_container = ft.Container(content=page1_content, expand=False)
    page2_container = ft.Container(content=page2_content, expand=False)
    
    # T2I/I2I 的滑动容器
    t2i_slider = ft.Row(
        controls=[page1_container, page2_container],
        spacing=0, alignment="start", vertical_alignment="start", expand=True,
        offset=utils.MyOffset(0, 0) if utils.MyOffset else None,
        animate_offset=utils.MyAnimation(300, "easeOut") if utils.MyAnimation else None
    )
    # 【新增】给 Slider 加一个容器，方便整体隐藏
    t2i_slider_container = ft.Container(content=t2i_slider, expand=True, clip_behavior=ft.ClipBehavior.HARD_EDGE, visible=True)

    # 【新增】历史记录容器
    history_container = ft.Container(content=history_app.get_content(), expand=True, visible=False, padding=ft.padding.all(0))

    # --- 5.4 底部指示点 ---
    dot1 = ft.Container(width=10, height=10, border_radius=5, bgcolor=current_primary_color, animate=utils.MyAnimation(200, "easeOut") if utils.MyAnimation else None)
    dot2 = ft.Container(width=10, height=10, border_radius=5, bgcolor="grey", animate=utils.MyAnimation(200, "easeOut") if utils.MyAnimation else None)
    dots_row = ft.Row([dot1, dot2], alignment="center", spacing=8)

    # --- 5.5 底部导航栏 ---
    nav_btn_menu_icon = ft.Icon("menu", size=24, color=current_text_color)
    nav_btn_menu_text = ft.Text("菜单", size=10, color=current_text_color)
    nav_btn_func_icon = ft.Icon("palette", size=24, color=current_text_color)
    nav_btn_func_text = ft.Text("文生图", size=10, color=current_text_color)
    nav_btn_gallery_icon = ft.Icon("image", size=24, color=current_text_color)
    nav_btn_gallery_text = ft.Text("结果", size=10, color=current_text_color)
    
    def on_nav_click(index):
        close_func_menu() 
        toggle_sidebar(False) 
        # 历史模式下点击导航，先切回 T2I ? 或者保持 History ?
        # 这里逻辑：点击“结果”或“功能”应当切换回 T2I/I2I 的相应页面
        # 简单处理：如果是 History 模式，点击左右两侧按钮暂不处理，或者强制切回 T2I
        if current_app_key == 'history':
             # 强制切回 T2I
             switch_app('t2i')
             if index == 1: # 如果点的是结果
                 switch_t2i_page(1)
             return

        switch_t2i_page(index)
    
    def on_menu_btn_click(e):
        close_func_menu()
        if is_sidebar_open: toggle_sidebar(False)
        else: toggle_sidebar(True)

    def create_nav_item(icon, text, on_click_func):
        return ft.Container(
            content=ft.Column([icon, text], spacing=2, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            expand=1, alignment=ft.alignment.center, padding=ft.padding.symmetric(vertical=5), bgcolor=ft.Colors.TRANSPARENT, ink=False, on_click=on_click_func
        )

    nav_item_menu = create_nav_item(nav_btn_menu_icon, nav_btn_menu_text, on_menu_btn_click)
    
    nav_item_func_container = ft.Container(
        content=ft.Column([nav_btn_func_icon, nav_btn_func_text], spacing=2, alignment=ft.MainAxisAlignment.CENTER, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        alignment=ft.alignment.center, padding=ft.padding.symmetric(vertical=5), bgcolor=ft.Colors.TRANSPARENT
    )
    nav_item_func = ft.GestureDetector(
        content=nav_item_func_container,
        expand=1,
        on_tap=lambda e: on_nav_click(0), 
        on_long_press_start=lambda e: open_func_menu(e) 
    )

    nav_item_gallery = create_nav_item(nav_btn_gallery_icon, nav_btn_gallery_text, lambda e: on_nav_click(1))

    bottom_nav_content = ft.Container(
        height=56, bgcolor=utils.get_dropdown_bgcolor(current_theme_mode),
        padding=0, border=ft.border.only(top=ft.BorderSide(0.5, "grey")),
        content=ft.Row([nav_item_menu, nav_item_func, nav_item_gallery], alignment="start", spacing=0, expand=True),
    )

    bottom_nav_drag_buffer = 0
    def on_bottom_nav_pan_update(e: ft.DragUpdateEvent):
        nonlocal bottom_nav_drag_buffer
        bottom_nav_drag_buffer += e.delta_x

    def on_bottom_nav_pan_end(e: ft.DragEndEvent):
        nonlocal bottom_nav_drag_buffer
        if current_app_key == 'history': return # 历史模式禁用滑动导航

        velocity = getattr(e, "velocity_x", 0)
        DIST_THRESHOLD, VELOCITY_THRESHOLD = 50, 800 
        if bottom_nav_drag_buffer < -DIST_THRESHOLD or velocity < -VELOCITY_THRESHOLD:
             if is_sidebar_open: toggle_sidebar(False)
             elif t2i_page_index == 0: switch_t2i_page(1)
        elif bottom_nav_drag_buffer > DIST_THRESHOLD or velocity > VELOCITY_THRESHOLD:
             if t2i_page_index == 1: switch_t2i_page(0)
             elif t2i_page_index == 0 and not is_sidebar_open: toggle_sidebar(True)
        bottom_nav_drag_buffer = 0

    bottom_nav = ft.GestureDetector(content=bottom_nav_content, on_pan_update=on_bottom_nav_pan_update, on_pan_end=on_bottom_nav_pan_end, visible=False)

    # --- 5.6 侧边栏 ---
    sidebar_icon_ref = ft.Icon("smart_toy", size=40, color=current_text_color)
    sidebar_title_ref = ft.Text("魔塔AI大全", size=18, weight="bold", color=current_text_color)
    sidebar_subtitle_ref = ft.Text("By_showevr", size=12, color=current_text_color)
    sidebar_items_container = ft.Column(spacing=5) 

    def build_sidebar_item(icon_name, text, key, is_selected):
        color = current_primary_color if is_selected else current_text_color
        bg = utils.get_opacity_color(0.1, current_primary_color) if is_selected else None
        nav_highlight_ref = ft.Container(width=4, height=20, border_radius=2, bgcolor=current_primary_color if is_selected else "transparent", animate=utils.MyAnimation(300, "easeOut") if utils.MyAnimation else None)
        return ft.Container(
            content=ft.Row([
                ft.Row([ft.Icon(icon_name, size=20, color=color), ft.Container(width=10), ft.Text(text, size=16, color=color, weight="bold" if is_selected else "normal")]),
                nav_highlight_ref
            ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
            padding=ft.padding.symmetric(horizontal=20, vertical=12), border_radius=30, bgcolor=bg, ink=True, on_click=lambda e: switch_app(key)
        )

    # 侧边栏底部功能项
    sidebar_theme_icon = ft.Icon("contrast", color=current_text_color, size=24)
    sidebar_theme_text = ft.Text("主题设置", color=current_text_color, size=16)
    sidebar_key_icon = ft.Icon("vpn_key", color=current_text_color, size=24)
    sidebar_key_text = ft.Text("Api_key", color=current_text_color, size=16)
    sidebar_power_icon = ft.Icon("flash_on", color=current_text_color, size=24)
    sidebar_power_text = ft.Text("强力生图模式", color=current_text_color, size=16)
    
    sidebar_theme_item = ft.Container(content=ft.Row([sidebar_theme_icon, ft.Container(width=10), sidebar_theme_text]), padding=ft.padding.symmetric(vertical=15, horizontal=20), on_click=lambda e: open_theme_dialog(e), ink=True)
    sidebar_key_item = ft.Container(content=ft.Row([sidebar_key_icon, ft.Container(width=10), sidebar_key_text]), padding=ft.padding.symmetric(vertical=15, horizontal=20), on_click=lambda e: open_settings_dialog(e), ink=True)
    sidebar_power_item = ft.Container(content=ft.Row([sidebar_power_icon, ft.Container(width=10), sidebar_power_text]), padding=ft.padding.symmetric(vertical=15, horizontal=20), on_click=lambda e: open_power_mode_dialog(e), ink=True)

    sidebar_div1 = ft.Divider(height=10, thickness=0.5, color="transparent")
    sidebar_div2 = ft.Divider(height=10, thickness=0.5, color="transparent")

    sidebar_content = ft.Column([
            ft.Container(padding=ft.padding.symmetric(horizontal=20), on_click=lambda e: toggle_sidebar(False), content=ft.Row([sidebar_icon_ref, ft.Column([sidebar_title_ref, sidebar_subtitle_ref], spacing=2)])),
            sidebar_div1, ft.Divider(color="transparent", height=10),
            ft.Container(padding=ft.padding.symmetric(horizontal=10), content=sidebar_items_container),
            ft.Container(expand=True), sidebar_div2,
            ft.Column([sidebar_theme_item, sidebar_power_item, sidebar_key_item], spacing=0)
        ], expand=True)

    sidebar_drag_buffer = 0
    def on_sidebar_pan_update(e: ft.DragUpdateEvent):
        nonlocal sidebar_drag_buffer
        sidebar_drag_buffer += e.delta_x
    def on_sidebar_pan_end(e: ft.DragEndEvent):
        nonlocal sidebar_drag_buffer
        velocity = getattr(e, "velocity_x", 0)
        if sidebar_drag_buffer < -50 or velocity < -800: toggle_sidebar(False)
        sidebar_drag_buffer = 0

    sidebar_gesture_detector = ft.GestureDetector(content=sidebar_content, on_pan_update=on_sidebar_pan_update, on_pan_end=on_sidebar_pan_end)
    sidebar_container = ft.Container(
        width=250, top=0, bottom=0, bgcolor="white", padding=ft.padding.only(top=50, bottom=20), 
        offset=utils.MyOffset(-1, 0) if utils.MyOffset else None,
        animate_offset=utils.MyAnimation(300, "easeOut") if utils.MyAnimation else None,
        content=sidebar_gesture_detector, shadow=ft.BoxShadow(blur_radius=10, color=ft.Colors.with_opacity(0.2, "black"))
    )

    # --- 5.7 顶部 App Bar ---
    def toggle_left_panel(e):
        nonlocal left_panel_visible
        left_panel_visible = not left_panel_visible
        toggle_panel_btn.icon = "keyboard_double_arrow_right" if not left_panel_visible else "keyboard_double_arrow_left"
        toggle_panel_btn.tooltip = "展开参数栏" if not left_panel_visible else "折叠参数栏"
        on_resize(None)
        custom_appbar.update()

    top_menu_btn = ft.IconButton("menu", icon_size=24, on_click=lambda e: toggle_sidebar(True))
    toggle_panel_btn = ft.IconButton("keyboard_double_arrow_left", tooltip="折叠参数栏", on_click=toggle_left_panel, visible=False)
    view_switch_btn = ft.IconButton(icon="image", tooltip="查看生成结果", visible=False, on_click=lambda e: switch_t2i_page(1 if t2i_page_index == 0 else 0))

    custom_appbar = ft.Container(
        height=50, padding=ft.padding.only(left=10, right=10),
        content=ft.Row([top_menu_btn, toggle_panel_btn, ft.Container(expand=True), view_switch_btn], alignment="start")
    )

    # --- 5.8 图库控制 ---
    def set_gallery_columns(cols):
        # 根据不同模块调用不同的 grid 设置
        if current_app_key == 't2i':
            t2i_app.set_grid_columns(cols)
        elif current_app_key == 'i2i':
            i2i_app.set_grid_columns(cols)
        elif current_app_key == 'history':
            history_app.set_grid_columns(cols)

    gallery_popup_menu = ft.PopupMenuButton(
        icon="circle_outlined", icon_size=30, tooltip="调整图库布局", surface_tint_color=ft.Colors.TRANSPARENT, 
        items=[
            ft.PopupMenuItem(text="1列 (大图)", on_click=lambda e: set_gallery_columns(1)),
            ft.PopupMenuItem(text="2列 (标准)", on_click=lambda e: set_gallery_columns(2)),
            ft.PopupMenuItem(text="3列 (小图)", on_click=lambda e: set_gallery_columns(3)),
            ft.PopupMenuItem(text="4列 (超小)", on_click=lambda e: set_gallery_columns(4)),
        ]
    )

    def on_gallery_btn_pan(e: ft.DragUpdateEvent):
        safe_w = float(page.width) if page.width else 360.0
        curr_left = float(gallery_control_gesture.left) if gallery_control_gesture.left not in [None, ""] else (safe_w - 60)
        curr_bottom = float(gallery_control_gesture.bottom) if gallery_control_gesture.bottom not in [None, ""] else 100.0
        gallery_control_gesture.right = None 
        gallery_control_gesture.left = curr_left + e.delta_x
        gallery_control_gesture.bottom = curr_bottom - e.delta_y
        gallery_control_gesture.update()

    gallery_control_gesture = ft.GestureDetector(content=ft.Container(content=gallery_popup_menu, bgcolor="transparent"), on_pan_update=on_gallery_btn_pan, right=20, left=None, bottom=100, visible=False)

    # ================= 6. 核心逻辑实现 =================

    def switch_t2i_page(index):
        nonlocal t2i_page_index
        t2i_page_index = index
        if is_sidebar_open: toggle_sidebar(False)

        if index == 0:
            nav_btn_func_icon.color = current_primary_color
            nav_btn_func_text.color = current_primary_color
            nav_btn_gallery_icon.color = current_text_color
            nav_btn_gallery_text.color = current_text_color
            view_switch_btn.icon = "image"
            view_switch_btn.tooltip = "查看结果"
        else:
            nav_btn_func_icon.color = current_text_color
            nav_btn_func_text.color = current_text_color
            nav_btn_gallery_icon.color = current_primary_color
            nav_btn_gallery_text.color = current_primary_color
            view_switch_btn.icon = "tune"
            view_switch_btn.tooltip = f"返回{nav_btn_func_text.value}"
            
        nav_item_func.content.update() 
        nav_item_gallery.update()
        view_switch_btn.update()
        
        update_gallery_btn_visibility()
        
        if is_wide_mode: return 
        
        # 仅在非历史模式下处理分页
        if current_app_key != 'history':
            page1_container.visible = (index == 0)
            page2_container.visible = (index == 1)
            t2i_slider.offset = None 
            page1_container.update()
            page2_container.update()
            t2i_slider.update()
            update_dots()

    def update_dots():
        dot1.bgcolor = current_primary_color if t2i_page_index == 0 else "grey"
        dot2.bgcolor = current_primary_color if t2i_page_index == 1 else "grey"
        dot1.update()
        dot2.update()

    def toggle_sidebar(open_it):
        nonlocal is_sidebar_open
        is_sidebar_open = open_it
        if utils.MyOffset:
            sidebar_container.offset = utils.MyOffset(0 if open_it else -1, 0)
            sidebar_container.update()
        
        if not is_wide_mode:
            mask.visible = open_it
            mask.opacity = 1 if open_it else 0
            mask.update()
        else:
            mask.visible = False
            mask.update()
        
        nav_btn_menu_icon.color = current_primary_color if open_it else current_text_color
        nav_btn_menu_text.color = current_primary_color if open_it else current_text_color
        nav_btn_menu_icon.update()
        nav_btn_menu_text.update()

        if not is_wide_mode and current_app_key != 'history':
            if open_it:
                nav_btn_func_icon.color = current_text_color
                nav_btn_func_text.color = current_text_color
                nav_btn_gallery_icon.color = current_text_color
                nav_btn_gallery_text.color = current_text_color
            else:
                if t2i_page_index == 0:
                    nav_btn_func_icon.color = current_primary_color
                    nav_btn_func_text.color = current_primary_color
                else:
                    nav_btn_gallery_icon.color = current_primary_color
                    nav_btn_gallery_text.color = current_primary_color
            nav_item_func.content.update()
            nav_item_gallery.update()
            
        update_gallery_btn_visibility()

    def on_resize(e):
        nonlocal is_wide_mode
        pw = page.width if page.width else 0
        ph = page.height if page.height else 0
        if pw == 0 or ph == 0: return

        new_is_wide = (pw > ph and pw > 600)
        is_wide_mode = new_is_wide

        # 调用各模块的 Resize
        t2i_app.on_resize(is_wide_mode, pw, ph)
        i2i_app.on_resize(is_wide_mode, pw, ph)
        history_app.on_resize(is_wide_mode, pw, ph)
        image_viewer.on_resize(is_wide_mode, pw, ph)

        if is_wide_mode: close_func_menu()

        if is_wide_mode:
            t2i_slider.offset = utils.MyOffset(0, 0)
            sidebar_container.width = pw * 0.5 if pw * 0.5 < 300 else 300 
            sidebar_container.bottom = 0
            if utils.MyOffset: sidebar_container.offset = utils.MyOffset(0 if is_sidebar_open else -1, 0)
            
            mask.bottom = 0
            mask.visible = False
            
            # 宽屏模式下对 Slider 内部容器的处理
            # 如果是历史模式，slider 本身就是隐藏的，所以这些逻辑不会影响视觉
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
            custom_appbar.height = 50
            if current_app_key != 'history':
                fixed_bottom_action_bar.visible = True
            sidebar_container.shadow = None

        else: 
            t2i_slider.offset = None 
            sidebar_container.width = pw 
            sidebar_container.bottom = 0 
            if utils.MyOffset: sidebar_container.offset = utils.MyOffset(0 if is_sidebar_open else -1, 0)
            
            mask.visible = is_sidebar_open
            mask.opacity = 1 if is_sidebar_open else 0
            
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
            if current_app_key != 'history':
                fixed_bottom_action_bar.visible = True
            sidebar_container.shadow = ft.BoxShadow(blur_radius=10, color=ft.Colors.with_opacity(0.2, "black"))

        # 使用统一函数更新
        update_gallery_btn_visibility()
        page.update()

    page.on_resize = on_resize

    # ================= 7. 设置与主题窗口 =================
    
    settings_dialog = ft.AlertDialog(title=ft.Text("全局设置", size=14), modal=True, surface_tint_color=ft.Colors.TRANSPARENT)
    theme_dialog = ft.AlertDialog(title=ft.Text("显示与主题", weight="bold", size=14), modal=True, surface_tint_color=ft.Colors.TRANSPARENT)
    power_mode_dialog = ft.AlertDialog(title=ft.Row([ft.Icon("flash_on", color="amber"), ft.Text("强力生图模式", weight="bold", size=14)]), modal=True, surface_tint_color=ft.Colors.TRANSPARENT)

    api_keys_field = ft.TextField(label="ModelScope Keys (每行一个)", value="\n".join(current_api_keys), multiline=True, min_lines=10, max_lines=25, text_size=12, content_padding=15, border_color=utils.get_border_color(current_theme_mode))
    baidu_config_field = ft.TextField(label="百度翻译配置 (第一行AppID，第二行密钥)", value=f"{current_baidu_config.get('appid','')}\n{current_baidu_config.get('key','')}", multiline=True, text_size=12, content_padding=10, height=90, border_color=utils.get_border_color(current_theme_mode))

    async def save_settings(e):
        nonlocal current_api_keys, current_baidu_config
        await utils.save_config_to_storage(page, "api_keys", api_keys_field.value)
        await utils.save_config_to_storage(page, "baidu_config", baidu_config_field.value)
        new_config = await utils.load_global_config(page)
        current_api_keys = new_config["api_keys"]
        current_baidu_config = new_config["baidu_config"]
        t2i_app.update_config(new_config)
        i2i_app.update_config(new_config)
        utils.safe_close_dialog(page, settings_dialog)
        page.snack_bar = ft.SnackBar(ft.Text("设置已保存"), open=True)
        page.update()

    def open_settings_dialog(e):
        api_keys_field.value = "\n".join(current_api_keys)
        baidu_config_field.value = f"{current_baidu_config.get('appid','')}\n{current_baidu_config.get('key','')}"
        settings_dialog.content = ft.Column([api_keys_field, ft.Container(height=15), baidu_config_field], tight=True, scroll=ft.ScrollMode.AUTO, width=300, spacing=0)
        settings_dialog.actions = [ft.TextButton("保存", on_click=save_settings)]
        utils.safe_open_dialog(page, settings_dialog)

    # ------------------ 强力模式相关逻辑 ------------------
    pm_enabled_switch = ft.Switch(label="启用强力生图", value=False, active_color="amber")
    pm_batch_slider = ft.Slider(min=1, max=50, divisions=49, label="{value}", value=10, active_color="amber")
    pm_delay_slider = ft.Slider(min=0.1, max=3.0, divisions=29, label="{value}秒", value=0.2, active_color="amber")
    pm_keys_container = ft.Column([], spacing=2)
    pm_limit_field = ft.TextField(label="每日API Key可调用的次数", value="200", keyboard_type="number", text_size=12, height=40, content_padding=10)

    async def save_power_mode_settings(e=None):
        nonlocal current_power_config
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
        
        await utils.save_config_to_storage(page, "power_mode_config", new_power_config)
        config["power_mode_config"] = new_power_config
        current_power_config = new_power_config
        t2i_app.update_config(config)
        i2i_app.update_config(config)
        utils.safe_close_dialog(page, power_mode_dialog)
        page.snack_bar = ft.SnackBar(ft.Text("强力模式配置已保存"), open=True)
        page.update()

    async def _init_power_mode_ui():
        pm_enabled_switch.value = current_power_config.get("enabled", False)
        pm_batch_slider.value = float(current_power_config.get("batch_size", 10))
        pm_delay_slider.value = float(current_power_config.get("request_delay", 0.2))
        pm_limit_field.value = str(current_power_config.get("daily_limit", 200))
        saved_selected = [k.strip() for k in current_power_config.get("selected_keys", []) if k]
        
        controls_list = []
        limit_val = int(current_power_config.get("daily_limit", 200))
        
        if not current_api_keys:
            controls_list.append(ft.Text("请先在 API Key 设置中添加 Key", color="red", size=12))
        else:
            for idx, raw_k in enumerate(current_api_keys):
                k = raw_k.strip() 
                if not k: continue
                usage = await utils.get_api_usage(page, k)
                remaining = max(0, limit_val - usage)
                is_checked = False
                if not saved_selected: is_checked = True 
                else: is_checked = (k in saved_selected)
                chk = ft.Checkbox(label=f"Key {idx+1} (剩余:{remaining})", value=is_checked, data=k)
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
                    border=ft.border.all(1, utils.get_border_color(current_theme_mode)),
                    border_radius=5,
                    padding=10,
                ), 
                ft.Container(height=10),
                pm_limit_field,
                ft.Text("提示: 此限制仅用于本地统计显示，不代表官方实际限制。", size=10, color="grey")
            ], tight=True, scroll=ft.ScrollMode.AUTO)
        )
        pm_keys_container.scroll = ft.ScrollMode.AUTO
        power_mode_dialog.actions = [
            ft.TextButton("取消", on_click=lambda e: utils.safe_close_dialog(page, power_mode_dialog)),
            ft.ElevatedButton("保存", on_click=lambda e: page.run_task(save_power_mode_settings), bgcolor="amber", color="black")
        ]
        utils.safe_open_dialog(page, power_mode_dialog)
        page.run_task(_init_power_mode_ui)

    # ----------------------------------------------------

    async def update_global_theme(mode=None, color_name=None):
        nonlocal current_primary_color, current_theme_mode, current_text_color
        
        if color_name:
            current_theme_color_name = color_name
            current_primary_color = utils.MORANDI_COLORS[color_name]
            await utils.save_config_to_storage(page, "theme_color", color_name)
            page.theme = ft.Theme(color_scheme_seed=current_primary_color, dialog_theme=ft.DialogTheme(surface_tint_color=ft.Colors.TRANSPARENT))
            switch_app(current_app_key) 
            sidebar_theme_icon.color = "grey"
            update_dots()
            gallery_popup_menu.icon_color = current_primary_color

        if mode:
            current_theme_mode = mode
            await utils.save_config_to_storage(page, "theme_mode", mode)
            current_text_color = utils.get_text_color(mode)
            
            sidebar_icon_ref.color = current_text_color
            sidebar_title_ref.color = current_text_color
            sidebar_subtitle_ref.color = current_text_color
            
            for icon in [sidebar_theme_icon, sidebar_key_icon, sidebar_power_icon]:
                icon.color = current_text_color
            for txt in [sidebar_theme_text, sidebar_key_text, sidebar_power_text]:
                txt.color = current_text_color

            switch_app(current_app_key)
            
            if not is_sidebar_open:
                nav_btn_menu_icon.color = current_text_color
                nav_btn_menu_text.color = current_text_color
                if t2i_page_index != 0: 
                    nav_btn_func_icon.color = current_text_color
                    nav_btn_func_text.color = current_text_color
                if t2i_page_index != 1:
                    nav_btn_gallery_icon.color = current_text_color
                    nav_btn_gallery_text.color = current_text_color

            if mode == "dark":
                page.theme_mode = ft.ThemeMode.DARK
                page.bgcolor = utils.BG_DARK
                main_content_bg.bgcolor = utils.BG_DARK
            elif mode == "warm":
                page.theme_mode = ft.ThemeMode.LIGHT
                page.bgcolor = utils.BG_WARM
                main_content_bg.bgcolor = utils.BG_WARM
            else:
                page.theme_mode = ft.ThemeMode.LIGHT
                page.bgcolor = utils.BG_LIGHT
                main_content_bg.bgcolor = utils.BG_LIGHT
            
            dialog_bg = utils.get_dialog_bgcolor(mode)
            settings_dialog.bgcolor = dialog_bg
            theme_dialog.bgcolor = dialog_bg
            power_mode_dialog.bgcolor = dialog_bg
            
            sidebar_container.bgcolor = utils.get_sidebar_bgcolor(mode)
            bottom_nav_content.bgcolor = utils.get_dropdown_bgcolor(mode)
            sidebar_div1.color = utils.get_opacity_color(0.2, current_text_color) 
            sidebar_div2.color = utils.get_opacity_color(0.2, current_text_color)
            
            border_c = utils.get_border_color(mode)
            api_keys_field.border_color = border_c
            baidu_config_field.border_color = border_c
            pm_limit_field.border_color = border_c
            
            # 更新功能菜单颜色
            func_menu_card.bgcolor = utils.get_dropdown_bgcolor(mode)

        t2i_app.update_theme(current_primary_color, current_theme_mode)
        i2i_app.update_theme(current_primary_color, current_theme_mode)
        # 【新增】更新历史模块主题
        history_app.update_theme(current_primary_color, current_theme_mode)
        image_viewer.update_theme(current_primary_color, current_theme_mode)

        if theme_dialog.open:
            theme_dialog.content = build_theme_content()
            theme_dialog.update()
        page.update()

    def build_theme_content():
        def color_dot(name, hex_c):
            is_selected = (hex_c == current_primary_color)
            return ft.Container(
                width=45, height=45, bgcolor=hex_c, border_radius=22,
                on_click=lambda e: page.run_task(update_global_theme, color_name=name),
                border=ft.border.all(3, current_primary_color) if is_selected else None,
                scale=utils.MyScale(1.1 if is_selected else 1.0) if utils.MyScale else None,
                animate_scale=utils.MyAnimation(200, "easeOut") if utils.MyAnimation else None
            )
        def mode_pill(text, mode_val):
            is_active = (mode_val == current_theme_mode)
            return ft.Container(
                content=ft.Text(text, color=current_primary_color if is_active else "grey", size=14),
                padding=ft.padding.symmetric(horizontal=18, vertical=8),
                border=ft.border.all(1.5, current_primary_color if is_active else "grey"),
                border_radius=20,
                bgcolor=utils.get_opacity_color(0.1, current_primary_color) if is_active else None,
                on_click=lambda e: page.run_task(update_global_theme, mode=mode_val)
            )
        return ft.Column([
            ft.Text("莫兰迪色系", size=13, color="grey"),
            ft.Divider(height=10, color="transparent"), 
            ft.Row([color_dot(n, h) for n, h in list(utils.MORANDI_COLORS.items())[:4]], spacing=12, alignment="start"),
            ft.Container(height=8),
            ft.Row([color_dot(n, h) for n, h in list(utils.MORANDI_COLORS.items())[4:]], spacing=12, alignment="start"),
            ft.Divider(height=30, thickness=0.5, color=utils.get_opacity_color(0.2, "grey")), 
            ft.Text("主题模式", size=13, color="grey"),
            ft.Divider(height=10, color="transparent"),
            ft.Row([mode_pill("护眼", "warm"), mode_pill("浅色", "light"), mode_pill("深色", "dark")], alignment="start", spacing=10)
        ], spacing=0, horizontal_alignment="start", tight=True)

    def open_theme_dialog(e):
        theme_dialog.content = ft.Container(content=build_theme_content(), width=300, padding=ft.padding.only(top=10, left=10, right=10))
        theme_dialog.actions = [ft.TextButton("确定", on_click=lambda e: utils.safe_close_dialog(page, theme_dialog))]
        utils.safe_open_dialog(page, theme_dialog)

    # ================= 8. 挂载与启动 =================
    
    main_content_bg = ft.Container(
        expand=True, bgcolor=utils.BG_LIGHT, padding=0,
        content=ft.SafeArea(
            content=ft.Column([
                custom_appbar,
                # 【修改】使用容器包裹 Slider，并加入 History Container
                t2i_slider_container,
                history_container,
                
                ft.Container(content=dots_row, height=0 if not is_wide_mode else 35, alignment=ft.alignment.center),
                bottom_nav 
            ], spacing=0),
            bottom=True, top=True
        )
    )
    
    # 将功能切换菜单加入最外层 Stack
    layout = ft.Stack([main_content_bg, mask, sidebar_container, func_menu_card, image_viewer.ui, gallery_control_gesture], expand=True)
    page.add(layout)
    
    await update_global_theme(current_theme_mode, current_theme_color_name)
    switch_app("t2i") 
    
    page.update()
    await asyncio.sleep(0.1)
    on_resize(None)

    if not current_api_keys: open_settings_dialog(None)

ft.app(target=main)