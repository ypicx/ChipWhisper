from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

# 现代 IDE 风格暗黑主题 (基于 Tailwind Zinc 与科技蓝)
WINDOW_BG = "#0D0D0F"       # 最深背景，用于主窗体与代码区
SURFACE_0 = "#141417"       # 侧边栏/基础面板底色
SURFACE_1 = "#1C1C1F"       # 卡片、悬浮输入框背景
SURFACE_2 = "#2B2B30"       # 悬停状态、选中高亮层
SURFACE_3 = "#3F3F46"       # 按下状态
TEXT_PRIMARY = "#E4E4E7"    # 柔和的白色主文本（护眼）
TEXT_SECONDARY = "#A1A1AA"  # 次级、补充信息文本
TEXT_MUTED = "#71717A"      # 极弱提示文字
ACCENT = "#3B82F6"          # 现代科技蓝 (Primary)
ACCENT_HOVER = "#60A5FA"    # 强调色悬浮
ACCENT_TEXT = "#FFFFFF"     # 强调色上的纯白文本
SUCCESS = "#10B981"         # 成功绿
WARNING = "#F59E0B"         # 警告黄
ERROR = "#EF4444"           # 错误红
BORDER = "rgba(255, 255, 255, 0.08)"
BORDER_STRONG = "rgba(255, 255, 255, 0.12)"


def build_palette() -> QPalette:
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(WINDOW_BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.Base, QColor(SURFACE_0))
    palette.setColor(QPalette.AlternateBase, QColor(SURFACE_1))
    palette.setColor(QPalette.Text, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.Button, QColor(SURFACE_1))
    palette.setColor(QPalette.ButtonText, QColor(TEXT_PRIMARY))
    palette.setColor(QPalette.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.HighlightedText, QColor(ACCENT_TEXT))
    return palette


def build_stylesheet() -> str:
    return f"""
    * {{
        color: {TEXT_PRIMARY};
        font-family: "Segoe UI Variable Text", "Segoe UI", "Microsoft YaHei UI", "PingFang SC", sans-serif;
        font-size: 13px;
        line-height: 1.5;
    }}

    /* 1. 基础背景层级区分 */
    QMainWindow, QWidget#AppShell {{ background: {WINDOW_BG}; }}
    QFrame#WorkspacePanel {{ background: {WINDOW_BG}; border: none; }}
    QFrame#SidebarPanel, QFrame#DialogueWorkspacePanel, QFrame#SolutionSidebarPanel {{
        background: {SURFACE_0}; border: 1px solid {BORDER}; border-radius: 12px;
    }}
    QFrame#SidebarPanelRight {{ background: {SURFACE_0}; border: none; border-left: 1px solid {BORDER}; }}
    QFrame#NavRail {{ background: {SURFACE_0}; border: none; border-right: 1px solid {BORDER}; }}
    QFrame#CopilotSidebarPanel {{ background: {SURFACE_0}; border: none; border-right: 1px solid {BORDER}; }}
    QFrame#WorkspaceCenterPanel {{ background: {WINDOW_BG}; border: none; }}

    /* 2. 极细半透明滚动条 (不抢占视觉) */
    QScrollBar:vertical {{ border: none; background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{
        background: rgba(255, 255, 255, 0.1); border-radius: 5px; min-height: 24px;
        border: 2px solid transparent; background-clip: padding-box;
    }}
    QScrollBar::handle:vertical:hover {{ background: rgba(255, 255, 255, 0.2); }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ border: none; background: none; height: 0; }}

    QScrollBar:horizontal {{ border: none; background: transparent; height: 10px; margin: 0; }}
    QScrollBar::handle:horizontal {{
        background: rgba(255, 255, 255, 0.1); border-radius: 5px; min-width: 24px;
        border: 2px solid transparent; background-clip: padding-box;
    }}
    QScrollBar::handle:horizontal:hover {{ background: rgba(255, 255, 255, 0.2); }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ border: none; background: none; width: 0; }}

    /* 3. 输入框与代码区域 */
    QLineEdit, QTextEdit, QPlainTextEdit {{
        background: {SURFACE_0}; border: 1px solid {BORDER_STRONG}; border-radius: 6px; padding: 6px 10px;
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {{ border: 1px solid {ACCENT}; }}
    QPlainTextEdit#CodeEditor, QTextEdit#CodeEditor {{
        font-family: "JetBrains Mono", "Cascadia Code", Consolas, monospace; font-size: 13px; background: {WINDOW_BG};
        border-radius: 8px; border: 1px solid {BORDER}; padding: 8px; line-height: 1.4;
    }}

    /* 4. 列表与树结构 (项目文件结构) */
    QTreeView, QListWidget {{ background: transparent; border: none; outline: none; }}
    QTreeView::item, QListWidget::item {{ padding: 6px 8px; border-radius: 6px; margin-bottom: 2px; }}
    QTreeView::item:hover, QListWidget::item:hover {{ background: {SURFACE_1}; }}
    QTreeView::item:selected, QListWidget::item:selected {{
        background: rgba(59, 130, 246, 0.15); color: {ACCENT}; font-weight: 600;
        border-left: 3px solid {ACCENT}; border-radius: 2px 6px 6px 2px;
    }}
    QListWidget#ProjectThreadList::item {{
        background: {SURFACE_1}; border: 1px solid {BORDER}; border-radius: 10px;
        padding: 10px 12px; margin: 0 0 8px 0;
    }}
    QListWidget#ProjectThreadList::item:selected {{
        background: rgba(59, 130, 246, 0.18); color: #DBEAFE; border: 1px solid rgba(59, 130, 246, 0.35);
    }}
    QTreeView::branch {{ background: transparent; }}
    QHeaderView::section {{
        background: transparent; color: {TEXT_SECONDARY}; border: none;
        border-bottom: 1px solid {BORDER}; padding: 6px; font-weight: 600;
    }}

    /* 5. 按钮风格 */
    QPushButton, QToolButton#ActionButton, QComboBox {{
        background: {SURFACE_1}; border: 1px solid {BORDER_STRONG}; border-radius: 6px; padding: 6px 10px; font-weight: 500;
    }}
    QPushButton:hover, QComboBox:hover {{ background: {SURFACE_2}; border-color: rgba(255,255,255,0.15); }}
    QPushButton:pressed {{ background: {SURFACE_3}; }}
    QComboBox::drop-down {{ border: none; width: 20px; }}

    /* 发送按钮/主操作按钮 */
    QPushButton#PrimaryButton, QPushButton#SendButton {{
        background: {ACCENT}; color: {ACCENT_TEXT}; border: none; font-weight: 600; border-radius: 6px; padding: 6px 16px;
    }}
    QPushButton#PrimaryButton:hover, QPushButton#SendButton:hover {{ background: {ACCENT_HOVER}; }}
    QPushButton#PrimaryButton:disabled, QPushButton#SendButton:disabled {{ background: {SURFACE_2}; color: {TEXT_MUTED}; }}

    /* 图标/次级幽灵按钮 */
    QPushButton#GhostButton, QToolButton#GhostButton {{ background: transparent; border: none; color: {TEXT_MUTED}; }}
    QPushButton#GhostButton:hover, QToolButton#GhostButton:hover {{ background: {SURFACE_1}; color: {TEXT_PRIMARY}; border-radius: 6px; }}
    /* 协商选项按钮 — 带可见边框，用于等待协商时的折中方案列表 */
    QPushButton#NegotiationOptionButton {{
        background: transparent; border: 1px solid {BORDER_STRONG}; border-radius: 6px;
        color: {TEXT_SECONDARY}; padding: 6px 10px; text-align: left;
    }}
    QPushButton#NegotiationOptionButton:hover {{
        background: {SURFACE_2}; border-color: {ACCENT}; color: {TEXT_PRIMARY};
    }}
    QPushButton#NegotiationOptionButton:pressed {{
        background: rgba(59, 130, 246, 0.12); border-color: {ACCENT};
    }}
    QToolButton#PanelToggleButton {{ background: transparent; border: none; color: {TEXT_MUTED}; border-radius: 6px; }}
    QToolButton#PanelToggleButton:hover {{ background: rgba(255,255,255,0.05); color: {TEXT_PRIMARY}; }}

    /* 6. 卡片与面板容器 */
    QFrame#Card, QFrame#CardElevated {{ background: transparent; border: none; }}
    QFrame#SidebarListCard, QFrame#SidebarSummaryCard, QFrame#ActionDeck {{
        background: {SURFACE_1}; border: 1px solid {BORDER}; border-radius: 8px;
    }}
    QFrame#WorkspaceSummaryCard, QFrame#BlueprintCanvasCard, QFrame#TerminalDeck,
    QFrame#WorkspaceToolbarCard, QFrame#EnvironmentSidebarCard {{
        background: {SURFACE_1}; border: 1px solid {BORDER}; border-radius: 12px;
    }}

    /* 协商内联卡片 — 嵌入聊天消息流 */
    QFrame#NegotiationInlineCard {{
        background: rgba(245, 158, 11, 0.06);
        border: 1px solid rgba(245, 158, 11, 0.28);
        border-radius: 10px;
        margin: 0px 4px;
    }}

    /* 聊天输入框外框聚焦反馈 */
    QFrame#ComposerCard {{ background: {SURFACE_1}; border: 1px solid {BORDER_STRONG}; border-radius: 12px; }}
    QFrame#ComposerCard:focus-within, QFrame#ComposerCard[composerActive="true"] {{
        border: 1px solid {ACCENT}; background: {SURFACE_0};
    }}
    QPlainTextEdit#ComposerInput {{ background: transparent; border: none; padding: 4px; font-size: 13px; line-height: 1.45; }}
    QFrame#WorkflowStrip {{ background: {SURFACE_1}; border: 1px solid {BORDER}; border-radius: 8px; }}

    /* 7. 聊天气泡：优化用户与AI的区分感 */
    QFrame[chatRole="user"] {{
        background: rgba(59, 130, 246, 0.16); border: 1px solid rgba(59, 130, 246, 0.28);
        border-radius: 12px; border-bottom-right-radius: 2px;
    }}
    QFrame[chatRole="assistant"] {{
        background: {SURFACE_1}; border: 1px solid {BORDER}; border-radius: 12px; padding: 0;
    }}
    QTextBrowser#ChatBubbleContent {{
        background: transparent; border: none; color: {TEXT_PRIMARY}; padding: 1px 0 3px 0;
    }}
    QTextBrowser#SidebarViewer, QTextBrowser#BlueprintViewer {{
        background: transparent; border: none; color: {TEXT_PRIMARY};
    }}

    /* 8. 排版与文字 */
    QLabel#HeroTitle {{ font-size: 17px; font-weight: 600; color: #FFFFFF; }}
    QLabel#SectionTitle {{ font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY}; }}
    QLabel#SidebarSectionTitle {{ font-size: 12px; font-weight: 600; color: {TEXT_SECONDARY}; letter-spacing: 0.3px; }}
    QLabel#SidebarSummaryValue {{ font-size: 12.5px; font-weight: 600; color: #FFFFFF; }}
    QLabel#SidebarMetricValue {{ font-size: 13px; font-weight: 600; color: #FFFFFF; }}
    QLabel#SidebarSummaryCaption, QLabel#SidebarMetricCaption {{ font-size: 12px; color: {TEXT_MUTED}; }}
    QLabel#SectionHint, QLabel#MetricCaption, QLabel#ChatTimestamp {{ font-size: 12px; color: {TEXT_MUTED}; }}
    QLabel#ChatBubbleRole {{ font-size: 13px; font-weight: 600; color: {TEXT_PRIMARY}; }}

    /* 9. 状态指示微标 */
    QLabel#StatusChip {{
        padding: 3px 8px; border-radius: 6px; font-size: 12px; font-weight: 600; border: 1px solid transparent;
    }}
    QLabel[statusKind="success"] {{
        background: rgba(16, 185, 129, 0.15); color: {SUCCESS}; border-color: rgba(16, 185, 129, 0.3);
    }}
    QLabel[statusKind="warning"] {{
        background: rgba(245, 158, 11, 0.15); color: {WARNING}; border-color: rgba(245, 158, 11, 0.3);
    }}
    QLabel[statusKind="error"] {{
        background: rgba(239, 68, 68, 0.15); color: {ERROR}; border-color: rgba(239, 68, 68, 0.3);
    }}
    QLabel[statusKind="neutral"] {{ background: {SURFACE_2}; color: {TEXT_SECONDARY}; border-color: {BORDER}; }}

    /* 10. 标签页 Tabs */
    QTabWidget::pane {{ border: none; border-top: 1px solid {BORDER_STRONG}; }}
    QTabBar::tab {{
        background: transparent; color: {TEXT_MUTED}; padding: 10px 16px; border: none;
        border-bottom: 2px solid transparent; font-weight: 500; font-size: 13px;
    }}
    QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; font-weight: 600; }}
    QTabBar::tab:hover:!selected {{ color: {TEXT_PRIMARY}; background: {SURFACE_1}; border-radius: 6px 6px 0 0; }}
    QSplitter::handle {{ background: transparent; }}
    QSplitter::handle:hover {{ background: rgba(59, 130, 246, 0.3); }}
    QSplitter::handle:pressed {{ background: {ACCENT}; }}

    /* 11. 导航栏按钮 (左侧 NavRail) */
    QToolButton#NavButton {{
        background: transparent; border: none; border-radius: 8px;
        padding: 8px; margin: 2px 4px; color: {TEXT_MUTED};
    }}
    QToolButton#NavButton:hover {{ background: {SURFACE_1}; color: {TEXT_PRIMARY}; }}
    QToolButton#NavButton:checked, QToolButton#NavButton[active="true"] {{
        background: rgba(59, 130, 246, 0.12); color: {ACCENT};
        border-left: 3px solid {ACCENT}; border-radius: 2px 8px 8px 2px;
    }}

    /* 12. 底部状态栏 */
    QFrame#StatusBar {{
        background: {SURFACE_0}; border-top: 1px solid {BORDER};
        padding: 4px 12px; min-height: 24px;
    }}
    QLabel#StatusBarText {{ font-size: 11px; color: {TEXT_MUTED}; }}
    QLabel#StatusBarAccent {{ font-size: 11px; color: {ACCENT}; font-weight: 600; }}

    /* 13. LoadingOverlay 半透明遮罩 */
    QWidget#LoadingOverlay {{
        background: rgba(13, 13, 15, 0.75);
    }}
    QLabel#LoadingLabel {{
        color: {TEXT_PRIMARY}; font-size: 15px; font-weight: 600;
        padding: 16px 28px;
        background: {SURFACE_1}; border: 1px solid {BORDER_STRONG};
        border-radius: 12px;
    }}

    /* 14. 危险按钮 (删除、重置) */
    QPushButton#DangerButton {{
        background: rgba(239, 68, 68, 0.12); color: {ERROR};
        border: 1px solid rgba(239, 68, 68, 0.25); border-radius: 6px;
        padding: 6px 10px; font-weight: 500;
    }}
    QPushButton#DangerButton:hover {{
        background: rgba(239, 68, 68, 0.22); border-color: rgba(239, 68, 68, 0.4);
    }}
    QPushButton#DangerButton:pressed {{ background: rgba(239, 68, 68, 0.35); }}

    /* 15. MetricValue 大数字 */
    QLabel#MetricValue {{
        font-size: 20px; font-weight: 700; color: #FFFFFF;
        letter-spacing: -0.3px;
    }}

    /* 16. CheckBox 自定义外观 */
    QCheckBox {{ spacing: 6px; color: {TEXT_PRIMARY}; }}
    QCheckBox::indicator {{
        width: 16px; height: 16px; border-radius: 4px;
        border: 1.5px solid {BORDER_STRONG}; background: {SURFACE_0};
    }}
    QCheckBox::indicator:hover {{ border-color: {ACCENT}; background: {SURFACE_1}; }}
    QCheckBox::indicator:checked {{
        background: {ACCENT}; border-color: {ACCENT};
        image: none;
    }}
    QCheckBox::indicator:checked:hover {{ background: {ACCENT_HOVER}; }}

    /* 17. ToolTip 悬浮提示 */
    QToolTip {{
        background: {SURFACE_1}; color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_STRONG}; border-radius: 6px;
        padding: 6px 10px; font-size: 12px;
    }}

    /* 18. WorkflowDot 流程点 */
    QLabel#WorkflowDot {{
        border-radius: 6px; border: 2px solid {BORDER_STRONG};
        background: {SURFACE_0};
    }}
    QLabel#WorkflowDot[stepState="active"] {{
        background: {ACCENT}; border-color: {ACCENT};
    }}
    QLabel#WorkflowDot[stepState="done"] {{
        background: {SUCCESS}; border-color: {SUCCESS};
    }}
    QLabel#WorkflowDot[stepState="error"] {{
        background: {ERROR}; border-color: {ERROR};
    }}

    /* 19. 对话框 */
    QDialog {{ background: {WINDOW_BG}; border: 1px solid {BORDER_STRONG}; border-radius: 12px; }}

    /* 20. QMessageBox 按钮 */
    QMessageBox QPushButton {{
        min-width: 72px; padding: 6px 16px;
    }}

    /* 21. 聊天线程面板折叠按钮 */
    QToolButton#CollapseButton {{
        background: transparent; border: none; color: {TEXT_MUTED};
        border-radius: 4px; padding: 2px;
    }}
    QToolButton#CollapseButton:hover {{ background: {SURFACE_1}; color: {TEXT_PRIMARY}; }}
    """
