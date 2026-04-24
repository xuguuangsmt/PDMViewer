import sys
import os
import xml.etree.ElementTree as ET
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QListWidget, QTableWidget,
                             QTableWidgetItem, QFileDialog, QHeaderView, QMessageBox, QComboBox, QSplitter)
from PyQt6.QtCore import Qt

# PDM 文件中使用的 XML 命名空间定义
NAMESPACES = {
    'a': 'attribute',
    'c': 'collection',
    'o': 'object'
}

class PDMReader:
    """
    PDM 文件解析类，负责从 PowerDesigner 的 .pdm (XML 格式) 文件中提取数据库表和字段信息。
    """
    def __init__(self, file_path):
        self.file_path = file_path
        self.tree = None
        self.root = None
        self._keys_map = {} # 存储键映射，格式：{key_id: [column_refs]}，用于识别主键
        self.tables = []    # 存储解析后的所有表信息

    def load(self):
        """
        加载并初始化 XML 树，构建基础数据映射。
        """
        if not os.path.exists(self.file_path):
            return False
        try:
            # 解析 XML 文件
            self.tree = ET.parse(self.file_path)
            self.root = self.tree.getroot()
            # 预处理：构建键与列的映射关系（用于判断主键）
            self._build_keys_map()
            # 解析所有表及其列信息
            self._parse_all_tables()
            return True
        except Exception as e:
            print(f"加载 PDM 失败: {e}")
            return False

    def _build_keys_map(self):
        """
        构建键映射表。在 PDM XML 中，主键定义在 <o:Key> 节点下，
        并通过 <o:Column Ref="..."/> 引用具体的列 ID。
        """
        self._keys_map = {}
        # 查找所有具有 Id 的 Key 对象
        for key_node in self.root.findall(".//o:Key[@Id]", NAMESPACES):
            key_id = key_node.get('Id')
            col_refs = []
            # 收集该键引用的所有列 ID
            for col_ref in key_node.findall(".//o:Column[@Ref]", NAMESPACES):
                col_refs.append(col_ref.get('Ref'))
            self._keys_map[key_id] = col_refs

    def _get_text(self, node, tag):
        """
        辅助函数：获取指定节点下某个标签的文本内容。
        """
        child = node.find(tag, NAMESPACES)
        return child.text if child is not None else ""

    def _parse_all_tables(self):
        """
        解析 PDM 中所有的表定义。
        """
        self.tables = []
        # 在 PDM 中，表定义在 <o:Table Id="..."> 节点中
        for table_node in self.root.findall(".//o:Table[@Id]", NAMESPACES):
            table_info = {
                'id': table_node.get('Id'),
                'name': self._get_text(table_node, 'a:Name'),       # 表名（描述）
                'code': self._get_text(table_node, 'a:Code'),       # 表代码（物理名）
                'comment': self._get_text(table_node, 'a:Comment'), # 表备注
                'columns': []
            }

            # 获取当前表的主键列 ID 列表
            pk_column_ids = []
            pk_node = table_node.find("c:PrimaryKey", NAMESPACES)
            if pk_node is not None:
                key_ref = pk_node.find("o:Key[@Ref]", NAMESPACES)
                if key_ref is not None:
                    key_id = key_ref.get('Ref')
                    pk_column_ids = self._keys_map.get(key_id, [])

            # 解析表下的所有列定义
            columns_node = table_node.find("c:Columns", NAMESPACES)
            if columns_node is not None:
                for column_node in columns_node.findall("o:Column[@Id]", NAMESPACES):
                    col_id = column_node.get('Id')
                    # 判断当前列是否属于主键
                    is_pk = '是' if col_id in pk_column_ids else ''
                    
                    col_info = {
                        'is_pk': is_pk,
                        'code': self._get_text(column_node, 'a:Code'),       # 字段名
                        'name': self._get_text(column_node, 'a:Name'),       # 字段描述
                        'data_type': self._get_text(column_node, 'a:DataType'), # 数据类型
                        'length': self._get_text(column_node, 'a:Length'),     # 长度
                        # Mandatory=1 表示必填，此处逻辑映射为“可空”列显示“否”
                        'mandatory': '否' if self._get_text(column_node, 'a:Column.Mandatory') == '1' else '是',
                        'default_value': self._get_text(column_node, 'a:DefaultValue'), # 缺省值
                        'comment': self._get_text(column_node, 'a:Comment'), # 备注
                        'constraint': '' # 约束（PDM中通常分散定义，此处预留）
                    }
                    table_info['columns'].append(col_info)
            
            self.tables.append(table_info)

    def search_tables(self, keyword):
        """
        根据关键字模糊搜索表（匹配名称或代码）。
        """
        if not keyword:
            return self.tables
        kw = keyword.lower()
        return [t for t in self.tables if kw in t['name'].lower() or kw in t['code'].lower()]

class PDMGuiApp(QMainWindow):
    """
    PyQt6 主界面类。
    """
    def __init__(self):
        super().__init__()
        self.font_size = 12 # 默认字号
        self.reader = None  # PDM 解析器实例
        self.init_ui()

    def init_ui(self):
        """
        初始化用户界面布局。
        """
        self.setWindowTitle("PDM 数据库结构浏览器 (PyQt6)")
        self.resize(1200, 800)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # --- 上方：条件搜索区域 ---
        condition_layout = QHBoxLayout()
        
        # 文件选择
        condition_layout.addWidget(QLabel("PDM文件:"))
        self.file_path_edit = QLineEdit()
        self.file_path_edit.setReadOnly(True)
        condition_layout.addWidget(self.file_path_edit)
        
        self.select_file_btn = QPushButton("选择文件...")
        self.select_file_btn.clicked.connect(self.on_select_file)
        condition_layout.addWidget(self.select_file_btn)

        # 模糊查找
        condition_layout.addWidget(QLabel("模糊查找:"))
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("输入表名或代码...")
        self.search_edit.returnPressed.connect(self.on_search) # 支持回车搜索
        condition_layout.addWidget(self.search_edit)

        self.search_btn = QPushButton("查询")
        self.search_btn.clicked.connect(self.on_search)
        self.search_btn.setEnabled(False) # 未加载文件前禁用
        condition_layout.addWidget(self.search_btn)
        
        # 字体调整
        condition_layout.addSpacing(20)
        condition_layout.addWidget(QLabel("字体大小:"))
        self.font_size_combo = QComboBox()
        self.font_size_combo.addItems(["10", "11", "12", "13", "14", "15", "16"])
        self.font_size_combo.setCurrentText("12")
        self.font_size_combo.currentTextChanged.connect(self.on_font_size_changed)
        condition_layout.addWidget(self.font_size_combo)
        
        main_layout.addLayout(condition_layout)

        # --- 下方：内容展示区域（使用 QSplitter 支持左右拖动） ---
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧面板：表名列表
        self.table_list_widget = QListWidget()
        self.table_list_widget.setMinimumWidth(200)
        self.table_list_widget.itemClicked.connect(self.on_table_selected)
        splitter.addWidget(self.table_list_widget)

        # 右侧面板：表结构展示表格
        self.structure_table = QTableWidget()
        self.structure_table.setColumnCount(9)
        self.structure_table.setHorizontalHeaderLabels([
            "是否主键", "字段名", "字段描述", "数据类型", "长度", "可空", "约束", "缺省值", "备注"
        ])
        # 设置表头可交互调整宽度
        self.structure_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # 启用滚动条策略
        self.structure_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.structure_table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        splitter.addWidget(self.structure_table)

        # 设置初始伸缩比例（左侧固定比例，右侧自动拉伸）
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        main_layout.addWidget(splitter)
        
        # 应用初始字体设置
        self.apply_font_size()

    def apply_font_size(self):
        """
        全局应用选定的字体大小。
        """
        font = QApplication.font()
        font.setPointSize(self.font_size)
        QApplication.setFont(font)
        self.table_list_widget.setFont(font)
        self.structure_table.setFont(font)

    def on_font_size_changed(self, size):
        """
        当用户更改字体大小下拉框时触发。
        """
        self.font_size = int(size)
        self.apply_font_size()
        self.on_search() # 刷新列表显示以适应新字体

    def on_select_file(self):
        """
        打开文件对话框选择 PDM 文件。
        """
        file_path, _ = QFileDialog.getOpenFileName(self, "选择 PDM 文件", "", "PDM Files (*.pdm);;All Files (*)")
        if file_path:
            self.file_path_edit.setText(file_path)
            self.load_pdm(file_path)

    def load_pdm(self, file_path):
        """
        解析选定的 PDM 文件。
        """
        self.reader = PDMReader(file_path)
        if self.reader.load():
            self.search_btn.setEnabled(True)
            self.on_search() # 初始加载显示所有表
        else:
            QMessageBox.critical(self, "错误", f"无法解析文件: {file_path}")

    def on_search(self):
        """
        执行模糊搜索并在左侧列表中展示结果。
        """
        if not self.reader:
            return
        
        keyword = self.search_edit.text()
        results = self.reader.search_tables(keyword)
        
        self.table_list_widget.clear()
        for t in results:
            item_text = f"{t['name']} ({t['code']})"
            self.table_list_widget.addItem(item_text)
            # 在列表项中存储表对象引用，方便点击时直接读取
            item = self.table_list_widget.item(self.table_list_widget.count() - 1)
            item.setData(Qt.ItemDataRole.UserRole, t)

    def on_table_selected(self, item):
        """
        当点击左侧列表中的表时，在右侧表格中展示该表的详细字段信息。
        """
        table_info = item.data(Qt.ItemDataRole.UserRole)
        if not table_info:
            return
        
        columns = table_info['columns']
        self.structure_table.setRowCount(len(columns))
        
        for row, col in enumerate(columns):
            # 填充表格行：是否主键, 字段名, 字段描述, 数据类型, 长度, 可空, 约束, 缺省值, 备注
            self.structure_table.setItem(row, 0, QTableWidgetItem(col['is_pk']))
            self.structure_table.setItem(row, 1, QTableWidgetItem(col['code']))
            self.structure_table.setItem(row, 2, QTableWidgetItem(col['name']))
            self.structure_table.setItem(row, 3, QTableWidgetItem(col['data_type']))
            self.structure_table.setItem(row, 4, QTableWidgetItem(col['length']))
            self.structure_table.setItem(row, 5, QTableWidgetItem(col['mandatory']))
            self.structure_table.setItem(row, 6, QTableWidgetItem(col['constraint']))
            self.structure_table.setItem(row, 7, QTableWidgetItem(col['default_value']))
            self.structure_table.setItem(row, 8, QTableWidgetItem(col['comment']))
            
            # 居中显示关键标志位
            self.structure_table.item(row, 0).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.structure_table.item(row, 5).setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        
        # 自动调整列宽以适应内容
        self.structure_table.resizeColumnsToContents()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PDMGuiApp()
    window.show()
    sys.exit(app.exec())
