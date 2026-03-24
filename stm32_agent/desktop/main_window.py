from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..llm_config import load_llm_config
from .widgets import AnimatedStackedWidget, StatusChip, _safe_icon
from .chat_page import ChatPage
from .projects_page import ProjectsPage
from .settings_page import SettingsPage

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("ChipWhisper")
        self.resize(1720, 1020)
        self.setMinimumSize(1400, 860)
        self.page_meta = [
            ("需求对话", "先描述功能，再确认方案与接线，最后生成并编译工程。"),
            ("项目文件", "查看和编辑当前工程文件，并继续在原工程基础上修改。"),
            ("环境配置", "配置模型 API、Keil、CubeMX 和固件包路径。"),
        ]

        self.settings_store = QSettings("ChipWhisper", "ChipWhisperDesktop")
        geometry = self.settings_store.value("mainWindowGeometry")
        if geometry:
            self.restoreGeometry(geometry)

        app_shell = QWidget()
        app_shell.setObjectName("AppShell")
        self.setCentralWidget(app_shell)

        shell_layout = QHBoxLayout(app_shell)
        shell_layout.setContentsMargins(0, 0, 0, 0)
        shell_layout.setSpacing(0)

        nav_rail = QFrame()
        nav_rail.setObjectName("NavRail")
        nav_rail.setFixedWidth(72)
        nav_layout = QVBoxLayout(nav_rail)
        nav_layout.setContentsMargins(0, 12, 0, 12)
        nav_layout.setSpacing(6)

        brand = QLabel("CW")
        brand.setObjectName("HeroTitle")
        brand.setAlignment(Qt.AlignCenter)
        brand.setStyleSheet("font-size: 14px; font-weight: 700; letter-spacing: 0.4px;")
        nav_layout.addWidget(brand)
        nav_layout.addSpacing(10)

        self.nav_buttons: list[QToolButton] = []
        for text, icon_name in (
            ("对话", "fa5s.comments"),
            ("项目", "fa5s.folder-open"),
            ("配置", "fa5s.cog"),
        ):
            button = QToolButton()
            button.setObjectName("NavButton")
            button.setText(text)
            button.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            button.setIcon(_safe_icon(icon_name))
            button.setIconSize(QSize(20, 20))
            button.setCheckable(True)
            button.setToolTip(text)
            button.setFixedSize(60, 58)
            self.nav_buttons.append(button)
            nav_layout.addWidget(button, 0, Qt.AlignHCenter)
        nav_layout.addStretch(1)

        body_widget = QWidget()
        body_layout = QVBoxLayout(body_widget)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        top_bar = QWidget()
        top_bar.setObjectName("TopBar")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(14, 8, 14, 8)
        top_bar_layout.setSpacing(10)
        title_col = QVBoxLayout()
        title_col.setContentsMargins(0, 0, 0, 0)
        title_col.setSpacing(2)
        hero_title = QLabel(self.page_meta[0][0])
        hero_title.setObjectName("HeroTitle")
        hero_subtitle = QLabel(self.page_meta[0][1])
        hero_subtitle.setObjectName("SectionHint")
        hero_subtitle.setWordWrap(True)
        self.hero_title_label = hero_title
        self.hero_subtitle_label = hero_subtitle
        title_col.addWidget(hero_title)
        title_col.addWidget(hero_subtitle)

        workspace_label = QLabel("ChipWhisper")
        workspace_label.setObjectName("MetricCaption")
        self.project_status_chip = StatusChip("未打开工程", "neutral")
        self.llm_status_chip = StatusChip("模型未配置", "warning")

        top_bar_layout.addLayout(title_col, 1)
        top_bar_layout.addWidget(workspace_label)
        top_bar_layout.addWidget(self.project_status_chip)
        top_bar_layout.addWidget(self.llm_status_chip)

        self.pages = AnimatedStackedWidget()
        self.chat_page = ChatPage()
        self.projects_page = ProjectsPage()
        self.settings_page = SettingsPage()

        self.pages.addWidget(self.chat_page)
        self.pages.addWidget(self.projects_page)
        self.pages.addWidget(self.settings_page)
        self.pages.setContentsMargins(12, 12, 12, 8)

        status_bar = QWidget()
        status_bar.setObjectName("StatusBar")
        status_bar_layout = QHBoxLayout(status_bar)
        status_bar_layout.setContentsMargins(10, 3, 10, 3)
        status_bar_layout.setSpacing(18)
        self.status_workspace_label = QLabel("ChipWhisper")
        self.status_workspace_label.setObjectName("StatusBarText")
        self.status_page_label = QLabel(self.page_meta[0][0])
        self.status_page_label.setObjectName("StatusBarText")
        self.status_project_label = QLabel("工程: 未打开")
        self.status_project_label.setObjectName("StatusBarText")
        self.status_model_label = QLabel("模型: 未配置")
        self.status_model_label.setObjectName("StatusBarText")
        status_bar_layout.addWidget(self.status_workspace_label)
        status_bar_layout.addWidget(self.status_page_label)
        status_bar_layout.addStretch(1)
        status_bar_layout.addWidget(self.status_project_label)
        status_bar_layout.addWidget(self.status_model_label)

        body_layout.addWidget(top_bar)
        body_layout.addWidget(self.pages, 1)
        body_layout.addWidget(status_bar)

        shell_layout.addWidget(nav_rail)
        shell_layout.addWidget(body_widget, 1)

        for index, button in enumerate(self.nav_buttons):
            button.clicked.connect(lambda checked=False, current_index=index: self.switch_page(current_index))
        self.nav_buttons[0].setChecked(True)

        self.chat_page.project_activated.connect(self._set_active_project)
        self.settings_page.profiles_changed.connect(self._refresh_profiles)
        self.settings_page.paths_saved.connect(self.chat_page.refresh_environment_sidebar)

        self._refresh_profiles()
        self.chat_page.load_ui_state(self.settings_store)
        self.pages.setCurrentIndex(0)
        self._update_page_chrome(0)

    def switch_page(self, index: int) -> None:
        for button_index, button in enumerate(self.nav_buttons):
            button.setChecked(button_index == index)
        self.pages.fade_to(index)
        self._update_page_chrome(index)

    def _set_active_project(self, project_dir: str) -> None:
        self.projects_page.set_project_root(project_dir)
        self.chat_page.set_project_root(project_dir)
        if project_dir:
            project_name = Path(project_dir).name
            self.project_status_chip.set_status(project_name, "success")
            self.status_project_label.setText(f"工程: {project_name}")
            return
        self.project_status_chip.set_status("未绑定工程", "neutral")
        self.status_project_label.setText("工程: 未绑定")

    def _refresh_profiles(self) -> None:
        self.chat_page.reload_profiles()
        config = load_llm_config()
        enabled_count = len([profile for profile in config.profiles if profile.enabled])
        if enabled_count:
            self.llm_status_chip.set_status(f"{enabled_count} 个模型", "success")
            self.status_model_label.setText(f"模型: {enabled_count} 个已启用")
        else:
            self.llm_status_chip.set_status("模型未配置", "warning")
            self.status_model_label.setText("模型: 未配置")

    def _update_page_chrome(self, index: int) -> None:
        if index < 0 or index >= len(self.page_meta):
            return
        title, subtitle = self.page_meta[index]
        self.hero_title_label.setText(title)
        self.hero_subtitle_label.setText(subtitle)
        self.status_page_label.setText(title)

    def closeEvent(self, event) -> None:  # pragma: no cover - GUI runtime path
        self.chat_page.save_ui_state(self.settings_store)
        self.settings_store.setValue("mainWindowGeometry", self.saveGeometry())
        super().closeEvent(event)
